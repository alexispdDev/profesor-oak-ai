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


class Ability(Base):
    __tablename__ = "abilities"

    ability_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str | None]
    # Abilities didn't exist as a mechanic before Gen 3 -- a Gen 1 species "having"
    # a later-generation ability (per modern PokeAPI) is a retrofit, not something
    # the original games had. This column tracks which generation introduced it.
    generation: Mapped[int]


class AbilityFlavorText(Base):
    __tablename__ = "ability_flavor_text"

    ability_id: Mapped[int] = mapped_column(
        ForeignKey("abilities.ability_id", ondelete="CASCADE"), primary_key=True
    )
    # Plain string, not an FK -- keyed by version_group (e.g. "ruby-sapphire"), not
    # an individual game_versions row; no VersionGroup table exists in this schema
    # (same choice already made for SpeciesEvolution.version_group).
    version_group: Mapped[str] = mapped_column(primary_key=True)
    flavor_text: Mapped[str]


class AbilityEffectChange(Base):
    __tablename__ = "ability_effect_changes"

    ability_id: Mapped[int] = mapped_column(
        ForeignKey("abilities.ability_id", ondelete="CASCADE"), primary_key=True
    )
    version_group: Mapped[str] = mapped_column(primary_key=True)
    effect: Mapped[str]


class TypeEfficacy(Base):
    __tablename__ = "type_efficacy"
    __table_args__ = (
        CheckConstraint("damage_factor IN (0, 0.5, 1, 2)", name="ck_type_efficacy_damage_factor"),
    )

    damage_type_id: Mapped[int] = mapped_column(ForeignKey("types.type_id"), primary_key=True)
    target_type_id: Mapped[int] = mapped_column(ForeignKey("types.type_id"), primary_key=True)
    damage_factor: Mapped[float]


class PastTypeEfficacy(Base):
    __tablename__ = "past_type_efficacy"
    __table_args__ = (
        CheckConstraint("damage_factor IN (0, 0.5, 1, 2)", name="ck_past_type_efficacy_damage_factor"),
    )

    # Only rows that differ from the current TypeEfficacy chart are stored, same
    # "only store the delta" convention as PokemonPastType/PastAbility/PastStat.
    generation: Mapped[int] = mapped_column(primary_key=True)
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


class Nature(Base):
    __tablename__ = "natures"

    nature_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    # Stat/flavor names as plain strings, not FKs -- this schema has no Stat or
    # BerryFlavor lookup table (base stats are plain columns on pokemon_forms;
    # berry-flavor.jsonl is outside this project's core ingestion scope).
    increased_stat: Mapped[str | None]
    decreased_stat: Mapped[str | None]
    likes_flavor: Mapped[str | None]
    hates_flavor: Mapped[str | None]


class Characteristic(Base):
    __tablename__ = "characteristics"
    __table_args__ = (
        Index("ux_characteristics_stat_modulo", "highest_stat", "gene_modulo", unique=True),
    )

    characteristic_id: Mapped[int] = mapped_column(primary_key=True)
    # PokeAPI gives this resource no `name` slug -- (highest_stat, gene_modulo) is
    # the real identity; description is a plain display field, not the key.
    highest_stat: Mapped[str]
    gene_modulo: Mapped[int]
    description: Mapped[str]


