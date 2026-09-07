"""merge special stats into gen1 accurate model

Revision ID: bc4926d1127f
Revises: 3f0770135610
Create Date: 2026-09-01 20:51:33.266150

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bc4926d1127f'
down_revision: Union[str, Sequence[str], None] = '3f0770135610'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Gen 1 had 5 stats (HP, Attack, Defense, Special, Speed) -- the Special Attack/
    Special Defense split didn't happen until Gen 2, and Game Freak didn't evenly
    divide the old value when they split it (111 of 151 species diverge). Separately,
    20 species got a real Attack/Defense/Speed buff in Gen 5/6. Both facts already
    live in pokemon_past_stats; this bakes them into pokemon_forms as the primary
    data and drops the now-redundant delta table, mirroring the types precedent.

    SQLite cannot add a STORED GENERATED column via plain ALTER TABLE ADD COLUMN
    ("cannot add a STORED column" -- verified), so changing base_stat_total's
    formula requires recreating the table. This is dangerous done naively: DROP
    TABLE on a table other tables hold ON DELETE CASCADE FKs to cascades away the
    dependent rows when PRAGMA foreign_keys=ON (verified in an isolated test) --
    dropping pokemon_forms this way would silently wipe pokemon_types/
    pokemon_moves/pokemon_cries/pokemon_game_indices for every species. Disabling
    the pragma for the duration of the recreate (confirmed safe in the same test)
    avoids this entirely.
    """
    op.execute("PRAGMA foreign_keys=OFF")

    op.execute("""
        CREATE TABLE pokemon_forms_new (
            form_id INTEGER NOT NULL,
            species_id INTEGER NOT NULL,
            form_name VARCHAR,
            is_default BOOLEAN NOT NULL,
            height_m FLOAT NOT NULL,
            weight_kg FLOAT NOT NULL,
            sprite_url VARCHAR,
            hp INTEGER NOT NULL,
            attack INTEGER NOT NULL,
            defense INTEGER NOT NULL,
            special INTEGER NOT NULL,
            speed INTEGER NOT NULL,
            base_stat_total INTEGER NOT NULL GENERATED ALWAYS AS (hp + attack + defense + special + speed) STORED,
            base_experience INTEGER,
            "order" INTEGER,
            PRIMARY KEY (form_id),
            FOREIGN KEY(species_id) REFERENCES pokemon_species (species_id) ON DELETE CASCADE
        )
    """)

    # hp/attack/defense/speed: use the earliest recorded historical value if this
    # species was ever rebalanced for that stat, else the current value (already
    # Gen-1-correct, never changed). special: always from past_stats -- it never
    # existed as a modern field, so there's no sensible current-value fallback
    # (verified 151/151 species have a generation-1 "special" row).
    op.execute("""
        INSERT INTO pokemon_forms_new
            (form_id, species_id, form_name, is_default, height_m, weight_kg,
             sprite_url, hp, attack, defense, special, speed, base_experience, "order")
        SELECT
            pf.form_id, pf.species_id, pf.form_name, pf.is_default, pf.height_m, pf.weight_kg,
            pf.sprite_url,
            COALESCE((SELECT pps.base_stat FROM pokemon_past_stats pps
                      WHERE pps.form_id = pf.form_id AND pps.stat_name = 'hp'
                      ORDER BY pps.generation ASC LIMIT 1), pf.hp),
            COALESCE((SELECT pps.base_stat FROM pokemon_past_stats pps
                      WHERE pps.form_id = pf.form_id AND pps.stat_name = 'attack'
                      ORDER BY pps.generation ASC LIMIT 1), pf.attack),
            COALESCE((SELECT pps.base_stat FROM pokemon_past_stats pps
                      WHERE pps.form_id = pf.form_id AND pps.stat_name = 'defense'
                      ORDER BY pps.generation ASC LIMIT 1), pf.defense),
            (SELECT pps.base_stat FROM pokemon_past_stats pps
                      WHERE pps.form_id = pf.form_id AND pps.stat_name = 'special'
                      ORDER BY pps.generation ASC LIMIT 1),
            COALESCE((SELECT pps.base_stat FROM pokemon_past_stats pps
                      WHERE pps.form_id = pf.form_id AND pps.stat_name = 'speed'
                      ORDER BY pps.generation ASC LIMIT 1), pf.speed),
            pf.base_experience, pf."order"
        FROM pokemon_forms pf
    """)

    op.execute("DROP TABLE pokemon_forms")
    op.execute("ALTER TABLE pokemon_forms_new RENAME TO pokemon_forms")

    op.execute("CREATE INDEX idx_pokemon_forms_species ON pokemon_forms (species_id)")
    op.execute(
        "CREATE UNIQUE INDEX ux_pokemon_forms_base ON pokemon_forms (species_id) WHERE form_name IS NULL"
    )

    op.execute("DROP TABLE pokemon_past_stats")

    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    """Downgrade schema.

    Schema-only best-effort: recreates the 6-stat shape (special_attack/
    special_defense both set to the merged "special" value, an approximation) and
    an empty pokemon_past_stats. The original divergent modern values and the full
    historical record aren't reversible without re-running the ingestion pipeline
    from scratch.
    """
    op.execute("PRAGMA foreign_keys=OFF")

    op.execute("""
        CREATE TABLE pokemon_forms_old (
            form_id INTEGER NOT NULL,
            species_id INTEGER NOT NULL,
            form_name VARCHAR,
            is_default BOOLEAN NOT NULL,
            height_m FLOAT NOT NULL,
            weight_kg FLOAT NOT NULL,
            sprite_url VARCHAR,
            hp INTEGER NOT NULL,
            attack INTEGER NOT NULL,
            defense INTEGER NOT NULL,
            special_attack INTEGER NOT NULL,
            special_defense INTEGER NOT NULL,
            speed INTEGER NOT NULL,
            base_stat_total INTEGER NOT NULL GENERATED ALWAYS AS (hp + attack + defense + special_attack + special_defense + speed) STORED,
            base_experience INTEGER,
            "order" INTEGER,
            PRIMARY KEY (form_id),
            FOREIGN KEY(species_id) REFERENCES pokemon_species (species_id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        INSERT INTO pokemon_forms_old
            (form_id, species_id, form_name, is_default, height_m, weight_kg,
             sprite_url, hp, attack, defense, special_attack, special_defense, speed,
             base_experience, "order")
        SELECT form_id, species_id, form_name, is_default, height_m, weight_kg,
               sprite_url, hp, attack, defense, special, special, speed,
               base_experience, "order"
        FROM pokemon_forms
    """)
    op.execute("DROP TABLE pokemon_forms")
    op.execute("ALTER TABLE pokemon_forms_old RENAME TO pokemon_forms")
    op.execute("CREATE INDEX idx_pokemon_forms_species ON pokemon_forms (species_id)")
    op.execute(
        "CREATE UNIQUE INDEX ux_pokemon_forms_base ON pokemon_forms (species_id) WHERE form_name IS NULL"
    )

    op.execute("PRAGMA foreign_keys=ON")

    op.create_table('pokemon_past_stats',
    sa.Column('form_id', sa.Integer(), nullable=False),
    sa.Column('generation', sa.Integer(), nullable=False),
    sa.Column('stat_name', sa.String(), nullable=False),
    sa.Column('base_stat', sa.Integer(), nullable=False),
    sa.Column('effort', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['form_id'], ['pokemon_forms.form_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('form_id', 'generation', 'stat_name')
    )
