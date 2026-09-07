import difflib
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from profesor_oak_ai.db.models import (
    Color,
    GameVersion,
    Item,
    Location,
    Move,
    PokedexEntry,
    PokemonColorAssociation,
    PokemonForm,
    PokemonLocationEncounter,
    PokemonMove,
    PokemonSpecies,
    PokemonType,
    PokemonTypeAssociation,
    SpeciesEvolution,
    TypeEfficacy,
)

MAX_MOVES_RETURNED = 20
MAX_POKEMON_LISTED = 35
MAX_LOCATIONS_RETURNED = 30
MAX_LOCATIONS_MATCHED = 10
MAX_SPECIES_PER_LOCATION = 30

NO_MATCH_MESSAGE = (
    "No specific Pokémon or type name was recognized in the question. "
    "Use the available tools to look up whatever is needed."
)


def find_species_by_name(session: Session, name: str) -> PokemonSpecies | None:
    name_lower = name.strip().lower()

    species = session.scalar(
        select(PokemonSpecies).where(func.lower(PokemonSpecies.name) == name_lower)
    )
    if species is not None:
        return species

    all_names = session.scalars(select(PokemonSpecies.name)).all()
    # cutoff=0.86: loose enough for real typos ("bulbasuar" -> 0.889), tight enough to
    # not conflate distinct species with similar names ("pichu" vs "pikachu" -> 0.833).
    close = difflib.get_close_matches(name_lower, [n.lower() for n in all_names], n=1, cutoff=0.86)
    if not close:
        return None
    return session.scalar(select(PokemonSpecies).where(func.lower(PokemonSpecies.name) == close[0]))


def find_move_by_name(session: Session, name: str) -> Move | None:
    # Move names are stored PokeAPI-style ("seismic-toss"), but a question will almost
    # always spell them with spaces ("Seismic Toss") -- normalize spaces to hyphens
    # before the exact-match attempt so the common case doesn't fall through to the
    # (slower, and space-vs-hyphen-blind) fuzzy match below.
    name_key = name.strip().lower().replace(" ", "-")

    move = session.scalar(select(Move).where(func.lower(Move.name) == name_key))
    if move is not None:
        return move

    all_names = session.scalars(select(Move.name)).all()
    close = difflib.get_close_matches(name_key, [n.lower() for n in all_names], n=1, cutoff=0.86)
    if not close:
        return None
    return session.scalar(select(Move).where(func.lower(Move.name) == close[0]))


# Generation 1's battle engine has a well-documented, narrow bug: a handful of moves
# skip the type-IMMUNITY check entirely (not just the damage-scaling step), so they
# hit a target their type should have zero effect on. This is NOT a property of the
# move's type in general -- an ordinary Fighting move (Karate Chop, Submission, ...)
# is still fully blocked by Ghost's immunity in Gen 1, only these specific named moves
# aren't. Fixed starting in Generation II. Sourced from Bulbapedia's Ghost-type page
# ("In Generation I only, Ghost-type Pokémon ... are affected by Bide, Counter,
# Seismic Toss, SonicBoom, and Super Fang, despite these moves being Normal- and
# Fighting-type, which the Ghost type is normally immune to") and corroborated by
# Smogon's Gen-1 mechanics guide for Seismic Toss/Night Shade/Counter/Bide.
GEN1_IMMUNITY_BYPASS_NOTE = {
    "seismic-toss": "Ghost-types are normally immune to Fighting moves, but this is a "
    "documented Generation I engine bug: Seismic Toss ignores that immunity and hits "
    "Ghost-types (e.g. Gengar) anyway. Fixed starting in Generation II.",
    "counter": "Ghost-types are normally immune to Fighting moves, but this is a "
    "documented Generation I engine bug: Counter ignores that immunity and hits "
    "Ghost-types (e.g. Gengar) anyway. Fixed starting in Generation II.",
    "bide": "Ghost-types are normally immune to Normal moves, but this is a documented "
    "Generation I engine bug: Bide ignores that immunity and hits Ghost-types (e.g. "
    "Gengar) anyway. Fixed starting in Generation II.",
    "sonic-boom": "Ghost-types are normally immune to Normal moves, but this is a "
    "documented Generation I engine bug: SonicBoom ignores that immunity and hits "
    "Ghost-types (e.g. Gengar) anyway. Fixed starting in Generation II.",
    "super-fang": "Ghost-types are normally immune to Normal moves, but this is a "
    "documented Generation I engine bug: Super Fang ignores that immunity and hits "
    "Ghost-types (e.g. Gengar) anyway. Fixed starting in Generation II.",
    "night-shade": "Normal-types are normally immune to Ghost moves, but this is a "
    "documented Generation I engine bug: Night Shade ignores that immunity and hits "
    "Normal-types anyway. Fixed starting in Generation II.",
}


def move_info(session: Session, move_name: str) -> dict | None:
    """A move's own metadata by name (not scoped to any one Pokémon's learnset) --
    its type, damage class, power/accuracy/pp, effect text, and (for the handful of
    Gen-1 moves affected) a note about the Generation I Ghost-type-immunity-bypass
    engine bug -- see GEN1_IMMUNITY_BYPASS_NOTE above; do NOT assume type immunity
    holds against every "fixed damage" move in Gen 1 just because it holds against a
    move's type in general, this specific short list is the confirmed exception.
    Returns None if no move matches."""
    move = find_move_by_name(session, move_name)
    if move is None:
        return None
    type_name = session.scalar(select(PokemonType.name).where(PokemonType.type_id == move.type_id))
    return {
        "name": move.name,
        "type": type_name,
        "damage_class": move.damage_class,
        "gen1_immunity_bypass_note": GEN1_IMMUNITY_BYPASS_NOTE.get(move.name),
        "power": move.power,
        "accuracy": move.accuracy,
        "pp": move.pp,
        "priority": move.priority,
        "effect_chance": move.effect_chance,
        "effect_description": move.effect_description,
    }


