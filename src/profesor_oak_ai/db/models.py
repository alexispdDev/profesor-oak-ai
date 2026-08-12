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


Index("idx_pokemon_forms_species", PokemonForm.species_id)
Index("idx_pokemon_types_type", PokemonTypeAssociation.type_id)
Index("idx_pokemon_moves_move", PokemonMove.move_id)
Index("idx_moves_type", Move.type_id)
