import json
from pathlib import Path

from sqlalchemy.orm import Session

from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import PokemonShapeAssociation, PokemonSpecies, Shape
from profesor_oak_ai.ingestion.populate import english_text, load_name_id_map

RAW_DATA_DIR = Path("pokemon_raw_data")


def get_or_create_shape(session: Session, cache: dict[str, int], data: dict) -> int:
    name = data["name"]
    if name in cache:
        return cache[name]
    awesome_name = english_text(data.get("awesome_names", []), "awesome_name")
    shape = Shape(name=name, awesome_name=awesome_name)
    session.add(shape)
    session.flush()
    cache[name] = shape.shape_id
    return shape.shape_id


def populate_shapes(session: Session) -> None:
    shape_cache = load_name_id_map(session, Shape, "shape_id")
    species_lookup = load_name_id_map(session, PokemonSpecies, "species_id")

    inserted = 0
    already_present = 0
    out_of_scope = 0

    with open(RAW_DATA_DIR / "pokemon-shape.jsonl", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            shape_id = get_or_create_shape(session, shape_cache, data)

            for entry in data["pokemon_species"]:
                species_id = species_lookup.get(entry["name"])
                if species_id is None:
                    out_of_scope += 1
                    continue

                if session.get(PokemonShapeAssociation, species_id) is not None:
                    already_present += 1
                    continue

                session.add(PokemonShapeAssociation(species_id=species_id, shape_id=shape_id))
                inserted += 1

            session.commit()
            print(f"{data['name']}: done")

    print(f"\nDone. {inserted} inserted, {already_present} already present, {out_of_scope} out of scope.")


def main() -> None:
    session = get_session(get_engine())
    try:
        populate_shapes(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