def moves_by_type(session: Session, move_type: str) -> list[dict] | None:
    """Every Gen-1 move of a given type, with each move's own damage class, power,
    accuracy, PP, and effect text -- for "which <type>-type move does X" questions
    (e.g. "which Fighting-type move hits multiple times in one turn") where the
    question describes a MOVE by a property, not by name. Without this, the only way
    to search moves by type is to already know a Pokémon that learns one (via
    moves_for_pokemon/search_moves) or to already know the move's name (via
    move_info) -- neither works when the move itself is what's being searched for,
    which forces guessing a name (or an unrelated Pokémon to fish through) from
    memory instead of actually looking. A move's type/power/etc. don't vary by Gen-1
    game version (only which Pokémon can LEARN a given move does), so this isn't
    version-scoped. Returns None if move_type isn't recognized; returns [] if the
    type is real but no move of it exists in this Gen-1 dataset (a real, meaningful
    answer, not a failure)."""
    move_type_row = session.scalar(
        select(PokemonType).where(func.lower(PokemonType.name) == move_type.strip().lower())
    )
    if move_type_row is None:
        return None

    moves = session.scalars(
        select(Move).where(Move.type_id == move_type_row.type_id).order_by(Move.name)
    ).all()
    return [
        {
            "name": m.name,
            "damage_class": m.damage_class,
            "power": m.power,
            "accuracy": m.accuracy,
            "pp": m.pp,
            "effect_description": m.effect_description,
        }
        for m in moves
    ]


def pokemon_learning_move(
    session: Session,
    move_name: str,
    learn_method: str | None = None,
    version: str | None = None,
    pokemon_type: str | None = None,
) -> dict | None:
    """The reverse of moves_for_pokemon: every Gen-1 species (default form) that can
    learn a given move, with its own type(s), learn method, and level -- for "which
    Pokémon learn move X" questions, where the caller doesn't already know a species
    name to look up. Without this, a question like "which dual-typed Pokémon learns
    Double Kick" has no way to be answered except guessing a single candidate species
    from memory and checking it in isolation -- which can both name a species that
    doesn't actually learn the move, AND miss that the real learners don't satisfy an
    extra constraint (like being dual-typed) at all, since only one guess was ever
    checked instead of the whole learner set.

    Returns None if the move itself isn't found. version optionally scopes to just
    "red"/"blue"/"yellow" (Red/Blue and Yellow can genuinely differ on who learns a
    move, or at what level) -- omit for every Gen-1 game combined. pokemon_type
    optionally restricts learners to species that have that type (in either slot) --
    pass this whenever the question already names a type constraint (e.g. "which
    Fighting-type Pokémon learn Rest") instead of fetching every learner and manually
    cross-referencing against a separate type list; for a widely-learnable move like
    a TM move, the unfiltered learner list can run to 100+ species, and manually
    checking a handful of names against it by eye is unnecessary work and an
    unnecessary chance to miscount, the same failure class server-side filtering has
    already fixed elsewhere in this toolset. An empty "learners" list is a real,
    meaningful answer (no Gen-1 Pokémon -- or none matching the given filters --
    learns this move), not a failure. Raises ValueError for an unrecognized version
    string.
    """
    move = find_move_by_name(session, move_name)
    if move is None:
        return None

    query = (
        select(
            PokemonSpecies.name,
            PokemonType.name.label("type_name"),
            PokemonMove.learn_method,
            PokemonMove.level_learned_at,
            PokemonMove.version_group,
        )
        .join(PokemonForm, PokemonForm.form_id == PokemonMove.form_id)
        .join(PokemonSpecies, PokemonSpecies.species_id == PokemonForm.species_id)
        .join(PokemonTypeAssociation, PokemonTypeAssociation.form_id == PokemonForm.form_id)
        .join(PokemonType, PokemonType.type_id == PokemonTypeAssociation.type_id)
        .where(PokemonMove.move_id == move.move_id, PokemonForm.is_default)
        .order_by(PokemonSpecies.species_id, PokemonTypeAssociation.slot)
    )
    if learn_method:
        query = query.where(PokemonMove.learn_method == learn_method.strip().lower())
    if version:
        query = query.where(PokemonMove.version_group == resolve_move_version_group(version))
    if pokemon_type:
        # Filters which SPECIES are included (has this type in any slot), not which
        # per-type-slot rows come back -- a separate EXISTS-style subquery rather than
        # a direct .where() on the same type join above, so a dual-typed match still
        # shows both of its own types in the result instead of only the matching one.
        matching_forms = (
            select(PokemonTypeAssociation.form_id)
            .join(PokemonType, PokemonType.type_id == PokemonTypeAssociation.type_id)
            .where(func.lower(PokemonType.name) == pokemon_type.strip().lower())
        )
        query = query.where(PokemonMove.form_id.in_(matching_forms))

    rows = session.execute(query).all()

    # One row per (species, type slot, version_group) -- collapse into one entry per
    # (species, learn_method), listing every type and keeping the earliest level
    # across duplicate version_group rows, the same way moves_for_pokemon does. Keying
    # on (species, learn_method) rather than species alone matters when a species
    # learns the same move by more than one method (e.g. level-up at a real level AND
    # machine, which is stored with level 0) -- collapsing those together would
    # otherwise blend an unrelated machine "level" 0 into a real level-up level via a
    # naive min() comparison.
    learners: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row.name, row.learn_method)
        entry = learners.setdefault(
            key,
            {"name": row.name, "types": [], "learn_method": row.learn_method, "level": row.level_learned_at},
        )
        if row.type_name not in entry["types"]:
            entry["types"].append(row.type_name)
        entry["level"] = min(entry["level"], row.level_learned_at)

    return {"move_name": move.name, "learners": list(learners.values())}


