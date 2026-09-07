"""add gen1ou usage moves table

Revision ID: ceb5e9156e07
Revises: b2c3d4e5f6a7
Create Date: 2026-09-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ceb5e9156e07'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Adds gen1ou_usage_moves: per-species, per-move real usage_percent from a single
    Smogon Generation 1 OU usage-stats snapshot (see pokemon_raw_data/gen1ou-1760.json).
    Only 62 of 151 Gen-1 species have any row here (that snapshot's coverage) -- this is
    also how team_builder.viable_pool identifies real-usage pool membership, with no
    separate species-level usage table needed.
    """
    op.create_table(
        "gen1ou_usage_moves",
        sa.Column("species_id", sa.Integer(), nullable=False),
        sa.Column("move_id", sa.Integer(), nullable=False),
        sa.Column("usage_percent", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["species_id"], ["pokemon_species.species_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["move_id"], ["moves.move_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("species_id", "move_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("gen1ou_usage_moves")
