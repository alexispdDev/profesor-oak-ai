from sqlalchemy import select
from sqlalchemy.orm import Session

from profesor_oak_ai.agent import retrieval
from profesor_oak_ai.db.models import Gen1ouUsageMove, Move, PokemonSpecies, PokemonType

# A real >=2x type weakness is worth caring about below this threshold; anything less
# (e.g. a 1.x multiplier that doesn't exist in this all-or-nothing Gen-1 type chart) is
# neutral or a resistance, not a liability.
WEAKNESS_THRESHOLD = 2.0

# A move counts as actually part of the metagame (not just technically learnable) once
# it's run on at least this fraction of a species' real recorded teams.
MEANINGFUL_MOVE_USAGE_PERCENT = 15.0


def _viable_pool_ids(session: Session) -> set[int]:
    """species_id set behind viable_pool -- shared with type_usage_severity's default
    pool so both use exactly the same real-usage-grounded species, computed once."""
    evolved_from_ids = {
        row[0]
        for row in session.execute(
            select(PokemonSpecies.evolves_from_species_id).where(
                PokemonSpecies.evolves_from_species_id.isnot(None)
            )
        )
    }
    pool_species_ids = {
        row[0]
        for row in session.execute(select(Gen1ouUsageMove.species_id).distinct())
    }
    return pool_species_ids - evolved_from_ids


def viable_pool(session: Session) -> list[str]:
    """The real-usage-grounded candidate pool for Gen-1 team-building: every
    fully-evolved species with at least one row in gen1ou_usage_moves (i.e. it actually
    appeared in a real Smogon Gen1-OU usage-stats snapshot, not just something that's
    technically learnable/reachable). A species that never evolves further already
    counts on its own; one that DOES have a further evolution is excluded even if the
    snapshot recorded it (e.g. Kadabra, Dragonair) -- a team is built around the
    fully-evolved form.

    Returned alphabetically -- deliberately NOT ranked by usage/popularity. An earlier
    draft ordered this by each species' own peak move usage_percent as a stand-in for
    real cross-species popularity, but that number is normalized within one species'
    own moveset, not comparable across species (it ties clear fringe picks with genuine
    staples), so it was dropped as a ranking signal entirely.
    """
    pool_ids = _viable_pool_ids(session)
    names = session.execute(
        select(PokemonSpecies.name).where(PokemonSpecies.species_id.in_(pool_ids))
    ).scalars().all()
    return sorted(names)


def type_usage_severity(
    session: Session, attacking_type: str, pool_species_ids: set[int] | None = None
) -> dict | None:
    """Pervasiveness of a given attacking type across the real-usage pool: the fraction
    of pool species that actually run a DAMAGING move of that type at a meaningful
    (>=MEANINGFUL_MOVE_USAGE_PERCENT) real usage rate. Deliberately excludes status
    moves -- a past bug let Rest/Agility (genuinely Psychic-typed but zero-power) count
    toward Psychic pervasiveness, inflating it well past what real damage pressure
    justified. Pass pool_species_ids to score against a caller-chosen subset instead of
    the full default pool (viable_pool's species_id set). Returns None if
    attacking_type isn't a recognized Gen-1 type.
    """
    type_row = session.scalar(
        select(PokemonType).where(PokemonType.name == attacking_type.strip().lower())
    )
    if type_row is None:
        return None

    pool_ids = pool_species_ids if pool_species_ids is not None else _viable_pool_ids(session)
    if not pool_ids:
        return {"attacking_type": type_row.name, "pervasiveness": 0.0, "qualifying_species": [], "pool_size": 0}

    rows = session.execute(
        select(PokemonSpecies.name)
        .join(Gen1ouUsageMove, Gen1ouUsageMove.species_id == PokemonSpecies.species_id)
        .join(Move, Move.move_id == Gen1ouUsageMove.move_id)
        .where(
            Move.type_id == type_row.type_id,
            Move.damage_class != "status",
            Gen1ouUsageMove.usage_percent >= MEANINGFUL_MOVE_USAGE_PERCENT,
            Gen1ouUsageMove.species_id.in_(pool_ids),
        )
        .distinct()
    ).scalars().all()

    qualifying_species = sorted(rows)
    return {
        "attacking_type": type_row.name,
        "pervasiveness": len(qualifying_species) / len(pool_ids),
        "qualifying_species": qualifying_species,
        "pool_size": len(pool_ids),
    }


