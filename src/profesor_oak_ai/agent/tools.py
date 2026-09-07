import json

from profesor_oak_ai.agent import retrieval, team_agent
from profesor_oak_ai.db.engine import get_engine, get_session


def _coerce_list(value: list[str] | str) -> list[str]:
    # Some models JSON-encode array arguments as a string instead of a real list.
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value]
    return value


def get_pokemon_info(name: str) -> str:
    """Look up a Pokémon's types, base stats, and Pokédex lore by name.

    Args:
        name: The Pokémon's name, e.g. "Pikachu".
    """
    session = get_session(get_engine())
    try:
        species = retrieval.find_species_by_name(session, name)
        if species is None:
            return f"No Pokémon named '{name}' was found in the Pokédex records."
        return retrieval.describe_pokemon(session, species)
    finally:
        session.close()


def get_move_info(move_name: str) -> str:
    """Look up a MOVE's own metadata by its name -- type, damage class, power,
    accuracy, PP, and effect text. Use this whenever a question is about a specific
    move itself (e.g. "does Seismic Toss...", "what does Thunder Wave do", "how much
    PP does Recover have") rather than about a Pokémon's learnset -- do not pass a
    move name to any Pokémon-keyed tool (get_pokemon_info, get_move_types,
    search_moves's pokemon_name, etc.), those resolve species names, not move names,
    and will report the move as an unrecognized Pokémon.

    For a small, specific set of Gen-1 moves (Seismic Toss, Counter, Bide, SonicBoom,
    Super Fang, Night Shade), this tool's result includes a "Generation I note" flagging
    a real, documented engine bug: these moves skip the type-IMMUNITY check entirely in
    Generation I (not just damage scaling), so e.g. Seismic Toss/Counter/Bide/SonicBoom/
    Super Fang actually DO hit Ghost-types like Gengar in Gen 1 despite Ghost's normal
    Fighting/Normal immunity, and Night Shade DOES hit Normal-types despite Ghost moves
    normally having no effect on Normal -- fixed starting in Generation II. This is NOT
    true of Fighting/Normal/Ghost moves in general (an ordinary move like Karate Chop is
    still fully blocked by Ghost's immunity in Gen 1) -- only these specific named moves.
    When this note is present for the move asked about, trust it over get_type_
    effectiveness/get_type_matchups' generic type-chart result for whether the move can
    hit the target at all; when absent, the normal type chart applies as usual.

    Args:
        move_name: The move's name, e.g. "Seismic Toss" or "Thunder Wave".
    """
    session = get_session(get_engine())
    try:
        info = retrieval.move_info(session, move_name)
        if info is None:
            return f"No move named '{move_name}' was found in the Pokédex records."
        lines = [
            f"Name: {info['name'].replace('-', ' ').title()}",
            f"Type: {info['type'].title()}",
            f"Damage class: {info['damage_class']}",
            f"Power: {info['power']}",
            f"Accuracy: {info['accuracy']}",
            f"PP: {info['pp']}",
        ]
        if info["effect_chance"] is not None:
            lines.append(f"Effect chance: {info['effect_chance']}%")
        if info["effect_description"]:
            lines.append(f"Effect: {info['effect_description']}")
        if info["gen1_immunity_bypass_note"]:
            lines.append(f"Generation I note: {info['gen1_immunity_bypass_note']}")
        return "\n".join(lines)
    finally:
        session.close()


def list_moves_by_type(move_type: str) -> str:
    """Every Gen-1 move of a given type, with each move's damage class, power,
    accuracy, PP, and effect text. Use this for "which <type>-type move does X"
    questions -- e.g. "which Fighting-type move hits multiple times in one turn",
    "which Water-type move always causes a critical hit" -- where the question
    describes a MOVE by some property rather than naming it directly.

    Do NOT answer this kind of question by guessing a Pokémon that might know a move
    of that type and calling search_moves on it, and do NOT guess the move's name
    directly from memory and call get_move_info -- both require already knowing the
    answer to find it. This tool searches moves by type directly, with no Pokémon or
    move name needed up front.

    Args:
        move_type: The move type to search, e.g. "fighting".
    """
    session = get_session(get_engine())
    try:
        moves = retrieval.moves_by_type(session, move_type)
        if moves is None:
            return f"Unknown type: {move_type}"
        if not moves:
            return f"No Gen-1 moves of type '{move_type}' were found in the Pokédex records."

        lines = [f"Gen-1 {move_type.title()}-type moves:"]
        for m in moves:
            lines.append(
                f"  - {m['name'].replace('-', ' ').title()} ({m['damage_class']}, "
                f"power={m['power']}, accuracy={m['accuracy']}, pp={m['pp']}): {m['effect_description']}"
            )
        return "\n".join(lines)
    finally:
        session.close()


