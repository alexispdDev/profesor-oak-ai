from qdrant_client.models import PointStruct
from sqlalchemy import select
from sqlalchemy.orm import Session

from profesor_oak_ai.agent.retrieval import get_representative_entry
from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import PokemonSpecies
from profesor_oak_ai.vectorstore.client import (
    COLLECTION_NAME,
    ensure_collection,
    get_qdrant_client,
)
from profesor_oak_ai.vectorstore.embeddings import embed_text


def populate_vectorstore(session: Session, client) -> None:
    ensure_collection(client)

    species_list = session.scalars(select(PokemonSpecies).order_by(PokemonSpecies.species_id)).all()
    total = len(species_list)
    inserted = 0
    skipped = 0

    for index, species in enumerate(species_list, 1):
        if client.retrieve(COLLECTION_NAME, ids=[species.species_id]):
            skipped += 1
            continue

        entry = get_representative_entry(session, species.species_id)
        if entry is None:
            print(f"[{index}/{total}] {species.name}: no lore entry, skipping")
            continue

        vector = embed_text(entry.entry)
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=species.species_id,
                    vector=vector,
                    payload={
                        "species_id": species.species_id,
                        "name": species.name,
                        "entry": entry.entry,
                    },
                )
            ],
        )
        inserted += 1
        print(f"[{index}/{total}] {species.name}: embedded")

    print(f"\nDone. {inserted} embedded, {skipped} already present.")


def main() -> None:
    session = get_session(get_engine())
    client = get_qdrant_client()
    try:
        populate_vectorstore(session, client)
    finally:
        session.close()


if __name__ == "__main__":
    main()