def liability_profile(session: Session, anchor_name: str) -> dict | None:
    """The named anchor's real >=WEAKNESS_THRESHOLD type weaknesses, each annotated
    with type_usage_severity's pervasiveness score plus the real named Pokémon (species,
    move, usage_percent) that actually threaten the anchor that way -- every pool member
    carrying a move of that attacking type, not just the ones that clear the "meaningful"
    usage bar (that filtering is type_usage_severity's job; this exposes the full raw
    picture so a caller can see exactly how thin or deep the threat list really is).
    Liabilities are sorted by pervasiveness descending. Returns None if anchor_name
    isn't a real Pokémon.
    """
    species = retrieval.find_species_by_name(session, anchor_name)
    if species is None:
        return None
    matchups = retrieval.defensive_type_matchups(session, anchor_name)
    if matchups is None:
        return None

    pool_ids = _viable_pool_ids(session)
    liabilities = []
    for attacking_type, multiplier in matchups["factors"].items():
        if multiplier < WEAKNESS_THRESHOLD:
            continue

        severity = type_usage_severity(session, attacking_type, pool_ids)
        type_row = session.scalar(select(PokemonType).where(PokemonType.name == attacking_type))

        users = session.execute(
            select(PokemonSpecies.name, Move.name, Gen1ouUsageMove.usage_percent)
            .join(Gen1ouUsageMove, Gen1ouUsageMove.species_id == PokemonSpecies.species_id)
            .join(Move, Move.move_id == Gen1ouUsageMove.move_id)
            .where(
                Move.type_id == type_row.type_id,
                Move.damage_class != "status",
                PokemonSpecies.species_id.in_(pool_ids),
            )
            .order_by(Gen1ouUsageMove.usage_percent.desc())
        ).all()

        liabilities.append(
            {
                "attacking_type": attacking_type,
                "multiplier": multiplier,
                "pervasiveness": severity["pervasiveness"],
                "users": [
                    {"name": name, "move_name": move_name, "usage_percent": usage_percent}
                    for name, move_name, usage_percent in users
                ],
            }
        )

    liabilities.sort(key=lambda lia: -lia["pervasiveness"])
    return {"name": species.name, "types": matchups["types"], "liabilities": liabilities}


def weakness_overlap(session: Session, pokemon_names: list[str]) -> list[dict]:
    """Audits a TEAM (not a single Pokémon, see liability_profile for that): finds
    every real >=WEAKNESS_THRESHOLD attacking type that 2+ of the named Pokémon are
    INDEPENDENTLY weak to. A weakness only one member has is fine -- the rest of the
    team can cover for it. A weakness shared by 2+ members is a real blind spot: a
    single attacker of that type threatens more than one Pokémon on the roster at
    once, regardless of how the rest of the team is built. Each shared weakness is
    annotated with the same pervasiveness score as liability_profile, so a caller can
    judge how dangerous the overlap actually is rather than treating every shared
    weakness as equally serious -- a higher pervasiveness number means more real
    danger, independent of how many members happen to share it.

    Assumes every name in pokemon_names already resolves to a real Pokémon (name
    resolution is the caller's job, same as elsewhere in this module) -- a name that
    doesn't resolve is silently excluded rather than raising, so one bad name doesn't
    blank out the whole audit.

    Returns a list of {"attacking_type", "pervasiveness", "members": [{"name",
    "multiplier"}]}, sorted by pervasiveness descending. Empty list is a real,
    meaningful answer: no shared weakness exists among the named Pokémon.
    """
    pool_ids = _viable_pool_ids(session)

    by_type: dict[str, list[dict]] = {}
    for name in pokemon_names:
        matchups = retrieval.defensive_type_matchups(session, name)
        if matchups is None:
            continue
        for attacking_type, multiplier in matchups["factors"].items():
            if multiplier < WEAKNESS_THRESHOLD:
                continue
            by_type.setdefault(attacking_type, []).append({"name": name, "multiplier": multiplier})

    overlaps = []
    for attacking_type, members in by_type.items():
        if len(members) < 2:
            continue
        severity = type_usage_severity(session, attacking_type, pool_ids)
        overlaps.append(
            {
                "attacking_type": attacking_type,
                "pervasiveness": severity["pervasiveness"],
                "members": members,
            }
        )

    overlaps.sort(key=lambda o: -o["pervasiveness"])
    return overlaps


