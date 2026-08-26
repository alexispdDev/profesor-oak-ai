import json
from pathlib import Path

from sqlalchemy.orm import Session

from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import GrowthRate, GrowthRateLevel, PokemonGrowthRateAssociation, PokemonSpecies
from profesor_oak_ai.ingestion.populate import load_name_id_map

RAW_DATA_DIR = Path("pokemon_raw_data")


def get_or_create_growth_rate(session: Session, cache: dict[str, int], name: str) -> int:
    if name in cache:
        return cache[name]
    growth_rate = GrowthRate(name=name)
    session.add(growth_rate)
    session.flush()
    cache[name] = growth_rate.growth_rate_id
    return growth_rate.growth_rate_id


def populate_growth_rate_levels(session: Session, growth_rate_id: int, levels_data: list[dict]) -> None:
    for entry in levels_data:
        if session.get(GrowthRateLevel, (growth_rate_id, entry["level"])) is not None:
            continue
        session.add(
            GrowthRateLevel(
                growth_rate_id=growth_rate_id, level=entry["level"], experience=entry["experience"]
            )
        )


def populate_growth_rates(session: Session) -> None:
    growth_rate_cache = load_name_id_map(session, GrowthRate, "growth_rate_id")
    species_lookup = load_name_id_map(session, PokemonSpecies, "species_id")

    inserted = 0
    already_present = 0
    out_of_scope = 0

    with open(RAW_DATA_DIR / "growth-rate.jsonl", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            growth_rate_id = get_or_create_growth_rate(session, growth_rate_cache, data["name"])
            populate_growth_rate_levels(session, growth_rate_id, data["levels"])

            for entry in data["pokemon_species"]:
                species_id = species_lookup.get(entry["name"])
                if species_id is None:
                    out_of_scope += 1
                    continue

                if session.get(PokemonGrowthRateAssociation, species_id) is not None:
                    already_present += 1
                    continue

                session.add(
                    PokemonGrowthRateAssociation(species_id=species_id, growth_rate_id=growth_rate_id)
                )
                inserted += 1

            session.commit()
            print(f"{data['name']}: done")

    print(f"\nDone. {inserted} inserted, {already_present} already present, {out_of_scope} out of scope.")


def main() -> None:
    session = get_session(get_engine())
    try:
        populate_growth_rates(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
