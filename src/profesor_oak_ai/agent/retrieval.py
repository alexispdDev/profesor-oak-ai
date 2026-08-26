import difflib
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from profesor_oak_ai.db.models import (
    Ability,
    Color,
    GameVersion,
    Item,
    Location,
    Move,
    PokedexEntry,
    PokemonAbility,
    PokemonColorAssociation,
    PokemonForm,
    PokemonHeldItem,
    PokemonLocationEncounter,
    PokemonMove,
    PokemonShapeAssociation,
    PokemonSpecies,
    PokemonType,
    PokemonTypeAssociation,
    Shape,
    TypeEfficacy,
)

MAX_MOVES_RETURNED = 20
MAX_POKEMON_LISTED = 30
MAX_LOCATIONS_RETURNED = 20

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


def get_shape_name(session: Session, species_id: int) -> str | None:
    return session.scalar(
        select(Shape.name)
        .join(PokemonShapeAssociation, PokemonShapeAssociation.shape_id == Shape.shape_id)
        .where(PokemonShapeAssociation.species_id == species_id)
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

    abilities = session.execute(
        select(Ability.name, PokemonAbility.is_hidden)
        .join(PokemonAbility, PokemonAbility.ability_id == Ability.ability_id)
        .where(PokemonAbility.form_id == form.form_id)
    ).all()
    ability_strs = [f"{name}{' (hidden)' if is_hidden else ''}" for name, is_hidden in abilities]

    entry = get_representative_entry(session, species.species_id)
    color_name = get_color_name(session, species.species_id)
    shape_name = get_shape_name(session, species.species_id)

    evolves_from_name = None
    if species.evolves_from_species_id:
        parent = session.get(PokemonSpecies, species.evolves_from_species_id)
        evolves_from_name = parent.name.title() if parent else None

    lines = [
        f"Name: {species.name.title()} (#{species.species_id}, Generation {species.generation})",
        f"Types: {', '.join(t.title() for t in types)}",
        f"Abilities: {', '.join(ability_strs)}",
        f"Stats: HP {form.hp}, Attack {form.attack}, Defense {form.defense}, "
        f"Sp.Atk {form.special_attack}, Sp.Def {form.special_defense}, Speed {form.speed} "
        f"(Total {form.base_stat_total})",
    ]
    if species.is_legendary:
        lines.append("This is a Legendary Pokémon.")
    if species.is_mythical:
        lines.append("This is a Mythical Pokémon.")
    if evolves_from_name:
        lines.append(f"Evolves from: {evolves_from_name}")
    if shape_name:
        lines.append(f"Body shape: {shape_name}")
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


def defensive_type_matchups(session: Session, pokemon_name: str) -> dict | None:
    """For a Pokémon's defending type(s), returns every attacking type's combined
    damage multiplier (accounting for both types on a dual-typed Pokémon)."""
    species = find_species_by_name(session, pokemon_name)
    if species is None:
        return None
    form = get_default_form(session, species)
    if form is None:
        return None

    defending_types = session.scalars(
        select(PokemonType.name)
        .join(PokemonTypeAssociation, PokemonTypeAssociation.type_id == PokemonType.type_id)
        .where(PokemonTypeAssociation.form_id == form.form_id)
        .order_by(PokemonTypeAssociation.slot)
    ).all()

    rows = session.execute(
        select(PokemonType.name, TypeEfficacy.damage_factor)
        .join(TypeEfficacy, TypeEfficacy.damage_type_id == PokemonType.type_id)
        .join(
            PokemonTypeAssociation,
            PokemonTypeAssociation.type_id == TypeEfficacy.target_type_id,
        )
        .where(PokemonTypeAssociation.form_id == form.form_id)
    ).all()

    factors: dict[str, float] = {}
    for attacking_type, damage_factor in rows:
        factors[attacking_type] = factors.get(attacking_type, 1.0) * damage_factor

    return {"types": list(defending_types), "factors": factors}


LEARN_METHOD_PRIORITY = {"level-up": 0, "egg": 1, "tutor": 2, "machine": 3}


def moves_for_pokemon(
    session: Session,
    species_name: str,
    move_type: str | None = None,
    learn_method: str | None = None,
) -> list[dict]:
    species = find_species_by_name(session, species_name)
    if species is None:
        return []
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
        )
        .join(PokemonMove, PokemonMove.move_id == Move.move_id)
        .where(PokemonMove.form_id == form.form_id)
    )
    if move_type:
        query = query.join(PokemonType, PokemonType.type_id == Move.type_id).where(
            func.lower(PokemonType.name) == move_type.strip().lower()
        )
    if learn_method:
        query = query.where(PokemonMove.learn_method == learn_method.strip().lower())

    rows = session.execute(query).all()

    # The same (move, learn_method) pair can repeat at different levels across game
    # versions (the schema doesn't scope learn data by version) -- keep only the
    # earliest level per (name, learn_method), NOT per name alone. Deduping by name
    # alone would let a move's level-less machine/egg/tutor entry (level_learned_at
    # defaults to 0) silently suppress its level-up entry, hiding real level data.
    best: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row.name, row.learn_method)
        if key not in best or row.level_learned_at < best[key]["level"]:
            best[key] = {
                "name": row.name,
                "damage_class": row.damage_class,
                "power": row.power,
                "accuracy": row.accuracy,
                "learn_method": row.learn_method,
                "level": row.level_learned_at,
            }

    # Level-up moves first (in level order), then egg/tutor/machine -- otherwise,
    # when no learn_method filter is given, TM/egg/tutor entries (level_learned_at=0)
    # would sort before every level-up move and crowd the capped result out entirely.
    results = sorted(
        best.values(),
        key=lambda m: (LEARN_METHOD_PRIORITY.get(m["learn_method"], 99), m["level"], m["name"]),
    )
    return results[:MAX_MOVES_RETURNED]


