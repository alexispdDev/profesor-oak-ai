import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import (
    GameVersion,
    Move,
    PokedexEntry,
    PokedexNumber,
    PokemonForm,
    PokemonMove,
    PokemonSpecies,
    PokemonType,
    PokemonTypeAssociation,
    TypeEfficacy,
)

RAW_DATA_DIR = Path("pokemon_raw_data")

# Scoped to red-blue/yellow (see ALLOWED_MOVE_VERSION_GROUPS below), only level-up
# and machine (TM/HM) ever occur -- egg moves and move tutors didn't exist yet, same
# generation as egg-groups/gender. The pokemon_moves.learn_method CHECK constraint
# still allows 'egg'/'tutor' (unchanged, a DB-level safety net) but this narrower
# set is what ingestion actually ever produces now. "stadium-surfing-pikachu" (the
# real Pokemon Stadium "Surfing Pikachu" transfer trick) also appears in this scope
# but is deliberately excluded -- a single (Pikachu, Surf) fact not worth a
# CHECK-constraint schema change for.
ALLOWED_LEARN_METHODS = {"level-up", "machine"}

# A move's version_group_details entries span every game it's ever been learnable in;
# only red-blue and yellow are Gen 1 (the Japanese-only red-green-japan/blue-japan
# version groups are irrelevant -- this app's game_versions table only tracks
# red/blue/yellow, same scope as pokedex_entries/game_indices).
ALLOWED_MOVE_VERSION_GROUPS = {"red-blue", "yellow"}

GENERATION_ROMAN_NUMERALS = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix"]
GENERATION_NAME_TO_INT = {
    f"generation-{numeral}": index + 1 for index, numeral in enumerate(GENERATION_ROMAN_NUMERALS)
}


@dataclass
class OfflineData:
    types: dict[str, dict]
    moves: dict[str, dict]
    species: dict[int, dict]
    pokemon: dict[str, dict]


def extract_id_from_url(url: str) -> int:
    return int(url.rstrip("/").rsplit("/", 1)[-1])


def gen1_type_entries(pokemon_data: dict) -> list[dict]:
    """Returns this pokemon's Gen-1-era type list. Uses the earliest past_types
    snapshot when the species was later retyped (e.g. Clefairy Normal->Fairy in
    Gen 6, Magnemite Electric->Electric/Steel in Gen 2), falling back to the
    current types list when it was never retyped. Picks the minimum generation
    among multiple entries defensively, though verified empirically that no
    in-scope species has more than one retype."""
    past = pokemon_data.get("past_types", [])
    if not past:
        return pokemon_data["types"]
    earliest = min(past, key=lambda p: GENERATION_NAME_TO_INT[p["generation"]["name"]])
    return earliest["types"]


def resolve_gen1_types(pokemon_data: dict, type_map: dict[str, int]) -> list[tuple[int, int]] | None:
    """Resolves this pokemon's Gen-1-era types to (type_id, slot) pairs. Returns
    None if any type can't be resolved even after the gen1_type_entries fallback --
    meaning this exact form (e.g. an Alolan/Galarian regional variant, or a
    non-canonical mega like a fictional "Mega Clefable") has no Gen-1 existence at
    all, not just an outdated type. A Pokemon can't have a missing primary type, so
    the whole form is skipped by the caller rather than just the unresolved slot."""
    resolved = []
    for type_entry in gen1_type_entries(pokemon_data):
        if type_entry.get("type") is None:
            continue
        type_id = type_map.get(type_entry["type"]["name"])
        if type_id is None:
            return None
        resolved.append((type_id, type_entry["slot"]))
    return resolved


def gen1_damage_relations(type_data: dict) -> dict:
    """Returns this type's Gen-1-era damage relations. Same past-value-override
    pattern as gen1_type_entries: uses the earliest past_damage_relations
    snapshot when this type's relations changed at some point since Gen 1,
    falling back to the current damage_relations when they've been stable."""
    past = type_data.get("past_damage_relations", [])
    if not past:
        return type_data["damage_relations"]
    earliest = min(past, key=lambda p: GENERATION_NAME_TO_INT[p["generation"]["name"]])
    return earliest["damage_relations"]


