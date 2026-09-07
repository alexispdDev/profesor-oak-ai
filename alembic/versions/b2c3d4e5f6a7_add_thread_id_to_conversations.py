"""add thread_id to conversations

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = '93dc9c2f5037'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Adds thread_id to conversations, enabling multi-turn conversation memory:
    rows sharing a thread_id are one ongoing exchange, reconstructed as
    "WHERE thread_id = ? ORDER BY created_at" rather than a separate table.
    Existing rows are backfilled with thread_id = their own conversation_id --
    each historical single-turn exchange becomes its own one-row thread, which
    is exactly what it was.
    """
    op.add_column("conversations", sa.Column("thread_id", sa.String(), nullable=True))
    op.execute("UPDATE conversations SET thread_id = conversation_id WHERE thread_id IS NULL")
    op.create_index("ix_conversations_thread_id", "conversations", ["thread_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_conversations_thread_id", table_name="conversations")
    op.drop_column("conversations", "thread_id")
