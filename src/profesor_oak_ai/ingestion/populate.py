import argparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import (
    Ability,
    GameVersion,
    Move,
    PokedexEntry,
    PokemonAbility,
    PokemonForm,
    PokemonMove,
    PokemonSpecies,
    PokemonType,
    PokemonTypeAssociation,
    TypeEfficacy,
)
from profesor_oak_ai.ingestion.pokeapi_client import PokeApiClient

# PokeAPI has a handful of obscure learn methods (e.g. "stadium-surfing-pikachu")
# tied to one-off special cases that our learn_method CHECK constraint doesn't cover.
ALLOWED_LEARN_METHODS = {"level-up", "machine", "egg", "tutor"}

GENERATION_ROMAN_NUMERALS = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix"]
GENERATION_NAME_TO_INT = {
    f"generation-{numeral}": index + 1 for index, numeral in enumerate(GENERATION_ROMAN_NUMERALS)
}


def extract_id_from_url(url: str) -> int:
    return int(url.rstrip("/").rsplit("/", 1)[-1])


def strip_species_prefix(pokemon_name: str, species_name: str) -> str:
    prefix = f"{species_name}-"
    return pokemon_name[len(prefix):] if pokemon_name.startswith(prefix) else pokemon_name


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


def populate_type_efficacy(client: PokeApiClient, session: Session, type_map: dict[str, int]) -> None:
    if session.scalar(select(func.count()).select_from(TypeEfficacy)):
        print("type_efficacy already populated, skipping")
        return

    rows = []
    for damage_name, damage_id in type_map.items():
        data = client.get(f"type/{damage_name}")
        relations = data["damage_relations"]
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


def get_or_create_ability(
    client: PokeApiClient, session: Session, cache: dict[str, int], name: str
) -> int:
    if name in cache:
        return cache[name]

    data = client.get(f"ability/{name}")
    description = english_text(data.get("effect_entries", []), "short_effect", "effect")

    ability = Ability(name=name, description=description)
    session.add(ability)
    session.flush()
    cache[name] = ability.ability_id
    return ability.ability_id


def get_or_create_move(
    client: PokeApiClient, session: Session, cache: dict[str, int], type_map: dict[str, int], name: str
) -> int:
    if name in cache:
        return cache[name]

    data = client.get(f"move/{name}")
    effect_description = english_text(data.get("effect_entries", []), "short_effect", "effect")

    move = Move(
        name=name,
        type_id=type_map[data["type"]["name"]],
        damage_class=data["damage_class"]["name"],
        power=data.get("power"),
        accuracy=data.get("accuracy"),
        pp=data["pp"],
        priority=data.get("priority", 0),
        effect_chance=data.get("effect_chance"),
        effect_description=effect_description,
    )
    session.add(move)
    session.flush()
    cache[name] = move.move_id
    return move.move_id


def insert_pokedex_entries(
    session: Session, species_id: int, species_data: dict, version_map: dict[str, int]
) -> None:
    entry_by_version: dict[str, str] = {}
    for entry in species_data.get("flavor_text_entries", []):
        if entry["language"]["name"] != "en":
            continue
        version_name = entry["version"]["name"]
        if version_name not in entry_by_version:
            entry_by_version[version_name] = entry["flavor_text"].replace("\n", " ").replace("\f", " ")

    for version_name, text in entry_by_version.items():
        version_id = version_map.get(version_name)
        if version_id is None:
            continue
        session.add(
            PokedexEntry(species_id=species_id, version_id=version_id, language="en", entry=text)
        )


def insert_forms(
    client: PokeApiClient,
    session: Session,
    type_map: dict[str, int],
    ability_cache: dict[str, int],
    move_cache: dict[str, int],
    species_id: int,
    species_data: dict,
) -> None:
    for variety in species_data.get("varieties", []):
        pokemon_data = client.get(variety["pokemon"]["url"])
        form_name = (
            None
            if variety["is_default"]
            else strip_species_prefix(pokemon_data["name"], species_data["name"])
        )
        stats = {s["stat"]["name"].replace("-", "_"): s["base_stat"] for s in pokemon_data["stats"]}

        form = PokemonForm(
            species_id=species_id,
            form_name=form_name,
            is_default=variety["is_default"],
            height_m=pokemon_data["height"] / 10,
            weight_kg=pokemon_data["weight"] / 10,
            sprite_url=pokemon_data["sprites"].get("front_default"),
            hp=stats["hp"],
            attack=stats["attack"],
            defense=stats["defense"],
            special_attack=stats["special_attack"],
            special_defense=stats["special_defense"],
            speed=stats["speed"],
        )
        session.add(form)
        session.flush()

        for type_entry in pokemon_data["types"]:
            session.add(
                PokemonTypeAssociation(
                    form_id=form.form_id,
                    type_id=type_map[type_entry["type"]["name"]],
                    slot=type_entry["slot"],
                )
            )

        for ability_entry in pokemon_data["abilities"]:
            ability_id = get_or_create_ability(
                client, session, ability_cache, ability_entry["ability"]["name"]
            )
            session.add(
                PokemonAbility(
                    form_id=form.form_id,
                    ability_id=ability_id,
                    slot=ability_entry["slot"],
                    is_hidden=ability_entry["is_hidden"],
                )
            )

        seen_move_keys: set[tuple[str, str, int]] = set()
        for move_entry in pokemon_data["moves"]:
            move_name = move_entry["move"]["name"]
            move_id: int | None = None
            for detail in move_entry["version_group_details"]:
                method = detail["move_learn_method"]["name"]
                if method not in ALLOWED_LEARN_METHODS:
                    continue
                level = detail["level_learned_at"]
                key = (move_name, method, level)
                if key in seen_move_keys:
                    continue
                seen_move_keys.add(key)

                if move_id is None:
                    move_id = get_or_create_move(client, session, move_cache, type_map, move_name)
                session.add(
                    PokemonMove(
                        form_id=form.form_id, move_id=move_id, learn_method=method, level_learned_at=level
                    )
                )


def populate_species_and_forms(
    client: PokeApiClient,
    session: Session,
    type_map: dict[str, int],
    version_map: dict[str, int],
    ability_cache: dict[str, int],
    move_cache: dict[str, int],
    max_species_id: int,
) -> dict[int, int | None]:
    evolution_map: dict[int, int | None] = {}

    for species_id in range(1, max_species_id + 1):
        species_data = client.get(f"pokemon-species/{species_id}")

        evolves_from = species_data.get("evolves_from_species")
        evolution_map[species_id] = extract_id_from_url(evolves_from["url"]) if evolves_from else None

        if session.get(PokemonSpecies, species_id) is not None:
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
        insert_forms(client, session, type_map, ability_cache, move_cache, species_id, species_data)

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

    client = PokeApiClient()
    session = get_session(get_engine())

    type_map = load_name_id_map(session, PokemonType, "type_id")
    version_map = load_name_id_map(session, GameVersion, "version_id")
    ability_cache = load_name_id_map(session, Ability, "ability_id")
    move_cache = load_name_id_map(session, Move, "move_id")

    populate_type_efficacy(client, session, type_map)

    evolution_map = populate_species_and_forms(
        client, session, type_map, version_map, ability_cache, move_cache, args.max_species_id
    )

    backfill_evolutions(session, evolution_map)

    session.close()
    print("Done.")


if __name__ == "__main__":
    main()