def gen1_stats(pokemon_data: dict) -> dict[str, int]:
    """Returns this pokemon's true Gen-1 stats: hp, attack, defense, special, speed
    -- Gen 1's real 5-stat model, not the modern 6-stat split (Special Attack/
    Special Defense didn't exist until Gen 2, and weren't an even division of the
    old Special value -- many species were independently rebalanced). Same
    past-value-override pattern as gen1_type_entries/gen1_damage_relations: for
    hp/attack/defense/speed, uses the earliest past_stats value if this species was
    ever rebalanced for that stat, else the current value (never changed, already
    correct). "special" always comes from past_stats -- it never existed as a
    modern field, so there's no current-value fallback."""
    earliest_past: dict[str, tuple[int, int]] = {}
    for entry in pokemon_data.get("past_stats", []):
        generation = GENERATION_NAME_TO_INT[entry["generation"]["name"]]
        for stat in entry["stats"]:
            name = stat["stat"]["name"]
            if name not in earliest_past or generation < earliest_past[name][0]:
                earliest_past[name] = (generation, stat["base_stat"])

    current = {s["stat"]["name"]: s["base_stat"] for s in pokemon_data["stats"]}

    def resolve(name: str) -> int:
        return earliest_past[name][1] if name in earliest_past else current[name]

    return {
        "hp": resolve("hp"),
        "attack": resolve("attack"),
        "defense": resolve("defense"),
        "special": earliest_past["special"][1],
        "speed": resolve("speed"),
    }


def english_text(entries: list[dict], *field_candidates: str) -> str | None:
    for entry in entries:
        if entry["language"]["name"] != "en":
            continue
        for field in field_candidates:
            if entry.get(field):
                return entry[field]
    return None


def load_name_id_map(session: Session, model, id_attr: str) -> dict[str, int]:
    return {row.name: getattr(row, id_attr) for row in session.scalars(select(model)).all()}


def load_offline_lookup(path: Path, key: str = "name") -> dict:
    lookup = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            lookup[data[key]] = data
    return lookup


def compute_damage_factors(relations: dict, type_map: dict[str, int]) -> dict[str, float]:
    factors = dict.fromkeys(type_map, 1.0)
    for rel in relations.get("double_damage_to", []):
        if rel["name"] in factors:
            factors[rel["name"]] = 2.0
    for rel in relations.get("half_damage_to", []):
        if rel["name"] in factors:
            factors[rel["name"]] = 0.5
    for rel in relations.get("no_damage_to", []):
        if rel["name"] in factors:
            factors[rel["name"]] = 0.0
    return factors


def populate_type_efficacy(session: Session, type_map: dict[str, int], offline: OfflineData) -> None:
    if session.scalar(select(func.count()).select_from(TypeEfficacy)):
        print("type_efficacy already populated, skipping")
        return

    rows = []
    for damage_name, damage_id in type_map.items():
        data = offline.types[damage_name]
        factors = compute_damage_factors(gen1_damage_relations(data), type_map)

        for target_name, factor in factors.items():
            rows.append(
                TypeEfficacy(
                    damage_type_id=damage_id, target_type_id=type_map[target_name], damage_factor=factor
                )
            )
        print(f"  type_efficacy: {damage_name} done")

    session.add_all(rows)
    session.commit()
    print(f"Inserted {len(rows)} type_efficacy rows")


