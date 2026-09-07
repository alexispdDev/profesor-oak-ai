"""scope pokemon_game_indices to gen 1 versions

Revision ID: d85318f5c20d
Revises: 01b2fa8492ba
Create Date: 2026-09-01 17:27:05.844458

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd85318f5c20d'
down_revision: Union[str, Sequence[str], None] = '01b2fa8492ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Unlike abilities/egg groups/characteristics/dark-steel-fairy, this data isn't
    anachronistic -- Gen 1 games had their own internal per-species index numbers
    too, and those rows (red/blue/yellow, 453 of 5,313) are genuinely correct. Only
    narrowing scope: drop the same index concept tracked across every later game
    version, which isn't wrong, just out of scope for a Gen-1-only app.
    """
    op.execute("""
        DELETE FROM pokemon_game_indices
        WHERE version_id NOT IN (
            SELECT version_id FROM game_versions WHERE name IN ('red', 'blue', 'yellow')
        )
    """)


def downgrade() -> None:
    """Downgrade schema.

    No-op: the deleted rows aren't reversible without re-running the ingestion
    pipeline from scratch, matching this project's other data-only downgrades.
    """
    pass
