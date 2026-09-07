"""correct gen1 counter effect text to normal fighting only

Revision ID: 93dc9c2f5037
Revises: 53ea0ef77241
Create Date: 2026-09-02 15:40:16.187061

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '93dc9c2f5037'
down_revision: Union[str, Sequence[str], None] = '53ea0ef77241'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Same class of bug as 53ea0ef77241's Low Kick fix, caught in this Pokédex's own
    get_move_info output: Counter's stored effect_description ("Inflicts twice the
    damage the user received from the last physical hit it took") describes a
    modern, broad "physical category" concept that doesn't exist in Generation 1 at
    all. Confirmed via Bulbapedia: in Generation I, Counter is hardcoded to check
    whether the last hit was specifically a Normal-type or Fighting-type attack --
    not a "physical move" in any generic sense. A physical-feeling move of any other
    type (Earthquake/Ground, Rock Slide/Rock, etc.) cannot be countered in Gen 1 at
    all; this restriction was loosened to "all physical moves" starting in
    Generation II.

    PokeAPI records no effect_changes entries for Counter (same as Low Kick), so this
    can only be hand-corrected -- added to GEN1_MOVE_EFFECT_CORRECTIONS in
    populate.py, following the same per-entry verification discipline as the
    jump-kick/high-jump-kick and low-kick corrections before it.
    """
    from sqlalchemy.orm import Session

    from profesor_oak_ai.db.models import Move
    from profesor_oak_ai.ingestion.populate import GEN1_MOVE_EFFECT_CORRECTIONS

    bind = op.get_bind()
    session = Session(bind=bind)

    effect_description, effect_chance = GEN1_MOVE_EFFECT_CORRECTIONS["counter"]
    move = session.scalar(sa.select(Move).where(Move.name == "counter"))
    if move is not None:
        move.effect_description = effect_description
        move.effect_chance = effect_chance

    session.commit()


def downgrade() -> None:
    """Downgrade schema.

    No-op: matches this project's other data-only downgrades -- not reversible
    without re-running the ingestion pipeline from scratch.
    """
    pass