class PokemonSpecies(Base):
    __tablename__ = "pokemon_species"

    species_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    generation: Mapped[int]
    is_legendary: Mapped[bool] = mapped_column(default=False)
    is_mythical: Mapped[bool] = mapped_column(default=False)
    # Eighths chance of being female: -1 = genderless, 0 = always male,
    # 8 = always female, e.g. 1 = 12.5% female / 87.5% male.
    gender_rate: Mapped[int]
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
    is_mega: Mapped[bool] = mapped_column(default=False)
    is_battle_only: Mapped[bool] = mapped_column(default=False)

    hp: Mapped[int]
    attack: Mapped[int]
    defense: Mapped[int]
    special_attack: Mapped[int]
    special_defense: Mapped[int]
    speed: Mapped[int]
    base_stat_total: Mapped[int] = mapped_column(
        Computed(
            "hp + attack + defense + special_attack + special_defense + speed",
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


class PokemonAbility(Base):
    __tablename__ = "pokemon_abilities"

    form_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_forms.form_id", ondelete="CASCADE"), primary_key=True
    )
    ability_id: Mapped[int] = mapped_column(
        ForeignKey("abilities.ability_id", ondelete="CASCADE"), primary_key=True
    )
    slot: Mapped[int]
    is_hidden: Mapped[bool] = mapped_column(default=False)


class PokemonMove(Base):
    __tablename__ = "pokemon_moves"
    __table_args__ = (
        CheckConstraint(
            "learn_method IN ('level-up', 'machine', 'egg', 'tutor')",
            name="ck_pokemon_moves_learn_method",
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


class PokemonEnrichment(Base):
    __tablename__ = "pokemon_enrichment"

    form_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_forms.form_id", ondelete="CASCADE"), primary_key=True
    )
    physical_traits: Mapped[str | None]
    model_name: Mapped[str | None]
    generated_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP"))


class Item(Base):
    __tablename__ = "items"

    item_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class PokemonHeldItem(Base):
    __tablename__ = "pokemon_held_items"

    form_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_forms.form_id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.item_id", ondelete="CASCADE"), primary_key=True
    )
    version_id: Mapped[int] = mapped_column(ForeignKey("game_versions.version_id"), primary_key=True)
    rarity: Mapped[int]


class PokemonGameIndex(Base):
    __tablename__ = "pokemon_game_indices"

    form_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_forms.form_id", ondelete="CASCADE"), primary_key=True
    )
    version_id: Mapped[int] = mapped_column(ForeignKey("game_versions.version_id"), primary_key=True)
    game_index: Mapped[int]


class PokemonPastType(Base):
    __tablename__ = "pokemon_past_types"
    __table_args__ = (CheckConstraint("slot IN (1, 2)", name="ck_pokemon_past_types_slot"),)

    form_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_forms.form_id", ondelete="CASCADE"), primary_key=True
    )
    generation: Mapped[int] = mapped_column(primary_key=True)
    slot: Mapped[int] = mapped_column(primary_key=True)
    type_id: Mapped[int] = mapped_column(ForeignKey("types.type_id"))


class PokemonPastAbility(Base):
    __tablename__ = "pokemon_past_abilities"

    form_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_forms.form_id", ondelete="CASCADE"), primary_key=True
    )
    generation: Mapped[int] = mapped_column(primary_key=True)
    slot: Mapped[int] = mapped_column(primary_key=True)
    ability_id: Mapped[int] = mapped_column(ForeignKey("abilities.ability_id"))
    is_hidden: Mapped[bool] = mapped_column(default=False)


class PokemonPastStat(Base):
    __tablename__ = "pokemon_past_stats"

    form_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_forms.form_id", ondelete="CASCADE"), primary_key=True
    )
    generation: Mapped[int] = mapped_column(primary_key=True)
    # No CHECK constraint here: past stats can use legacy stat names (e.g. "special",
    # Gen 1's single stat before it split into special-attack/special-defense in Gen 2)
    # that aren't among the 6 current stat names used elsewhere in this schema.
    stat_name: Mapped[str] = mapped_column(primary_key=True)
    base_stat: Mapped[int]
    effort: Mapped[int]


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


class Shape(Base):
    __tablename__ = "shapes"

    shape_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    # Fancy anatomical nickname, e.g. "Mensal" for quadruped, "Anthropomorphic" for
    # humanoid -- genuinely distinct from name, not just a rephrasing of it.
    awesome_name: Mapped[str | None]