def get_default_form(session: Session, species: PokemonSpecies) -> PokemonForm | None:
    return session.scalar(
        select(PokemonForm).where(
            PokemonForm.species_id == species.species_id, PokemonForm.is_default
        )
    )


def get_representative_entry(session: Session, species_id: int) -> PokedexEntry | None:
    return session.scalar(
        select(PokedexEntry)
        .where(PokedexEntry.species_id == species_id, PokedexEntry.language == "en")
        .order_by(PokedexEntry.version_id.desc())
    )


def get_color_name(session: Session, species_id: int) -> str | None:
    return session.scalar(
        select(Color.name)
        .join(PokemonColorAssociation, PokemonColorAssociation.color_id == Color.color_id)
        .where(PokemonColorAssociation.species_id == species_id)
    )


def describe_pokemon(session: Session, species: PokemonSpecies) -> str:
    form = get_default_form(session, species)
    if form is None:
        return f"No data available for {species.name}."

    types = session.scalars(
        select(PokemonType.name)
        .join(PokemonTypeAssociation, PokemonTypeAssociation.type_id == PokemonType.type_id)
        .where(PokemonTypeAssociation.form_id == form.form_id)
        .order_by(PokemonTypeAssociation.slot)
    ).all()

    entry = get_representative_entry(session, species.species_id)
    color_name = get_color_name(session, species.species_id)

    evolves_from_name = None
    if species.evolves_from_species_id:
        parent = session.get(PokemonSpecies, species.evolves_from_species_id)
        evolves_from_name = parent.name.title() if parent else None

    lines = [
        f"Name: {species.name.title()} (#{species.species_id}, Generation {species.generation})",
        f"Types: {', '.join(t.title() for t in types)}",
        f"Stats: HP {form.hp}, Attack {form.attack}, Defense {form.defense}, "
        f"Special {form.special}, Speed {form.speed} "
        f"(Total {form.base_stat_total})",
    ]
    if species.is_legendary:
        lines.append("This is a Legendary Pokémon.")
    if species.is_mythical:
        lines.append("This is a Mythical Pokémon.")
    if evolves_from_name:
        lines.append(f"Evolves from: {evolves_from_name}")
    if color_name:
        lines.append(f"Primary color: {color_name}")
    if entry is not None:
        lines.append(f"Pokédex entry: {entry.entry}")

    return "\n".join(lines)


def type_effectiveness(session: Session, attacking_type: str, defending_types: list[str]) -> float:
    attacker = session.scalar(
        select(PokemonType).where(func.lower(PokemonType.name) == attacking_type.strip().lower())
    )
    if attacker is None:
        raise ValueError(f"Unknown type: {attacking_type}")

    factor = 1.0
    for defending_type in defending_types:
        defender = session.scalar(
            select(PokemonType).where(func.lower(PokemonType.name) == defending_type.strip().lower())
        )
        if defender is None:
            raise ValueError(f"Unknown type: {defending_type}")
        row = session.get(TypeEfficacy, (attacker.type_id, defender.type_id))
        factor *= row.damage_factor if row is not None else 1.0

    return factor


def _combined_defensive_factors(session: Session, defending_type_ids: list[int]) -> dict[str, float]:
    """Every attacking type's damage multiplier against a set of defending type ids,
    multiplied together when there's more than one (dual-typed defense)."""
    rows = session.execute(
        select(PokemonType.name, TypeEfficacy.damage_factor)
        .join(TypeEfficacy, TypeEfficacy.damage_type_id == PokemonType.type_id)
        .where(TypeEfficacy.target_type_id.in_(defending_type_ids))
    ).all()
    factors: dict[str, float] = {}
    for attacking_type, damage_factor in rows:
        factors[attacking_type] = factors.get(attacking_type, 1.0) * damage_factor
    return factors


def defensive_type_matchups(session: Session, pokemon_name: str) -> dict | None:
    """For a named Pokémon's defending type(s), returns every attacking type's
    combined damage multiplier (accounting for both types on a dual-typed Pokémon).
    For a hypothetical/generic type combo with no real Pokémon involved (e.g. "a pure
    Ghost-type" or "a Water/Flying-type"), use type_matchups_for_types instead --
    that doesn't require resolving an actual species."""
    species = find_species_by_name(session, pokemon_name)
    if species is None:
        return None
    form = get_default_form(session, species)
    if form is None:
        return None

    type_rows = session.execute(
        select(PokemonType.type_id, PokemonType.name)
        .join(PokemonTypeAssociation, PokemonTypeAssociation.type_id == PokemonType.type_id)
        .where(PokemonTypeAssociation.form_id == form.form_id)
        .order_by(PokemonTypeAssociation.slot)
    ).all()

    type_ids = [r.type_id for r in type_rows]
    names = [r.name for r in type_rows]
    return {"types": names, "factors": _combined_defensive_factors(session, type_ids)}


def type_matchups_for_types(session: Session, defending_types: list[str]) -> dict | None:
    """Same computation as defensive_type_matchups (every attacking type's combined
    damage multiplier against one or two defending types), but for a raw type combo
    instead of a named Pokémon -- for hypothetical "a pure X-type" or "an X/Y-type"
    questions that don't name a real species. Returns None if any type isn't
    recognized."""
    type_ids = []
    names = []
    for defending_type in defending_types:
        row = session.scalar(
            select(PokemonType).where(func.lower(PokemonType.name) == defending_type.strip().lower())
        )
        if row is None:
            return None
        type_ids.append(row.type_id)
        names.append(row.name)

    return {"types": names, "factors": _combined_defensive_factors(session, type_ids)}