def locations_for_pokemon(
    session: Session, species_name: str, version: str | None = None
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
            func.min(PokemonLocationEncounter.min_level).label("min_level"),
            func.max(PokemonLocationEncounter.max_level).label("max_level"),
        )
        .join(PokemonLocationEncounter, PokemonLocationEncounter.location_id == Location.location_id)
        .join(GameVersion, GameVersion.version_id == PokemonLocationEncounter.version_id)
        .where(PokemonLocationEncounter.form_id == form.form_id)
        .group_by(Location.location_id, GameVersion.version_id)
    )
    if version:
        query = query.where(func.lower(GameVersion.name) == version.strip().lower())
    query = query.order_by(Location.name).limit(MAX_LOCATIONS_RETURNED)

    rows = session.execute(query).all()
    return [
        {"location": r.location, "version": r.version, "min_level": r.min_level, "max_level": r.max_level}
        for r in rows
    ]


def held_items_for_pokemon(session: Session, species_name: str) -> list[dict]:
    species = find_species_by_name(session, species_name)
    if species is None:
        return []
    form = get_default_form(session, species)
    if form is None:
        return []

    query = (
        select(Item.name.label("item"), PokemonHeldItem.rarity)
        .join(PokemonHeldItem, PokemonHeldItem.item_id == Item.item_id)
        .where(PokemonHeldItem.form_id == form.form_id)
        .order_by(Item.name)
    )
    rows = session.execute(query).all()

    # The same item/rarity typically repeats across many game versions; collapse to one
    # row per item (first-seen rarity) rather than listing every version, matching how
    # moves_for_pokemon collapses cross-version repetition.
    items: dict[str, int] = {}
    for row in rows:
        items.setdefault(row.item, row.rarity)
    return [{"item": name, "rarity": rarity} for name, rarity in items.items()]


def _mentions(text: str, candidates: list[str]) -> list[str]:
    text_lower = text.lower()
    # Word-boundary match, not plain substring -- otherwise e.g. "mew" false-positives
    # inside "mewtwo", and "abra" inside "kadabra".
    return [c for c in candidates if re.search(rf"\b{re.escape(c.lower())}\b", text_lower)]


def retrieve_context(session: Session, user_query: str) -> str:
    species_names = session.scalars(select(PokemonSpecies.name)).all()
    type_names = session.scalars(select(PokemonType.name)).all()

    matched_species = _mentions(user_query, list(species_names))
    matched_types = _mentions(user_query, list(type_names))

    blocks = []
    for name in matched_species:
        species = find_species_by_name(session, name)
        if species is not None:
            blocks.append(describe_pokemon(session, species))
    for type_name in matched_types:
        blocks.append(
            f"Type note: '{type_name.title()}' type was mentioned in the question; "
            "use the get_type_effectiveness tool for exact matchup numbers."
        )

    if not blocks:
        return NO_MATCH_MESSAGE
    return "\n\n".join(blocks)


def list_pokemon_by_type(session: Session, type_name: str) -> list[str]:
    names = session.scalars(
        select(PokemonSpecies.name)
        .join(PokemonForm, PokemonForm.species_id == PokemonSpecies.species_id)
        .join(PokemonTypeAssociation, PokemonTypeAssociation.form_id == PokemonForm.form_id)
        .join(PokemonType, PokemonType.type_id == PokemonTypeAssociation.type_id)
        .where(
            PokemonForm.is_default,
            func.lower(PokemonType.name) == type_name.strip().lower(),
        )
        .order_by(PokemonSpecies.species_id)
        .limit(MAX_POKEMON_LISTED)
    ).all()
    return list(names)


def list_pokemon_by_color(session: Session, color_name: str) -> list[str]:
    names = session.scalars(
        select(PokemonSpecies.name)
        .join(PokemonColorAssociation, PokemonColorAssociation.species_id == PokemonSpecies.species_id)
        .join(Color, Color.color_id == PokemonColorAssociation.color_id)
        .where(func.lower(Color.name) == color_name.strip().lower())
        .order_by(PokemonSpecies.species_id)
        .limit(MAX_POKEMON_LISTED)
    ).all()
    return list(names)


def list_pokemon_by_shape(
    session: Session, shapes: list[str], pokemon_type: str | None = None
) -> list[str]:
    shapes_lower = [s.strip().lower() for s in shapes]
    query = (
        select(PokemonSpecies.name)
        .join(PokemonShapeAssociation, PokemonShapeAssociation.species_id == PokemonSpecies.species_id)
        .join(Shape, Shape.shape_id == PokemonShapeAssociation.shape_id)
        .where(func.lower(Shape.name).in_(shapes_lower))
    )
    if pokemon_type:
        query = (
            query.join(PokemonForm, PokemonForm.species_id == PokemonSpecies.species_id)
            .join(PokemonTypeAssociation, PokemonTypeAssociation.form_id == PokemonForm.form_id)
            .join(PokemonType, PokemonType.type_id == PokemonTypeAssociation.type_id)
            .where(
                PokemonForm.is_default,
                func.lower(PokemonType.name) == pokemon_type.strip().lower(),
            )
        )
    query = query.order_by(PokemonSpecies.species_id).limit(MAX_POKEMON_LISTED)
    return list(session.scalars(query).all())
