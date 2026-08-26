import json

from profesor_oak_ai.agent import retrieval
from profesor_oak_ai.db.engine import get_engine, get_session
from profesor_oak_ai.vectorstore.client import COLLECTION_NAME, get_qdrant_client
from profesor_oak_ai.vectorstore.embeddings import embed_text

LORE_SEARCH_LIMIT = 5
LORE_SCORE_THRESHOLD = 0.5


def _coerce_list(value: list[str] | str) -> list[str]:
    # Some models JSON-encode array arguments as a string instead of a real list.
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value]
    return value


def get_pokemon_info(name: str) -> str:
    """Look up a Pokémon's types, abilities, base stats, and Pokédex lore by name.

    Args:
        name: The Pokémon's name, e.g. "Pikachu".
    """
    session = get_session(get_engine())
    try:
        species = retrieval.find_species_by_name(session, name)
        if species is None:
            return f"No Pokémon named '{name}' was found in the Pokédex records."
        return retrieval.describe_pokemon(session, species)
    finally:
        session.close()


def get_type_effectiveness(attacking_type: str, defending_types: list[str]) -> str:
    """Compute the damage multiplier of an attacking type against one or two defending types.

    Args:
        attacking_type: The attacking move's type, e.g. "water".
        defending_types: One or two defending Pokémon types, e.g. ["fire"] or ["grass", "poison"].
    """
    defending_types = _coerce_list(defending_types)

    session = get_session(get_engine())
    try:
        factor = retrieval.type_effectiveness(session, attacking_type, defending_types)
        return f"{attacking_type.title()} vs {'/'.join(defending_types).title()}: x{factor} damage."
    except ValueError as exc:
        return str(exc)
    finally:
        session.close()


def get_type_matchups(pokemon_name: str) -> str:
    """Get a Pokémon's full defensive type-matchup profile: every attacking type's
    combined damage multiplier against it (accounting for both types if dual-typed).
    Use this instead of calling get_type_effectiveness repeatedly when asked for a
    Pokémon's overall weaknesses/resistances rather than one specific matchup.

    Args:
        pokemon_name: The Pokémon's name, e.g. "Bulbasaur".
    """
    session = get_session(get_engine())
    try:
        result = retrieval.defensive_type_matchups(session, pokemon_name)
        if result is None:
            return f"No Pokémon named '{pokemon_name}' was found in the Pokédex records."

        buckets: dict[float, list[str]] = {}
        for type_name, factor in result["factors"].items():
            buckets.setdefault(factor, []).append(type_name)

        labels = {
            4.0: "4x weak to",
            2.0: "2x weak to",
            0.5: "0.5x resistant to",
            0.25: "0.25x resistant to",
            0.0: "immune to (0x)",
        }
        types_label = "/".join(t.title() for t in result["types"])
        lines = [f"{pokemon_name.title()} ({types_label}) type matchups:"]
        for factor in (4.0, 2.0, 0.5, 0.25, 0.0):
            names = sorted(buckets.get(factor, []))
            if names:
                lines.append(f"  {labels[factor]}: " + ", ".join(n.title() for n in names))
        return "\n".join(lines)
    finally:
        session.close()


def list_pokemon_by_type(pokemon_type: str) -> str:
    """List Pokémon that have a given type.

    Args:
        pokemon_type: The type to filter by, e.g. "water".
    """
    session = get_session(get_engine())
    try:
        names = retrieval.list_pokemon_by_type(session, pokemon_type)
        if not names:
            return f"No Pokémon found of type '{pokemon_type}'."
        return f"Pokémon of type '{pokemon_type}': " + ", ".join(n.title() for n in names)
    finally:
        session.close()


def list_pokemon_by_color(color: str) -> str:
    """List Pokémon that have a given primary color.

    Args:
        color: The color to filter by, e.g. "yellow", "green", "blue".
    """
    session = get_session(get_engine())
    try:
        names = retrieval.list_pokemon_by_color(session, color)
        if not names:
            return f"No Pokémon found with color '{color}'."
        return f"Pokémon with color '{color}': " + ", ".join(n.title() for n in names)
    finally:
        session.close()


def search_moves(
    pokemon_name: str, move_type: str | None = None, learn_method: str | None = None
) -> str:
    """List moves a Pokémon can learn, optionally filtered by move type or learn method.

    Args:
        pokemon_name: The Pokémon's name, e.g. "Charizard".
        move_type: Optional move type filter, e.g. "fire". Omit for all types.
        learn_method: Optional learn method filter: "level-up", "machine", "egg", or "tutor".
    """
    session = get_session(get_engine())
    try:
        moves = retrieval.moves_for_pokemon(session, pokemon_name, move_type, learn_method)
        if not moves:
            return f"No matching moves found for '{pokemon_name}'."
        lines = [
            f"- {m['name'].title()} ({m['damage_class']}, power={m['power']}, "
            f"accuracy={m['accuracy']}, via {m['learn_method']}"
            + (f" at level {m['level']}" if m["learn_method"] == "level-up" else "")
            + ")"
            for m in moves
        ]
        return "\n".join(lines)
    finally:
        session.close()


