"""remove evolutions with out of scope baby parent

Revision ID: 5b9e1e47908f
Revises: 29c35b5e4695
Create Date: 2026-09-01 21:39:33.427683

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b9e1e47908f'
down_revision: Union[str, Sequence[str], None] = '29c35b5e4695'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    These 10 species' only species_evolutions row described evolving from a Gen
    2+ "baby" Pokemon (Pichu, Cleffa, Igglybuff, Tyrogue, Mime Jr., Smoochum,
    Elekid, Magby, Munchlax) that didn't exist in Gen 1 -- in the original games
    each of these 10 was a standalone, non-evolving species. version_group is not
    a reliable signal for this (PokeAPI mislabels Tyrogue->Hitmonlee/Hitmonchan as
    "red-blue" despite Tyrogue being Gen 2); identified instead by walking the raw
    evolution-chain data and checking whether each evolution's immediate parent
    species is itself one of the 151 in-scope species.
    """
    op.execute("""
        DELETE FROM species_evolutions
        WHERE species_id IN (
            SELECT species_id FROM pokemon_species
            WHERE name IN (
                'pikachu', 'clefairy', 'jigglypuff', 'hitmonlee', 'hitmonchan',
                'mr-mime', 'jynx', 'electabuzz', 'magmar', 'snorlax'
            )
        )
    """)


def downgrade() -> None:
    """Downgrade schema.

    No-op: the deleted rows aren't reversible without re-running the ingestion
    pipeline from scratch, matching this project's other data-only downgrades.
    """
    pass
