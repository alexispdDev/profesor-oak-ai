"""add generation to abilities

Revision ID: 8e12f496be0f
Revises: 32d68b447220
Create Date: 2026-08-26 08:22:40.042102

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e12f496be0f'
down_revision: Union[str, Sequence[str], None] = '32d68b447220'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Plain (non-batch) add_column, same as is_mega/gender_rate -- avoids
    # batch_alter_table's recreate path uniformly for every ALTER in this project.
    op.add_column('abilities', sa.Column('generation', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('abilities', 'generation')
