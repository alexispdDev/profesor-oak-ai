import difflib
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from profesor_oak_ai.db.models import (
    Ability,
    Move,
    PokedexEntry,
    PokemonAbility,
    PokemonForm,
    PokemonMove,
    PokemonSpecies,
    PokemonType,
    PokemonTypeAssociation,
    TypeEfficacy,
)

MAX_MOVES_RETURNED = 20
MAX_POKEMON_LISTED = 30

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
    if species.shape:
        lines.append(f"Body shape: {species.shape}")
    if species.color:
        lines.append(f"Primary color: {species.color}")
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

    query = query.order_by(PokemonMove.level_learned_at)
    rows = session.execute(query).all()

    # The same move can repeat at different levels across game versions (the schema
    # doesn't scope learn data by version); keep only the earliest level per move name.
    seen_names: set[str] = set()
    results = []
    for row in rows:
        if row.name in seen_names:
            continue
        seen_names.add(row.name)
        results.append(
            {
                "name": row.name,
                "damage_class": row.damage_class,
                "power": row.power,
                "accuracy": row.accuracy,
                "learn_method": row.learn_method,
                "level": row.level_learned_at,
            }
        )
        if len(results) >= MAX_MOVES_RETURNED:
            break

    return results


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


def list_pokemon_by_shape(
    session: Session, shapes: list[str], pokemon_type: str | None = None
) -> list[str]:
    shapes_lower = [s.strip().lower() for s in shapes]
    query = select(PokemonSpecies.name).where(func.lower(PokemonSpecies.shape).in_(shapes_lower))
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
