"""correct gen1 move effect text for generation-specific mechanics

Revision ID: c58a1de2c59c
Revises: b4a66741b07d
Create Date: 2026-09-02 12:46:40.859330

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c58a1de2c59c'
down_revision: Union[str, Sequence[str], None] = 'b4a66741b07d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    moves.effect_description was always populated from PokeAPI's top-level
    effect_entries, which holds each move's CURRENT (latest-generation) effect text --
    d515bb238c40 already corrected power/accuracy/pp/type for the 56 Gen-1 moves whose
    current-game values diverge from Gen 1, but never touched effect text, which can
    diverge the same way. Confirmed case, verified against Bulbapedia's move pages:
    Jump Kick/High Jump Kick's stored text ("If the user misses, it takes half the
    damage it would have inflicted in recoil") is the Generation III+ mechanic -- in
    Generation I, a miss instead deals a flat 1 HP of crash damage (Generation II's own
    mechanic, 1/8 of the would-be damage, is different from both and also not what's
    stored).

    An initial version of this migration tried to derive ALL Gen-1 moves' effect text
    automatically from PokeAPI's effect_changes field (which looks like it should
    generalize the same "earliest historical value wins" approach d515bb238c40 used for
    power/accuracy/pp). That was reverted after a test run produced confidently-wrong
    or misleadingly-incomplete text for over a dozen moves (e.g. Blizzard's earliest
    effect_changes entry is "Does not interact with Hail" -- true but anachronistic
    since Hail didn't exist before Generation III, and it silently dropped Blizzard's
    actually-defining Gen-1 fact, its freeze chance): effect_changes entries are
    inconsistently structured across moves -- sometimes a full replacement
    description, often just a narrow errata footnote -- so treating the earliest entry
    as reliably-complete Gen-1 text isn't sound. This migration instead applies only
    the hand-verified jump-kick/high-jump-kick correction (GEN1_MOVE_EFFECT_CORRECTIONS
    in populate.py), matching d515bb238c40's per-entry verification discipline rather
    than trusting a heuristic across the board.
    """
    from sqlalchemy.orm import Session

    from profesor_oak_ai.db.models import Move
    from profesor_oak_ai.ingestion.populate import GEN1_MOVE_EFFECT_CORRECTIONS

    bind = op.get_bind()
    session = Session(bind=bind)

    # GEN1_MOVE_EFFECT_CORRECTIONS values are (effect_description, effect_chance)
    # tuples as of the low-kick addition in a later migration -- kept in sync here
    # (rather than left as a frozen string-only snapshot) since this migration
    # imports the constant live from populate.py, matching this project's existing
    # convention of migrations reading current ingestion code rather than duplicating
    # frozen literal data (see this migration's docstring above). This keeps a fresh
    # install (which replays every migration from scratch, so this one runs against
    # today's populate.py) consistent with an existing install that applies each
    # correction's own follow-up migration incrementally.
    for name, (effect_description, effect_chance) in GEN1_MOVE_EFFECT_CORRECTIONS.items():
        move = session.scalar(sa.select(Move).where(Move.name == name))
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