def offensive_type_matchups(session: Session, attacking_type: str) -> dict | None:
    """For a single attacking type, the damage multiplier of its attacks against every
    defending type -- the inverse of defensive_type_matchups, which fixes the defender
    and varies the attacker; this fixes the attacker and varies the defender. Returns
    None if the type name isn't recognized."""
    attacker = session.scalar(
        select(PokemonType).where(func.lower(PokemonType.name) == attacking_type.strip().lower())
    )
    if attacker is None:
        return None

    rows = session.execute(
        select(PokemonType.name, TypeEfficacy.damage_factor)
        .join(TypeEfficacy, TypeEfficacy.target_type_id == PokemonType.type_id)
        .where(TypeEfficacy.damage_type_id == attacker.type_id)
    ).all()

    return {"attacking_type": attacker.name, "factors": {name: factor for name, factor in rows}}


def evolution_chain(session: Session, pokemon_name: str) -> dict | None:
    """Returns the named Pokémon's full evolution family: every stage/branch reachable
    from the family's root ancestor (grouped by depth, so a branching family like
    Eevee's is represented correctly), the total number of stages in the family, and
    which stage the named Pokémon itself is at. Returns None if the name isn't found.
    Walking evolves_from_species_id both up (to find the root) and down (to find every
    descendant) is required because describe_pokemon() only ever reports the backward
    link ("Evolves from") -- there is no other way to learn a Pokémon's forward
    evolutions or total stage count."""
    species = find_species_by_name(session, pokemon_name)
    if species is None:
        return None

    rows = session.execute(
        select(PokemonSpecies.species_id, PokemonSpecies.name, PokemonSpecies.evolves_from_species_id)
    ).all()
    parent = {sid: parent_id for sid, _, parent_id in rows}
    name_by_id = {sid: name for sid, name, _ in rows}
    children: dict[int, list[int]] = {}
    for sid, parent_id in parent.items():
        if parent_id is not None:
            children.setdefault(parent_id, []).append(sid)

    def root_of(sid: int) -> int:
        seen = set()
        while parent.get(sid) is not None:
            if sid in seen:  # defensive: FK has no acyclic guarantee
                break
            seen.add(sid)
            sid = parent[sid]
        return sid

    root_id = root_of(species.species_id)

    depth_by_id = {root_id: 0}
    queue = [root_id]
    while queue:
        current = queue.pop(0)
        for child_id in children.get(current, []):
            depth_by_id[child_id] = depth_by_id[current] + 1
            queue.append(child_id)

    by_depth: dict[int, list[str]] = {}
    for sid, depth in depth_by_id.items():
        by_depth.setdefault(depth, []).append(name_by_id[sid])

    # Gen-1 has exactly one evolution condition row per evolved species (verified: no
    # species in this dataset has more than one -- there's no version-group or
    # branching-method duplication to worry about here), so a plain dict keyed by the
    # evolved species' own id is safe and doesn't need to disambiguate multiple rows.
    family_ids = list(depth_by_id.keys())
    condition_rows = session.execute(
        select(SpeciesEvolution, Item.name)
        .select_from(SpeciesEvolution)
        .outerjoin(Item, Item.item_id == SpeciesEvolution.item_id)
        .where(SpeciesEvolution.species_id.in_(family_ids))
    ).all()

    # Phrased as "evolves FROM <parent> <condition>", not just "<condition>", so the
    # condition unambiguously reads as the trigger for entering this stage (from the
    # previous one) rather than as this stage's own trigger for evolving further --
    # the two are easy to conflate (e.g. Machoke's line would otherwise misread as
    # Machoke itself requiring a level to evolve into Machamp, when that level-28
    # condition is actually Machop's trigger for becoming Machoke, and Machoke->Machamp
    # is a level-free trade).
    conditions_by_name: dict[str, str] = {}
    for evolution, item_name in condition_rows:
        evolved_name = name_by_id[evolution.species_id]
        parent_id = parent.get(evolution.species_id)
        parent_name = name_by_id[parent_id].title() if parent_id is not None else None
        from_clause = f"from {parent_name} " if parent_name else ""
        if evolution.trigger_type == "level-up" and evolution.min_level is not None:
            conditions_by_name[evolved_name] = f"evolves {from_clause}at level {evolution.min_level}"
        elif evolution.trigger_type == "use-item" and item_name is not None:
            conditions_by_name[evolved_name] = (
                f"evolves {from_clause}using a {item_name.replace('-', ' ').title()}"
            )
        elif evolution.trigger_type == "trade":
            conditions_by_name[evolved_name] = f"evolves {from_clause}by trading"
        else:
            conditions_by_name[evolved_name] = f"evolves {from_clause}via {evolution.trigger_type}"

    return {
        "species_name": species.name,
        "own_stage": depth_by_id[species.species_id] + 1,
        "total_stages": max(depth_by_id.values()) + 1,
        "by_depth": by_depth,
        "conditions_by_name": conditions_by_name,
    }


LEARN_METHOD_PRIORITY = {"level-up": 0, "egg": 1, "tutor": 2, "machine": 3}

# PokeAPI scopes move learnsets by version_group, not by individual game -- Red and
# Blue are always identical for move data (unlike location encounters, which do have
# real Red-vs-Blue exclusives), so both map to the same "red-blue" group; Yellow is
# its own group. A handful of Gen-1 moves genuinely differ between them (e.g.
# Charizard's Fly is Yellow-only, a documented post-Red/Blue fix).
VERSION_TO_MOVE_VERSION_GROUP = {"red": "red-blue", "blue": "red-blue", "yellow": "yellow"}
ALL_MOVE_VERSION_GROUPS = frozenset(VERSION_TO_MOVE_VERSION_GROUP.values())


