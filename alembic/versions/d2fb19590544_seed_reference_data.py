"""seed reference data

Revision ID: d2fb19590544
Revises: 880f1d8b7240
Create Date: 2026-08-05 15:43:05.427365

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2fb19590544'
down_revision: Union[str, Sequence[str], None] = '880f1d8b7240'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TYPE_NAMES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
]

GAME_VERSIONS = [
    ("red", 1), ("blue", 1), ("yellow", 1),
    ("gold", 2), ("silver", 2), ("crystal", 2),
    ("ruby", 3), ("sapphire", 3), ("emerald", 3), ("firered", 3), ("leafgreen", 3),
    ("diamond", 4), ("pearl", 4), ("platinum", 4), ("heartgold", 4), ("soulsilver", 4),
    ("black", 5), ("white", 5), ("black-2", 5), ("white-2", 5),
    ("x", 6), ("y", 6), ("omega-ruby", 6), ("alpha-sapphire", 6),
    ("sun", 7), ("moon", 7), ("ultra-sun", 7), ("ultra-moon", 7),
    ("lets-go-pikachu", 7), ("lets-go-eevee", 7),
    ("sword", 8), ("shield", 8), ("brilliant-diamond", 8), ("shining-pearl", 8),
    ("legends-arceus", 8),
    ("scarlet", 9), ("violet", 9),
]

types_table = sa.table("types", sa.column("name", sa.String))
game_versions_table = sa.table(
    "game_versions", sa.column("name", sa.String), sa.column("generation", sa.Integer)
)


def upgrade() -> None:
    """Upgrade schema."""
    op.bulk_insert(types_table, [{"name": name} for name in TYPE_NAMES])
    op.bulk_insert(
        game_versions_table,
        [{"name": name, "generation": gen} for name, gen in GAME_VERSIONS],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(game_versions_table.delete())
    op.execute(types_table.delete())
