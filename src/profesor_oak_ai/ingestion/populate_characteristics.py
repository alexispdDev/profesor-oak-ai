import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import Characteristic
from profesor_oak_ai.ingestion.populate import english_text

RAW_DATA_DIR = Path("pokemon_raw_data")


def populate_characteristics(session: Session) -> None:
    inserted = 0
    already_present = 0

    with open(RAW_DATA_DIR / "characteristic.jsonl", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            highest_stat = data["highest_stat"]["name"]
            gene_modulo = data["gene_modulo"]

            existing = session.execute(
                select(Characteristic).where(
                    Characteristic.highest_stat == highest_stat,
                    Characteristic.gene_modulo == gene_modulo,
                )
            ).scalar_one_or_none()
            if existing is not None:
                already_present += 1
                continue

            description = english_text(data["descriptions"], "description")
            session.add(
                Characteristic(highest_stat=highest_stat, gene_modulo=gene_modulo, description=description)
            )
            inserted += 1

    session.commit()
    print(f"Done. {inserted} inserted, {already_present} already present.")


def main() -> None:
    session = get_session(get_engine())
    try:
        populate_characteristics(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
