"""make types and type efficacy gen1 canonical

Revision ID: 01b2fa8492ba
Revises: 8bf6d4c0ce10
Create Date: 2026-09-01 16:38:33.730710

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01b2fa8492ba'
down_revision: Union[str, Sequence[str], None] = '8bf6d4c0ce10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Makes types/type_efficacy/pokemon_types Gen-1-canonical instead of "modern is
    primary, Gen-1 is a stored delta" -- this app is about Gen 1, so e.g. Clefairy
    must show as Normal (its real Gen-1 type), not Fairy (its Gen-6 retype).
    Order matters: read pokemon_past_types/past_type_efficacy before dropping them,
    and clear pokemon_moves/moves references to dark/steel/fairy before removing
    those type rows (Move.type_id has no ondelete=CASCADE).
    """
    # 0. 18 alternate forms (16 Alolan/Galarian regional variants, plus
    # clefable-mega [non-canonical, no real generation at all] and gyarados-mega
    # [a real Gen 6 mechanic]) have dark/steel/fairy as a defining part of their
    # typing with no Gen-1 form to fall back to -- unlike the 7 species below,
    # there's no historical value to restore, so the forms are removed outright.
    # Their pokemon_types/pokemon_moves/pokemon_cries/pokemon_game_indices/
    # pokemon_form_triggers/pokemon_past_stats/pokemon_past_types rows all cascade
    # via PokemonForm's FKs; species_evolutions.base_form_id/evolved_form_id does
    # NOT cascade, so the 6 regional-evolution condition rows referencing them
    # (e.g. Alolan Rattata -> Alolan Raticate at night) must be deleted first.
    anachronistic_forms = (
        "SELECT pf.form_id FROM pokemon_forms pf "
        "JOIN pokemon_species sp ON sp.species_id = pf.species_id "
        "WHERE (sp.name, pf.form_name) IN ("
        "  ('clefable', 'mega'), ('gyarados', 'mega'),"
        "  ('diglett', 'alola'), ('dugtrio', 'alola'),"
        "  ('grimer', 'alola'), ('muk', 'alola'),"
        "  ('meowth', 'alola'), ('meowth', 'galar'),"
        "  ('moltres', 'galar'), ('ninetales', 'alola'),"
        "  ('persian', 'alola'), ('rapidash', 'galar'),"
        "  ('raticate', 'alola'), ('raticate', 'totem-alola'),"
        "  ('rattata', 'alola'), ('sandshrew', 'alola'),"
        "  ('sandslash', 'alola'), ('weezing', 'galar')"
        ")"
    )
    op.execute(f"""
        DELETE FROM species_evolutions
        WHERE base_form_id IN ({anachronistic_forms}) OR evolved_form_id IN ({anachronistic_forms})
    """)
    op.execute(f"DELETE FROM pokemon_forms WHERE form_id IN ({anachronistic_forms})")

    # 1. Correct the 7 species retyped after Gen 1 (Clefairy family, Mr. Mime,
    # Magnemite family) to their real Gen-1 type, using the value already recorded
    # in pokemon_past_types.
    op.execute("""
        UPDATE pokemon_types
        SET type_id = (
            SELECT ppt.type_id FROM pokemon_past_types ppt
            WHERE ppt.form_id = pokemon_types.form_id AND ppt.slot = pokemon_types.slot
        )
        WHERE EXISTS (
            SELECT 1 FROM pokemon_past_types ppt
            WHERE ppt.form_id = pokemon_types.form_id AND ppt.slot = pokemon_types.slot
        )
    """)

    # 2. Bite existed in Gen 1 as a Normal-type move (retyped to Dark in Gen 4) --
    # reclassify rather than delete.
    op.execute("""
        UPDATE moves SET type_id = (SELECT type_id FROM types WHERE name = 'normal')
        WHERE name = 'bite'
    """)

    # 3-4. The other 69 dark/steel/fairy moves are genuinely later-generation moves
    # with no Gen-1 form at all. Clear their learnset entries before deleting the
    # moves themselves (no cascade on Move.type_id).
    op.execute("""
        DELETE FROM pokemon_moves WHERE move_id IN (
            SELECT m.move_id FROM moves m JOIN types t ON t.type_id = m.type_id
            WHERE t.name IN ('dark', 'steel', 'fairy')
        )
    """)
    op.execute("""
        DELETE FROM moves WHERE move_id IN (
            SELECT m.move_id FROM moves m JOIN types t ON t.type_id = m.type_id
            WHERE t.name IN ('dark', 'steel', 'fairy')
        )
    """)

    # 5. Apply the 4 real Gen-1 type-effectiveness quirks (already isolated in
    # past_type_efficacy) as the primary chart values.
    op.execute("""
        UPDATE type_efficacy
        SET damage_factor = (
            SELECT pte.damage_factor FROM past_type_efficacy pte
            WHERE pte.damage_type_id = type_efficacy.damage_type_id
              AND pte.target_type_id = type_efficacy.target_type_id
        )
        WHERE EXISTS (
            SELECT 1 FROM past_type_efficacy pte
            WHERE pte.damage_type_id = type_efficacy.damage_type_id
              AND pte.target_type_id = type_efficacy.target_type_id
        )
    """)

    # 6. Remove all dark/steel/fairy interactions from the chart.
    op.execute("""
        DELETE FROM type_efficacy WHERE damage_type_id IN (
            SELECT type_id FROM types WHERE name IN ('dark', 'steel', 'fairy')
        ) OR target_type_id IN (
            SELECT type_id FROM types WHERE name IN ('dark', 'steel', 'fairy')
        )
    """)

    # 7-8. Both tables are now redundant: the deltas they held are baked into the
    # primary tables above.
    op.drop_table('past_type_efficacy')
    op.drop_table('pokemon_past_types')

    # 9. Safe now -- nothing references these three type rows any more.
    op.execute("DELETE FROM types WHERE name IN ('dark', 'steel', 'fairy')")


