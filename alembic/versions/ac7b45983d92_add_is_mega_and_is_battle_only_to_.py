"""add is_mega and is_battle_only to pokemon_forms

Revision ID: ac7b45983d92
Revises: 378d87097aa1
Create Date: 2026-08-25 10:40:20.735590

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac7b45983d92'
down_revision: Union[str, Sequence[str], None] = '378d87097aa1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # pokemon_forms has a SQLite GENERATED (STORED) column, base_stat_total.
    # op.batch_alter_table's recreate strategy copies data via "INSERT INTO new_table
    # SELECT ... FROM old_table", which fails with "cannot INSERT into generated column"
    # since SQLite forbids writing to GENERATED columns even when the value round-trips
    # from itself. Plain op.add_column (not batch) issues a native SQLite
    # "ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT ..." instead, which SQLite supports
    # directly with no table recreate, sidestepping the issue entirely.
    op.add_column('pokemon_forms', sa.Column('is_mega', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('pokemon_forms', sa.Column('is_battle_only', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    # Same reasoning as upgrade(): avoid batch_alter_table's recreate strategy, which
    # chokes on the generated base_stat_total column. Plain op.drop_column uses SQLite's
    # native ALTER TABLE ... DROP COLUMN instead.
    op.drop_column('pokemon_forms', 'is_battle_only')
    op.drop_column('pokemon_forms', 'is_mega')