def list_pokemon_learning_move(
    move_name: str,
    learn_method: str | None = None,
    version: str | None = None,
    pokemon_type: str | None = None,
) -> str:
    """Find every Gen-1 Pokémon that can learn a given move, with each learner's own
    type(s), learn method, and level. Use this for "which Pokémon learn move X"
    questions -- especially ones with an extra constraint like "which DUAL-TYPED
    Pokémon learns X" or "which Water-type learns X" -- instead of naming a candidate
    species from memory and checking only that one guess. Guessing a single candidate
    is exactly how this fails: the guess can turn out not to actually learn the move
    at all, and even when it does, checking only one candidate can miss that NONE of
    the real learners satisfy the extra constraint (e.g. every real learner turns out
    to be single-typed), which only shows up by looking at the full learner list this
    tool returns, not by verifying one guess in isolation.

    An empty learner list is a real, meaningful answer (no Gen-1 Pokémon -- or none
    matching the given filters -- learns this move), not a failure; report that
    plainly rather than falling back to a guessed name.

    Args:
        move_name: The move's name, e.g. "Double Kick".
        learn_method: Optional learn method filter: "level-up" or "machine". Omit for
            either.
        version: Optional Gen-1 game filter: "red", "blue", or "yellow". Red/Blue and
            Yellow can genuinely differ on who learns a move, or at what level -- pass
            this whenever the question names a specific game. Omit for the union
            across all Gen-1 games.
        pokemon_type: Optional type filter, e.g. "fighting" -- restricts to learners
            that have that type (in either slot). ALWAYS pass this when the question
            already names a type constraint (e.g. "which Fighting-type Pokémon learn
            Rest") rather than fetching every learner unfiltered and manually
            cross-referencing against a separate list_pokemon_by_type call -- a widely
            TM-learnable move can have 100+ unfiltered learners, and manually checking
            a handful of names against that by eye is unnecessary work with an
            unnecessary chance of miscounting.
    """
    session = get_session(get_engine())
    try:
        try:
            result = retrieval.pokemon_learning_move(session, move_name, learn_method, version, pokemon_type)
        except ValueError as exc:
            return str(exc)
        if result is None:
            return f"No move named '{move_name}' was found in the Pokédex records."

        learners = result["learners"]
        scope = f" in {version.title()}" if version else ""
        method_note = f" via {learn_method}" if learn_method else ""
        type_note = f" that are {pokemon_type.title()}-type" if pokemon_type else ""
        if not learners:
            return (
                f"No Gen-1 Pokémon{type_note} learns {result['move_name'].replace('-', ' ').title()}"
                f"{method_note}{scope}."
            )

        lines = [
            f"Pokémon{type_note} that learn {result['move_name'].replace('-', ' ').title()}"
            f"{method_note}{scope}:"
        ]
        for entry in sorted(learners, key=lambda e: e["name"]):
            types_str = "/".join(t.title() for t in entry["types"])
            # Spelled out explicitly rather than left for the caller to infer by
            # counting "/"-separated types -- that inference has been observed to fail
            # in practice (a single-typed entry like "(Fighting)" misread as dual-typed).
            type_count_note = "dual-typed" if len(entry["types"]) >= 2 else "single-typed"
            level_note = f" at level {entry['level']}" if entry["learn_method"] == "level-up" else ""
            lines.append(
                f"  - {entry['name'].title()} ({types_str}, {type_count_note}), "
                f"via {entry['learn_method']}{level_note}"
            )
        return "\n".join(lines)
    finally:
        session.close()


# Well-documented, static Generation I battle-engine bugs -- not Pokédex data (no
# species/move/type-specific lookup resolves them), and not something an LLM should
# guess about from memory: a quick reliability check of five of these found the model
# answering two of four confidently WRONG (claiming Hyper Beam's recharge still
# applies after a KO, and that stats simply cap at 999 with no overflow) and one
# vague/hedged rather than stating the actual mechanic -- worse than the ~50% hit rate
# guessing implies, since a wrong answer here reads exactly as confident as a right
# one. Sourced and cross-checked against Bulbapedia and Smogon's Gen-1 mechanics
# guide; the Psychic/Ghost entry is included for completeness even though it's
# already correctly encoded in the type_efficacy table (get_type_effectiveness('ghost',
# ['psychic']) already returns 0.0) -- keep both in sync if either changes.
GEN1_BATTLE_ENGINE_BUGS = """\
Known Generation I (Red/Blue/Yellow) battle-engine bugs -- these are real, \
documented quirks of the original game code, not intended design, and were \
patched starting in Generation II unless noted otherwise:

1. Psychic/Ghost type-chart inversion: Ghost-type moves were intended to be \
super effective (2x) against Psychic-type Pokémon, but the type chart was coded \
backwards -- Psychic-types are instead completely IMMUNE (0x) to Ghost-type \
moves. (Lick was the only damaging Ghost-type move in Gen 1, so this meant \
Ghost-types had no way to hit Psychic-types super-effectively at all.)

2. Focus Energy inverts critical-hit rate: Focus Energy was intended to \
multiply the user's critical-hit ratio by 4x, but an inverted operation makes \
it DIVIDE the critical-hit ratio by 4 instead -- using Focus Energy makes the \
user only 1/4 as likely to land a critical hit as if it had never used the \
move at all.

3. The 1/256 miss chance: for any move that checks accuracy against the \
target, the accuracy roll is a random value from 0-255 that must come out \
strictly less than the move's accuracy (out of 256) to hit -- so even a move \
listed at "100%" accuracy has a roughly 1/256 (~0.4%) chance to miss, since \
rolling 255 always fails regardless of the move's accuracy stat. Swift and \
Bide are the exceptions: they skip the accuracy check entirely and cannot \
miss this way.

4. Stat overflow past 999: stat stages combined with badge-boost stacking can \
push a stat to the 999 display cap, but this isn't a clean, safe clamp -- \
further stat modification (particularly a decrease) once a stat is at or near \
that ceiling can overflow the value's storage and wrap it around to a very \
small number (effectively near 0), instantly gutting a stat that looked \
maxed-out. This is a real but fragile/edge-case interaction, not simply "stats \
cap at 999 with no side effects."

5. Hyper Beam's recharge turn has exceptions: Hyper Beam normally forces the \
user to spend its next turn recharging, but that recharge turn is skipped \
entirely if the move misses, knocks out the target, or breaks a Substitute -- \
the user can act freely on the following turn in those cases, not just when \
the move successfully hits and the target survives.

6. Multi-hit moves share ONE critical-hit roll: for a multi-hit move (e.g. \
Double Kick, Fury Attack, Twineedle, Comet Punch), the critical-hit check is \
NOT rolled independently per hit -- it's calculated once (on the first hit) \
and that same result is applied to every subsequent hit in the same use of \
the move. So a multi-hit move either critically hits on all of its hits, or \
none of them -- never some but not others.

If a battle-mechanics question isn't one of these six, do not extrapolate a \
similar-sounding "Gen-1 bug" from this list -- treat it as outside this tool's \
scope."""


