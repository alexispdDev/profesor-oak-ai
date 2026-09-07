import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from profesor_oak_ai.agent import retrieval
from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import Gen1ouUsageMove, Move
from profesor_oak_ai.ingestion.populate import RAW_DATA_DIR

USAGE_FILE = RAW_DATA_DIR / "gen1ou-1760.json"

# Smogon's chaos-stats move slugs are the move name lowercased with spaces/hyphens
# stripped ("body-slam" -> "bodyslam"), except for this one real mismatch: Smogon
# spells it "visegrip" (a misspelling carried over from the original game text),
# while PokeAPI's slug is "vice-grip" -> "vicegrip". Maps a Smogon slug to the
# stripped form of the real PokeAPI move name it actually refers to.
MOVE_SLUG_ALIASES = {"visegrip": "vicegrip"}


def _stripped(name: str) -> str:
    return name.replace("-", "").lower()


def build_move_lookup(session: Session) -> dict[str, int]:
    """Maps a stripped move slug (Smogon-style, no hyphens) to its move_id."""
    moves = session.execute(select(Move.move_id, Move.name)).all()
    return {_stripped(name): move_id for move_id, name in moves}


def populate_gen1ou_usage(session: Session) -> None:
    if not USAGE_FILE.exists():
        print(f"{USAGE_FILE} not found -- skipping gen1ou usage-stats ingestion.")
        return

    with open(USAGE_FILE) as f:
        snapshot = json.load(f)

    move_lookup = build_move_lookup(session)
    existing_keys = set(
        session.execute(select(Gen1ouUsageMove.species_id, Gen1ouUsageMove.move_id)).all()
    )

    inserted = already_present = unresolved_species = unresolved_moves = 0
    for species_name, entry in snapshot["data"].items():
        species = retrieval.find_species_by_name(session, species_name)
        if species is None:
            # Smogon's display names carry punctuation PokeAPI slugs drop entirely
            # ("Mr. Mime" -> "mr-mime") -- retry with it stripped before giving up.
            normalized = species_name.lower().replace(".", "").replace("'", "").replace(" ", "-")
            species = retrieval.find_species_by_name(session, normalized)
        if species is None:
            unresolved_species += 1
            print(f"  no match for species '{species_name}' -- skipping its moveset")
            continue

        # Abilities/Items/Spreads/Tera Types/Happiness all break down the SAME weighted
        # total (Gen 1 has no real abilities/items to vary, so every entry in those
        # categories is a single dummy value) -- that total, not "Raw count" (an
        # unweighted battle count on a different scale), is the correct denominator for
        # turning a move's weighted count into a real usage_percent.
        weighted_total = sum(entry["Abilities"].values())
        if weighted_total <= 0:
            continue

        for raw_slug, weighted_count in entry["Moves"].items():
            # A move can appear with a literal weighted count of 0 -- the export
            # includes it structurally even though no real team in this snapshot ran
            # it. That's not usage data, just padding, so it's never stored.
            if weighted_count <= 0:
                continue

            slug = MOVE_SLUG_ALIASES.get(raw_slug, raw_slug)
            move_id = move_lookup.get(slug)
            if move_id is None:
                unresolved_moves += 1
                continue

            key = (species.species_id, move_id)
            if key in existing_keys:
                already_present += 1
                continue

            usage_percent = weighted_count / weighted_total * 100
            session.add(
                Gen1ouUsageMove(species_id=species.species_id, move_id=move_id, usage_percent=usage_percent)
            )
            existing_keys.add(key)
            inserted += 1

    session.commit()
    print(
        f"Done. {inserted} inserted, {already_present} already present, "
        f"{unresolved_species} species not matched, {unresolved_moves} moves not matched."
    )


def main() -> None:
    session = get_session(get_engine())
    try:
        populate_gen1ou_usage(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
