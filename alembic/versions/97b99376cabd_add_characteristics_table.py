"""add characteristics table

Revision ID: 97b99376cabd
Revises: 2304e950e9a3
Create Date: 2026-08-26 07:53:56.028849

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '97b99376cabd'
down_revision: Union[str, Sequence[str], None] = '2304e950e9a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('characteristics',
    sa.Column('characteristic_id', sa.Integer(), nullable=False),
    sa.Column('highest_stat', sa.String(), nullable=False),
    sa.Column('gene_modulo', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('characteristic_id')
    )
    op.create_index(
        'ux_characteristics_stat_modulo',
        'characteristics',
        ['highest_stat', 'gene_modulo'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ux_characteristics_stat_modulo', table_name='characteristics')
    op.drop_table('characteristics')