def get_gen1_battle_engine_bugs() -> str:
    """Reference list of well-documented Generation I battle-ENGINE bugs/mechanics
    (not Pokédex facts) -- critical-hit rate, accuracy/miss rolls, stat overflow,
    Hyper Beam's recharge exceptions, multi-hit moves' shared critical-hit roll, and
    the Psychic/Ghost type-chart inversion. Call this for any question about Gen-1
    battle mechanics/glitches/bugs in this space (e.g. "does Focus Energy work as
    intended in Gen 1", "can a 100% accuracy move miss", "what happens to overflowed
    stats", "does Hyper Beam always need a recharge turn", "does each hit of Double
    Kick roll crits independently") instead of answering from memory -- these are
    exactly the kind of specific, easy-to-get-backwards trivia an LLM should not
    guess at. This is a small, fixed, hand-verified list, not a general glitch
    database -- if the question describes a mechanic not covered here, don't invent
    a similar-sounding answer; say the records don't cover it (per the grounding
    rule) rather than extrapolating.
    """
    return GEN1_BATTLE_ENGINE_BUGS


def get_type_effectiveness(attacking_type: str, defending_types: list[str]) -> str:
    """Compute the damage multiplier of an attacking type against one or two defending types.

    Args:
        attacking_type: The attacking move's type, e.g. "water".
        defending_types: One or two defending Pokémon types, e.g. ["fire"] or ["grass", "poison"].
    """
    defending_types = _coerce_list(defending_types)

    session = get_session(get_engine())
    try:
        factor = retrieval.type_effectiveness(session, attacking_type, defending_types)
        return f"{attacking_type.title()} vs {'/'.join(defending_types).title()}: x{factor} damage."
    except ValueError as exc:
        return str(exc)
    finally:
        session.close()


def get_type_matchups(pokemon_name: str) -> str:
    """Get a Pokémon's full DEFENSIVE type-matchup profile: every attacking type's
    combined damage multiplier against it (accounting for both types if dual-typed) --
    i.e. what is strong/weak against this Pokémon. Use this instead of calling
    get_type_effectiveness repeatedly when asked for a Pokémon's overall
    weaknesses/resistances rather than one specific matchup.

    Do NOT use this for "which types/Pokémon resist THIS Pokémon's own attacks" or
    "what is this Pokémon's move strong/weak against" questions -- that is the
    opposite, OFFENSIVE direction; use get_offensive_type_matchups(attacking_type)
    instead, passing this Pokémon's own type. Reversing this tool's defensive output to
    answer an offensive question gives a wrong answer for asymmetric types (e.g.
    Electric resists Flying defensively, but Electric attacks are super effective,
    not resisted, against Flying).

    This tool requires resolving a real, named Pokémon species. For a hypothetical
    type combo with no real Pokémon named (e.g. "a pure Ghost-type Pokémon" or "a
    Water/Flying-type"), use get_type_weaknesses(defending_types) instead -- do not
    substitute a real Pokémon of that type here, and do not fall back to
    get_type_effectiveness for a single self-vs-self comparison (e.g. Ghost vs Ghost)
    when the question asks for the type's FULL weakness profile.

    Args:
        pokemon_name: The Pokémon's name, e.g. "Bulbasaur".
    """
    session = get_session(get_engine())
    try:
        result = retrieval.defensive_type_matchups(session, pokemon_name)
        if result is None:
            return f"No Pokémon named '{pokemon_name}' was found in the Pokédex records."
        types_label = "/".join(t.title() for t in result["types"])
        return f"{pokemon_name.title()} ({types_label}) type matchups:\n" + _format_defensive_buckets(
            result["factors"]
        )
    finally:
        session.close()


