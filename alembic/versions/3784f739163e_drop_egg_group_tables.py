"""drop egg group tables

Revision ID: 3784f739163e
Revises: 417d5b98090d
Create Date: 2026-09-01 15:16:19.974970

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3784f739163e'
down_revision: Union[str, Sequence[str], None] = '417d5b98090d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table('pokemon_egg_groups')
    op.drop_table('egg_groups')


def downgrade() -> None:
    """Downgrade schema."""
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
