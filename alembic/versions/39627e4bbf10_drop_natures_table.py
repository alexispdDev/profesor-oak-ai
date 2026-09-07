"""drop natures table

Revision ID: 39627e4bbf10
Revises: d85318f5c20d
Create Date: 2026-09-01 17:35:30.478727

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '39627e4bbf10'
down_revision: Union[str, Sequence[str], None] = 'd85318f5c20d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table('natures')


def downgrade() -> None:
    """Downgrade schema."""
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