def gen1_move_values(data: dict) -> dict:
    """Returns this move's Gen-1-era type/power/accuracy/pp. Only meaningful for
    moves that existed in Generation 1 (data["generation"]["name"] ==
    "generation-i") -- callers must gate on that, since past_values entries also
    exist for moves introduced later (e.g. Curse, Gen 2) where there's no Gen-1
    fact to recover and the "earliest" entry is just an early-but-still-later-gen
    value, not a Gen-1 one.

    Each past_values entry only carries the fields that changed at that
    version_group's transition (confirmed against known real Gen-1 move data,
    e.g. Jump Kick 70/95/25 and Tackle 35/95/35), and entries are already
    chronological, so the Gen-1 value for each field is the first entry (oldest
    to newest) that specifies it, falling back to the current value when no
    entry ever specifies that field (never changed).
    """
    past_values = data.get("past_values", [])

    def earliest(field: str):
        for pv in past_values:
            if pv.get(field) is not None:
                return pv[field]
        return data.get(field)

    type_name = data["type"]["name"]
    for pv in past_values:
        if pv.get("type") is not None:
            type_name = pv["type"]["name"]
            break

    return {
        "type_name": type_name,
        "power": earliest("power"),
        "accuracy": earliest("accuracy"),
        "pp": earliest("pp"),
    }


# Hand-verified Gen-1-era effect text corrections, for moves whose current-game
# effect_entries text (PokeAPI always exposes the LATEST generation's text at the top
# level) describes a mechanic that only started applying in a later generation.
#
# PokeAPI's effect_changes field looks like it should make this derivable in general
# (it lists each later version_group alongside "the text before that change"), but
# that approach was tried and reverted: effect_changes entries are inconsistently
# structured across moves -- for some moves they're a full replacement effect
# description (this is true for jump-kick/high-jump-kick, verified below), but for
# many others they're a narrow errata/interaction footnote (e.g. Blizzard's earliest
# effect_changes entry is "Does not interact with Hail" -- true but anachronistic,
# since Hail didn't exist before Generation III, and it silently drops Blizzard's
# actually-defining Gen-1 fact, its freeze chance). Blindly using the earliest entry
# produced confidently-wrong or misleadingly-incomplete text for over a dozen moves in
# a test run, so this is a hand-curated list instead, following the same "verify each
# entry, don't trust a heuristic across the board" discipline as GEN1_MOVE_CORRECTIONS
# above (power/accuracy/pp/type) -- add to it only after checking the specific move's
# real Gen-1 mechanic against an authoritative source, not from effect_changes alone.
#
# jump-kick/high-jump-kick: confirmed via Bulbapedia's move pages -- "If it misses,
# the user will take crash damage of 1 HP" in Generation I; only Generation III
# introduced the "half the damage it would have dealt" mechanic currently stored
# (Generation II's own mechanic, 1/8 of the would-be damage, is different from both).
#
# low-kick: confirmed via Bulbapedia -- "Low Kick has a power of 50, an accuracy of
# 90%, and has a 30% chance of causing the target to flinch" in Generation I; the
# weight-based power scaling (already correctly excluded from the power/accuracy
# fields by GEN1_MOVE_CORRECTIONS above, which pulls 50/90 from PokeAPI's
# ruby-sapphire past_values entry) wasn't introduced until Generation III, and cost
# the move its flinch chance when it was. Unlike jump-kick/high-jump-kick, this one
# has NO effect_changes entries at all (PokeAPI never recorded historical effect text
# for it), so even the reverted general-heuristic approach couldn't have caught this --
# it can only be hand-corrected. Also restores effect_chance to 30 (the flinch-chance
# probability, dropped entirely by the modern weight-based effect_entries, which has
# no percentage-chance field at all) -- confirmed against Rolling Kick/Stomp/Headbutt's
# already-correct "chance to flinch" entries, all stored with effect_chance=30.
#
# counter: confirmed via Bulbapedia -- "If the last amount of damage done before the
# use of Counter ... was dealt by a Normal-type or Fighting-type attack ..., Counter
# will do twice as much damage to the opponent" in Generation I. The stored text
# ("last physical hit") is misleadingly modern: Generation 1 has no move-level
# physical/special split at all (damage class is purely type-determined, e.g. every
# Water-type move is "special" and every Normal-type move is "physical"), and Counter
# doesn't even use that determination -- it's hardcoded to check the attacking move's
# TYPE against Normal/Fighting specifically, not a "physical" classification broadly.
# A physical-feeling move of any other type -- Earthquake (Ground), Rock Slide
# (Rock), etc. -- cannot be countered in Gen 1 at all. Also has no effect_changes
# entries (same as low-kick), so this can only be hand-corrected.
#
# Each entry is (effect_description, effect_chance) -- effect_chance is None when the
# move's Gen-1 mechanic genuinely has no percentage-chance component (unlike Low
# Kick's, this is NOT "unknown/uncorrected", it's the real absence of that field).
GEN1_MOVE_EFFECT_CORRECTIONS: dict[str, tuple[str, int | None]] = {
    "jump-kick": ("If this move misses, the user takes 1 point of damage in recoil.", None),
    "high-jump-kick": ("If this move misses, the user takes 1 point of damage in recoil.", None),
    "low-kick": ("Has a chance to make the target flinch.", 30),
    "counter": (
        "Inflicts twice the damage the user took from the last Normal-type or "
        "Fighting-type attack that hit it this turn. Does not counter attacks of any "
        "other type, even ones that would be physical in later generations (e.g. "
        "Earthquake or Rock Slide).",
        None,
    ),
}


