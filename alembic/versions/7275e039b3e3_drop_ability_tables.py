"""drop ability tables

Revision ID: 7275e039b3e3
Revises: 8a84b57c3ff3
Create Date: 2026-09-01 14:03:58.478755

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7275e039b3e3'
down_revision: Union[str, Sequence[str], None] = '8a84b57c3ff3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table('pokemon_abilities')
    op.drop_table('ability_flavor_text')
    op.drop_table('ability_effect_changes')
    op.drop_table('pokemon_past_abilities')
    op.drop_table('abilities')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('abilities',
    sa.Column('ability_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('generation', sa.Integer(), server_default='0', nullable=False),
    sa.PrimaryKeyConstraint('ability_id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('pokemon_abilities',
    sa.Column('form_id', sa.Integer(), nullable=False),
    sa.Column('ability_id', sa.Integer(), nullable=False),
    sa.Column('slot', sa.Integer(), nullable=False),
    sa.Column('is_hidden', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['ability_id'], ['abilities.ability_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['form_id'], ['pokemon_forms.form_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('form_id', 'ability_id')
    )
    op.create_table('ability_flavor_text',
    sa.Column('ability_id', sa.Integer(), nullable=False),
    sa.Column('version_group', sa.String(), nullable=False),
    sa.Column('flavor_text', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['ability_id'], ['abilities.ability_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('ability_id', 'version_group')
    )
    op.create_table('ability_effect_changes',
    sa.Column('ability_id', sa.Integer(), nullable=False),
    sa.Column('version_group', sa.String(), nullable=False),
    sa.Column('effect', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['ability_id'], ['abilities.ability_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('ability_id', 'version_group')
    )
    op.create_table('pokemon_past_abilities',
    sa.Column('form_id', sa.Integer(), nullable=False),
    sa.Column('generation', sa.Integer(), nullable=False),
    sa.Column('slot', sa.Integer(), nullable=False),
    sa.Column('ability_id', sa.Integer(), nullable=False),
    sa.Column('is_hidden', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['ability_id'], ['abilities.ability_id'], ),
    sa.ForeignKeyConstraint(['form_id'], ['pokemon_forms.form_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('form_id', 'generation', 'slot')
    )