def resolve_move_version_group(version: str) -> str:
    """Raises ValueError for a version string that isn't "red"/"blue"/"yellow" --
    e.g. a caller passing "red and blue" or "redblue" as one combined value, which a
    question phrased as "in Pokémon Red and Blue" can tempt. Deliberately an error
    (mirroring type_effectiveness's ValueError for an unrecognized type), not a
    silent empty-result return like earlier versions of this scoping logic used:
    silently treating an unrecognized version as "matches nothing" produced a real
    observed false negative (a genuine Fighting-type Rest-learner incorrectly
    reported as nonexistent) instead of surfacing the malformed input so it can be
    corrected."""
    version_group = VERSION_TO_MOVE_VERSION_GROUP.get(version.strip().lower())
    if version_group is None:
        raise ValueError(
            f"Unknown version: '{version}' (expected one of 'red', 'blue', 'yellow' -- "
            "pass a single game, not a combined value like 'red and blue')"
        )
    return version_group


def moves_for_pokemon(
    session: Session,
    species_name: str,
    move_type: str | None = None,
    learn_method: str | None = None,
    version: str | None = None,
    move_name: str | None = None,
) -> list[dict] | None:
    """Returns None if the species itself isn't found (an ungrounded lookup -- the
    subject was never confirmed real), or [] if the species is real but nothing
    matches the given filters (a real, grounded negative result, e.g. "Charizard
    learns no Flying-type moves in Red" -- not a failure). Callers must keep that
    distinction instead of treating both as the same "nothing found" case: a filtered
    query legitimately returning empty for a real, confirmed Pokémon (as version
    scoping now makes routine) is a meaningful answer, not evidence the lookup failed.

    move_name filters to one exact move (fuzzy-matched via find_move_by_name, same as
    get_move_info) -- when given, the result is exempt from MAX_MOVES_RETURNED
    truncation, since a single named move can never produce more than a handful of
    rows (one per learn method/version). This matters: without it, a "does <Pokémon>
    learn <move>" question answered via the unfiltered/type-filtered list can silently
    truncate before reaching the asked-about move (e.g. it starts with a late-alphabet
    letter), and a caller who doesn't notice the cut-off can wrongly conclude -- or
    even confidently claim -- the move doesn't appear when it was simply never in the
    truncated page.

    Raises ValueError for an unrecognized version string.
    """
    species = find_species_by_name(session, species_name)
    if species is None:
        return None
    form = get_default_form(session, species)
    if form is None:
        return []

    query = (
        select(
            Move.name,
            Move.damage_class,
            Move.power,
            Move.accuracy,
            PokemonMove.learn_method,
            PokemonMove.level_learned_at,
            PokemonMove.version_group,
            PokemonType.name.label("type_name"),
        )
        .join(PokemonMove, PokemonMove.move_id == Move.move_id)
        .join(PokemonType, PokemonType.type_id == Move.type_id)
        .where(PokemonMove.form_id == form.form_id)
    )
    if move_name:
        move = find_move_by_name(session, move_name)
        if move is None:
            return []
        query = query.where(Move.move_id == move.move_id)
    if move_type:
        query = query.where(func.lower(PokemonType.name) == move_type.strip().lower())
    if learn_method:
        query = query.where(PokemonMove.learn_method == learn_method.strip().lower())
    if version:
        query = query.where(PokemonMove.version_group == resolve_move_version_group(version))

    rows = session.execute(query).all()

    # The same (move, learn_method) can have separate rows per version_group (usually
    # at the same level -- Red/Blue and Yellow rarely disagree on the level itself,
    # only on whether the move is learnable at all) -- keep the earliest level per
    # (name, learn_method), NOT per name alone (a level-less machine/egg/tutor entry
    # would otherwise silently suppress a level-up entry), while separately tracking
    # every version_group that entry actually appeared in so callers can tell a
    # Red/Blue-and-Yellow move from a Yellow-only (or Red/Blue-only) one.
    best: dict[tuple[str, str], dict] = {}
    versions_by_key: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        key = (row.name, row.learn_method)
        versions_by_key.setdefault(key, set()).add(row.version_group)
        if key not in best or row.level_learned_at < best[key]["level"]:
            best[key] = {
                "name": row.name,
                "type": row.type_name,
                "damage_class": row.damage_class,
                "power": row.power,
                "accuracy": row.accuracy,
                "learn_method": row.learn_method,
                "level": row.level_learned_at,
            }
    for key, entry in best.items():
        entry["versions"] = sorted(versions_by_key[key])
        entry["all_versions"] = versions_by_key[key] == ALL_MOVE_VERSION_GROUPS

    # Level-up moves first (in level order), then egg/tutor/machine -- otherwise,
    # when no learn_method filter is given, TM/egg/tutor entries (level_learned_at=0)
    # would sort before every level-up move and crowd the capped result out entirely.
    results = sorted(
        best.values(),
        key=lambda m: (LEARN_METHOD_PRIORITY.get(m["learn_method"], 99), m["level"], m["name"]),
    )
    if move_name:
        return results
    return results[:MAX_MOVES_RETURNED]


