"""add growth rates and levels tables

Revision ID: a978386a73e4
Revises: 20a7571b5d6b
Create Date: 2026-08-25 21:24:08.152218

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a978386a73e4'
down_revision: Union[str, Sequence[str], None] = '20a7571b5d6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('growth_rates',
    sa.Column('growth_rate_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('growth_rate_id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('pokemon_growth_rates',
    sa.Column('species_id', sa.Integer(), nullable=False),
    sa.Column('growth_rate_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['growth_rate_id'], ['growth_rates.growth_rate_id'], ),
    sa.ForeignKeyConstraint(['species_id'], ['pokemon_species.species_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('species_id')
    )
    op.create_table('growth_rate_levels',
    sa.Column('growth_rate_id', sa.Integer(), nullable=False),
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('experience', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['growth_rate_id'], ['growth_rates.growth_rate_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('growth_rate_id', 'level')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('growth_rate_levels')
    op.drop_table('pokemon_growth_rates')
    op.drop_table('growth_rates')
