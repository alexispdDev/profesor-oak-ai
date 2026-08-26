"""add past_type_efficacy table

Revision ID: 32d68b447220
Revises: dd444dd44add
Create Date: 2026-08-26 08:16:34.373145

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32d68b447220'
down_revision: Union[str, Sequence[str], None] = 'dd444dd44add'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('past_type_efficacy',
    sa.Column('generation', sa.Integer(), nullable=False),
    sa.Column('damage_type_id', sa.Integer(), nullable=False),
    sa.Column('target_type_id', sa.Integer(), nullable=False),
    sa.Column('damage_factor', sa.Float(), nullable=False),
    sa.CheckConstraint('damage_factor IN (0, 0.5, 1, 2)', name='ck_past_type_efficacy_damage_factor'),
    sa.ForeignKeyConstraint(['damage_type_id'], ['types.type_id'], ),
    sa.ForeignKeyConstraint(['target_type_id'], ['types.type_id'], ),
    sa.PrimaryKeyConstraint('generation', 'damage_type_id', 'target_type_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('past_type_efficacy')