def move_types_for_pokemon(
    session: Session, species_name: str, version: str | None = None
) -> list[str] | None:
    """Every distinct type of DAMAGING move (physical/special, i.e. actual attacks --
    status moves like Rest or Reflect deal no damage and are excluded) in a Pokémon's
    full Gen-1 movepool (level-up + machine combined). Unlike moves_for_pokemon, this is
    never truncated by MAX_MOVES_RETURNED -- a movepool with more moves than that cap
    would otherwise silently lose whichever types only show up in the moves past the
    cutoff (e.g. a Pokémon's only Electric or Ice move landing at position 21+).
    version optionally scopes this to just "red"/"blue"/"yellow" (Red/Blue and Yellow
    can genuinely differ, e.g. a Yellow-only TM move) -- omit for the union across all
    Gen-1 versions. Raises ValueError for an unrecognized version string. Returns None
    if the species isn't found; returns [] if the species is real but has no matching
    moves."""
    species = find_species_by_name(session, species_name)
    if species is None:
        return None
    form = get_default_form(session, species)
    if form is None:
        return []

    query = (
        select(PokemonType.name)
        .distinct()
        .join(Move, Move.type_id == PokemonType.type_id)
        .join(PokemonMove, PokemonMove.move_id == Move.move_id)
        .where(PokemonMove.form_id == form.form_id, Move.damage_class != "status")
    )
    if version:
        query = query.where(PokemonMove.version_group == resolve_move_version_group(version))
    return sorted(session.execute(query).scalars().all())


def pokemon_resisting_attacks(
    session: Session, species_name: str, version: str | None = None
) -> dict | None:
    """Every Gen-1 Pokémon species that resists or is immune to EVERY damaging move type
    in the given Pokémon's movepool (see move_types_for_pokemon) -- i.e. a real dual-typed
    species' full defensive profile, not a single type in isolation, so a species whose
    second type reintroduces a weakness (e.g. Ground resists Electric, but a Rock/Ground
    Pokémon is still weak to the Fighting moves in the same movepool) is correctly
    excluded. Computed directly in Python/SQL rather than left to the caller to intersect
    several get_offensive_type_matchups calls by hand, since that step-by-step
    union/intersection arithmetic is exactly what an LLM tends to get wrong (reporting
    "resists at least one" instead of "resists all", or mixing up which type resisted
    which). version optionally scopes the movepool to just "red"/"blue"/"yellow" (Red/Blue
    and Yellow can genuinely differ, e.g. a Yellow-only TM move) -- omit for the union
    across all Gen-1 versions. Returns None if the species isn't found; returns
    {"attacking_types": [], "resisting": []} if it has no damaging moves on record.
    Otherwise returns {"attacking_types": [...], "resisting": [{"name": ..., "types":
    [...], "factors": {attacking_type: combined_multiplier}}, ...]} -- an empty
    "resisting" list is a real, meaningful answer (it means no Pokémon resists the
    *entire* movepool at once), not a failure. Raises ValueError for an unrecognized
    version string (propagated from move_types_for_pokemon)."""
    move_types = move_types_for_pokemon(session, species_name, version)
    if move_types is None:
        return None
    if not move_types:
        return {"attacking_types": [], "resisting": []}

    attacker_type_ids = {
        row.name: row.type_id
        for row in session.execute(
            select(PokemonType.name, PokemonType.type_id).where(PokemonType.name.in_(move_types))
        )
    }

    efficacy = {
        (row.damage_type_id, row.target_type_id): row.damage_factor
        for row in session.execute(
            select(TypeEfficacy.damage_type_id, TypeEfficacy.target_type_id, TypeEfficacy.damage_factor)
        )
    }

    form_types: dict[int, list[int]] = {}
    for row in session.execute(
        select(PokemonTypeAssociation.form_id, PokemonTypeAssociation.type_id).order_by(
            PokemonTypeAssociation.slot
        )
    ):
        form_types.setdefault(row.form_id, []).append(row.type_id)

    type_names_by_id = {type_id: name for name, type_id in attacker_type_ids.items()}
    type_names_by_id.update(
        {row.type_id: row.name for row in session.execute(select(PokemonType.type_id, PokemonType.name))}
    )

    species_forms = session.execute(
        select(PokemonSpecies.name, PokemonForm.form_id)
        .join(PokemonForm, PokemonForm.species_id == PokemonSpecies.species_id)
        .where(PokemonForm.is_default)
        .order_by(PokemonSpecies.species_id)
    ).all()

    resisting = []
    for name, form_id in species_forms:
        defending_ids = form_types.get(form_id, [])
        if not defending_ids:
            continue
        factors = {}
        resists_all = True
        for move_type in move_types:
            attacker_id = attacker_type_ids[move_type]
            factor = 1.0
            for defender_id in defending_ids:
                factor *= efficacy.get((attacker_id, defender_id), 1.0)
            factors[move_type] = factor
            if factor >= 1.0:
                resists_all = False
        if resists_all:
            resisting.append(
                {
                    "name": name,
                    "types": [type_names_by_id[d] for d in defending_ids],
                    "factors": factors,
                }
            )

    return {"attacking_types": move_types, "resisting": resisting}


