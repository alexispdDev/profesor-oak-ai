"""add grounding source to conversations

Revision ID: 690b8a8fb806
Revises: 3d5a9dc5c679
Create Date: 2026-08-31 17:55:14.380402

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '690b8a8fb806'
down_revision: Union[str, Sequence[str], None] = '3d5a9dc5c679'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("conversations", sa.Column("grounding_source", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("conversations", "grounding_source")
