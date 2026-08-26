import json
from pathlib import Path

from sqlalchemy.orm import Session

from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import PokemonFormTrigger
from profesor_oak_ai.ingestion.populate_from_raw import build_form_lookup

RAW_DATA_DIR = Path("pokemon_raw_data")


def populate_form_triggers(session: Session) -> None:
    form_lookup = build_form_lookup(session)

    inserted = 0
    already_present = 0
    out_of_scope = 0

    with open(RAW_DATA_DIR / "pokemon-form.jsonl", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            trigger_conditions = data.get("trigger_conditions")
            if not trigger_conditions:
                continue

            form_id = form_lookup.get(data["name"])
            if form_id is None:
                out_of_scope += 1
                continue

            for tc in trigger_conditions:
                trigger_type = tc["trigger"]
                if session.get(PokemonFormTrigger, (form_id, trigger_type)) is not None:
                    already_present += 1
                    continue
                session.add(
                    PokemonFormTrigger(form_id=form_id, trigger_type=trigger_type, trigger_name=tc.get("name"))
                )
                inserted += 1

    session.commit()
    print(f"Done. {inserted} inserted, {already_present} already present, {out_of_scope} out of scope.")


def main() -> None:
    session = get_session(get_engine())
    try:
        populate_form_triggers(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
