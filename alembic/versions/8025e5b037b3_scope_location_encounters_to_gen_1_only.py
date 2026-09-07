"""scope location encounters to gen 1 only

Revision ID: 8025e5b037b3
Revises: 39627e4bbf10
Create Date: 2026-09-01 17:45:14.512135

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8025e5b037b3'
down_revision: Union[str, Sequence[str], None] = '39627e4bbf10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Unlike pokemon_game_indices, this table backed a real, working "ask about a
    later game" feature in get_pokemon_locations/get_location_info -- user
    decided to remove that capability and scope strictly to Gen 1 anyway.
    """
    op.execute("""
        DELETE FROM pokemon_location_encounters
        WHERE version_id NOT IN (SELECT version_id FROM game_versions WHERE generation = 1)
    """)
    # Locations with zero remaining encounters (i.e. exclusively later-game areas
    # like Lumiose City or a Galar Max Raid Den) are now orphaned.
    op.execute("""
        DELETE FROM locations
        WHERE location_id NOT IN (SELECT DISTINCT location_id FROM pokemon_location_encounters)
    """)


def downgrade() -> None:
    """Downgrade schema.

    No-op: the deleted rows aren't reversible without re-running the ingestion
    pipeline from scratch, matching this project's other data-only downgrades.
    """
    pass