def enabler_stats(
    session: Session,
    pokemon_names: list[str],
    reference_speeds: dict[str, int] | None = None,
    move_checks: list[str] | None = None,
) -> list[dict]:
    """Raw stats (HP, Attack, Defense, Special, Speed, crit rate) and movepool facts
    for comparing candidates -- no scoring, no verdict, just the numbers to compare
    (e.g. as the "cleaner" role's Attack/Special comparison, or a move-access check, in
    Task C). Doesn't touch usage data at all, unlike every other function in this
    module -- pure PokemonForm stats plus move-learnability checks.

    reference_speeds is already-resolved {name: speed} pairs, not raw Pokémon names
    to look up -- name resolution is the caller's job, same as elsewhere in this
    module (a tool wrapper would resolve reference_pokemon names to their Speed
    before calling this). move_checks are move names to check learnability for via
    retrieval.pokemon_learning_move, e.g. ["explosion", "self-destruct"].

    A name in pokemon_names that doesn't resolve to a real species is silently
    excluded from the result rather than raising, same convention as
    weakness_overlap.
    """
    move_checks = move_checks or []
    learners_by_move = {}
    for move_name in move_checks:
        result = retrieval.pokemon_learning_move(session, move_name)
        learners_by_move[move_name] = {l["name"] for l in result["learners"]} if result else set()

    stats = []
    for name in pokemon_names:
        species = retrieval.find_species_by_name(session, name)
        if species is None:
            continue
        form = retrieval.get_default_form(session, species)
        if form is None:
            continue
        stats.append(
            {
                "name": species.name,
                "hp": form.hp,
                "attack": form.attack,
                "defense": form.defense,
                "special": form.special,
                "speed": form.speed,
                "crit_rate": round(form.speed * 100 / 512, 1),
                "outspeeds": {
                    ref_name: form.speed > ref_speed for ref_name, ref_speed in (reference_speeds or {}).items()
                },
                "learns": {move_name: species.name in learners_by_move[move_name] for move_name in move_checks},
            }
        )

    return stats