def get_or_create_move(
    session: Session, cache: dict[str, int], type_map: dict[str, int], offline_moves: dict[str, dict], name: str
) -> int | None:
    if name in cache:
        return cache[name]

    data = offline_moves[name]

    if data["generation"]["name"] == "generation-i":
        resolved = gen1_move_values(data)
        type_name = resolved["type_name"]
        power = resolved["power"]
        accuracy = resolved["accuracy"]
        pp = resolved["pp"]
        if name in GEN1_MOVE_EFFECT_CORRECTIONS:
            effect_description, effect_chance = GEN1_MOVE_EFFECT_CORRECTIONS[name]
        else:
            effect_description = english_text(data.get("effect_entries", []), "short_effect", "effect")
            effect_chance = data.get("effect_chance")
    else:
        type_name = data["type"]["name"]
        power = data.get("power")
        accuracy = data.get("accuracy")
        pp = data["pp"]
        effect_description = english_text(data.get("effect_entries", []), "short_effect", "effect")
        effect_chance = data.get("effect_chance")

    type_id = type_map.get(type_name)
    if type_id is None:
        return None

    move = Move(
        name=name,
        type_id=type_id,
        damage_class=data["damage_class"]["name"],
        power=power,
        accuracy=accuracy,
        pp=pp,
        priority=data.get("priority", 0),
        effect_chance=effect_chance,
        effect_description=effect_description,
    )
    session.add(move)
    session.flush()
    cache[name] = move.move_id
    return move.move_id


def insert_learned_moves(
    session: Session,
    type_map: dict[str, int],
    move_cache: dict[str, int],
    offline_moves: dict[str, dict],
    form_id: int,
    pokemon_data: dict,
) -> None:
    # Keyed including version_group (not just move/method/level) -- red-blue and
    # yellow are kept as separate facts, not merged, so a move learnable in only one
    # of them (e.g. Charizard's Fly, a documented Yellow-only fix to a Red/Blue
    # oversight) doesn't get reported as available in both.
    seen_move_keys: set[tuple[str, str, int, str]] = set()
    for move_entry in pokemon_data["moves"]:
        # Check for a qualifying Gen-1 learn entry BEFORE calling get_or_create_move --
        # a species' "moves" list includes every move learnable in any generation
        # through the present, and most entries have no red-blue/yellow match at all
        # (e.g. Overheat, Curse). Calling get_or_create_move unconditionally would
        # create/cache a Move row for those anyway, leaving orphaned rows with no
        # pokemon_moves reference once ingestion finishes -- the exact bug fixed as a
        # one-time cleanup in migration d515bb238c40, which a fresh install shouldn't
        # reintroduce.
        gen1_entries = [
            detail
            for detail in move_entry["version_group_details"]
            if detail["version_group"]["name"] in ALLOWED_MOVE_VERSION_GROUPS
            and detail["move_learn_method"]["name"] in ALLOWED_LEARN_METHODS
        ]
        if not gen1_entries:
            continue

        move_name = move_entry["move"]["name"]
        move_id = get_or_create_move(session, move_cache, type_map, offline_moves, move_name)
        if move_id is None:
            # No Gen-1 form of this move exists at all (dark/steel/fairy with
            # no historical override) -- skip it entirely, not just its type.
            continue
        for detail in gen1_entries:
            method = detail["move_learn_method"]["name"]
            level = detail["level_learned_at"]
            version_group = detail["version_group"]["name"]
            key = (move_name, method, level, version_group)
            if key in seen_move_keys:
                continue
            seen_move_keys.add(key)

            session.add(
                PokemonMove(
                    form_id=form_id,
                    move_id=move_id,
                    learn_method=method,
                    level_learned_at=level,
                    version_group=version_group,
                )
            )


