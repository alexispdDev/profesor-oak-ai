"""seed missing game versions for location encounters

Revision ID: 378d87097aa1
Revises: ed4cb632557f
Create Date: 2026-08-13 11:04:38.895048

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '378d87097aa1'
down_revision: Union[str, Sequence[str], None] = 'ed4cb632557f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_GAME_VERSIONS = [
    # Original Japanese releases, absent from the initial seed migration's version list.
    ("red-japan", 1),
    ("green-japan", 1),
    ("blue-japan", 1),
    # Pokemon XD: Gale of Darkness (GameCube), contemporary with Gen 3.
    ("xd", 3),
    # Sword/Shield DLC expansions -- PokeAPI models each as its own "version".
    ("the-isle-of-armor-sword", 8),
    ("the-isle-of-armor-shield", 8),
    ("the-crown-tundra-sword", 8),
    ("the-crown-tundra-shield", 8),
]

game_versions_table = sa.table(
    "game_versions", sa.column("name", sa.String), sa.column("generation", sa.Integer)
)


def upgrade() -> None:
    """Upgrade schema."""
    op.bulk_insert(
        game_versions_table,
        [{"name": name, "generation": gen} for name, gen in NEW_GAME_VERSIONS],
    )


def downgrade() -> None:
    """Downgrade schema."""
    names = [name for name, _ in NEW_GAME_VERSIONS]
    op.execute(game_versions_table.delete().where(game_versions_table.c.name.in_(names)))
