import os
from dataclasses import dataclass, field

from openai import OpenAI
from sqlalchemy.orm import Session

from profesor_oak_ai.agent import retrieval, team_builder

TEAM_SIZE = 6

# The default last-two-slot roles for every build_team call, unless the caller passes
# its own role_overrides (including an explicit empty list, for a fully-automatic
# build with no fixed roles at all).
DEFAULT_ROLE_OVERRIDES = ["special_sponge", "cleaner"]

# At most this many roster members may have Speed <= SLOW_SPEED_THRESHOLD -- Task C
# policy, not a fact about the data, so it lives here rather than in team_builder.py.
# Tested at 85 first (too strict -- it spent the whole budget on the anchor plus one
# teammate, permanently blocking any further slow pick) and revised to 60, the value
# that actually produced a clean roster in the real hand-walked run.
SLOW_SPEED_THRESHOLD = 60
SLOW_SPEED_BUDGET = 2

# A liability is worth forcing a pick over once either condition holds: a very high
# raw multiplier (4x, an outright quadruple weakness) or a merely-2x weakness that's
# still genuinely common across the real metagame (pervasiveness >= 0.15).
HARD_REQUIREMENT_MULTIPLIER = 4.0
HARD_REQUIREMENT_PERVASIVENESS = 0.15

# The tie-break formula's coverage-breadth weight: (Speed_A - Speed_B) -
# (Coverage_B - Coverage_A) * COVERAGE_WEIGHT. Only checked against two real data
# points so far (Gengar vs Electrode, Alakazam vs Mr. Mime) -- worth re-validating as
# more real ties come up.
COVERAGE_WEIGHT = 10

# Move-access tie-break: if exactly one tied candidate learns either of these, it
# wins outright, ahead of the Speed/coverage formula (see _pick_best_by_tie_break).
EXPLOSION_MOVES = ("explosion", "self-destruct")

# The "cleaner" role's minimum HP+Defense to even be considered fast/bulky enough to
# survive a hit and keep sweeping -- a pure Speed-first ranking picks a fragile
# suicide-lead (Electrode, bulk 130) over a real cleaner (Tauros, bulk 170). Only
# validated against this one real case so far.
CLEANER_BULK_FLOOR = 150

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")


@dataclass
class _PickRecord:
    name: str
    reason: str
    detail: str = ""


@dataclass
class _BuildState:
    roster: list[str]
    trail: list[_PickRecord] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


def _hard_requirements(session: Session, member: str) -> list[dict]:
    profile = team_builder.liability_profile(session, member)
    if profile is None:
        return []
    return [
        lia
        for lia in profile["liabilities"]
        if lia["multiplier"] >= HARD_REQUIREMENT_MULTIPLIER
        or lia["pervasiveness"] >= HARD_REQUIREMENT_PERVASIVENESS
    ]


def _open_requirements(session: Session, roster: list[str]) -> list[dict]:
    """Every hard-requirement liability introduced by ANY current roster member,
    filtered to the ones nobody on the roster currently resists."""
    all_liabilities: dict[str, dict] = {}
    for member in roster:
        for lia in _hard_requirements(session, member):
            entry = all_liabilities.setdefault(
                lia["attacking_type"], {"attacking_type": lia["attacking_type"], "pervasiveness": lia["pervasiveness"]}
            )
            entry["pervasiveness"] = max(entry["pervasiveness"], lia["pervasiveness"])

    open_reqs = []
    for attacking_type, info in all_liabilities.items():
        covered = False
        for member in roster:
            matchups = retrieval.defensive_type_matchups(session, member)
            if matchups is not None and matchups["factors"].get(attacking_type, 1.0) < 1.0:
                covered = True
                break
        if not covered:
            open_reqs.append(info)

    open_reqs.sort(key=lambda r: -r["pervasiveness"])
    return open_reqs


def _slow_count(session: Session, roster: list[str]) -> int:
    return sum(1 for t in team_builder.speed_tiers(session, roster) if t["speed"] <= SLOW_SPEED_THRESHOLD)


def _speed_eligible(session: Session, roster: list[str], candidate_speed: int) -> bool:
    if candidate_speed > SLOW_SPEED_THRESHOLD:
        return True
    return _slow_count(session, roster) < SLOW_SPEED_BUDGET