def _format_defensive_buckets(factors: dict[str, float]) -> str:
    buckets: dict[float, list[str]] = {}
    for type_name, factor in factors.items():
        buckets.setdefault(factor, []).append(type_name)

    labels = {
        4.0: "4x weak to",
        2.0: "2x weak to",
        0.5: "0.5x resistant to",
        0.25: "0.25x resistant to",
        0.0: "immune to (0x)",
    }
    lines = []
    for factor in (4.0, 2.0, 0.5, 0.25, 0.0):
        names = sorted(buckets.get(factor, []))
        if names:
            lines.append(f"  {labels[factor]}: " + ", ".join(n.title() for n in names))
    return "\n".join(lines)


def get_type_weaknesses(defending_types: list[str]) -> str:
    """Get the full DEFENSIVE damage-multiplier profile for a hypothetical type combo
    with no real Pokémon named -- e.g. "what is a pure Ghost-type Pokémon weak to" or
    "what damage multipliers apply to a Water/Flying-type". This is the same
    computation as get_type_matchups but for a raw 1-2 type combo instead of a real
    species -- use get_type_matchups instead whenever the question actually names a
    real Pokémon. Do NOT use get_type_effectiveness here: a single self-vs-self call
    (e.g. Ghost vs Ghost) only answers one matchup, not the type's full weakness
    profile that "which types are super effective against X" asks for.

    Do NOT use this for "which Pokémon are type X" or "which Pokémon are PURE type X"
    questions -- those ask which species have a type, not what damage multipliers
    apply to a type; use list_pokemon_by_type(pokemon_type, pure_only=...) instead.
    This tool only answers questions about damage multipliers (weak to/resistant
    to/immune to), never a list of Pokémon names.

    Args:
        defending_types: One or two defending types, e.g. ["ghost"] or ["water", "flying"].
    """
    defending_types = _coerce_list(defending_types)
    session = get_session(get_engine())
    try:
        result = retrieval.type_matchups_for_types(session, defending_types)
        if result is None:
            return f"Unknown type: one of {defending_types}"
        types_label = "/".join(t.title() for t in result["types"])
        return f"A {types_label}-type Pokémon's type matchups:\n" + _format_defensive_buckets(
            result["factors"]
        )
    finally:
        session.close()


def get_offensive_type_matchups(attacking_type: str) -> str:
    """Get a type's full OFFENSIVE matchup profile: the damage multiplier of its
    attacks against every defending type -- i.e. what this type's moves are strong/weak
    against, or which types resist them. This is the opposite of get_type_matchups
    (which is defensive: what is strong/weak against a Pokémon). Use this for "which
    Pokémon/types resist X's move/attack", "what is X-type strong against", or "X's
    move is effective/ineffective against which types" questions.

    Args:
        attacking_type: The attacking type, e.g. "electric". For "<Pokémon>'s move" or
            "<Pokémon>'s attack" questions with no specific move named, use that
            Pokémon's own type (call get_pokemon_info first if its type isn't already
            known).

    This tool's buckets are single, PURE types only (e.g. "Bug, Flying, Poison,
    Psychic all resist Fighting") -- do NOT use it, plus list_pokemon_by_type or manual
    guessing, to answer "which Pokémon double-resist/are immune to <type>" or similar
    exact-multiplier questions. A real dual-typed species combines two types' factors
    (e.g. Zubat is Poison/Flying, each resisting Fighting at 0.5x, combining to 0.25x
    double resistance) -- reading this tool's single-type buckets and guessing which
    real species pair up two of them is exactly the kind of error-prone manual
    reasoning that produces wrong species lists (or an incorrect "nothing does this"
    when real double-resistant species exist). Use
    list_pokemon_by_type_matchup(attacking_type) instead -- it computes each real
    species' actual combined multiplier server-side.

    For "which types/Pokémon resist <Pokémon>'s attacks" (i.e. its whole movepool, not
    one type), do NOT chain calls to this tool by hand -- use
    list_pokemon_resisting_attacks(pokemon_name) instead, which computes the correct
    intersection across every move type in one deterministic call.
    """
    session = get_session(get_engine())
    try:
        result = retrieval.offensive_type_matchups(session, attacking_type)
        if result is None:
            return f"Unknown type: {attacking_type}"

        buckets: dict[float, list[str]] = {}
        for type_name, factor in result["factors"].items():
            if factor != 1.0:
                buckets.setdefault(factor, []).append(type_name)

        labels = {
            2.0: "super effective (2x) against",
            0.5: "not very effective / resisted (0.5x) by",
            0.0: "no effect (0x) against",
        }
        lines = [f"{result['attacking_type'].title()}-type attacks:"]
        for factor in (2.0, 0.5, 0.0):
            names = sorted(buckets.get(factor, []))
            if names:
                lines.append(f"  {labels[factor]}: " + ", ".join(n.title() for n in names))
        return "\n".join(lines)
    finally:
        session.close()


