"""add habitats and pokemon_habitats tables

Revision ID: e84f57894150
Revises: ac7b45983d92
Create Date: 2026-08-25 11:03:55.602117

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e84f57894150'
down_revision: Union[str, Sequence[str], None] = 'ac7b45983d92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('habitats',
    sa.Column('habitat_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('habitat_id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('pokemon_habitats',
    sa.Column('species_id', sa.Integer(), nullable=False),
    sa.Column('habitat_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['habitat_id'], ['habitats.habitat_id'], ),
    sa.ForeignKeyConstraint(['species_id'], ['pokemon_species.species_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('species_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('pokemon_habitats')
    op.drop_table('habitats')
