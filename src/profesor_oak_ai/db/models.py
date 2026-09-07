from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Computed, ForeignKey, Index, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PokemonType(Base):
    __tablename__ = "types"

    type_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class GameVersion(Base):
    __tablename__ = "game_versions"

    version_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    generation: Mapped[int]


class TypeEfficacy(Base):
    __tablename__ = "type_efficacy"
    __table_args__ = (
        CheckConstraint("damage_factor IN (0, 0.5, 1, 2)", name="ck_type_efficacy_damage_factor"),
    )

    damage_type_id: Mapped[int] = mapped_column(ForeignKey("types.type_id"), primary_key=True)
    target_type_id: Mapped[int] = mapped_column(ForeignKey("types.type_id"), primary_key=True)
    damage_factor: Mapped[float]


class Move(Base):
    __tablename__ = "moves"
    __table_args__ = (
        CheckConstraint(
            "damage_class IN ('physical', 'special', 'status')", name="ck_moves_damage_class"
        ),
    )

    move_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    type_id: Mapped[int] = mapped_column(ForeignKey("types.type_id"))
    damage_class: Mapped[str]
    power: Mapped[int | None]
    accuracy: Mapped[int | None]
    pp: Mapped[int]
    priority: Mapped[int] = mapped_column(default=0)
    effect_chance: Mapped[int | None]
    effect_description: Mapped[str | None]

    type: Mapped[PokemonType] = relationship()


class PokemonSpecies(Base):
    __tablename__ = "pokemon_species"

    species_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    generation: Mapped[int]
    is_legendary: Mapped[bool] = mapped_column(default=False)
    is_mythical: Mapped[bool] = mapped_column(default=False)
    evolves_from_species_id: Mapped[int | None] = mapped_column(
        ForeignKey("pokemon_species.species_id")
    )

    evolves_from: Mapped[PokemonSpecies | None] = relationship(remote_side=[species_id])
    forms: Mapped[list[PokemonForm]] = relationship(back_populates="species")
    pokedex_entries: Mapped[list[PokedexEntry]] = relationship(back_populates="species")


class PokedexEntry(Base):
    __tablename__ = "pokedex_entries"

    species_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_species.species_id", ondelete="CASCADE"), primary_key=True
    )
    version_id: Mapped[int] = mapped_column(ForeignKey("game_versions.version_id"), primary_key=True)
    language: Mapped[str] = mapped_column(primary_key=True, default="en")
    entry: Mapped[str]

    species: Mapped[PokemonSpecies] = relationship(back_populates="pokedex_entries")
    version: Mapped[GameVersion] = relationship()


class PokedexNumber(Base):
    __tablename__ = "pokedex_numbers"
    __table_args__ = (
        CheckConstraint("pokedex IN ('national', 'kanto')", name="ck_pokedex_numbers_pokedex"),
    )

    species_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_species.species_id", ondelete="CASCADE"), primary_key=True
    )
    # Scoped to the two dexes covering this project's full Gen-1 species range --
    # see ingestion_gaps.txt for the other 32 dexes considered and skipped.
    pokedex: Mapped[str] = mapped_column(primary_key=True)
    entry_number: Mapped[int]


class PokemonForm(Base):
    __tablename__ = "pokemon_forms"
    __table_args__ = (
        Index(
            "ux_pokemon_forms_base",
            "species_id",
            unique=True,
            sqlite_where=text("form_name IS NULL"),
        ),
    )

    form_id: Mapped[int] = mapped_column(primary_key=True)
    species_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_species.species_id", ondelete="CASCADE")
    )
    form_name: Mapped[str | None]
    is_default: Mapped[bool] = mapped_column(default=True)
    height_m: Mapped[float]
    weight_kg: Mapped[float]
    sprite_url: Mapped[str | None]
    base_experience: Mapped[int | None]
    order: Mapped[int | None]

    hp: Mapped[int]
    attack: Mapped[int]
    defense: Mapped[int]
    # Gen 1 had a single Special stat, not the Special Attack/Special Defense split
    # introduced in Gen 2 -- and the split wasn't an even division of the old value,
    # so this must be sourced from history, not derived from the modern fields.
    special: Mapped[int]
    speed: Mapped[int]
    base_stat_total: Mapped[int] = mapped_column(
        Computed(
            "hp + attack + defense + special + speed",
            persisted=True,
        )
    )

    species: Mapped[PokemonSpecies] = relationship(back_populates="forms")


class PokemonTypeAssociation(Base):
    __tablename__ = "pokemon_types"
    __table_args__ = (CheckConstraint("slot IN (1, 2)", name="ck_pokemon_types_slot"),)

    form_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_forms.form_id", ondelete="CASCADE"), primary_key=True
    )
    type_id: Mapped[int] = mapped_column(
        ForeignKey("types.type_id", ondelete="CASCADE"), primary_key=True
    )
    slot: Mapped[int]


