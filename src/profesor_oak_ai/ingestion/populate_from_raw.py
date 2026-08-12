import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import (
    Ability,
    GameVersion,
    Item,
    PokemonCries,
    PokemonForm,
    PokemonGameIndex,
    PokemonHeldItem,
    PokemonPastAbility,
    PokemonPastStat,
    PokemonPastType,
    PokemonSpecies,
    PokemonType,
)
from profesor_oak_ai.ingestion.populate import GENERATION_NAME_TO_INT, english_text, load_name_id_map

RAW_DATA_DIR = Path("pokemon_raw_data")


def build_form_lookup(session: Session) -> dict[str, int]:
    """Maps PokeAPI's 'pokemon' resource name (e.g. 'venusaur-mega') to our internal
    form_id, for every form already ingested by populate.py."""
    rows = session.execute(
        select(PokemonForm.form_id, PokemonForm.form_name, PokemonSpecies.name).join(
            PokemonSpecies, PokemonSpecies.species_id == PokemonForm.species_id
        )
    ).all()
    return {
        (species_name if form_name is None else f"{species_name}-{form_name}"): form_id
        for form_id, form_name, species_name in rows
    }


def load_offline_lookup(path: Path) -> dict[str, dict]:
    lookup = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            lookup[data["name"]] = data
    return lookup


def get_or_create_ability_offline(
    session: Session, cache: dict[str, int], offline_abilities: dict[str, dict], name: str
) -> int | None:
    if name in cache:
        return cache[name]
    data = offline_abilities.get(name)
    if data is None:
        return None
    description = english_text(data.get("effect_entries", []), "short_effect", "effect")
    ability = Ability(name=name, description=description)
    session.add(ability)
    session.flush()
    cache[name] = ability.ability_id
    return ability.ability_id


def get_or_create_item_offline(
    session: Session, cache: dict[str, int], offline_items: dict[str, dict], name: str
) -> int | None:
    if name in cache:
        return cache[name]
    if name not in offline_items:
        return None
    item = Item(name=name)
    session.add(item)
    session.flush()
    cache[name] = item.item_id
    return item.item_id


def insert_held_items(
    session: Session,
    form_id: int,
    held_items: list[dict],
    version_map: dict[str, int],
    item_cache: dict[str, int],
    offline_items: dict[str, dict],
) -> None:
    for held in held_items:
        item_id = get_or_create_item_offline(session, item_cache, offline_items, held["item"]["name"])
        if item_id is None:
            continue
        for detail in held["version_details"]:
            version_id = version_map.get(detail["version"]["name"])
            if version_id is None:
                continue
            session.add(
                PokemonHeldItem(
                    form_id=form_id, item_id=item_id, version_id=version_id, rarity=detail["rarity"]
                )
            )


def insert_game_indices(
    session: Session, form_id: int, game_indices: list[dict], version_map: dict[str, int]
) -> None:
    for entry in game_indices:
        version_id = version_map.get(entry["version"]["name"])
        if version_id is None:
            continue
        session.add(
            PokemonGameIndex(form_id=form_id, version_id=version_id, game_index=entry["game_index"])
        )


def insert_past_types(
    session: Session, form_id: int, past_types: list[dict], type_map: dict[str, int]
) -> None:
    for entry in past_types:
        generation = GENERATION_NAME_TO_INT[entry["generation"]["name"]]
        for slot_entry in entry["types"]:
            # A past-types slot can have a null type (e.g. a Pokemon that only had one
            # type in an older generation) -- notes.txt's len(x) > 0 check doesn't
            # actually catch this (a dict with a null value still has the same key
            # count), which would crash on `x['type']['name']`. Skip explicitly instead.
            if slot_entry.get("type") is None:
                continue
            type_id = type_map.get(slot_entry["type"]["name"])
            if type_id is None:
                continue
            session.add(
                PokemonPastType(
                    form_id=form_id, generation=generation, slot=slot_entry["slot"], type_id=type_id
                )
            )


