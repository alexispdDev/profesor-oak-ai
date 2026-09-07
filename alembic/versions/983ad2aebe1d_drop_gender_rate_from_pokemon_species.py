"""drop gender rate from pokemon species

Revision ID: 983ad2aebe1d
Revises: 5b9e1e47908f
Create Date: 2026-09-02 00:45:50.200058

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '983ad2aebe1d'
down_revision: Union[str, Sequence[str], None] = '5b9e1e47908f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Gender as a mechanic didn't exist until Generation 2 -- Gen 1 Pokemon had no
    male/female distinction at all. Same category as abilities/natures/egg
    groups/characteristics/shapes: a later-generation mechanic with zero agent-
    layer consumers (confirmed via agent_tool_gaps.txt, part of the never-built
    "breeding info tool" sketch).
    """
    op.drop_column('pokemon_species', 'gender_rate')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'pokemon_species',
        sa.Column('gender_rate', sa.Integer(), nullable=False, server_default='-1'),
    )
