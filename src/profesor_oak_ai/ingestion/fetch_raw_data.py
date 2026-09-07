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
    "characteristic", "egg-group", "gender", "growth-rate", "nature",
    "pokeathlon-stat", "pokemon", "pokemon-color",
    "pokemon-species",
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


def load_failed_items(output_path: Path) -> list[dict] | None:
    """Returns the items that failed on a previous run of this endpoint, or None if
    there's no record of a partial failure (output_path is either missing or the
    previous run completed with no failures)."""
    failed_path = output_path.with_name(output_path.name + ".failed.json")
    if not failed_path.exists():
        return None
    with open(failed_path, encoding="utf-8") as f:
        return json.load(f)


def save_failed_items(output_path: Path, failed_items: list[dict]) -> None:
    failed_path = output_path.with_name(output_path.name + ".failed.json")
    if failed_items:
        with open(failed_path, "w", encoding="utf-8") as f:
            json.dump(failed_items, f)
    elif failed_path.exists():
        failed_path.unlink()


def fetch_items(client: PokeApiClient, items: list[dict], f_out, desc: str, write_fn) -> list[dict]:
    """Fetches each item's url and passes (f_out, item, data) to write_fn on success.
    Returns the items that failed to fetch."""
    failed = []
    for item in tqdm(items, desc=desc):
        try:
            data = client.get(item["url"])
            write_fn(f_out, item, data)
        except RuntimeError as e:
            # RuntimeError is what PokeApiClient.get() raises after exhausting its
            # own retries -- a real API-level failure worth skipping-and-continuing
            # on. Anything else (KeyError, TypeError, ...) means the response shape
            # or our own code is wrong and should surface immediately, not be
            # silently swallowed for every item in the loop.
            tqdm.write(f"Error fetching {item.get('name', item.get('id', item.get('url')))}: {e}")
            failed.append(item)
    return failed


def _write_raw(f_out, item: dict, data: dict) -> None:
    f_out.write(json.dumps(data, ensure_ascii=False) + "\n")


def _write_encounter(f_out, item: dict, data: dict) -> None:
    f_out.write(json.dumps({"id": item["id"], "locations": data}, ensure_ascii=False) + "\n")


def dump_resource(
    client: PokeApiClient, endpoint: str, output_dir: Path, force: bool = False
) -> int:
    """Fetches one endpoint's resources to JSONL. Returns the number of items that
    failed to fetch (0 if skipped or fully successful). A partial failure is recorded
    in a '{endpoint}.jsonl.failed.json' sidecar so the next run (without --force)
    retries only the failed items instead of refetching the whole endpoint."""
    output_path = output_dir / f"{endpoint}.jsonl"

    if output_path.exists() and not force:
        failed_items = load_failed_items(output_path)
        if failed_items is None:
            print(f"{endpoint}: already fetched, skipping")
            return 0
        print(f"{endpoint}: retrying {len(failed_items)} previously failed item(s)")
        with open(output_path, "a", encoding="utf-8") as f_out:
            still_failed = fetch_items(client, failed_items, f_out, endpoint, _write_raw)
        save_failed_items(output_path, still_failed)
        return len(still_failed)

    resources = get_resource_list(client, endpoint)
    with open(output_path, "w", encoding="utf-8") as f_out:
        failed_items = fetch_items(client, resources, f_out, endpoint, _write_raw)
    save_failed_items(output_path, failed_items)
    return len(failed_items)


def dump_location_area_encounters(
    client: PokeApiClient, output_dir: Path, force: bool = False
) -> int:
    """Returns the number of Pokémon whose encounters failed to fetch (0 if skipped
    or fully successful). Same failed-item sidecar/retry behavior as dump_resource."""
    output_path = output_dir / "pokemon_location_areas.jsonl"

    if output_path.exists() and not force:
        failed_items = load_failed_items(output_path)
        if failed_items is None:
            print("location-area-encounters: already fetched, skipping")
            return 0
        print(f"location-area-encounters: retrying {len(failed_items)} previously failed item(s)")
        with open(output_path, "a", encoding="utf-8") as f_out:
            still_failed = fetch_items(
                client, failed_items, f_out, "location-area-encounters", _write_encounter
            )
        save_failed_items(output_path, still_failed)
        return len(still_failed)

    pokemon_path = output_dir / "pokemon.jsonl"
    # Extract only the (small) id/url pair from each line rather than keeping every
    # full pokemon record in memory -- each record is large (stats/moves/abilities/
    # sprites/etc.) and only the id and encounters URL are actually needed here.
    items = []
    with open(pokemon_path, encoding="utf-8") as f_in:
        for line in f_in:
            entry = json.loads(line)
            items.append({"id": entry["id"], "url": entry["location_area_encounters"]})

    with open(output_path, "w", encoding="utf-8") as f_out:
        failed_items = fetch_items(client, items, f_out, "location-area-encounters", _write_encounter)
    save_failed_items(output_path, failed_items)
    return len(failed_items)


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