def list_pokemon_by_type_matchup(attacking_type: str) -> str:
    """Every real Gen-1 Pokémon species, grouped by the COMBINED damage multiplier
    they take from a single attacking type -- accounting for a real dual-typed
    species' actual two-type combo (e.g. Zubat is Poison/Flying, each resisting
    Fighting at 0.5x, combining to a 0.25x double resistance), not a single type in
    isolation. Use this for "which Pokémon double-resist/are immune to/are 4x weak to
    <type>" questions, or any question asking for actual SPECIES (not just type names)
    at a specific damage multiplier against one attacking type.

    Do NOT try to answer this by reading get_offensive_type_matchups' single-type
    buckets and guessing which real dual-type species combine two of them -- that
    manual reasoning is exactly what produces wrong species lists, or an incorrect
    "no Pokémon does this" when real qualifying species exist. This tool computes
    every species' actual combined multiplier server-side instead.

    Args:
        attacking_type: The attacking type, e.g. "fighting".
    """
    session = get_session(get_engine())
    try:
        result = retrieval.pokemon_by_type_matchup(session, attacking_type)
        if result is None:
            return f"Unknown type: {attacking_type}"

        buckets = result["buckets"]
        if not buckets:
            return (
                f"No Gen-1 Pokémon takes non-neutral damage from "
                f"{result['attacking_type'].title()}-type attacks."
            )

        labels = {
            4.0: "4x weak to",
            2.0: "2x weak to",
            0.5: "0.5x resistant to",
            0.25: "0.25x (double) resistant to",
            0.0: "immune (0x) to",
        }
        lines = [f"Gen-1 Pokémon by combined matchup against {result['attacking_type'].title()}-type attacks:"]
        for factor in (4.0, 2.0, 0.5, 0.25, 0.0):
            entries = buckets.get(factor, [])
            if not entries:
                continue
            lines.append(f"  {labels[factor]}:")
            for entry in entries:
                types_str = "/".join(t.title() for t in entry["types"])
                lines.append(f"    - {entry['name'].title()} ({types_str})")
        return "\n".join(lines)
    finally:
        session.close()


def get_pokemon_evolution_chain(pokemon_name: str) -> str:
    """Get a Pokémon's full evolution family: every stage and branch (in both
    directions), the total number of stages in the family, which stage this Pokémon
    itself is at, and the condition (level, evolution item, or trade) that triggers
    each step. Always call this for "how many evolution stages/forms does X have",
    "what does X evolve from/into", or "at what level/how does X evolve" questions
    instead of answering from memory -- this Pokédex only covers Generation 1, and some
    real-world evolution lines include a pre-evolution from a later generation (e.g.
    Pikachu's real-world line also has Pichu) that does not exist here, so general
    knowledge is not reliable.

    Args:
        pokemon_name: The Pokémon's name, e.g. "Pikachu".
    """
    session = get_session(get_engine())
    try:
        chain = retrieval.evolution_chain(session, pokemon_name)
        if chain is None:
            return f"No Pokémon named '{pokemon_name}' was found in the Pokédex records."

        summary = (
            f"{chain['species_name'].title()} is stage {chain['own_stage']} of "
            f"{chain['total_stages']} in its evolution family."
        )
        lines = [summary]
        conditions = chain["conditions_by_name"]
        for depth in sorted(chain["by_depth"]):
            for name in sorted(chain["by_depth"][depth]):
                condition = conditions.get(name)
                suffix = f" ({condition})" if condition else ""
                lines.append(f"  Stage {depth + 1}: {name.title()}{suffix}")
        return "\n".join(lines)
    finally:
        session.close()


def list_pokemon_by_type(pokemon_type: str, pure_only: bool = False) -> str:
    """List Pokémon that have a given type.

    Args:
        pokemon_type: The type to filter by, e.g. "water".
        pure_only: Set True only when the question specifically asks for "pure X-type"
            Pokémon (single-typed, no secondary type) -- e.g. "which Pokémon are pure
            Ghost-type". Omit/False for a plain "which Pokémon are type X" question,
            which should include dual-typed Pokémon too. Do not use get_type_weaknesses
            or any type-matchup tool for this kind of listing question -- those compute
            damage multipliers, not which Pokémon have a type.
    """
    session = get_session(get_engine())
    try:
        names = retrieval.list_pokemon_by_type(session, pokemon_type, pure_only)
        if not names:
            pure_note = " (pure/single-typed only)" if pure_only else ""
            return f"No Pokémon found of type '{pokemon_type}'{pure_note}."
        pure_label = "pure " if pure_only else ""
        return f"Pokémon of {pure_label}type '{pokemon_type}': " + ", ".join(n.title() for n in names)
    finally:
        session.close()


def list_pokemon_by_color(color: str) -> str:
    """List Pokémon that have a given primary color.

    Args:
        color: The color to filter by, e.g. "yellow", "green", "blue".
    """
    session = get_session(get_engine())
    try:
        names = retrieval.list_pokemon_by_color(session, color)
        if not names:
            return f"No Pokémon found with color '{color}'."
        return f"Pokémon with color '{color}': " + ", ".join(n.title() for n in names)
    finally:
        session.close()


