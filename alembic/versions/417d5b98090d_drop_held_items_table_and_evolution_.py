"""drop held items table and evolution held_item_id column

Revision ID: 417d5b98090d
Revises: 7275e039b3e3
Create Date: 2026-09-01 14:58:24.297018

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '417d5b98090d'
down_revision: Union[str, Sequence[str], None] = '7275e039b3e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table('pokemon_held_items')
    # Unlike generation/gender_rate/shape (plain columns with no constraint attached),
    # held_item_id is referenced by its own FOREIGN KEY clause in the table
    # definition -- SQLite's native ALTER TABLE ... DROP COLUMN refuses to drop a
    # column named in the table's own FK definition ("unknown column ... in foreign
    # key definition"), so batch_alter_table's recreate-the-table strategy is required
    # here, unlike the plain-drop_column convention used elsewhere in this project.
    with op.batch_alter_table('species_evolutions', schema=None) as batch_op:
        batch_op.drop_column('held_item_id')


def downgrade() -> None:
    """Downgrade schema."""
    # Plain add_column can't restore the original FK to items.item_id (SQLite has no
    # native ALTER TABLE ADD CONSTRAINT) without batch_alter_table's recreate path --
    # same trade-off already accepted elsewhere in this project for downgrade paths.
    op.add_column('species_evolutions', sa.Column('held_item_id', sa.Integer(), nullable=True))
    op.create_table('pokemon_held_items',
    sa.Column('form_id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('rarity', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['form_id'], ['pokemon_forms.form_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['item_id'], ['items.item_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['version_id'], ['game_versions.version_id'], ),
    sa.PrimaryKeyConstraint('form_id', 'item_id', 'version_id')
    )
