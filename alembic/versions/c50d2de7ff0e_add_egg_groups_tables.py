"""add egg groups tables

Revision ID: c50d2de7ff0e
Revises: a978386a73e4
Create Date: 2026-08-25 21:28:32.746446

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c50d2de7ff0e'
down_revision: Union[str, Sequence[str], None] = 'a978386a73e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('egg_groups',
    sa.Column('egg_group_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('egg_group_id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('pokemon_egg_groups',
    sa.Column('species_id', sa.Integer(), nullable=False),
    sa.Column('egg_group_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['egg_group_id'], ['egg_groups.egg_group_id'], ),
    sa.ForeignKeyConstraint(['species_id'], ['pokemon_species.species_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('species_id', 'egg_group_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('pokemon_egg_groups')
    op.drop_table('egg_groups')