def get_move_types(pokemon_name: str, version: str | None = None) -> str:
    """Get every distinct move type in a Pokémon's full Gen-1 movepool (level-up +
    machine moves combined, deduped to just the types). Use this -- not search_moves --
    to see the raw set of attacking types a Pokémon has access to: search_moves's move
    list is capped and can silently drop a type that only shows up in a move past the
    cutoff.

    For "which types/Pokémon resist <Pokémon>'s attacks" questions, do NOT use this tool
    plus manual per-type reasoning -- use list_pokemon_resisting_attacks instead, which
    computes the correct intersection for you server-side. Use get_move_types only when
    the question wants the attacking types themselves (e.g. "what types of attacks can X
    use"), not who resists them.

    Args:
        pokemon_name: The Pokémon's name, e.g. "Nidoran-M".
        version: Optional Gen-1 game filter: "red", "blue", or "yellow". Red/Blue and
            Yellow can genuinely differ (e.g. a Yellow-only TM move) -- pass this
            whenever the question names a specific game, and omit it only for a
            generic "in Gen-1" question that wants the union across all of them.
    """
    session = get_session(get_engine())
    try:
        try:
            types = retrieval.move_types_for_pokemon(session, pokemon_name, version)
        except ValueError as exc:
            return str(exc)
        if types is None:
            return f"No Pokémon named '{pokemon_name}' was found in the Pokédex records."
        if not types:
            return f"No known moves found for '{pokemon_name}'" + (
                f" in {version.title()}." if version else "."
            )
        scope = f" in {version.title()}" if version else ""
        return f"{pokemon_name.title()}'s movepool{scope} covers these types: " + ", ".join(
            t.title() for t in types
        )
    finally:
        session.close()


def list_pokemon_resisting_attacks(pokemon_name: str, version: str | None = None) -> str:
    """For "which Pokémon/types resist <Pokémon>'s attacks" questions (its whole
    movepool, not one named move or type): find every Gen-1 Pokémon species that
    resists or is immune to ALL of the given Pokémon's damaging move types at once,
    accounting for each candidate's own real dual-type defense (so a candidate whose
    second type reintroduces a weakness to one of those attack types is correctly
    excluded, not just checked type-by-type). This replaces manually chaining
    get_move_types + get_offensive_type_matchups and intersecting the results by hand --
    always prefer this tool for that question pattern, since it computes the
    intersection deterministically instead of relying on step-by-step reasoning.

    An empty result is a real, meaningful answer -- Gen-1 type coverage is broad enough
    that many movepools (especially ones spanning 4+ types) have no Pokémon that
    resists every single one simultaneously. Report that plainly rather than treating
    it as a failed lookup or falling back to listing Pokémon that only resist *some* of
    the attack types.

    If the question asks for types rather than named Pokémon, report the distinct set
    of types appearing among the returned Pokémon instead of listing every species.

    Args:
        pokemon_name: The attacking Pokémon's name, e.g. "Nidoran-M".
        version: Optional Gen-1 game filter: "red", "blue", or "yellow" -- scopes the
            movepool considered to just that game (Red/Blue and Yellow can genuinely
            differ). Pass this whenever the question names a specific game; omit it
            for a generic "in Gen-1" question.
    """
    session = get_session(get_engine())
    try:
        try:
            result = retrieval.pokemon_resisting_attacks(session, pokemon_name, version)
        except ValueError as exc:
            return str(exc)
        if result is None:
            return f"No Pokémon named '{pokemon_name}' was found in the Pokédex records."

        attacking_types = result["attacking_types"]
        scope = f" in {version.title()}" if version else ""
        if not attacking_types:
            return f"No known damaging moves found for '{pokemon_name}'{scope}."

        types_label = ", ".join(t.title() for t in attacking_types)
        header = f"{pokemon_name.title()}'s damaging movepool{scope} covers: {types_label}.\n"

        resisting = result["resisting"]
        if not resisting:
            return (
                header
                + "No Pokémon in the Gen-1 Pokédex resists or is immune to ALL of those "
                "attack types at once."
            )

        lines = [header + "Pokémon that resist or are immune to ALL of those attack types:"]
        for entry in resisting:
            types_str = "/".join(t.title() for t in entry["types"])
            factor_str = ", ".join(
                f"{t.title()} x{entry['factors'][t]:g}" for t in attacking_types
            )
            lines.append(f"  - {entry['name'].title()} ({types_str}): {factor_str}")
        return "\n".join(lines)
    finally:
        session.close()


_VERSION_GROUP_LABELS = {"red-blue": "Red/Blue only", "yellow": "Yellow only"}