def backfill_gen1_moves(
    session: Session, type_map: dict[str, int], move_cache: dict[str, int], offline: OfflineData
) -> None:
    """One-time repair for species/forms already in the DB whose pokemon_moves rows
    were inserted before ALLOWED_MOVE_VERSION_GROUPS existed. Not part of the normal
    ingestion flow -- populate_species_and_forms skips a species entirely once its
    PokemonSpecies row exists, so a fresh insert_forms run never needs this; it's
    used only by the one-off migration that scoped existing learnsets down to Gen 1.
    """
    species_ids = session.scalars(select(PokemonSpecies.species_id)).all()
    for species_id in species_ids:
        species_data = offline.species[species_id]
        variety = next(v for v in species_data["varieties"] if v["is_default"])
        pokemon_data = offline.pokemon[variety["pokemon"]["name"]]
        form = session.scalars(
            select(PokemonForm).where(PokemonForm.species_id == species_id)
        ).one()
        insert_learned_moves(session, type_map, move_cache, offline.moves, form.form_id, pokemon_data)


ALLOWED_POKEDEX_VERSIONS = {"red", "blue", "yellow"}


def insert_pokedex_entries(
    session: Session, species_id: int, species_data: dict, version_map: dict[str, int]
) -> None:
    entry_by_version: dict[str, str] = {}
    for entry in species_data.get("flavor_text_entries", []):
        if entry["language"]["name"] != "en":
            continue
        version_name = entry["version"]["name"]
        if version_name not in ALLOWED_POKEDEX_VERSIONS:
            continue
        if version_name not in entry_by_version:
            entry_by_version[version_name] = entry["flavor_text"].replace("\n", " ").replace("\f", " ")

    for version_name, text in entry_by_version.items():
        version_id = version_map.get(version_name)
        if version_id is None:
            continue
        if session.get(PokedexEntry, (species_id, version_id, "en")) is not None:
            continue
        session.add(
            PokedexEntry(species_id=species_id, version_id=version_id, language="en", entry=text)
        )


def insert_pokedex_numbers(session: Session, species_id: int, species_data: dict) -> None:
    for entry in species_data.get("pokedex_numbers", []):
        pokedex_name = entry["pokedex"]["name"]
        if pokedex_name not in {"national", "kanto"}:
            continue
        if session.get(PokedexNumber, (species_id, pokedex_name)) is not None:
            continue
        session.add(
            PokedexNumber(species_id=species_id, pokedex=pokedex_name, entry_number=entry["entry_number"])
        )


def insert_forms(
    session: Session,
    type_map: dict[str, int],
    move_cache: dict[str, int],
    offline: OfflineData,
    species_id: int,
    species_data: dict,
) -> None:
    # Gen 1 had exactly one form per species -- no held items, no Mega Evolution
    # (Gen 6), no Gigantamax (Gen 8), no regional/cosmetic variants of any kind.
    # Only the default variety is ever ingested.
    variety = next(v for v in species_data["varieties"] if v["is_default"])
    pokemon_data = offline.pokemon[variety["pokemon"]["name"]]

    resolved_types = resolve_gen1_types(pokemon_data, type_map)
    if resolved_types is None:
        # Shouldn't happen for a species' own default variety (every in-scope
        # species' Gen-1 type resolves via gen1_type_entries) -- defensive only.
        return

    stats = gen1_stats(pokemon_data)

    form = PokemonForm(
        species_id=species_id,
        height_m=pokemon_data["height"] / 10,
        weight_kg=pokemon_data["weight"] / 10,
        sprite_url=pokemon_data["sprites"].get("front_default"),
        hp=stats["hp"],
        attack=stats["attack"],
        defense=stats["defense"],
        special=stats["special"],
        speed=stats["speed"],
    )
    session.add(form)
    session.flush()

    for type_id, slot in resolved_types:
        session.add(
            PokemonTypeAssociation(form_id=form.form_id, type_id=type_id, slot=slot)
        )

    insert_learned_moves(session, type_map, move_cache, offline.moves, form.form_id, pokemon_data)


