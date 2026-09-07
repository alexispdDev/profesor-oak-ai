import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.db.models import Item, Move, PokemonSpecies, SpeciesEvolution
from profesor_oak_ai.ingestion.populate import RAW_DATA_DIR, load_name_id_map, load_offline_lookup
from profesor_oak_ai.ingestion.populate_from_raw import build_form_lookup, get_or_create_item_offline

# evolution-trigger.jsonl has 16 total trigger types; only these 3 occur for
# species_id <= 151 (Gen 8/9 triggers like "shed" never appear in scope).
ALLOWED_TRIGGERS = {"level-up", "trade", "use-item"}

# The 5 classic evolution stones are the only evolution items that existed in Gen 1 --
# ice-stone (Gen 7, Alolan-form evolutions) and galarica-cuff (Gen 8, Galarian-form
# evolutions) also appear in the raw data for in-scope species but are anachronistic.
# held_item (evolving while holding an item, e.g. Chansey->Blissey via Oval Stone) is
# an entirely Gen 4+ mechanic with no Gen-1 case at all, so it's never allowed.
ALLOWED_EVOLUTION_ITEMS = {"fire-stone", "water-stone", "thunder-stone", "leaf-stone", "moon-stone"}


def resolve_form(form_lookup: dict[str, int], form_ref: dict | None) -> int | None:
    if form_ref is None:
        return None
    return form_lookup.get(form_ref["name"])


def build_row(
    session: Session,
    species_id: int,
    ed: dict,
    form_lookup: dict[str, int],
    item_cache: dict[str, int],
    offline_items: dict[str, dict],
    move_map: dict[str, int],
) -> SpeciesEvolution:
    item = ed.get("item")
    known_move = ed.get("known_move")
    region = ed.get("region")

    return SpeciesEvolution(
        species_id=species_id,
        trigger_type=ed["trigger"]["name"],
        version_group=ed["version_group"]["name"],
        is_default=ed["is_default"],
        min_level=ed.get("min_level"),
        item_id=get_or_create_item_offline(session, item_cache, offline_items, item["name"])
        if item else None,
        known_move_id=move_map.get(known_move["name"]) if known_move else None,
        min_happiness=ed.get("min_happiness"),
        time_of_day=ed.get("time_of_day") or None,
        relative_physical_stats=ed.get("relative_physical_stats"),
        region=region["name"] if region else None,
        base_form_id=resolve_form(form_lookup, ed.get("base_form")),
        evolved_form_id=resolve_form(form_lookup, ed.get("evolved_form")),
    )


def walk_chain(
    node: dict, species_lookup: dict[str, int], parent_in_scope: bool = True
) -> list[tuple[int, dict, bool]]:
    """Recursively collects (species_id, evolution_details_entry, parent_in_scope)
    triples for every in-scope species below this node. Always recurses into
    evolves_to regardless of whether the current node is in scope -- out-of-scope
    and in-scope species can interleave within one chain (e.g. Tyrogue, out of
    scope, evolving into Hitmonlee/Hitmonchan, both in scope).

    parent_in_scope tracks whether the immediate parent (the species this node
    evolves FROM) is itself one of the 151 in-scope species. When it isn't, the
    evolution condition describes a mechanism requiring a later-generation "baby"
    species (Pichu, Cleffa, Tyrogue, Mime Jr., Smoochum, Elekid, Magby, Munchlax)
    that didn't exist in Gen 1 -- the caller skips these entirely. version_group is
    NOT a reliable signal for this on its own: PokeAPI mislabels Tyrogue->Hitmonlee/
    Hitmonchan as "red-blue" despite Tyrogue being Gen 2, so this must be checked
    structurally via the chain's actual parent-child relationship."""
    pairs = []
    species_id = species_lookup.get(node["species"]["name"])
    if species_id is not None:
        for ed in node.get("evolution_details", []):
            pairs.append((species_id, ed, parent_in_scope))
    this_in_scope = species_id is not None
    for child in node.get("evolves_to", []):
        pairs.extend(walk_chain(child, species_lookup, this_in_scope))
    return pairs


def natural_key(row: SpeciesEvolution) -> tuple:
    return (row.species_id, row.trigger_type, row.version_group, row.evolved_form_id, row.base_form_id)


def load_existing_keys(session: Session) -> set[tuple]:
    rows = session.execute(
        select(
            SpeciesEvolution.species_id,
            SpeciesEvolution.trigger_type,
            SpeciesEvolution.version_group,
            SpeciesEvolution.evolved_form_id,
            SpeciesEvolution.base_form_id,
        )
    ).all()
    return {tuple(r) for r in rows}


def populate_evolutions(session: Session) -> None:
    species_lookup = load_name_id_map(session, PokemonSpecies, "species_id")
    form_lookup = build_form_lookup(session)
    move_map = load_name_id_map(session, Move, "move_id")
    item_cache = load_name_id_map(session, Item, "item_id")
    offline_items = load_offline_lookup(RAW_DATA_DIR / "item.jsonl")
    existing_keys = load_existing_keys(session)

    inserted = 0
    already_present = 0
    skipped_trigger = 0
    skipped_item = 0
    skipped_form = 0
    skipped_parent = 0

    with open(RAW_DATA_DIR / "evolution-chain.jsonl", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            for species_id, ed, parent_in_scope in walk_chain(data["chain"], species_lookup):
                if not parent_in_scope:
                    skipped_parent += 1
                    continue

                trigger_name = ed["trigger"]["name"] if ed["trigger"] else None
                if trigger_name not in ALLOWED_TRIGGERS:
                    skipped_trigger += 1
                    continue

                item = ed.get("item")
                if ed.get("held_item") or (item and item["name"] not in ALLOWED_EVOLUTION_ITEMS):
                    skipped_item += 1
                    continue

                # A condition disambiguated by base_form/evolved_form describes a
                # regional-variant form (e.g. Alolan Raichu) that no longer exists
                # in this schema -- Gen 1 had no alternate forms at all. Skip the
                # whole condition rather than silently dropping just the
                # disambiguation and inserting a form-blind approximation.
                base_form = ed.get("base_form")
                evolved_form = ed.get("evolved_form")
                if (base_form and resolve_form(form_lookup, base_form) is None) or (
                    evolved_form and resolve_form(form_lookup, evolved_form) is None
                ):
                    skipped_form += 1
                    continue

                row = build_row(session, species_id, ed, form_lookup, item_cache, offline_items, move_map)
                key = natural_key(row)
                if key in existing_keys:
                    already_present += 1
                    continue

                session.add(row)
                existing_keys.add(key)
                inserted += 1

            session.commit()
            print(f"chain {data['id']}: done")

    print(
        f"\nDone. {inserted} inserted, {already_present} already present, "
        f"{skipped_trigger} skipped (out-of-scope trigger), "
        f"{skipped_item} skipped (anachronistic item), "
        f"{skipped_form} skipped (regional-variant form), "
        f"{skipped_parent} skipped (out-of-scope baby parent)."
    )


def main() -> None:
    session = get_session(get_engine())
    try:
        populate_evolutions(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
