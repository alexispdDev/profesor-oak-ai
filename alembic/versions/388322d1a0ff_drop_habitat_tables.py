"""drop habitat tables

Revision ID: 388322d1a0ff
Revises: d515bb238c40
Create Date: 2026-09-02 01:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '388322d1a0ff'
down_revision: Union[str, Sequence[str], None] = 'd515bb238c40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Habitat categorization (search Pokemon by habitat in the Pokedex app) was
    introduced in Generation 3 (Ruby/Sapphire) as a Pokedex search feature --
    same category as shape (dropped in 29c35b5e4695), unlike growth_rate which
    is real Gen-1 gameplay math (the EXP curve) and stays untouched. No
    generation field in PokeAPI's raw data and no historical override to
    correct to, so full removal is the only consistent option.
    """
    op.drop_table('pokemon_habitats')
    op.drop_table('habitats')


def downgrade() -> None:
    """Downgrade schema."""
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
