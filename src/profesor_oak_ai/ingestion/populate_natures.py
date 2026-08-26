import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import Nature

RAW_DATA_DIR = Path("pokemon_raw_data")


def populate_natures(session: Session) -> None:
    inserted = 0
    already_present = 0

    with open(RAW_DATA_DIR / "nature.jsonl", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            if session.execute(select(Nature).where(Nature.name == data["name"])).scalar_one_or_none():
                already_present += 1
                continue

            session.add(
                Nature(
                    name=data["name"],
                    increased_stat=data["increased_stat"]["name"] if data["increased_stat"] else None,
                    decreased_stat=data["decreased_stat"]["name"] if data["decreased_stat"] else None,
                    likes_flavor=data["likes_flavor"]["name"] if data["likes_flavor"] else None,
                    hates_flavor=data["hates_flavor"]["name"] if data["hates_flavor"] else None,
                )
            )
            inserted += 1

    session.commit()
    print(f"Done. {inserted} inserted, {already_present} already present.")


def main() -> None:
    session = get_session(get_engine())
    try:
        populate_natures(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
