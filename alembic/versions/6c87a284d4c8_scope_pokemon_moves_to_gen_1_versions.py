"""scope pokemon moves to gen 1 versions

Revision ID: 6c87a284d4c8
Revises: 388322d1a0ff
Create Date: 2026-09-02 01:32:44.836794

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6c87a284d4c8'
down_revision: Union[str, Sequence[str], None] = '388322d1a0ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    pokemon_moves currently includes every move learnable in ANY generation through
    the present -- insert_forms's move-learning loop never checked version_group,
    only learn_method. Unlike every other correction this session, pokemon_moves has
    no version column at all, so the fix can't be derived from sibling tables already
    in the database -- it has to be re-parsed from pokemon_raw_data/pokemon.jsonl
    directly, the same source populate.py itself reads. Also, simply wiping the table
    and re-running populate.py would NOT repopulate it: populate_species_and_forms
    skips a species entirely once its PokemonSpecies row exists, so insert_forms (and
    its move-loop) never runs again for already-ingested species.

    Given that, this is a deliberate, one-time exception to this project's "every
    migration is pure SQL" convention: it imports and calls the corrected ingestion
    helpers directly, guaranteeing the live DB ends up identical to what a fresh
    install now produces, rather than hand-duplicating ~4,200 rows of literal data
    (the scale that made the 56-row move-correction migration's literal-values
    approach reasonable doesn't extend here).

    Also cleans up moves that no longer have any learnset reference now that
    movesets are Gen-1-scoped (Overheat, Curse, Dragon Pulse, etc. -- later-
    generation-only moves that were only ever reachable via a non-Gen-1 game),
    same orphan-cleanup pattern as d515bb238c40. Expected: moves 529 -> 164.
    """
    from sqlalchemy.orm import Session

    from profesor_oak_ai.db.models import Move, PokemonType
    from profesor_oak_ai.ingestion.populate import (
        OfflineData,
        RAW_DATA_DIR,
        backfill_gen1_moves,
        load_name_id_map,
        load_offline_lookup,
    )

    bind = op.get_bind()
    session = Session(bind=bind)

    op.execute("DELETE FROM pokemon_moves")

    type_map = load_name_id_map(session, PokemonType, "type_id")
    move_cache = load_name_id_map(session, Move, "move_id")
    offline = OfflineData(
        types=load_offline_lookup(RAW_DATA_DIR / "type.jsonl"),
        moves=load_offline_lookup(RAW_DATA_DIR / "move.jsonl"),
        species=load_offline_lookup(RAW_DATA_DIR / "pokemon-species.jsonl", key="id"),
        pokemon=load_offline_lookup(RAW_DATA_DIR / "pokemon.jsonl"),
    )
    backfill_gen1_moves(session, type_map, move_cache, offline)
    session.commit()

    op.execute(
        "DELETE FROM moves WHERE move_id NOT IN (SELECT DISTINCT move_id FROM pokemon_moves)"
    )


def downgrade() -> None:
    """Downgrade schema.

    No-op: the deleted rows aren't reversible without re-running the ingestion
    pipeline from scratch, matching this project's other data-only downgrades.
    """
    pass
