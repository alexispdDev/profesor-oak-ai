import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import GameVersion, Location, PokemonLocationEncounter
from profesor_oak_ai.ingestion.populate import load_name_id_map
from profesor_oak_ai.ingestion.populate_from_raw import build_form_lookup

RAW_DATA_DIR = Path("pokemon_raw_data")


def build_pokemon_id_to_name(path: Path) -> dict[int, str]:
    mapping = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            mapping[data["id"]] = data["name"]
    return mapping


def get_or_create_location(session: Session, cache: dict[str, int], name: str) -> int:
    if name in cache:
        return cache[name]
    location = Location(name=name)
    session.add(location)
    session.flush()
    cache[name] = location.location_id
    return location.location_id


def insert_encounters_for_form(
    session: Session,
    form_id: int,
    locations: list[dict],
    version_map: dict[str, int],
    location_cache: dict[str, int],
) -> int:
    seen_keys: set[tuple[int, int, str, int, int]] = set()
    inserted = 0

    for loc in locations:
        location_id = get_or_create_location(session, location_cache, loc["location_area"]["name"])

        for version_detail in loc["version_details"]:
            version_id = version_map.get(version_detail["version"]["name"])
            if version_id is None:
                continue

            for encounter in version_detail["encounter_details"]:
                key = (
                    location_id,
                    version_id,
                    encounter["method"]["name"],
                    encounter["min_level"],
                    encounter["max_level"],
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                session.add(
                    PokemonLocationEncounter(
                        form_id=form_id,
                        location_id=location_id,
                        version_id=version_id,
                        method=encounter["method"]["name"],
                        min_level=encounter["min_level"],
                        max_level=encounter["max_level"],
                        chance=encounter["chance"],
                    )
                )
                inserted += 1

    return inserted


def populate_location_encounters(session: Session) -> None:
    form_lookup = build_form_lookup(session)
    pokemon_id_to_name = build_pokemon_id_to_name(RAW_DATA_DIR / "pokemon.jsonl")
    version_map = load_name_id_map(session, GameVersion, "version_id")
    location_cache = load_name_id_map(session, Location, "location_id")

    processed = 0
    already_done = 0
    out_of_scope = 0
    total_rows = 0

    with open(RAW_DATA_DIR / "pokemon_location_areas.jsonl", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            name = pokemon_id_to_name.get(data["id"])
            form_id = form_lookup.get(name) if name else None
            if form_id is None:
                out_of_scope += 1
                continue

            existing = session.execute(
                select(PokemonLocationEncounter.form_id)
                .where(PokemonLocationEncounter.form_id == form_id)
                .limit(1)
            ).first()
            if existing is not None:
                already_done += 1
                continue

            inserted = insert_encounters_for_form(
                session, form_id, data["locations"], version_map, location_cache
            )
            session.commit()
            total_rows += inserted
            processed += 1
            print(f"{name}: {inserted} encounter rows")

    print(
        f"\nDone. {processed} forms processed ({total_rows} encounter rows), "
        f"{already_done} already done, {out_of_scope} out of scope."
    )


def main() -> None:
    session = get_session(get_engine())
    try:
        populate_location_encounters(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