def pokemon_by_type_matchup(session: Session, attacking_type: str) -> dict | None:
    """Every Gen-1 Pokémon species (default form), grouped by the COMBINED damage
    multiplier they take from a single attacking type -- accounting for a real
    dual-typed species' actual two-type combo, not a single type in isolation. This is
    the species-level counterpart to get_offensive_type_matchups (which only reports
    pure, single TYPES in each bucket, e.g. "Bug, Flying, Poison, Psychic all resist
    Fighting at 0.5x") and to pokemon_resisting_attacks (which needs a named Pokémon's
    whole movepool, not a bare type) -- for "which Pokémon double-resist/are immune
    to/are 4x weak to <type>" questions, a real double-resistant species' combined
    factor (e.g. Zubat, Poison/Flying, both resisting Fighting at 0.5x each -> 0.25x
    combined) can only be found by actually combining two real types per species, not
    by reading get_offensive_type_matchups' single-type buckets and guessing which
    dual-type combos exist. Returns None if attacking_type isn't recognized. Otherwise
    returns {"attacking_type": ..., "buckets": {factor: [{"name":..., "types":[...]},
    ...]}} with only non-neutral (factor != 1.0) buckets included, each species sorted
    by name."""
    attacker = session.scalar(
        select(PokemonType).where(func.lower(PokemonType.name) == attacking_type.strip().lower())
    )
    if attacker is None:
        return None

    efficacy = {
        row.target_type_id: row.damage_factor
        for row in session.execute(
            select(TypeEfficacy.target_type_id, TypeEfficacy.damage_factor).where(
                TypeEfficacy.damage_type_id == attacker.type_id
            )
        )
    }

    type_names_by_id = {row.type_id: row.name for row in session.execute(select(PokemonType.type_id, PokemonType.name))}

    form_types: dict[int, list[int]] = {}
    for row in session.execute(
        select(PokemonTypeAssociation.form_id, PokemonTypeAssociation.type_id).order_by(
            PokemonTypeAssociation.slot
        )
    ):
        form_types.setdefault(row.form_id, []).append(row.type_id)

    species_forms = session.execute(
        select(PokemonSpecies.name, PokemonForm.form_id)
        .join(PokemonForm, PokemonForm.species_id == PokemonSpecies.species_id)
        .where(PokemonForm.is_default)
        .order_by(PokemonSpecies.species_id)
    ).all()

    buckets: dict[float, list[dict]] = {}
    for name, form_id in species_forms:
        defending_ids = form_types.get(form_id, [])
        if not defending_ids:
            continue
        factor = 1.0
        for defender_id in defending_ids:
            factor *= efficacy.get(defender_id, 1.0)
        if factor == 1.0:
            continue
        buckets.setdefault(factor, []).append(
            {"name": name, "types": [type_names_by_id[d] for d in defending_ids]}
        )

    for entries in buckets.values():
        entries.sort(key=lambda e: e["name"])

    return {"attacking_type": attacker.name, "buckets": buckets}


# "fishing" isn't a real method value in this schema -- Gen-1 rods are recorded as
# three separate methods by rod strength. Expanding the natural-language "fishing"
# query into all three avoids making the caller already know that internal split.
FISHING_METHODS = ("old-rod", "good-rod", "super-rod")


def _normalize_encounter_method(method: str | None) -> tuple[str, ...] | None:
    if not method:
        return None
    normalized = method.strip().lower()
    if normalized in ("fishing", "fish", "rod"):
        return FISHING_METHODS
    return (normalized,)


def locations_for_pokemon(
    session: Session, species_name: str, version: str | None = None, method: str | None = None
) -> list[dict]:
    species = find_species_by_name(session, species_name)
    if species is None:
        return []
    form = get_default_form(session, species)
    if form is None:
        return []

    query = (
        select(
            Location.name.label("location"),
            GameVersion.name.label("version"),
            PokemonLocationEncounter.method,
            func.min(PokemonLocationEncounter.min_level).label("min_level"),
            func.max(PokemonLocationEncounter.max_level).label("max_level"),
        )
        .join(PokemonLocationEncounter, PokemonLocationEncounter.location_id == Location.location_id)
        .join(GameVersion, GameVersion.version_id == PokemonLocationEncounter.version_id)
        .where(PokemonLocationEncounter.form_id == form.form_id)
        .group_by(Location.location_id, GameVersion.version_id, PokemonLocationEncounter.method)
    )
    # pokemon_location_encounters only contains Gen-1 data (red/blue/yellow and
    # their Japanese originals) -- no generation filter needed here, unlike when
    # this table covered every game the species has ever appeared in.
    if version:
        query = query.where(func.lower(GameVersion.name) == version.strip().lower())
    methods = _normalize_encounter_method(method)
    if methods:
        query = query.where(PokemonLocationEncounter.method.in_(methods))
    query = query.order_by(Location.name).limit(MAX_LOCATIONS_RETURNED)

    rows = session.execute(query).all()
    return [
        {
            "location": r.location,
            "version": r.version,
            "method": r.method,
            "min_level": r.min_level,
            "max_level": r.max_level,
        }
        for r in rows
    ]


def find_locations(session: Session, name: str) -> list[str]:
    """Every location whose name contains all the query's words as a contiguous run of
    whole hyphen-separated words -- e.g. "Seafoam Islands" matches every floor
    (seafoam-islands-1f, seafoam-islands-b1f, ...), and "Route 1" matches
    kanto-route-1-area without falsely matching Route 10 (comparing whole words, not
    substrings, avoids that collision). Location names are far more granular than a
    casual query (one row per floor/sub-area), so this returns every matching row
    rather than a single best match."""
    query_words = name.strip().lower().split()
    if not query_words:
        return []
    all_names = session.scalars(select(Location.name)).all()
    matches = []
    for loc_name in all_names:
        words = loc_name.split("-")
        for i in range(len(words) - len(query_words) + 1):
            if words[i : i + len(query_words)] == query_words:
                matches.append(loc_name)
                break
    return matches