def populate_species_and_forms(
    session: Session,
    type_map: dict[str, int],
    version_map: dict[str, int],
    move_cache: dict[str, int],
    offline: OfflineData,
    max_species_id: int,
) -> dict[int, int | None]:
    evolution_map: dict[int, int | None] = {}

    for species_id in range(1, max_species_id + 1):
        species_data = offline.species[species_id]

        evolves_from = species_data.get("evolves_from_species")
        evolution_map[species_id] = extract_id_from_url(evolves_from["url"]) if evolves_from else None

        existing = session.get(PokemonSpecies, species_id)
        if existing is not None:
            insert_pokedex_numbers(session, species_id, species_data)
            session.commit()
            print(f"[{species_id}/{max_species_id}] {species_data['name']} already present, skipping")
            continue

        species = PokemonSpecies(
            species_id=species_id,
            name=species_data["name"],
            generation=GENERATION_NAME_TO_INT[species_data["generation"]["name"]],
            is_legendary=species_data["is_legendary"],
            is_mythical=species_data["is_mythical"],
        )
        session.add(species)

        insert_pokedex_entries(session, species_id, species_data, version_map)
        insert_pokedex_numbers(session, species_id, species_data)
        insert_forms(session, type_map, move_cache, offline, species_id, species_data)

        session.commit()
        print(f"[{species_id}/{max_species_id}] {species_data['name']} done")

    return evolution_map


def backfill_evolutions(session: Session, evolution_map: dict[int, int | None]) -> None:
    updated = 0
    skipped_out_of_scope = 0
    for species_id, evolves_from_id in evolution_map.items():
        if evolves_from_id is None:
            continue
        # evolves_from may point outside the ingested scope (e.g. Pikachu -> Pichu,
        # a Gen 2 baby not present when ingesting Gen 1 only) -- can't satisfy the FK yet.
        if session.get(PokemonSpecies, evolves_from_id) is None:
            skipped_out_of_scope += 1
            continue
        species = session.get(PokemonSpecies, species_id)
        if species.evolves_from_species_id != evolves_from_id:
            species.evolves_from_species_id = evolves_from_id
            updated += 1
    session.commit()
    print(
        f"Backfilled evolves_from_species_id for {updated} species "
        f"({skipped_out_of_scope} skipped: evolves-from out of ingested scope)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate the Pokedex database from PokeAPI")
    parser.add_argument("--max-species-id", type=int, default=151)
    args = parser.parse_args()

    if args.max_species_id > 151:
        raise SystemExit("Gen-1-only scope: --max-species-id must be <= 151")

    session = get_session(get_engine())
    try:
        type_map = load_name_id_map(session, PokemonType, "type_id")
        version_map = load_name_id_map(session, GameVersion, "version_id")
        move_cache = load_name_id_map(session, Move, "move_id")

        offline = OfflineData(
            types=load_offline_lookup(RAW_DATA_DIR / "type.jsonl"),
            moves=load_offline_lookup(RAW_DATA_DIR / "move.jsonl"),
            species=load_offline_lookup(RAW_DATA_DIR / "pokemon-species.jsonl", key="id"),
            pokemon=load_offline_lookup(RAW_DATA_DIR / "pokemon.jsonl"),
        )

        populate_type_efficacy(session, type_map, offline)

        evolution_map = populate_species_and_forms(
            session, type_map, version_map, move_cache, offline, args.max_species_id
        )

        backfill_evolutions(session, evolution_map)
    finally:
        session.close()
    print("Done.")


if __name__ == "__main__":
    main()
