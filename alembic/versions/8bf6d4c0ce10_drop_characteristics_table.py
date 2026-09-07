"""drop characteristics table

Revision ID: 8bf6d4c0ce10
Revises: 3784f739163e
Create Date: 2026-09-01 15:27:00.642420

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8bf6d4c0ce10'
down_revision: Union[str, Sequence[str], None] = '3784f739163e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table('characteristics')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('characteristics',
    sa.Column('characteristic_id', sa.Integer(), nullable=False),
    sa.Column('highest_stat', sa.String(), nullable=False),
    sa.Column('gene_modulo', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('characteristic_id')
    )
    op.create_index(
        'ux_characteristics_stat_modulo', 'characteristics', ['highest_stat', 'gene_modulo'], unique=True
    )
