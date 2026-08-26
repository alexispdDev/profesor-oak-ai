"""add pokedex_numbers table

Revision ID: dd444dd44add
Revises: 5e9d15e8d735
Create Date: 2026-08-26 08:08:42.847136

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dd444dd44add'
down_revision: Union[str, Sequence[str], None] = '5e9d15e8d735'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('pokedex_numbers',
    sa.Column('species_id', sa.Integer(), nullable=False),
    sa.Column('pokedex', sa.String(), nullable=False),
    sa.Column('entry_number', sa.Integer(), nullable=False),
    sa.CheckConstraint("pokedex IN ('national', 'kanto')", name='ck_pokedex_numbers_pokedex'),
    sa.ForeignKeyConstraint(['species_id'], ['pokemon_species.species_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('species_id', 'pokedex')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('pokedex_numbers')
