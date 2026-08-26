"""add gender_rate to pokemon_species

Revision ID: b940b6074bd0
Revises: c50d2de7ff0e
Create Date: 2026-08-25 21:33:16.894202

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b940b6074bd0'
down_revision: Union[str, Sequence[str], None] = 'c50d2de7ff0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Plain (non-batch) add_column, same as is_mega/is_battle_only: pokemon_species
    # has no GENERATED column, so this isn't strictly required here, but it avoids
    # batch_alter_table's recreate path uniformly for every ALTER in this project.
    op.add_column(
        'pokemon_species',
        sa.Column('gender_rate', sa.Integer(), nullable=False, server_default='-1'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('pokemon_species', 'gender_rate')