def structural_coverage(
    session: Session, anchor_name: str, team_names: list[str], extra_move_checks: list[str] | None = None
) -> dict | None:
    """Requirement-vs-coverage matrix for the CURRENT state of a team being built
    around anchor_name -- a snapshot evaluation of team_names as given, not a
    finished-roster audit. Requirements are DERIVED from the anchor's own real
    liabilities (see liability_profile), NOT a fixed generic checklist -- an
    uncovered tradeable-tier liability (low pervasiveness) is a normal, expected gap
    at any point before the roster is complete, not necessarily something that needs
    fixing before the next pick.

    A liability counts as covered when a team_names member's combined defensive
    factor against that attacking type is < 1.0 (any resistance or immunity, 0.5x/
    0.25x/0x all count) -- reuses retrieval.defensive_type_matchups per member rather
    than reimplementing type-multiplier lookups. extra_move_checks are near-universal
    Gen-1 fixtures worth checking regardless of anchor (e.g. ["explosion",
    "self-destruct"] for trade-out capability) -- reuses the same
    retrieval.pokemon_learning_move primitive as enabler_stats.

    team_names may include or exclude the anchor itself -- whichever the caller
    passes is just checked for coverage like any other name. An unresolved name is
    silently excluded, same convention as weakness_overlap/enabler_stats. Returns
    None if anchor_name itself isn't a real Pokémon.
    """
    profile = liability_profile(session, anchor_name)
    if profile is None:
        return None

    member_factors: dict[str, dict[str, float]] = {}
    for member in team_names:
        matchups = retrieval.defensive_type_matchups(session, member)
        if matchups is not None:
            member_factors[member] = matchups["factors"]

    type_requirements = []
    for lia in profile["liabilities"]:
        covered_by = [
            {"name": member, "multiplier": factors[lia["attacking_type"]]}
            for member, factors in member_factors.items()
            if factors.get(lia["attacking_type"], 1.0) < 1.0
        ]
        type_requirements.append(
            {
                "attacking_type": lia["attacking_type"],
                "pervasiveness": lia["pervasiveness"],
                "covered_by": covered_by,
            }
        )

    move_requirements = {}
    for move_name in extra_move_checks or []:
        result = retrieval.pokemon_learning_move(session, move_name)
        learners = {l["name"] for l in result["learners"]} if result else set()
        move_requirements[move_name] = [
            member for member in team_names if member.strip().lower() in learners
        ]

    return {"anchor": profile["name"], "type_requirements": type_requirements, "move_requirements": move_requirements}


def speed_tiers(session: Session, pokemon_names: list[str]) -> list[dict]:
    """Pacing check, not a weakness-coverage check -- doesn't touch types, liabilities,
    or usage data at all. Each named Pokémon's real base Speed and the actual Gen-1
    critical-hit rate (speed * 100 / 512, a real Gen-1-specific mechanic -- later games
    compute crits differently), sorted fastest to slowest.

    Pure data, no verdict, same as every other function here -- this does NOT decide
    whether a roster's speed spread is "healthy." That's a Task C concern (e.g. a rule
    like "at most 2 of 6 roster members may have Speed <= 85"), enforced in the
    orchestration pipeline against this function's output, not decided here.

    An unresolved name is silently excluded, same convention as the rest of this module.
    """
    stats = []
    for name in pokemon_names:
        species = retrieval.find_species_by_name(session, name)
        if species is None:
            continue
        form = retrieval.get_default_form(session, species)
        if form is None:
            continue
        stats.append({"name": species.name, "speed": form.speed, "crit_rate": round(form.speed * 100 / 512, 1)})

    stats.sort(key=lambda s: -s["speed"])
    return stats


def offensive_coverage(session: Session, pokemon_name: str) -> dict | None:
    """How many distinct defending types a Pokémon's FULL learnable movepool (level-up
    + machine, not just real-usage moves -- see retrieval.move_types_for_pokemon) can
    hit super-effectively (>=2x). Built for Task C's Speed/coverage-breadth tie-break
    formula -- this function only supplies the raw count and the real type names behind
    it, never a verdict; the formula itself (and its weighting) lives in Task C, keeping
    the same "team_builder returns data, Task C decides" split as every other function
    here.

    Returns None if pokemon_name isn't a real Pokémon.
    """
    species = retrieval.find_species_by_name(session, pokemon_name)
    if species is None:
        return None

    move_types = retrieval.move_types_for_pokemon(session, pokemon_name) or []
    supereffective_against: set[str] = set()
    for move_type in move_types:
        matchup = retrieval.offensive_type_matchups(session, move_type)
        if matchup is None:
            continue
        supereffective_against.update(
            defending_type for defending_type, factor in matchup["factors"].items() if factor >= 2.0
        )

    return {
        "name": species.name,
        "move_types": move_types,
        "supereffective_against": sorted(supereffective_against),
    }
