"""add relevance and cost tracking to conversations

Revision ID: 3d5a9dc5c679
Revises: 7c3dbd3419b0
Create Date: 2026-08-26 11:34:38.142686

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d5a9dc5c679'
down_revision: Union[str, Sequence[str], None] = '7c3dbd3419b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("conversations", sa.Column("relevance", sa.String(), nullable=True))
    op.add_column("conversations", sa.Column("relevance_explanation", sa.String(), nullable=True))
    op.add_column("conversations", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("conversations", sa.Column("completion_tokens", sa.Integer(), nullable=True))
    op.add_column("conversations", sa.Column("total_tokens", sa.Integer(), nullable=True))
    op.add_column("conversations", sa.Column("cached_tokens", sa.Integer(), nullable=True))
    op.add_column("conversations", sa.Column("eval_prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("conversations", sa.Column("eval_completion_tokens", sa.Integer(), nullable=True))
    op.add_column("conversations", sa.Column("eval_total_tokens", sa.Integer(), nullable=True))
    op.add_column("conversations", sa.Column("cost", sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("conversations", "cost")
    op.drop_column("conversations", "eval_total_tokens")
    op.drop_column("conversations", "eval_completion_tokens")
    op.drop_column("conversations", "eval_prompt_tokens")
    op.drop_column("conversations", "cached_tokens")
    op.drop_column("conversations", "total_tokens")
    op.drop_column("conversations", "completion_tokens")
    op.drop_column("conversations", "prompt_tokens")
    op.drop_column("conversations", "relevance_explanation")
    op.drop_column("conversations", "relevance")
