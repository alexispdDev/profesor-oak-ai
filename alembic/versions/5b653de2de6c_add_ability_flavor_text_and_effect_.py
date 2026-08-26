"""add ability flavor text and effect changes tables

Revision ID: 5b653de2de6c
Revises: 8e12f496be0f
Create Date: 2026-08-26 08:27:36.660345

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b653de2de6c'
down_revision: Union[str, Sequence[str], None] = '8e12f496be0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('ability_flavor_text',
    sa.Column('ability_id', sa.Integer(), nullable=False),
    sa.Column('version_group', sa.String(), nullable=False),
    sa.Column('flavor_text', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['ability_id'], ['abilities.ability_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('ability_id', 'version_group')
    )
    op.create_table('ability_effect_changes',
    sa.Column('ability_id', sa.Integer(), nullable=False),
    sa.Column('version_group', sa.String(), nullable=False),
    sa.Column('effect', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['ability_id'], ['abilities.ability_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('ability_id', 'version_group')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('ability_effect_changes')
    op.drop_table('ability_flavor_text')
