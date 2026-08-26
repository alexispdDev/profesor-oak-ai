"""add natures table

Revision ID: 2304e950e9a3
Revises: b940b6074bd0
Create Date: 2026-08-26 07:51:01.868416

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2304e950e9a3'
down_revision: Union[str, Sequence[str], None] = 'b940b6074bd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('natures',
    sa.Column('nature_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('increased_stat', sa.String(), nullable=True),
    sa.Column('decreased_stat', sa.String(), nullable=True),
    sa.Column('likes_flavor', sa.String(), nullable=True),
    sa.Column('hates_flavor', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('nature_id'),
    sa.UniqueConstraint('name')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('natures')