def downgrade() -> None:
    """Downgrade schema.

    Schema-only best-effort, matching this project's other downgrades: recreates
    the two dropped tables empty. Does not attempt to restore the deleted
    dark/steel/fairy type rows, the 18 deleted forms (or their species_evolutions
    rows), the 69 deleted moves, Bite's original type_id, or the corrected
    type_efficacy/pokemon_types values -- those data corrections aren't reversible
    without re-running the ingestion pipeline from scratch.
    """
    op.create_table('past_type_efficacy',
    sa.Column('generation', sa.Integer(), nullable=False),
    sa.Column('damage_type_id', sa.Integer(), nullable=False),
    sa.Column('target_type_id', sa.Integer(), nullable=False),
    sa.Column('damage_factor', sa.Float(), nullable=False),
    sa.CheckConstraint('damage_factor IN (0, 0.5, 1, 2)', name='ck_past_type_efficacy_damage_factor'),
    sa.ForeignKeyConstraint(['damage_type_id'], ['types.type_id'], ),
    sa.ForeignKeyConstraint(['target_type_id'], ['types.type_id'], ),
    sa.PrimaryKeyConstraint('generation', 'damage_type_id', 'target_type_id')
    )
    op.create_table('pokemon_past_types',
    sa.Column('form_id', sa.Integer(), nullable=False),
    sa.Column('generation', sa.Integer(), nullable=False),
    sa.Column('slot', sa.Integer(), nullable=False),
    sa.Column('type_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('slot IN (1, 2)', name='ck_pokemon_past_types_slot'),
    sa.ForeignKeyConstraint(['form_id'], ['pokemon_forms.form_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['type_id'], ['types.type_id'], ),
    sa.PrimaryKeyConstraint('form_id', 'generation', 'slot')
    )
