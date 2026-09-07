"""remove non-default forms and mega/gigantamax data

Revision ID: 3f0770135610
Revises: 8025e5b037b3
Create Date: 2026-09-01 18:04:56.106542

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f0770135610'
down_revision: Union[str, Sequence[str], None] = '8025e5b037b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Gen 1 had exactly one form per species -- no alternate forms of any kind
    (no held items, no Mega Evolution [Gen 6], no Gigantamax [Gen 8], no
    regional/cosmetic variants). Removes all 69 non-default forms and the
    now-permanently-dead is_mega/is_battle_only columns and
    pokemon_form_triggers table that existed only to describe them.
    """
    # species_evolutions.base_form_id/evolved_form_id has no cascade -- must clear
    # the 8 regional-variant evolution condition rows (e.g. Alolan Raichu) before
    # the forms they reference can be deleted. Each affected species' plain Gen-1
    # (red-blue) evolution row is untouched.
    op.execute("""
        DELETE FROM species_evolutions
        WHERE base_form_id IN (SELECT form_id FROM pokemon_forms WHERE is_default = 0)
           OR evolved_form_id IN (SELECT form_id FROM pokemon_forms WHERE is_default = 0)
    """)
    # Cascades to pokemon_types, pokemon_moves, pokemon_cries, pokemon_game_indices,
    # pokemon_form_triggers, pokemon_past_stats (all ondelete="CASCADE" on form_id).
    op.execute("DELETE FROM pokemon_forms WHERE is_default = 0")

    op.drop_table('pokemon_form_triggers')

    # Plain (non-batch) drop_column, matching this project's established convention
    # for these exact two columns (ac7b45983d92 used plain add_column originally to
    # avoid batch_alter_table's recreate path choking on pokemon_forms' computed
    # base_stat_total column).
    op.drop_column('pokemon_forms', 'is_mega')
    op.drop_column('pokemon_forms', 'is_battle_only')


def downgrade() -> None:
    """Downgrade schema.

    Schema-only best-effort: recreates pokemon_form_triggers (empty) and the two
    columns (default False). Does not restore the deleted forms, their
    types/moves/cries/game_indices/past_stats rows, or the 8 species_evolutions
    rows -- not reversible without re-running the ingestion pipeline from scratch.
    """
    op.add_column('pokemon_forms', sa.Column('is_mega', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column(
        'pokemon_forms', sa.Column('is_battle_only', sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.create_table('pokemon_form_triggers',
    sa.Column('form_id', sa.Integer(), nullable=False),
    sa.Column('trigger_type', sa.String(), nullable=False),
    sa.Column('trigger_name', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['form_id'], ['pokemon_forms.form_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('form_id', 'trigger_type')
    )