class PokemonMove(Base):
    __tablename__ = "pokemon_moves"
    __table_args__ = (
        CheckConstraint(
            "learn_method IN ('level-up', 'machine', 'egg', 'tutor')",
            name="ck_pokemon_moves_learn_method",
        ),
        # PokeAPI reports move learnsets per version_group, not per individual game --
        # Red and Blue are always identical for move data (there's no version-exclusive
        # moveset the way there is for location encounters), so "red-blue" is one unit
        # and "yellow" is the other. A real, meaningful distinction: some Gen-1 moves
        # (e.g. Charizard's Fly) are only learnable starting in Yellow, a well-known
        # oversight patched after Red/Blue shipped -- collapsing the two into one
        # undifferentiated learnset (as this table used to) reports those as available
        # in Red/Blue when they aren't.
        CheckConstraint(
            "version_group IN ('red-blue', 'yellow')",
            name="ck_pokemon_moves_version_group",
        ),
    )

    form_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_forms.form_id", ondelete="CASCADE"), primary_key=True
    )
    move_id: Mapped[int] = mapped_column(
        ForeignKey("moves.move_id", ondelete="CASCADE"), primary_key=True
    )
    learn_method: Mapped[str] = mapped_column(primary_key=True)
    level_learned_at: Mapped[int] = mapped_column(primary_key=True, default=0)
    version_group: Mapped[str] = mapped_column(primary_key=True)


class Item(Base):
    __tablename__ = "items"

    item_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class PokemonGameIndex(Base):
    __tablename__ = "pokemon_game_indices"

    form_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_forms.form_id", ondelete="CASCADE"), primary_key=True
    )
    version_id: Mapped[int] = mapped_column(ForeignKey("game_versions.version_id"), primary_key=True)
    game_index: Mapped[int]


class PokemonCries(Base):
    __tablename__ = "pokemon_cries"

    form_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_forms.form_id", ondelete="CASCADE"), primary_key=True
    )
    latest: Mapped[str | None]
    legacy: Mapped[str | None]


class Color(Base):
    __tablename__ = "colors"

    color_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class PokemonColorAssociation(Base):
    __tablename__ = "pokemon_colors"

    # species_id alone as PK (not composite with color_id): a species has at most one
    # color, unlike types (1-2 per form) -- this enforces that 1:1 constraint in the DB.
    species_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_species.species_id", ondelete="CASCADE"), primary_key=True
    )
    color_id: Mapped[int] = mapped_column(ForeignKey("colors.color_id"))




class GrowthRate(Base):
    __tablename__ = "growth_rates"

    growth_rate_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class PokemonGrowthRateAssociation(Base):
    __tablename__ = "pokemon_growth_rates"

    # species_id alone as PK: a species has at most one growth rate, same 1:1
    # reasoning as PokemonColorAssociation.
    species_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_species.species_id", ondelete="CASCADE"), primary_key=True
    )
    growth_rate_id: Mapped[int] = mapped_column(ForeignKey("growth_rates.growth_rate_id"))


class GrowthRateLevel(Base):
    __tablename__ = "growth_rate_levels"

    growth_rate_id: Mapped[int] = mapped_column(
        ForeignKey("growth_rates.growth_rate_id", ondelete="CASCADE"), primary_key=True
    )
    level: Mapped[int] = mapped_column(primary_key=True)
    experience: Mapped[int]


class Location(Base):
    __tablename__ = "locations"

    location_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class PokemonLocationEncounter(Base):
    __tablename__ = "pokemon_location_encounters"

    form_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_forms.form_id", ondelete="CASCADE"), primary_key=True
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.location_id", ondelete="CASCADE"), primary_key=True
    )
    version_id: Mapped[int] = mapped_column(ForeignKey("game_versions.version_id"), primary_key=True)
    # Not normalized into a lookup table, matching learn_method/stat_name elsewhere in
    # this schema -- a real ~47-value vocabulary, but kept as a plain string by convention.
    method: Mapped[str] = mapped_column(primary_key=True)
    # Level range is part of the key: the same (form, location, version, method) can
    # legitimately have multiple distinct level ranges.
    min_level: Mapped[int] = mapped_column(primary_key=True)
    max_level: Mapped[int] = mapped_column(primary_key=True)
    chance: Mapped[int]


