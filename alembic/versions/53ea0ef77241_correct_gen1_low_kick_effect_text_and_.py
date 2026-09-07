"""correct gen1 low kick effect text and flinch chance

Revision ID: 53ea0ef77241
Revises: c58a1de2c59c
Create Date: 2026-09-02 15:19:03.354389

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '53ea0ef77241'
down_revision: Union[str, Sequence[str], None] = 'c58a1de2c59c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Same class of bug as c58a1de2c59c's Jump Kick/High Jump Kick fix, caught in this
    Pokédex's own list_moves_by_type tool output: Low Kick's stored effect_description
    ("Inflicts more damage to heavier targets, with a maximum of 120 power") is the
    Generation III+ weight-based mechanic, and effect_chance was None. Confirmed via
    Bulbapedia: in Generation I, Low Kick was simply "a power of 50, an accuracy of
    90%, and has a 30% chance of causing the target to flinch" -- no weight scaling at
    all. The power/accuracy fields (50/90) were already correct (d515bb238c40 already
    pulled them from PokeAPI's ruby-sapphire past_values entry, which happens to
    predate the Generation III weight-scaling change too), but effect_chance/
    effect_description were never touched.

    Unlike jump-kick/high-jump-kick, PokeAPI records NO effect_changes entries at all
    for Low Kick, so even the (reverted) general effect_changes-based heuristic
    wouldn't have caught this -- confirmed only by checking Bulbapedia directly, hand-
    added to GEN1_MOVE_EFFECT_CORRECTIONS in populate.py (now (description, chance)
    tuples instead of bare strings, c58a1de2c59c updated to match) alongside the
    jump-kick/high-jump-kick entries, following the same per-entry verification
    discipline. effect_chance=30 is corroborated by this dataset's own
    already-correct "chance to flinch" moves (Rolling Kick, Stomp, Headbutt), all
    stored with effect_chance=30.
    """
    from sqlalchemy.orm import Session

    from profesor_oak_ai.db.models import Move
    from profesor_oak_ai.ingestion.populate import GEN1_MOVE_EFFECT_CORRECTIONS

    bind = op.get_bind()
    session = Session(bind=bind)

    effect_description, effect_chance = GEN1_MOVE_EFFECT_CORRECTIONS["low-kick"]
    move = session.scalar(sa.select(Move).where(Move.name == "low-kick"))
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