def search_moves(
    pokemon_name: str,
    move_type: str | None = None,
    learn_method: str | None = None,
    version: str | None = None,
    move_name: str | None = None,
) -> str:
    """List moves a Pokémon can learn, optionally filtered by move type or learn method,
    including each move's own type. Capped to the most relevant matches (UNLESS
    move_name is given -- see below) -- for finding every attacking type a Pokémon has
    access to (e.g. "which types/Pokémon resist <Pokémon>'s attacks" questions), use
    get_move_types instead, which is never truncated.

    Red/Blue and Yellow can genuinely differ on which moves are learnable (e.g.
    Charizard can only learn Fly starting in Yellow -- a documented Red/Blue-era
    oversight) -- when the question names a specific game, pass version so the result
    is scoped correctly rather than guessed from an unscoped list. When version is
    omitted, any returned move that ISN'T learnable in every Gen-1 game is tagged
    "[Red/Blue only]" or "[Yellow only]" in its line -- do not claim a tagged move is
    learnable in a game the tag doesn't name.

    Args:
        pokemon_name: The Pokémon's name, e.g. "Charizard".
        move_type: Optional move type filter, e.g. "fire". Omit for all types.
        learn_method: Optional learn method filter: "level-up" or "machine" (the only
            two that existed in Generation 1 -- egg moves and move tutors didn't).
        version: Optional Gen-1 game filter: "red", "blue", or "yellow". Omit for the
            union across all of them (with per-move version tags as described above).
        move_name: Optional exact move name, e.g. "Submission" -- ALWAYS pass this for
            a "does <Pokémon> learn <move>" yes/no question instead of leaving it unset
            and scanning the general list by eye. A single named move can never need
            truncation, so this result is exempt from the cap that otherwise applies:
            omitting move_name and scanning a capped, possibly-truncated general list
            for one specific move by eye is exactly how a real answer gets missed (the
            move can be truncated off the page without any visible sign of it) or, worse,
            reported as absent/present incorrectly. Omit (leave as "any move", i.e. no
            filter) only when the question isn't about one specific named move.
    """
    session = get_session(get_engine())
    try:
        try:
            moves = retrieval.moves_for_pokemon(
                session, pokemon_name, move_type, learn_method, version, move_name
            )
        except ValueError as exc:
            return str(exc)
        if moves is None:
            return f"No Pokémon named '{pokemon_name}' was found in the Pokédex records."
        if not moves:
            # A real, grounded negative result (not a failed lookup) -- the species is
            # confirmed real, it just has no moves matching this filter combination
            # (e.g. version-scoped queries routinely produce this now).
            scope = f" in {version.title()}" if version else ""
            filters = ", ".join(
                f"{label}={value}"
                for label, value in (("move", move_name), ("type", move_type), ("method", learn_method))
                if value
            )
            filter_note = f" matching {filters}" if filters else ""
            return f"{pokemon_name.title()} has no known moves{filter_note}{scope}."
        lines = []
        for m in moves:
            tag = ""
            if not version and not m["all_versions"]:
                labels = {_VERSION_GROUP_LABELS[vg] for vg in m["versions"]}
                tag = f" [{', '.join(sorted(labels))}]"
            lines.append(
                f"- {m['name'].title()} ({m['type'].title()}-type, {m['damage_class']}, "
                f"power={m['power']}, accuracy={m['accuracy']}, via {m['learn_method']}"
                + (f" at level {m['level']}" if m["learn_method"] == "level-up" else "")
                + f"){tag}"
            )
        return "\n".join(lines)
    finally:
        session.close()




def get_pokemon_locations(
    pokemon_name: str, version: str | None = None, method: str | None = None
) -> str:
    """Find where a Pokémon can be encountered in the wild, with level range and
    encounter method per location. Only Gen-1 games are in scope (red/blue/yellow and
    their Japanese originals); omitting version searches all of them together.

    Args:
        pokemon_name: The Pokémon's name, e.g. "Pikachu".
        version: Optional Gen-1 game version filter, e.g. "red" or "yellow" (Yellow's
            early encounters differ from Red/Blue). Omit to search all Gen-1 games.
        method: Optional encounter method filter. Gen-1 values: "walk" (grass/cave),
            "surf", "fishing" (covers old-rod/good-rod/super-rod together), "static"
            (fixed encounters, e.g. legendaries), "gift", "npc-trade", "pokeflute".
            Always pass this when the question asks about a specific way of catching a
            Pokémon (e.g. "by fishing") rather than guessing which locations qualify.
    """
    session = get_session(get_engine())
    try:
        locations = retrieval.locations_for_pokemon(session, pokemon_name, version, method)
        if not locations:
            return f"No known wild locations found for '{pokemon_name}'."
        lines = [
            f"- {loc['location'].replace('-', ' ').title()} ({loc['version']}, "
            f"via {loc['method']}, level {loc['min_level']}-{loc['max_level']})"
            for loc in locations
        ]
        return "\n".join(lines)
    finally:
        session.close()


def get_location_info(
    location_name: str, version: str | None = None, method: str | None = None
) -> str:
    """Find which Pokémon can be encountered at a named place (e.g. "Seafoam Islands",
    "Route 1"), aggregating every sub-area/floor that matches the name, with level
    range and encounter method. Only Gen-1 games are in scope (red/blue/yellow and
    their Japanese originals); omitting version searches all of them together. Use
    this for "what is <place>" or "what Pokémon are at <place>" questions -- there is
    no route-map, region, or "how to reach it" data available, only which Pokémon can
    be found there, so say so plainly if asked for more.

    Args:
        location_name: The place's name, e.g. "Seafoam Islands" or "Route 1".
        version: Optional Gen-1 game version filter, e.g. "red" or "yellow". Omit to
            search all Gen-1 games.
        method: Optional encounter method filter. Gen-1 values: "walk" (grass/cave),
            "surf", "fishing" (covers old-rod/good-rod/super-rod together), "static"
            (fixed encounters, e.g. legendaries), "gift", "npc-trade", "pokeflute".
            Always pass this when the question asks about a specific way of catching a
            Pokémon (e.g. "by fishing") rather than guessing which results qualify.
    """
    session = get_session(get_engine())
    try:
        results = retrieval.pokemon_at_location(session, location_name, version, method)
        if results is None:
            return f"No location matching '{location_name}' was found in the Pokédex records."
        if not results:
            return f"No known Pokémon encounters found at '{location_name}'."

        scope_label = version.strip() if version else "the Gen-1 games"
        lines = []
        current_location = None
        for row in results:
            if row["location"] != current_location:
                current_location = row["location"]
                lines.append(f"{current_location.replace('-', ' ').title()} ({scope_label}):")
            lines.append(
                f"  - {row['species'].title()} (via {row['method']}, "
                f"level {row['min_level']}-{row['max_level']})"
            )
        return "\n".join(lines)
    finally:
        session.close()


