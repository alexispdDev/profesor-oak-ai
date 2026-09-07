#!/bin/sh
set -e

if [ -z "$(ls -A pokemon_raw_data 2>/dev/null)" ]; then
    echo "Fetching raw PokeAPI dump (one-time)..."
    uv run python -m profesor_oak_ai.ingestion.fetch_raw_data
fi

echo "Applying database migrations..."
uv run alembic upgrade head

echo "Populating database from raw dump (idempotent, skips rows already inserted)..."
uv run python -m profesor_oak_ai.ingestion.populate --max-species-id 151
uv run python -m profesor_oak_ai.ingestion.populate_from_raw
uv run python -m profesor_oak_ai.ingestion.populate_colors
uv run python -m profesor_oak_ai.ingestion.populate_growth_rates
uv run python -m profesor_oak_ai.ingestion.populate_evolutions
uv run python -m profesor_oak_ai.ingestion.populate_location_encounters
uv run python -m profesor_oak_ai.ingestion.populate_gen1ou_usage

exec "$@"