def insert_past_abilities(
    session: Session,
    form_id: int,
    past_abilities: list[dict],
    ability_cache: dict[str, int],
    offline_abilities: dict[str, dict],
) -> None:
    for entry in past_abilities:
        generation = GENERATION_NAME_TO_INT[entry["generation"]["name"]]
        for a in entry["abilities"]:
            if a["ability"] is None:
                continue
            ability_id = get_or_create_ability_offline(
                session, ability_cache, offline_abilities, a["ability"]["name"]
            )
            if ability_id is None:
                continue
            session.add(
                PokemonPastAbility(
                    form_id=form_id,
                    generation=generation,
                    slot=a["slot"],
                    ability_id=ability_id,
                    is_hidden=a["is_hidden"],
                )
            )


def insert_past_stats(session: Session, form_id: int, past_stats: list[dict]) -> None:
    for entry in past_stats:
        # notes.txt never captured which generation a past-stats block belongs to,
        # even though the raw data has it (same shape as past_types/past_abilities) --
        # without it, a Pokemon with past stats from multiple generations would be
        # ambiguous. Captured here via the composite PK's generation column.
        generation = GENERATION_NAME_TO_INT[entry["generation"]["name"]]
        for stat in entry["stats"]:
            session.add(
                PokemonPastStat(
                    form_id=form_id,
                    generation=generation,
                    stat_name=stat["stat"]["name"],
                    base_stat=stat["base_stat"],
                    effort=stat["effort"],
                )
            )


def insert_cries(session: Session, form_id: int, cries: dict | None) -> None:
    cries = cries or {}
    session.add(PokemonCries(form_id=form_id, latest=cries.get("latest"), legacy=cries.get("legacy")))


def process_pokemon_record(
    session: Session,
    data: dict,
    form_id: int,
    version_map: dict[str, int],
    type_map: dict[str, int],
    ability_cache: dict[str, int],
    offline_abilities: dict[str, dict],
    item_cache: dict[str, int],
    offline_items: dict[str, dict],
) -> None:
    form = session.get(PokemonForm, form_id)
    form.base_experience = data.get("base_experience")
    form.order = data.get("order")

    insert_held_items(
        session, form_id, data.get("held_items", []), version_map, item_cache, offline_items
    )
    insert_game_indices(session, form_id, data.get("game_indices", []), version_map)
    insert_past_types(session, form_id, data.get("past_types", []), type_map)
    insert_past_abilities(
        session, form_id, data.get("past_abilities", []), ability_cache, offline_abilities
    )
    insert_past_stats(session, form_id, data.get("past_stats", []))
    insert_cries(session, form_id, data.get("cries"))


def main() -> None:
    session = get_session(get_engine())

    form_lookup = build_form_lookup(session)
    version_map = load_name_id_map(session, GameVersion, "version_id")
    type_map = load_name_id_map(session, PokemonType, "type_id")
    ability_cache = load_name_id_map(session, Ability, "ability_id")
    item_cache = load_name_id_map(session, Item, "item_id")

    offline_abilities = load_offline_lookup(RAW_DATA_DIR / "ability.jsonl")
    offline_items = load_offline_lookup(RAW_DATA_DIR / "item.jsonl")

    processed = 0
    already_done = 0
    out_of_scope = 0

    with open(RAW_DATA_DIR / "pokemon.jsonl", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            form_id = form_lookup.get(data["name"])
            if form_id is None:
                out_of_scope += 1
                continue

            if session.get(PokemonCries, form_id) is not None:
                already_done += 1
                continue

            process_pokemon_record(
                session,
                data,
                form_id,
                version_map,
                type_map,
                ability_cache,
                offline_abilities,
                item_cache,
                offline_items,
            )
            session.commit()
            processed += 1
            print(f"{data['name']}: done")

    session.close()
    print(f"\nDone. {processed} forms processed, {already_done} already done, {out_of_scope} out of scope.")


if __name__ == "__main__":
    main()