def build_team(
    anchor_name: str,
    fixed_members: list[str] | None = None,
    role_overrides: list[str] | None = None,
) -> str:
    """Assembles a complete, verified 6-Pokémon Gen-1 team around anchor_name. This is
    the ONLY entry point for a team-building request -- it runs a deterministic
    pipeline internally (real liability discovery, candidate search, tie-breaking,
    and a final overlap/coverage audit), so call this once and relay its result rather
    than trying to reconstruct the process yourself from the type/matchup/usage tools.

    Args:
        anchor_name: The Pokémon to build the team around, e.g. "Dragonite".
        fixed_members: Optional Pokémon the user has already explicitly named as part
            of the team (besides the anchor) -- these are locked in as-is, consuming
            their own roster slots before the rest is filled automatically.
        role_overrides: Optional role names applied to the LAST slots of the roster,
            in order. Defaults to ["special_sponge", "cleaner"] when omitted -- every
            team gets a dedicated special sponge and cleaner in its last two slots
            unless the user asks otherwise. Pass a different list (e.g. just
            ["special_sponge"], or roles in a different order) if the user asks for
            different specific roles, or an explicit empty list [] if the user asks
            for a fully-automatic build with no fixed roles at all. Only
            "special_sponge" (ranked by HP*Special) and "cleaner" (ranked by bulk,
            then Speed, then offense) are recognized.
    """
    session = get_session(get_engine())
    try:
        fixed_members = _coerce_list(fixed_members) if fixed_members is not None else None
        role_overrides = _coerce_list(role_overrides) if role_overrides is not None else None
        if role_overrides:
            unknown = [r for r in role_overrides if r not in team_agent.ROLE_SCORERS]
            if unknown:
                known = ", ".join(sorted(team_agent.ROLE_SCORERS))
                return f"Unrecognized role(s) {unknown} -- only these are supported: {known}."
        return team_agent.build_team(session, anchor_name, fixed_members, role_overrides)
    finally:
        session.close()


TOOLS = [
    get_pokemon_info,
    get_move_info,
    list_moves_by_type,
    get_gen1_battle_engine_bugs,
    get_type_effectiveness,
    get_type_matchups,
    get_type_weaknesses,
    get_offensive_type_matchups,
    list_pokemon_by_type_matchup,
    get_pokemon_evolution_chain,
    list_pokemon_by_type,
    list_pokemon_by_color,
    search_moves,
    get_move_types,
    list_pokemon_learning_move,
    list_pokemon_resisting_attacks,
    get_pokemon_locations,
    get_location_info,
    build_team,
]

# Tools whose success does NOT prove the question's subject is real, so a successful
# call must not be treated as grounding. A denylist rather than an allowlist: every
# other tool either resolves a caller-supplied Pokémon name against the DB, or is a
# pure category filter/listing with no free-form "subject" argument to fabricate --
# both are real DB data, so they should ground by default. get_type_effectiveness is
# the exception: it takes two bare type strings framed as "attacker vs defender," which
# is exactly what let the model pass a made-up stand-in type for a nonexistent subject
# and still get a "successful" result (the original "Bo Jackson" incident: treating it
# as a fictional Normal-type stand-in). get_type_weaknesses and
# get_offensive_type_matchups are deliberately NOT included here even though they also
# take bare type strings: unlike get_type_effectiveness, they exist specifically to
# answer hypothetical/generic type questions with no creature named at all ("a pure
# Ghost-type Pokémon"), so denylisting them would make that entire question category
# permanently unanswerable -- a certain regression versus a residual, not-yet-observed
# misuse risk that's already mitigated by their docstrings and system prompt rule 4.
NON_GROUNDING_TOOLS = {
    "get_type_effectiveness",
}

# Prefixes tool functions above use for their "nothing found" results, so callers
# (the tool-calling loop) can tell a real lookup from an empty one without re-parsing.
# Deliberately does NOT include "<Pokémon> has no known moves..." (search_moves) or
# "No known moves found for '<Pokémon>' in <version>" (get_move_types) -- those are a
# real, grounded negative result for a CONFIRMED species (its filtered/version-scoped
# movepool is genuinely empty), not a failed lookup; treating them as failures would
# force the "insufficient information" fallback over a correct, informative answer
# (e.g. "Charizard learns no Flying-type moves in Red") every time a version- or
# type-scoped move search legitimately comes back empty, which version scoping now
# makes routine.
FAILURE_PREFIXES = (
    "No Pokémon named",
    "No move named",
    "Unknown type:",
    "Unknown version:",
    "No Pokémon found of type",
    "No Pokémon found with color",
    "No known wild locations found",
    "No location matching",
    "No known Pokémon encounters found at",
)


def is_failure(result: str) -> bool:
    return result.startswith(FAILURE_PREFIXES)
