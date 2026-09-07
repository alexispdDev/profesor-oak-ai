"""drop pokemon_enrichment table

Revision ID: 8a84b57c3ff3
Revises: c2c6f1e0710c
Create Date: 2026-09-01 12:42:05.616073

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a84b57c3ff3'
down_revision: Union[str, Sequence[str], None] = 'c2c6f1e0710c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table('pokemon_enrichment')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('pokemon_enrichment',
    sa.Column('form_id', sa.Integer(), nullable=False),
    sa.Column('physical_traits', sa.String(), nullable=True),
    sa.Column('model_name', sa.String(), nullable=True),
    sa.Column('generated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.ForeignKeyConstraint(['form_id'], ['pokemon_forms.form_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('form_id')
    )