class SpeciesEvolution(Base):
    __tablename__ = "species_evolutions"
    __table_args__ = (
        # Mirrors PokemonMove.learn_method/ALLOWED_LEARN_METHODS: PokeAPI has Gen
        # 8/9-only triggers (e.g. "shed", "three-defeated-bisharp") that never
        # occur for species_id <= 151 and aren't covered by this CHECK constraint.
        CheckConstraint(
            "trigger_type IN ('level-up', 'trade', 'use-item')",
            name="ck_species_evolutions_trigger_type",
        ),
        # Natural key for idempotent re-runs (verified: zero collisions across all
        # 100 in-scope evolution_details entries).
        Index(
            "ux_species_evolutions_natural_key",
            "species_id", "trigger_type", "version_group", "evolved_form_id", "base_form_id",
            unique=True,
        ),
    )

    evolution_id: Mapped[int] = mapped_column(primary_key=True)
    # The EVOLVED species (child). The parent is already known via that species'
    # own pokemon_species.evolves_from_species_id -- not duplicated here.
    species_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_species.species_id", ondelete="CASCADE")
    )
    # Named trigger_type, not "trigger" -- a SQLite reserved word.
    trigger_type: Mapped[str]
    version_group: Mapped[str]
    is_default: Mapped[bool] = mapped_column(default=True)
    min_level: Mapped[int | None]
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.item_id"))
    known_move_id: Mapped[int | None] = mapped_column(ForeignKey("moves.move_id"))
    min_happiness: Mapped[int | None]
    time_of_day: Mapped[str | None]
    relative_physical_stats: Mapped[int | None]
    region: Mapped[str | None]
    # Disambiguates which regional-variant form this condition applies to (e.g.
    # mainland vs. Alolan Raticate); null for the common single-path case.
    base_form_id: Mapped[int | None] = mapped_column(ForeignKey("pokemon_forms.form_id"))
    evolved_form_id: Mapped[int | None] = mapped_column(ForeignKey("pokemon_forms.form_id"))


class Gen1ouUsageMove(Base):
    __tablename__ = "gen1ou_usage_moves"

    # A single Smogon Generation 1 OU usage-stats snapshot (14,136 rated battles, 1760
    # rating cutoff -- see pokemon_raw_data/gen1ou-1760.json) covers only 62 of the 151
    # Gen-1 species, so species_id being part of the PK (not a dex-wide 1:1 pattern like
    # PokemonColorAssociation) means only those 62 species have any row here at all --
    # that's also how team_builder.viable_pool identifies real-usage pool membership,
    # with no separate species-level table needed.
    species_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_species.species_id", ondelete="CASCADE"), primary_key=True
    )
    move_id: Mapped[int] = mapped_column(ForeignKey("moves.move_id", ondelete="CASCADE"), primary_key=True)
    # Precomputed from the raw snapshot's weighted move count divided by that species'
    # weighted total (the sum of its Abilities/Items/Spreads breakdown -- Gen 1 has no
    # abilities/items to actually vary, so every entry there is a single dummy value
    # that sums to the species' true weighted appearance total; "Raw count" is a
    # different, unweighted number and is NOT the right denominator). The raw weight has
    # no independent meaning outside that one division, so only the resulting
    # percentage is stored.
    usage_percent: Mapped[float]


class Conversation(Base):
    __tablename__ = "conversations"

    # String (UUID) PK generated in application code, not autoincrement -- needed so
    # it can be handed back to the caller immediately.
    conversation_id: Mapped[str] = mapped_column(primary_key=True)
    question: Mapped[str]
    answer: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP"))

    # LLM-as-judge relevance classification for this answer, plus token/cost tracking
    # for both the main answer and the judge call. NULL for conversations logged before
    # this tracking existed -- there's no way to retroactively recover token usage.
    relevance: Mapped[str | None]
    relevance_explanation: Mapped[str | None]
    prompt_tokens: Mapped[int | None]
    completion_tokens: Mapped[int | None]
    total_tokens: Mapped[int | None]
    cached_tokens: Mapped[int | None]
    eval_prompt_tokens: Mapped[int | None]
    eval_completion_tokens: Mapped[int | None]
    eval_total_tokens: Mapped[int | None]
    cost: Mapped[float | None]

    # How the answer's subject was confirmed real: "context" (baseline retrieval before
    # the model's first turn), "tool" (a name-resolving tool call), or "none" (never
    # grounded). NULL for conversations logged before this tracking existed.
    grounding_source: Mapped[str | None]

    # Groups multiple turns of one ongoing exchange -- the first turn's thread_id
    # equals its own conversation_id (self-referencing root); later turns in the
    # same thread reuse that value, letting history be reconstructed with
    # "WHERE thread_id = ? ORDER BY created_at" instead of a separate table. NULL
    # for conversations logged before multi-turn memory existed.
    thread_id: Mapped[str | None] = mapped_column(index=True)


Index("idx_pokemon_forms_species", PokemonForm.species_id)
Index("idx_pokemon_types_type", PokemonTypeAssociation.type_id)
Index("idx_pokemon_moves_move", PokemonMove.move_id)
Index("idx_moves_type", Move.type_id)
