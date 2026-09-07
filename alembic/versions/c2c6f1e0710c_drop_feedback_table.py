"""drop feedback table

Revision ID: c2c6f1e0710c
Revises: 690b8a8fb806
Create Date: 2026-08-31 18:11:18.339469

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2c6f1e0710c'
down_revision: Union[str, Sequence[str], None] = '690b8a8fb806'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table('feedback')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('feedback',
    sa.Column('feedback_id', sa.Integer(), nullable=False),
    sa.Column('conversation_id', sa.String(), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.CheckConstraint('rating IN (-1, 1)', name='ck_feedback_rating'),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.conversation_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('feedback_id')
    )