def _introduces_no_new_overlap(session: Session, roster: list[str], candidate: str) -> bool:
    """Only a HARD-REQUIREMENT-tier shared weakness disqualifies a candidate -- a
    tradeable-tier overlap (e.g. Dragonite/Cloyster both sharing Rock at pervasiveness
    0.03) was accepted throughout the real hand-walked run and never caused a
    rejection there; rejecting on ANY overlap regardless of severity is stricter than
    what was actually validated and blocks real, correct picks (Cloyster itself would
    fail this check against Dragonite otherwise)."""
    overlaps = team_builder.weakness_overlap(session, roster + [candidate])
    hard_overlaps_involving_candidate = [
        o
        for o in overlaps
        if any(m["name"] == candidate for m in o["members"])
        and (o["pervasiveness"] >= HARD_REQUIREMENT_PERVASIVENESS or any(m["multiplier"] >= HARD_REQUIREMENT_MULTIPLIER for m in o["members"]))
    ]
    return not hard_overlaps_involving_candidate


def _resistant_real_candidates_by_tier(session: Session, attacking_type: str, pool: set[str]) -> list[set[str]]:
    """Real pool members that resist or are immune to attacking_type, grouped by
    resistance tier and ORDERED strongest-first (immune, then 0.25x, then 0.5x) --
    grounded in viable_pool membership so a species with zero real usage (e.g.
    Dewgong-style theoretical answers) never gets considered.

    A 0.5x resistance is a structurally weaker answer than a 0.25x/immune one (the
    original Cloyster-over-Starmie case -- Cloyster's 0.25x plus freeze immunity beat
    Starmie's mere 0.5x on real type-chart strength, not on stats), so the caller
    should always exhaust the strongest tier's real, speed/overlap-eligible candidates
    before considering the next -- but a stronger tier existing at all doesn't mean it
    has anyone left once those filters apply (every real Electric-resistant Ground/
    immune candidate turned out to also be Ice-weak, colliding with Dragonite), so the
    weaker tier must still be tried rather than giving up.
    """
    matchup = retrieval.pokemon_by_type_matchup(session, attacking_type)
    if matchup is None:
        return []

    by_factor: dict[float, set[str]] = {}
    for factor, entries in matchup["buckets"].items():
        if factor < 1.0:
            names = {e["name"] for e in entries} & pool
            if names:
                by_factor[factor] = names

    return [by_factor[factor] for factor in sorted(by_factor)]


def _learns_any_explosion_move(session: Session, candidate: str) -> bool:
    stats = team_builder.enabler_stats(session, [candidate], move_checks=list(EXPLOSION_MOVES))
    return bool(stats) and any(stats[0]["learns"][m] for m in EXPLOSION_MOVES)


def _coverage_count(session: Session, name: str) -> int:
    coverage = team_builder.offensive_coverage(session, name)
    return len(coverage["supereffective_against"]) if coverage else 0


def _tie_break_score(session: Session, a: str, b: str) -> float:
    speed_a = team_builder.speed_tiers(session, [a])[0]["speed"]
    speed_b = team_builder.speed_tiers(session, [b])[0]["speed"]
    cov_a = _coverage_count(session, a)
    cov_b = _coverage_count(session, b)
    return (speed_a - speed_b) - (cov_b - cov_a) * COVERAGE_WEIGHT


def _pick_best_by_tie_break(session: Session, roster: list[str], candidates: list[str]) -> tuple[str, str]:
    """Move-access (Explosion/Self-Destruct) is checked FIRST, for every tie: if
    exactly one candidate learns either move, it wins outright, formula skipped. Only
    when move-access is tied (all candidates learn it, or none do) does the
    Speed/coverage formula decide. This is the general form of what was originally a
    narrower "roster already has 2 learners, one candidate would make it 3" rule --
    found too narrow while verifying against the real Cloyster-over-Lapras decision
    (made via Explosion/Self-Destruct access, before the formula existed): the two
    cases that established "formula decides everything" (Gengar/Electrode,
    Alakazam/Mr. Mime) both happened to have TIED move-access, so that rule was never
    actually tested against a case where move-access differs. Cloyster vs Lapras is
    exactly that case, and move-access was the real reason Cloyster won.
    """
    if len(candidates) == 1:
        return candidates[0], "only real, eligible candidate"

    explosion_learners = [c for c in candidates if _learns_any_explosion_move(session, c)]
    if len(explosion_learners) == 1:
        winner = explosion_learners[0]
        return winner, "the only candidate with real Explosion/Self-Destruct access -- move-access decides before the formula runs"

    best = candidates[0]
    for challenger in candidates[1:]:
        if _tie_break_score(session, challenger, best) > 0:
            best = challenger
    return best, "won the Speed/coverage tie-break formula (move-access was tied)"


def _score_special_sponge(session: Session, name: str) -> float:
    stats = team_builder.enabler_stats(session, [name])
    return stats[0]["hp"] * stats[0]["special"] if stats else -1.0


