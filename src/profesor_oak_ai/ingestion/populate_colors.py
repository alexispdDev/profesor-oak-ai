import json
from pathlib import Path

from sqlalchemy.orm import Session

from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import Color, PokemonColorAssociation, PokemonSpecies
from profesor_oak_ai.ingestion.populate import load_name_id_map

RAW_DATA_DIR = Path("pokemon_raw_data")


def get_or_create_color(session: Session, cache: dict[str, int], name: str) -> int:
    if name in cache:
        return cache[name]
    color = Color(name=name)
    session.add(color)
    session.flush()
    cache[name] = color.color_id
    return color.color_id


def populate_colors(session: Session) -> None:
    color_cache = load_name_id_map(session, Color, "color_id")
    species_lookup = load_name_id_map(session, PokemonSpecies, "species_id")

    inserted = 0
    already_present = 0
    out_of_scope = 0

    with open(RAW_DATA_DIR / "pokemon-color.jsonl", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            color_id = get_or_create_color(session, color_cache, data["name"])

            for entry in data["pokemon_species"]:
                species_id = species_lookup.get(entry["name"])
                if species_id is None:
                    out_of_scope += 1
                    continue

                if session.get(PokemonColorAssociation, species_id) is not None:
                    already_present += 1
                    continue

                session.add(PokemonColorAssociation(species_id=species_id, color_id=color_id))
                inserted += 1

            session.commit()
            print(f"{data['name']}: done")

    print(f"\nDone. {inserted} inserted, {already_present} already present, {out_of_scope} out of scope.")


def main() -> None:
    session = get_session(get_engine())
    try:
        populate_colors(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
