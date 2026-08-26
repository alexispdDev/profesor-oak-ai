"""add species_evolutions table

Revision ID: 20a7571b5d6b
Revises: e84f57894150
Create Date: 2026-08-25 21:15:36.735223

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20a7571b5d6b'
down_revision: Union[str, Sequence[str], None] = 'e84f57894150'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'species_evolutions',
        sa.Column('evolution_id', sa.Integer(), nullable=False),
        sa.Column('species_id', sa.Integer(), nullable=False),
        sa.Column('trigger_type', sa.String(), nullable=False),
        sa.Column('version_group', sa.String(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('min_level', sa.Integer(), nullable=True),
        sa.Column('item_id', sa.Integer(), nullable=True),
        sa.Column('held_item_id', sa.Integer(), nullable=True),
        sa.Column('known_move_id', sa.Integer(), nullable=True),
        sa.Column('min_happiness', sa.Integer(), nullable=True),
        sa.Column('time_of_day', sa.String(), nullable=True),
        sa.Column('relative_physical_stats', sa.Integer(), nullable=True),
        sa.Column('region', sa.String(), nullable=True),
        sa.Column('base_form_id', sa.Integer(), nullable=True),
        sa.Column('evolved_form_id', sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "trigger_type IN ('level-up', 'trade', 'use-item')",
            name='ck_species_evolutions_trigger_type',
        ),
        sa.ForeignKeyConstraint(['species_id'], ['pokemon_species.species_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['item_id'], ['items.item_id']),
        sa.ForeignKeyConstraint(['held_item_id'], ['items.item_id']),
        sa.ForeignKeyConstraint(['known_move_id'], ['moves.move_id']),
        sa.ForeignKeyConstraint(['base_form_id'], ['pokemon_forms.form_id']),
        sa.ForeignKeyConstraint(['evolved_form_id'], ['pokemon_forms.form_id']),
        sa.PrimaryKeyConstraint('evolution_id'),
    )
    op.create_index(
        'ux_species_evolutions_natural_key',
        'species_evolutions',
        ['species_id', 'trigger_type', 'version_group', 'evolved_form_id', 'base_form_id'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ux_species_evolutions_natural_key', table_name='species_evolutions')
    op.drop_table('species_evolutions')