def _score_cleaner(session: Session, name: str) -> tuple[int, int, int]:
    """Bulk floor first (clears CLEANER_BULK_FLOOR on hp+defense), then Speed, then
    best offensive stat. A pure Speed-first formula picks a fragile suicide-lead
    (Electrode) over a real cleaner (Tauros) -- a cleaner needs to survive a hit and
    keep sweeping, not just be fast. Encoded as a tuple so the bulk check dominates
    the max() comparison in _pick_role without a separate filtering pass."""
    stats = team_builder.enabler_stats(session, [name])
    if not stats:
        return (0, -1, -1)
    bulk = stats[0]["hp"] + stats[0]["defense"]
    clears_bulk_floor = 1 if bulk >= CLEANER_BULK_FLOOR else 0
    return (clears_bulk_floor, stats[0]["speed"], max(stats[0]["attack"], stats[0]["special"]))


ROLE_SCORERS = {
    "special_sponge": _score_special_sponge,
    "cleaner": _score_cleaner,
}


def _pick_role(session: Session, roster: list[str], role: str, pool: list[str]) -> tuple[str, str]:
    scorer = ROLE_SCORERS[role]
    remaining = [c for c in pool if c not in [n.lower() for n in roster]]
    best = max(remaining, key=lambda c: scorer(session, c))
    return best, f'best "{role}" candidate by role-specific stats -- selection process bypassed as requested'


def _record_role_pick_facts(session: Session, roster: list[str], winner: str) -> str:
    overlaps = team_builder.weakness_overlap(session, roster + [winner])
    involved = [o for o in overlaps if any(m["name"] == winner for m in o["members"])]
    hard_own = _hard_requirements(session, winner)
    facts = []
    facts.append("introduces no new overlap" if not involved else f"introduces new overlap: {involved}")
    if hard_own:
        facts.append(f"own hard-requirement liabilities: {[l['attacking_type'] for l in hard_own]}")
    else:
        facts.append("no own hard-requirement liabilities")
    return "; ".join(facts)


def _assemble_roster(session: Session, anchor: str, fixed_members: list[str] | None, role_overrides: list[str] | None) -> _BuildState:
    state = _BuildState(roster=[anchor] + list(fixed_members or []))
    role_slots = list(role_overrides or [])

    while len(state.roster) < TEAM_SIZE:
        slots_remaining = TEAM_SIZE - len(state.roster)
        pool = team_builder.viable_pool(session)

        if slots_remaining <= len(role_slots):
            role = role_slots.pop(0)
            winner, reason = _pick_role(session, state.roster, role, pool)
            facts = _record_role_pick_facts(session, state.roster, winner)
            state.roster.append(winner)
            state.trail.append(_PickRecord(name=winner, reason=reason, detail=facts))
            continue

        open_reqs = _open_requirements(session, state.roster)
        picked = False
        for req in open_reqs:
            attacking_type = req["attacking_type"]
            tiers = _resistant_real_candidates_by_tier(session, attacking_type, set(pool))

            eligible: list[str] = []
            for tier in tiers:
                tier_names = tier - {n.lower() for n in state.roster}
                tier_eligible = []
                for c in sorted(tier_names):
                    speed = team_builder.speed_tiers(session, [c])[0]["speed"]
                    if not _speed_eligible(session, state.roster, speed):
                        continue
                    if not _introduces_no_new_overlap(session, state.roster, c):
                        continue
                    tier_eligible.append(c)
                if tier_eligible:
                    eligible = tier_eligible
                    break

            if not eligible:
                state.unresolved.append(
                    f"{attacking_type} (pervasiveness {req['pervasiveness']:.2f}): no real candidate resists it "
                    f"at any tier without failing the speed budget or reintroducing an existing overlap"
                )
                continue

            winner, reason = _pick_best_by_tie_break(session, state.roster, eligible)
            state.roster.append(winner)
            state.trail.append(
                _PickRecord(name=winner, reason=f"answers {attacking_type} liability ({reason})")
            )
            picked = True
            break

        if picked:
            continue

        # No open hard requirement (or all open ones were genuine dead ends this pass)
        # -- open role-free pick under the same speed/overlap filters.
        candidates = []
        for c in pool:
            if c in [n.lower() for n in state.roster]:
                continue
            speed = team_builder.speed_tiers(session, [c])[0]["speed"]
            if not _speed_eligible(session, state.roster, speed):
                continue
            if not _introduces_no_new_overlap(session, state.roster, c):
                continue
            candidates.append(c)

        if not candidates:
            # Structurally impossible to keep going without breaking a rule -- stop
            # rather than loop forever silently violating the speed/overlap rules.
            break

        winner, reason = _pick_best_by_tie_break(session, state.roster, candidates)
        state.roster.append(winner)
        state.trail.append(_PickRecord(name=winner, reason=f"open pick ({reason})"))

    return state


