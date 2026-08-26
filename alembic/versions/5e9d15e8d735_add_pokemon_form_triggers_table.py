"""add pokemon_form_triggers table

Revision ID: 5e9d15e8d735
Revises: 97b99376cabd
Create Date: 2026-08-26 08:04:17.995113

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e9d15e8d735'
down_revision: Union[str, Sequence[str], None] = '97b99376cabd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('pokemon_form_triggers',
    sa.Column('form_id', sa.Integer(), nullable=False),
    sa.Column('trigger_type', sa.String(), nullable=False),
    sa.Column('trigger_name', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['form_id'], ['pokemon_forms.form_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('form_id', 'trigger_type')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('pokemon_form_triggers')
