"""add conversations and feedback tables

Revision ID: 7c3dbd3419b0
Revises: f37eefb7922f
Create Date: 2026-08-26 10:37:21.672380

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c3dbd3419b0'
down_revision: Union[str, Sequence[str], None] = 'f37eefb7922f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('conversations',
    sa.Column('conversation_id', sa.String(), nullable=False),
    sa.Column('question', sa.String(), nullable=False),
    sa.Column('answer', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.PrimaryKeyConstraint('conversation_id')
    )
    op.create_table('feedback',
    sa.Column('feedback_id', sa.Integer(), nullable=False),
    sa.Column('conversation_id', sa.String(), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.CheckConstraint('rating IN (-1, 1)', name='ck_feedback_rating'),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.conversation_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('feedback_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('feedback')
    op.drop_table('conversations')
