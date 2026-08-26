import json
from pathlib import Path

from sqlalchemy.orm import Session

from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import EggGroup, PokemonEggGroupAssociation, PokemonSpecies
from profesor_oak_ai.ingestion.populate import load_name_id_map

RAW_DATA_DIR = Path("pokemon_raw_data")


def get_or_create_egg_group(session: Session, cache: dict[str, int], name: str) -> int:
    if name in cache:
        return cache[name]
    egg_group = EggGroup(name=name)
    session.add(egg_group)
    session.flush()
    cache[name] = egg_group.egg_group_id
    return egg_group.egg_group_id


def populate_egg_groups(session: Session) -> None:
    egg_group_cache = load_name_id_map(session, EggGroup, "egg_group_id")
    species_lookup = load_name_id_map(session, PokemonSpecies, "species_id")

    inserted = 0
    already_present = 0
    out_of_scope = 0

    with open(RAW_DATA_DIR / "egg-group.jsonl", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            egg_group_id = get_or_create_egg_group(session, egg_group_cache, data["name"])

            for entry in data["pokemon_species"]:
                species_id = species_lookup.get(entry["name"])
                if species_id is None:
                    out_of_scope += 1
                    continue

                if session.get(PokemonEggGroupAssociation, (species_id, egg_group_id)) is not None:
                    already_present += 1
                    continue

                session.add(PokemonEggGroupAssociation(species_id=species_id, egg_group_id=egg_group_id))
                inserted += 1

            session.commit()
            print(f"{data['name']}: done")

    print(f"\nDone. {inserted} inserted, {already_present} already present, {out_of_scope} out of scope.")


def main() -> None:
    session = get_session(get_engine())
    try:
        populate_egg_groups(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
