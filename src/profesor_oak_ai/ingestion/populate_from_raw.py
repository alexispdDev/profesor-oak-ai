import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import (
    GameVersion,
    Item,
    PokemonCries,
    PokemonForm,
    PokemonGameIndex,
    PokemonSpecies,
)
from profesor_oak_ai.ingestion.populate import RAW_DATA_DIR, load_name_id_map


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


ALLOWED_GAME_INDEX_VERSIONS = {"red", "blue", "yellow"}


def insert_game_indices(
    session: Session, form_id: int, game_indices: list[dict], version_map: dict[str, int]
) -> None:
    for entry in game_indices:
        version_name = entry["version"]["name"]
        if version_name not in ALLOWED_GAME_INDEX_VERSIONS:
            continue
        version_id = version_map.get(version_name)
        if version_id is None:
            continue
        session.add(
            PokemonGameIndex(form_id=form_id, version_id=version_id, game_index=entry["game_index"])
        )


def insert_cries(session: Session, form_id: int, cries: dict | None) -> None:
    cries = cries or {}
    session.add(PokemonCries(form_id=form_id, latest=cries.get("latest"), legacy=cries.get("legacy")))


def process_pokemon_record(
    session: Session,
    data: dict,
    form_id: int,
    version_map: dict[str, int],
) -> None:
    form = session.get(PokemonForm, form_id)
    form.base_experience = data.get("base_experience")
    form.order = data.get("order")

    insert_game_indices(session, form_id, data.get("game_indices", []), version_map)
    insert_cries(session, form_id, data.get("cries"))


def main() -> None:
    session = get_session(get_engine())
    try:
        form_lookup = build_form_lookup(session)
        version_map = load_name_id_map(session, GameVersion, "version_id")

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
                )
                session.commit()
                processed += 1
                print(f"{data['name']}: done")
    finally:
        session.close()
    print(f"\nDone. {processed} forms processed, {already_done} already done, {out_of_scope} out of scope.")


if __name__ == "__main__":
    main()
