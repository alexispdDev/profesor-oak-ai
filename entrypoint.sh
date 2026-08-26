#!/bin/sh
set -e

needs_ingest=0
[ -f data/pokedex.db ] || needs_ingest=1

if [ -z "$(ls -A pokemon_raw_data 2>/dev/null)" ]; then
    echo "Fetching raw PokeAPI dump (one-time)..."
    uv run python -m profesor_oak_ai.ingestion.fetch_raw_data
fi

echo "Applying database migrations..."
uv run alembic upgrade head

if [ "$needs_ingest" = "1" ]; then
    echo "Populating database from raw dump (one-time)..."
    uv run python -m profesor_oak_ai.ingestion.populate --max-species-id 151
    uv run python -m profesor_oak_ai.ingestion.populate_from_raw
    uv run python -m profesor_oak_ai.ingestion.populate_colors
    uv run python -m profesor_oak_ai.ingestion.populate_habitats
    uv run python -m profesor_oak_ai.ingestion.populate_shapes
    uv run python -m profesor_oak_ai.ingestion.populate_growth_rates
    uv run python -m profesor_oak_ai.ingestion.populate_egg_groups
    uv run python -m profesor_oak_ai.ingestion.populate_evolutions
    uv run python -m profesor_oak_ai.ingestion.populate_natures
    uv run python -m profesor_oak_ai.ingestion.populate_characteristics
    uv run python -m profesor_oak_ai.ingestion.populate_form_triggers
    uv run python -m profesor_oak_ai.ingestion.populate_location_encounters
fi

exec "$@"
