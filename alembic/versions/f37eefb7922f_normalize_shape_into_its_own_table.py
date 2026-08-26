"""normalize shape into its own table

Revision ID: f37eefb7922f
Revises: 5b653de2de6c
Create Date: 2026-08-26 09:12:12.043318

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f37eefb7922f'
down_revision: Union[str, Sequence[str], None] = '5b653de2de6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
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
    # Plain (non-batch) drop_column, same non-batch convention used for every ALTER
    # in this project -- pokemon_species has no generated column so batch mode
    # would work here too, but kept uniform.
    op.drop_column('pokemon_species', 'shape')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('pokemon_species', sa.Column('shape', sa.String(), nullable=True))
    op.drop_table('pokemon_shapes')
    op.drop_table('shapes')