class PokemonShapeAssociation(Base):
    __tablename__ = "pokemon_shapes"

    # species_id alone as PK (not composite with shape_id): a species has at most
    # one shape, same 1:1 reasoning as PokemonColorAssociation.
    species_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_species.species_id", ondelete="CASCADE"), primary_key=True
    )
    shape_id: Mapped[int] = mapped_column(ForeignKey("shapes.shape_id"))


class Habitat(Base):
    __tablename__ = "habitats"

    habitat_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class PokemonHabitatAssociation(Base):
    __tablename__ = "pokemon_habitats"

    # species_id alone as PK (not composite with habitat_id): a species has at most
    # one habitat, same 1:1 reasoning as PokemonColorAssociation.
    species_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_species.species_id", ondelete="CASCADE"), primary_key=True
    )
    habitat_id: Mapped[int] = mapped_column(ForeignKey("habitats.habitat_id"))


class GrowthRate(Base):
    __tablename__ = "growth_rates"

    growth_rate_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class PokemonGrowthRateAssociation(Base):
    __tablename__ = "pokemon_growth_rates"

    # species_id alone as PK: a species has at most one growth rate, same 1:1
    # reasoning as PokemonColorAssociation/PokemonHabitatAssociation.
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


class EggGroup(Base):
    __tablename__ = "egg_groups"

    egg_group_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class PokemonEggGroupAssociation(Base):
    __tablename__ = "pokemon_egg_groups"

    # Composite PK (not species_id alone): unlike color/habitat/growth_rate, a
    # species can belong to up to 2 egg groups (verified: 279/1025 species have 2).
    species_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_species.species_id", ondelete="CASCADE"), primary_key=True
    )
    egg_group_id: Mapped[int] = mapped_column(
        ForeignKey("egg_groups.egg_group_id"), primary_key=True
    )


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


class PokemonFormTrigger(Base):
    __tablename__ = "pokemon_form_triggers"

    form_id: Mapped[int] = mapped_column(
        ForeignKey("pokemon_forms.form_id", ondelete="CASCADE"), primary_key=True
    )
    # "held-item", "gigantamax-factor", "move", "ability", "consumed-item", "key-item".
    trigger_type: Mapped[str] = mapped_column(primary_key=True)
    # e.g. "venusaurite" for a held-item trigger; null for gigantamax-factor (no item).
    trigger_name: Mapped[str | None]


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
    # Named trigger_type (not "trigger", a SQLite reserved word) -- matches the
    # existing PokemonFormTrigger.trigger_type naming.
    trigger_type: Mapped[str]
    version_group: Mapped[str]
    is_default: Mapped[bool] = mapped_column(default=True)
    min_level: Mapped[int | None]
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.item_id"))
    held_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.item_id"))
    known_move_id: Mapped[int | None] = mapped_column(ForeignKey("moves.move_id"))
    min_happiness: Mapped[int | None]
    time_of_day: Mapped[str | None]
    relative_physical_stats: Mapped[int | None]
    region: Mapped[str | None]
    # Disambiguates which regional-variant form this condition applies to (e.g.
    # mainland vs. Alolan Raticate); null for the common single-path case.
    base_form_id: Mapped[int | None] = mapped_column(ForeignKey("pokemon_forms.form_id"))
    evolved_form_id: Mapped[int | None] = mapped_column(ForeignKey("pokemon_forms.form_id"))


class Conversation(Base):
    __tablename__ = "conversations"

    # String (UUID) PK generated in application code, not autoincrement -- needed so
    # it can be handed back to the caller immediately and referenced later for feedback.
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


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (CheckConstraint("rating IN (-1, 1)", name="ck_feedback_rating"),)

    feedback_id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.conversation_id", ondelete="CASCADE")
    )
    rating: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP"))


Index("idx_pokemon_forms_species", PokemonForm.species_id)
Index("idx_pokemon_types_type", PokemonTypeAssociation.type_id)
Index("idx_pokemon_moves_move", PokemonMove.move_id)
Index("idx_moves_type", Move.type_id)