def _final_audit(session: Session, anchor: str, roster: list[str]) -> dict:
    return {
        "weakness_overlap": team_builder.weakness_overlap(session, roster),
        "structural_coverage": team_builder.structural_coverage(session, anchor, roster),
    }


def _narrate(anchor: str, state: _BuildState, audit: dict) -> str:
    client = OpenAI()
    trail_lines = [f"- {p.name}: {p.reason}" + (f" ({p.detail})" if p.detail else "") for p in state.trail]
    unresolved_lines = [f"- {u}" for u in state.unresolved] or ["- none"]

    hard_overlaps = [
        o
        for o in audit["weakness_overlap"]
        if o["pervasiveness"] >= HARD_REQUIREMENT_PERVASIVENESS
        or any(m["multiplier"] >= HARD_REQUIREMENT_MULTIPLIER for m in o["members"])
    ]
    tradeable_overlaps = [o for o in audit["weakness_overlap"] if o not in hard_overlaps]

    def _fmt_overlap(o: dict) -> str:
        members = ", ".join(f"{m['name']} ({m['multiplier']:g}x)" for m in o["members"])
        return f"- {o['attacking_type']} (pervasiveness {o['pervasiveness']:.2f}): {members}"

    hard_overlap_lines = [_fmt_overlap(o) for o in hard_overlaps] or ["- none"]
    tradeable_overlap_lines = [_fmt_overlap(o) for o in tradeable_overlaps] or ["- none"]

    prompt = (
        f"You are Professor Oak. A Gen-1 team has already been fully assembled and verified "
        f"by a deterministic pipeline -- your only job is to narrate it clearly and "
        f"enthusiastically. Do not second-guess or change any pick.\n\n"
        f"Anchor: {anchor}\n"
        f"Final roster ({len(state.roster)} Pokemon): {', '.join(state.roster)}\n\n"
        f"Why each pick was made, in order:\n" + "\n".join(trail_lines) + "\n\n"
        f"Liabilities that could NOT be resolved by any real candidate (state this plainly, "
        f"do not hide it):\n" + "\n".join(unresolved_lines) + "\n\n"
        f"HARD-REQUIREMENT-tier shared weaknesses in the FINAL roster (pervasiveness >= "
        f"{HARD_REQUIREMENT_PERVASIVENESS} or a 4x+ multiplier) -- these are a REAL, serious "
        f"flaw (multiple team members can be knocked out by the same real attacking type at "
        f"once). You MUST call these out explicitly and prominently as a caveat, in their own "
        f"clearly-labeled section -- do not bury them in a generic summary or downplay them, "
        f"even though the team is otherwise complete and correct:\n"
        + "\n".join(hard_overlap_lines) + "\n\n"
        f"Tradeable-tier shared weaknesses (low pervasiveness, mention only briefly if at all):\n"
        + "\n".join(tradeable_overlap_lines) + "\n\n"
        f"Write the final answer for the user now."
    )
    response = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt}])
    return response.choices[0].message.content or ""


def build_team(
    session: Session,
    anchor_name: str,
    fixed_members: list[str] | None = None,
    role_overrides: list[str] | None = None,
) -> str:
    """Deterministically assembles a 6-Pokemon Gen-1 team around anchor_name, then
    makes exactly one LLM call to narrate the already-fixed result. See
    team_agent.py's module docstring / the project plan for the full algorithm.

    fixed_members: Pokemon the caller has already locked in, consuming their own
        roster slots before the automated process fills the rest.
    role_overrides: role names (e.g. ["special_sponge", "cleaner"]) applied to the
        LAST len(role_overrides) slots, bypassing the hard-requirement search for
        those slots entirely. Unrecognized role names raise KeyError. Defaults to
        DEFAULT_ROLE_OVERRIDES (special_sponge + cleaner) when omitted -- pass an
        explicit empty list for a fully-automatic build with no fixed roles at all.

    Returns a plain "not found" string if anchor_name isn't a real Pokemon, matching
    every other grounding-sensitive function in this app.
    """
    species = retrieval.find_species_by_name(session, anchor_name)
    if species is None:
        return f"No Pokémon named '{anchor_name}' was found in the Pokédex records."

    if role_overrides is None:
        role_overrides = DEFAULT_ROLE_OVERRIDES

    state = _assemble_roster(session, species.name, fixed_members, role_overrides)
    audit = _final_audit(session, species.name, state.roster)
    return _narrate(species.name, state, audit)