def list_pokemon_by_shape(shapes: list[str], pokemon_type: str | None = None) -> str:
    """List Pokémon matching one or more official body-shape categories (authoritative
    Pokédex data, useful for questions about legs, wings, or general body plan).

    IMPORTANT: legless Pokémon are spread across SIX categories, not one -- for any
    "no legs" / "legless" question, pass all six in a single call:
    ["ball", "squiggle", "fish", "arms", "blob", "tentacles"].

    Args:
        shapes: One or more of: "ball" (round, no legs), "squiggle" (serpentine, no legs),
            "fish" (finned, no legs), "arms" (has arms but no legs), "blob" (amorphous, no
            legs), "tentacles" (no legs), "upright" (bipedal, 2 legs), "humanoid" (bipedal,
            2 legs), "quadruped" (4 legs), "legs" (multiple legs, e.g. insectoid), "wings"
            (winged), "bug-wings" (winged insectoid), "heads" (head only), "armor"
            (armored/shelled). Pass multiple values to cover a broader question in one call.
        pokemon_type: Optional type filter, e.g. "water". Omit to search across all types.
    """
    shapes = _coerce_list(shapes)
    session = get_session(get_engine())
    try:
        names = retrieval.list_pokemon_by_shape(session, shapes, pokemon_type)
        if not names:
            return f"No Pokémon found with body shape(s) {shapes}."
        return f"Pokémon with body shape(s) {shapes}: " + ", ".join(n.title() for n in names)
    finally:
        session.close()


def get_pokemon_locations(pokemon_name: str, version: str | None = None) -> str:
    """Find where a Pokémon can be encountered in the wild, with level range per location.

    Args:
        pokemon_name: The Pokémon's name, e.g. "Pikachu".
        version: Optional game version filter, e.g. "red". Omit to search across all versions
            (a Pokémon can have many version-specific locations, so filtering by version
            when the user names a specific game gives a more useful, shorter answer).
    """
    session = get_session(get_engine())
    try:
        locations = retrieval.locations_for_pokemon(session, pokemon_name, version)
        if not locations:
            return f"No known wild locations found for '{pokemon_name}'."
        lines = [
            f"- {loc['location'].replace('-', ' ').title()} ({loc['version']}, "
            f"level {loc['min_level']}-{loc['max_level']})"
            for loc in locations
        ]
        return "\n".join(lines)
    finally:
        session.close()


def get_held_items(pokemon_name: str) -> str:
    """Find items a wild Pokémon can be found holding.

    Args:
        pokemon_name: The Pokémon's name, e.g. "Butterfree".
    """
    session = get_session(get_engine())
    try:
        items = retrieval.held_items_for_pokemon(session, pokemon_name)
        if not items:
            return f"No known held items found for '{pokemon_name}'."
        lines = [
            f"- {item['item'].replace('-', ' ').title()} ({item['rarity']}% chance)"
            for item in items
        ]
        return "\n".join(lines)
    finally:
        session.close()


def search_pokemon_lore(query: str) -> str:
    """Semantically search Pokédex lore/flavor text for Pokémon matching a descriptive or
    thematic query -- use this for questions that name-based or structured lookups can't
    answer, e.g. "which Pokémon is described as sleeping in sunlight" or "a creature that
    stores electricity in its cheeks". Not for exact name lookups (use get_pokemon_info)
    or structured filters like type/shape (use the list_pokemon_by_* tools).

    Args:
        query: A natural-language description of the trait, theme, or behavior to search for.
    """
    client = get_qdrant_client()
    vector = embed_text(query)
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=LORE_SEARCH_LIMIT,
        score_threshold=LORE_SCORE_THRESHOLD,
    ).points

    if not results:
        return f"No Pokémon lore found matching '{query}'."

    lines = [f"- {r.payload['name'].title()}: {r.payload['entry']}" for r in results]
    return "\n".join(lines)


TOOLS = [
    get_pokemon_info,
    get_type_effectiveness,
    get_type_matchups,
    list_pokemon_by_type,
    list_pokemon_by_color,
    search_moves,
    list_pokemon_by_shape,
    get_pokemon_locations,
    get_held_items,
    search_pokemon_lore,
]

# Prefixes tool functions above use for their "nothing found" results, so callers
# (the tool-calling loop) can tell a real lookup from an empty one without re-parsing.
FAILURE_PREFIXES = (
    "No Pokémon named",
    "Unknown type:",
    "No Pokémon found of type",
    "No Pokémon found with color",
    "No matching moves found",
    "No Pokémon found with body shape",
    "No known wild locations found",
    "No known held items found",
    "No Pokémon lore found matching",
)


def is_failure(result: str) -> bool:
    return result.startswith(FAILURE_PREFIXES)