def pokemon_at_location(
    session: Session, location_name: str, version: str | None = None, method: str | None = None
) -> list[dict] | None:
    """For every location matching location_name (e.g. every floor of Seafoam
    Islands), the Pokémon encounterable there with level range and encounter method
    (Gen-1 games only, like locations_for_pokemon). Returns None if no location
    matches at all (distinct from an empty list, which means the location exists but
    has no matching encounters -- e.g. filtered out by version/method)."""
    matching_names = find_locations(session, location_name)
    if not matching_names:
        return None

    query = (
        select(
            Location.name.label("location"),
            PokemonSpecies.name.label("species"),
            GameVersion.name.label("version"),
            PokemonLocationEncounter.method,
            PokemonLocationEncounter.min_level,
            PokemonLocationEncounter.max_level,
        )
        .join(PokemonLocationEncounter, PokemonLocationEncounter.location_id == Location.location_id)
        .join(GameVersion, GameVersion.version_id == PokemonLocationEncounter.version_id)
        .join(PokemonForm, PokemonForm.form_id == PokemonLocationEncounter.form_id)
        .join(PokemonSpecies, PokemonSpecies.species_id == PokemonForm.species_id)
        .where(Location.name.in_(matching_names))
    )
    # pokemon_location_encounters only contains Gen-1 data -- no generation filter
    # needed here (see locations_for_pokemon).
    if version:
        query = query.where(func.lower(GameVersion.name) == version.strip().lower())
    methods = _normalize_encounter_method(method)
    if methods:
        query = query.where(PokemonLocationEncounter.method.in_(methods))
    rows = session.execute(query).all()

    # Collapse to one row per (location, species, method): the same encounter typically
    # repeats across several Gen-1 versions with only minor level differences, and
    # without this a multi-floor location's row count explodes by version count. Method
    # stays part of the key (not collapsed away) since the same species can be
    # encountered at the same spot via genuinely different methods (e.g. walk vs a
    # rod), which is real, useful information, not version-repetition noise.
    grouped: dict[str, dict[tuple[str, str], dict]] = {}
    for r in rows:
        entry = grouped.setdefault(r.location, {}).setdefault(
            (r.species, r.method),
            {
                "location": r.location,
                "species": r.species,
                "method": r.method,
                "min_level": r.min_level,
                "max_level": r.max_level,
            },
        )
        entry["min_level"] = min(entry["min_level"], r.min_level)
        entry["max_level"] = max(entry["max_level"], r.max_level)

    # Cap per-location AND overall: a broad query (e.g. just "Route", matching every
    # numbered route) could otherwise return an unbounded number of locations, while a
    # flat overall cap alone would let one large location's species list (e.g. a
    # multi-floor dungeon) consume the whole budget and hide every other matched
    # location entirely -- capping both dimensions guarantees each matched location
    # gets represented.
    results = []
    for location in sorted(grouped)[:MAX_LOCATIONS_MATCHED]:
        species_entries = sorted(grouped[location].values(), key=lambda e: (e["species"], e["method"]))
        results.extend(species_entries[:MAX_SPECIES_PER_LOCATION])
    return results



def _mentions(text: str, candidates: list[str]) -> list[str]:
    text_lower = text.lower()
    # Word-boundary match, not plain substring -- otherwise e.g. "mew" false-positives
    # inside "mewtwo", and "abra" inside "kadabra".
    return [c for c in candidates if re.search(rf"\b{re.escape(c.lower())}\b", text_lower)]


def retrieve_context(session: Session, user_query: str) -> str:
    """Returns a hint block for any type name mentioned in the query, or
    NO_MATCH_MESSAGE. Deliberately does NOT pre-fetch and inject species data for a
    Pokémon name found in the query -- every question about a specific Pokémon must go
    through get_pokemon_info (rule 2 in the system prompt), even when the name is
    spelled correctly, so the tool is actually invoked (and the answer is auditable via
    ConversationResult.grounding_source / tools_called) rather than silently answered
    from a regex match that a misspelling could just as easily have missed."""
    type_names = session.scalars(select(PokemonType.name)).all()
    matched_types = _mentions(user_query, list(type_names))

    if not matched_types:
        return NO_MATCH_MESSAGE
    blocks = [
        f"Type note: '{type_name.title()}' type was mentioned in the question; "
        "use the get_type_effectiveness tool for exact matchup numbers."
        for type_name in matched_types
    ]
    return "\n\n".join(blocks)


def list_pokemon_by_type(session: Session, type_name: str, pure_only: bool = False) -> list[str]:
    """Species with the given type. pure_only=True restricts to species with no
    secondary type at all -- "has this type" and "is PURELY this type" are different
    questions (e.g. every Gen-1 Ghost-type is also Poison-type, so "pure Ghost-type"
    correctly returns none, even though "Ghost-type" returns Gastly/Haunter/Gengar)."""
    query = (
        select(PokemonSpecies.name)
        .join(PokemonForm, PokemonForm.species_id == PokemonSpecies.species_id)
        .join(PokemonTypeAssociation, PokemonTypeAssociation.form_id == PokemonForm.form_id)
        .join(PokemonType, PokemonType.type_id == PokemonTypeAssociation.type_id)
        .where(
            PokemonForm.is_default,
            func.lower(PokemonType.name) == type_name.strip().lower(),
        )
    )
    if pure_only:
        dual_typed_forms = select(PokemonTypeAssociation.form_id).where(PokemonTypeAssociation.slot == 2)
        query = query.where(PokemonForm.form_id.not_in(dual_typed_forms))
    query = query.order_by(PokemonSpecies.species_id).limit(MAX_POKEMON_LISTED)
    return list(session.scalars(query).all())


def list_pokemon_by_color(session: Session, color_name: str) -> list[str]:
    names = session.scalars(
        select(PokemonSpecies.name)
        .join(PokemonColorAssociation, PokemonColorAssociation.species_id == PokemonSpecies.species_id)
        .join(Color, Color.color_id == PokemonColorAssociation.color_id)
        .where(func.lower(Color.name) == color_name.strip().lower())
        .order_by(PokemonSpecies.species_id)
        .limit(MAX_POKEMON_LISTED)
    ).all()
    return names
