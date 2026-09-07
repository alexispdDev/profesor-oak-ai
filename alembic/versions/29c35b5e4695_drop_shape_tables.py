"""drop shape tables

Revision ID: 29c35b5e4695
Revises: bc4926d1127f
Create Date: 2026-09-01 21:16:05.124126

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '29c35b5e4695'
down_revision: Union[str, Sequence[str], None] = 'bc4926d1127f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Body-shape categorization (search Pokemon by shape in the Pokedex app) has no
    generation field in PokeAPI's raw data at all, unlike types/abilities/moves --
    it was introduced as a Pokedex search feature well after Gen 1. With no
    historical override to correct to (unlike types/stats), full removal is the
    only consistent option, same as abilities/egg-groups/characteristics/natures.
    """
    op.drop_table('pokemon_shapes')
    op.drop_table('shapes')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('shapes',
    sa.Column('shape_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('awesome_name', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('shape_id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('pokemon_shapes',
    sa.Column('species_id', sa.Integer(), nullable=False),
    sa.Column('shape_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['shape_id'], ['shapes.shape_id'], ),
    sa.ForeignKeyConstraint(['species_id'], ['pokemon_species.species_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('species_id')
    )
