import argparse
import json
from pathlib import Path

from tqdm import tqdm

from profesor_oak_ai.ingestion.pokeapi_client import PokeApiClient

OUTPUT_DIR = Path("pokemon_raw_data")

ENDPOINTS = [
    "berry", "berry-firmness", "berry-flavor",
    "contest-type", "contest-effect", "super-contest-effect",
    "currency",
    "encounter-method", "encounter-condition", "encounter-condition-value",
    "evolution-chain", "evolution-trigger",
    "generation",
    "pokedex",
    "version", "version-group",
    "item", "item-attribute", "item-category", "item-fling-effect",
    "item-pocket",
    "location", "location-area",
    "pal-park-area",
    "region",
    "machine",
    "move", "move-ailment", "move-battle-style", "move-category", "move-damage-class",
    "move-learn-method", "move-target",
    "ability", "characteristic", "egg-group", "gender", "growth-rate", "nature",
    "pokeathlon-stat", "pokemon", "pokemon-color", "pokemon-form", "pokemon-habitat",
    "pokemon-shape", "pokemon-species",
    "stat",
    "type",
    "language",
]


LIST_PAGE_LIMIT = 100_000  # PokeAPI defaults list endpoints to a page size of 20;
# requesting a huge limit gets everything in a single request instead of dozens/
# hundreds of paginated round-trips (e.g. ~65 requests for pokemon/ alone at limit=20).


def get_resource_list(client: PokeApiClient, resource: str) -> list[dict]:
    url = f"{resource}/?limit={LIST_PAGE_LIMIT}"
    resource_list: list[dict] = []

    while True:
        data = client.get(url)
        resource_list.extend(data["results"])
        url = data["next"]
        if url is None:
            break
    return resource_list


def dump_resource(
    client: PokeApiClient, endpoint: str, output_dir: Path, force: bool = False
) -> int:
    """Fetches one endpoint's resources to JSONL. Returns the number of items that
    failed to fetch (0 if skipped or fully successful)."""
    output_path = output_dir / f"{endpoint}.jsonl"
    if output_path.exists() and not force:
        print(f"{endpoint}: already fetched, skipping")
        return 0

    resources = get_resource_list(client, endpoint)
    failures = 0

    with open(output_path, "w", encoding="utf-8") as f_out:
        for item in tqdm(resources, desc=endpoint):
            try:
                data = client.get(item["url"])
                f_out.write(json.dumps(data, ensure_ascii=False) + "\n")
            except RuntimeError as e:
                # RuntimeError is what PokeApiClient.get() raises after exhausting its
                # own retries -- a real API-level failure worth skipping-and-continuing
                # on. Anything else (KeyError, TypeError, ...) means the response shape
                # or our own code is wrong and should surface immediately, not be
                # silently swallowed for every item in the loop.
                tqdm.write(f"Error fetching {item.get('name', item.get('url'))}: {e}")
                failures += 1

    return failures


def dump_location_area_encounters(
    client: PokeApiClient, output_dir: Path, force: bool = False
) -> int:
    """Returns the number of Pokémon whose encounters failed to fetch (0 if skipped
    or fully successful)."""
    output_path = output_dir / "pokemon_location_areas.jsonl"
    if output_path.exists() and not force:
        print("location-area-encounters: already fetched, skipping")
        return 0

    pokemon_path = output_dir / "pokemon.jsonl"
    with open(pokemon_path, encoding="utf-8") as f:
        total = sum(1 for _ in f)

    failures = 0
    with (
        open(output_path, "w", encoding="utf-8") as f_out,
        open(pokemon_path, encoding="utf-8") as f_in,
    ):
        # Stream pokemon.jsonl line-by-line rather than loading every full record into
        # memory up front -- each record is large (stats/moves/abilities/sprites/etc.)
        # and only the id is actually needed here.
        for line in tqdm(f_in, total=total, desc="location-area-encounters"):
            entry = json.loads(line)
            pokemon_id = entry["id"]
            url = entry["location_area_encounters"]
            try:
                data = client.get(url)
                f_out.write(json.dumps({"id": pokemon_id, "locations": data}, ensure_ascii=False) + "\n")
            except RuntimeError as e:
                tqdm.write(f"Error fetching encounters for {pokemon_id}: {e}")
                failures += 1

    return failures


LOCATION_AREA_ENCOUNTERS = "location-area-encounters"
ALL_TARGETS = [*ENDPOINTS, LOCATION_AREA_ENCOUNTERS]


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump PokeAPI's resource catalog to raw JSONL")
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="ENDPOINT",
        help=f"Only fetch these targets instead of all of them, e.g. --only pokemon move. "
        f"Also accepts '{LOCATION_AREA_ENCOUNTERS}'.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refetch even if the output file already exists.",
    )
    args = parser.parse_args()

    targets = args.only if args.only else ALL_TARGETS
    unknown = set(targets) - set(ALL_TARGETS)
    if unknown:
        raise SystemExit(f"Unknown endpoint(s): {', '.join(sorted(unknown))}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    client = PokeApiClient()

    failures_by_target: dict[str, int] = {}

    for endpoint in targets:
        if endpoint == LOCATION_AREA_ENCOUNTERS:
            continue
        print(endpoint)
        failures = dump_resource(client, endpoint, OUTPUT_DIR, force=args.force)
        if failures:
            failures_by_target[endpoint] = failures

    if LOCATION_AREA_ENCOUNTERS in targets:
        failures = dump_location_area_encounters(client, OUTPUT_DIR, force=args.force)
        if failures:
            failures_by_target[LOCATION_AREA_ENCOUNTERS] = failures

    total_failures = sum(failures_by_target.values())
    if total_failures:
        print(f"\nDone, with {total_failures} item(s) failed:")
        for target, count in failures_by_target.items():
            print(f"  {target}: {count}")
    else:
        print("\nDone, no failures.")


if __name__ == "__main__":
    main()
