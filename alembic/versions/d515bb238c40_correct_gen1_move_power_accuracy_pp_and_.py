"""correct gen1 move power accuracy pp and type

Revision ID: d515bb238c40
Revises: c938780d5d01
Create Date: 2026-09-02 01:08:57.150044

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd515bb238c40'
down_revision: Union[str, Sequence[str], None] = 'c938780d5d01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (name, gen1_type, gen1_power, gen1_accuracy, gen1_pp) for the 56 moves (of the
# 164 currently-ingested moves that actually existed in Generation 1) whose
# current-game power/accuracy/pp/type diverges from their real Gen-1 value.
# Values are PokeAPI's move.past_values, resolved per field as "the earliest
# (oldest) entry that specifies this field, else the current value never
# changed" -- verified against known real Gen-1 data (e.g. Leech Life 20/15,
# Jump Kick 70/95/25, Explosion 170, Self-Destruct 130). Moves that exist in the
# DB but were introduced after Gen 1 (e.g. Curse, Overheat) are untouched here --
# there's no Gen-1 fact to restore for them, and they're out of scope for a
# Gen-1-only app regardless (pending the separate moves-generation-filtering
# cleanup).
GEN1_MOVE_CORRECTIONS = [
    ('absorb', 'grass', 20, 100, 20),
    ('acid-armor', 'poison', None, None, 40),
    ('barrier', 'psychic', None, None, 30),
    ('bind', 'normal', 15, 75, 20),
    ('bite', 'normal', 60, 100, 25),
    ('blizzard', 'ice', 120, 90, 5),
    ('bubble', 'water', 20, 100, 30),
    ('clamp', 'water', 35, 75, 10),
    ('crabhammer', 'water', 90, 85, 10),
    ('dig', 'ground', 100, 100, 10),
    ('disable', 'normal', None, 55, 20),
    ('double-edge', 'normal', 100, 100, 15),
    ('explosion', 'normal', 170, 100, 5),
    ('fire-blast', 'fire', 120, 85, 5),
    ('fire-spin', 'fire', 15, 70, 15),
    ('flamethrower', 'fire', 95, 100, 15),
    ('flash', 'normal', None, 70, 20),
    ('fly', 'flying', 70, 95, 15),
    ('glare', 'normal', None, 75, 30),
    ('growth', 'normal', None, None, 40),
    ('gust', 'normal', 40, 100, 35),
    ('high-jump-kick', 'fighting', 85, 90, 20),
    ('hydro-pump', 'water', 120, 80, 5),
    ('ice-beam', 'ice', 95, 100, 10),
    ('jump-kick', 'fighting', 70, 95, 25),
    ('karate-chop', 'normal', 50, 100, 25),
    ('leech-life', 'bug', 20, 100, 15),
    ('lick', 'ghost', 20, 100, 30),
    ('low-kick', 'fighting', 50, 90, 20),
    ('mega-drain', 'grass', 40, 100, 10),
    ('minimize', 'normal', None, None, 20),
    ('petal-dance', 'grass', 70, 100, 20),
    ('pin-missile', 'bug', 14, 85, 20),
    ('poison-gas', 'poison', None, 55, 40),
    ('psywave', 'psychic', None, 80, 15),
    ('razor-wind', 'normal', 80, 75, 10),
    ('recover', 'normal', None, None, 20),
    ('roar', 'normal', None, 100, 20),
    ('rock-throw', 'rock', 50, 65, 15),
    ('sand-attack', 'normal', None, 100, 15),
    ('self-destruct', 'normal', 130, 100, 5),
    ('skull-bash', 'normal', 100, 100, 15),
    ('smog', 'poison', 20, 70, 20),
    ('submission', 'fighting', 80, 80, 25),
    ('surf', 'water', 95, 100, 15),
    ('swords-dance', 'normal', None, None, 30),
    ('tackle', 'normal', 35, 95, 35),
    ('thrash', 'normal', 90, 100, 20),
    ('thunder', 'electric', 120, 70, 10),
    ('thunder-wave', 'electric', None, 100, 20),
    ('thunderbolt', 'electric', 95, 100, 15),
    ('toxic', 'poison', None, 85, 10),
    ('vine-whip', 'grass', 35, 100, 10),
    ('whirlwind', 'normal', None, 85, 20),
    ('wing-attack', 'flying', 35, 100, 35),
    ('wrap', 'normal', 15, 85, 20),
]


def upgrade() -> None:
    """Upgrade schema.

    Type correction for gust/sand-attack/karate-chop closes the same bug Bite
    had (fixed in 01b2fa8492ba): their current type (flying/ground/fighting)
    still exists in our Gen-1 type table, so the earlier "fall back to
    past_values only when the current type is missing" logic in
    get_or_create_move never triggered for them -- they silently kept their
    modern type instead of their real Gen-1 type (Normal for all three, per
    past_values' gold-silver transition). Rewrote get_or_create_move to always
    resolve type/power/accuracy/pp from past_values for Gen-1-existing moves,
    which incidentally surfaced 53 more moves with power/accuracy/pp drift
    (e.g. Leech Life 80->20, Explosion 250->170, Tackle 40/100->35/95) --
    genuine post-Gen-1 rebalances, same category as the Special-stat species
    rebalance in bc4926d1127f.

    Also deletes 15 fully-orphaned move rows (zero pokemon_moves references)
    discovered while fresh-rebuild-verifying the above: Let's-Go partner-Pikachu
    and Gigantamax signature moves (zippy-zap, sizzly-slide, chloroblast, etc.)
    left over from before insert_forms was scoped to default varieties only --
    they were only ever reachable via non-default varieties like
    "pikachu-starter" that current ingestion never processes, so nothing in the
    live DB actually uses them; a fresh rebuild never recreates them.
    """
    for name, type_name, power, accuracy, pp in GEN1_MOVE_CORRECTIONS:
        op.execute(
            sa.text(
                """
                UPDATE moves
                SET type_id = (SELECT type_id FROM types WHERE name = :type_name),
                    power = :power,
                    accuracy = :accuracy,
                    pp = :pp
                WHERE name = :name
                """
            ).bindparams(type_name=type_name, power=power, accuracy=accuracy, pp=pp, name=name)
        )

    op.execute("""
        DELETE FROM moves WHERE move_id NOT IN (SELECT DISTINCT move_id FROM pokemon_moves)
    """)


def downgrade() -> None:
    """Downgrade schema.

    No-op: the prior (incorrect) values aren't recoverable without re-running
    the ingestion pipeline from scratch, matching this project's other
    data-only downgrades.
    """
    pass
