"""scope pokemon moves to red-blue vs yellow version groups

Revision ID: b4a66741b07d
Revises: 6c87a284d4c8
Create Date: 2026-09-02 11:45:43.220848

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4a66741b07d'
down_revision: Union[str, Sequence[str], None] = '6c87a284d4c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    pokemon_moves collapsed red-blue and yellow into one undifferentiated Gen-1
    learnset -- PokeAPI actually reports move learnsets per version_group (red-blue
    is one unit, yellow is the other; Red and Blue are always identical for move
    data, unlike location encounters), and the two genuinely differ for some
    species: Charizard's Fly is a well-known Yellow-only fix to a Red/Blue-era
    oversight, learnable starting in Yellow but not in Red/Blue at all. Without a
    version_group column, that fact was unrepresentable -- every ingested move
    looked equally available everywhere in Gen 1.

    Same one-time exception as 6c87a284d4c8: this can't be derived from sibling
    tables already in the database, so it re-parses pokemon_raw_data/pokemon.jsonl
    via the corrected ingestion helpers rather than hand-writing literal data.
    SQLite can't ALTER a primary key in place, so the table is dropped and
    recreated with version_group added to it, then fully repopulated.

    The set of distinct moves referenced doesn't change (same ALLOWED_MOVE_VERSION_GROUPS/
    ALLOWED_LEARN_METHODS filter as before, just no longer collapsed by version) --
    no orphan-move cleanup is needed this time.
    """
    op.drop_table('pokemon_moves')
    op.create_table(
        'pokemon_moves',
        sa.Column('form_id', sa.Integer(), nullable=False),
        sa.Column('move_id', sa.Integer(), nullable=False),
        sa.Column('learn_method', sa.String(), nullable=False),
        sa.Column('level_learned_at', sa.Integer(), nullable=False),
        sa.Column('version_group', sa.String(), nullable=False),
        sa.CheckConstraint(
            "learn_method IN ('level-up', 'machine', 'egg', 'tutor')",
            name='ck_pokemon_moves_learn_method',
        ),
        sa.CheckConstraint(
            "version_group IN ('red-blue', 'yellow')",
            name='ck_pokemon_moves_version_group',
        ),
        sa.ForeignKeyConstraint(['form_id'], ['pokemon_forms.form_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['move_id'], ['moves.move_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint(
            'form_id', 'move_id', 'learn_method', 'level_learned_at', 'version_group'
        ),
    )
    with op.batch_alter_table('pokemon_moves', schema=None) as batch_op:
        batch_op.create_index('idx_pokemon_moves_move', ['move_id'], unique=False)

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


def downgrade() -> None:
    """Downgrade schema.

    No-op: matches 6c87a284d4c8 and this project's other data-only downgrades --
    not reversible without re-running the ingestion pipeline from scratch.
    """
    pass
