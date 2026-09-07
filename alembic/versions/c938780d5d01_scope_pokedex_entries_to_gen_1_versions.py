"""scope pokedex entries to gen 1 versions

Revision ID: c938780d5d01
Revises: 983ad2aebe1d
Create Date: 2026-09-02 00:50:52.765774

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c938780d5d01'
down_revision: Union[str, Sequence[str], None] = '983ad2aebe1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    get_representative_entry() was picking the LATEST version's flavor text
    (ORDER BY version_id DESC over all 4,578 rows spanning Gen 1-8), not a Gen-1
    one -- confirmed live, Bulbasaur's description was being sourced from
    Sword/Shield. Only 453 of 4,578 rows (9.9%) are actually Gen 1 (red/blue/
    yellow); all 151 species have full Gen-1 coverage, so no fallback is needed.
    No version-selection feature depends on the broader data (unlike
    pokemon_location_encounters), so scoped down entirely rather than just fixing
    the query -- get_representative_entry's existing ORDER BY version_id DESC
    then naturally picks Yellow (version_id 3, the highest among the 3 remaining
    Gen-1 versions) with no code change needed there.
    """
    op.execute("""
        DELETE FROM pokedex_entries
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
