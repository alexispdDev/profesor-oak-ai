## Professor Oak AI: Pokémon Battle & Lore Assistant
### Problem Statement

When playing Pokémon or researching the games, getting accurate information is surprisingly tricky because the data is split into two completely different types:

* **Strict Numeric Stats**: Things like type effectiveness, base stats, and move sets where precision is key.

* **Open-ended Lore**: Background stories, legendary myths, and Pokédex descriptions spread across different game versions.

General-purpose LLMs usually struggle here. They frequently hallucinate stats, mix up mechanics between different game generations, or confuse move pools. On the flip side, manually digging through wikis and spreadsheets to prepare a single battle strategy takes too much time.

#### Project Goal & Solution

Professor Oak AI is a domain-specific RAG (Retrieval-Augmented Generation) assistant designed to act as an expert guide for Pokémon trainers.

Instead of relying solely on the LLM's pre-trained memory, this system grounds its answers in a curated dataset combining structured game mechanics and Pokédex entries.

#### Key Features

* **Battle & Tactical Advice**: Offers team-building suggestions and type match-up strategies using verified stat data.

* **Canonical Pokédex Lore**: Surfaces official in-game descriptions for a named Pokémon, straight from canonical Pokédex entries.

* **Structured Retrieval**: Uses keyword/name matching against a curated SQL database to keep answers grounded and hallucination-free.

## Architecture

```mermaid
flowchart TD
    RawData["PokeAPI raw dump<br/>pokemon_raw_data/*.jsonl"]
    Ingestion["Ingestion pipeline<br/>8 scripts (fetch + 7 populate_*.py)"]
    DB[("SQLite<br/>data/pokedex.db<br/>23 tables")]
    Retrieval["retrieval.py<br/>SQLAlchemy queries"]
    Tools["tools.py<br/>19 LLM-callable tools"]
    LLM["llm.py<br/>OpenAI tool-calling loop"]
    CLI["cli.py<br/>interactive + one-shot"]
    API["api.py<br/>FastAPI (/question)"]
    Conv["conversations.py<br/>ask_and_log"]
    Eval["evaluation/<br/>ground truth + LLM-judge"]
    User["User"]

    RawData --> Ingestion --> DB
    DB --> Retrieval --> Tools --> LLM
    DB -.direct query, team_builder.py.-> Tools
    Retrieval -.baseline context.-> LLM
    Tools -.narration call, team_agent.py.-> LLM
    User --> CLI --> Conv
    User --> API --> Conv
    Conv --> LLM --> Conv
    Conv --> DB
    DB -.-> Eval
    LLM -.-> Eval

    style DB fill:#336791,color:#fff
    style LLM fill:#10a37f,color:#fff
    style Eval fill:#f46800,color:#fff
```

Every question first gets a baseline context block injected automatically (`retrieve_context`, a keyword/name match against the question text — no LLM call needed for this step), then goes through an OpenAI tool-calling loop that can call any of 19 tools to fetch more specific data before answering. Most tools go through `retrieval.py`, but the team-building tool (`build_team`) is its own self-contained pipeline: `team_builder.py` queries the database directly (not through `retrieval.py`) and `team_agent.py` deterministically assembles a full roster, making its own separate OpenAI call at the very end just to narrate the already-decided result in prose — a second, independent LLM call site nested inside the outer tool-calling loop, not a call back into it. `cli.py` and `api.py` are both thin callers around the same `conversations.ask_and_log()` orchestration, so every conversation gets persisted identically to the same SQLite database the agent reads from, regardless of which interface was used.

## Quickstart

```bash
uv sync
echo "OPENAI_API_KEY=sk-..." >> .env

# build the database (fetches the PokeAPI dump once, then ingests it offline)
uv run alembic upgrade head
uv run python -m profesor_oak_ai.ingestion.fetch_raw_data
uv run python -m profesor_oak_ai.ingestion.populate --max-species-id 151
uv run python -m profesor_oak_ai.ingestion.populate_from_raw
uv run python -m profesor_oak_ai.ingestion.populate_colors
uv run python -m profesor_oak_ai.ingestion.populate_growth_rates
uv run python -m profesor_oak_ai.ingestion.populate_evolutions
uv run python -m profesor_oak_ai.ingestion.populate_location_encounters
uv run python -m profesor_oak_ai.ingestion.populate_gen1ou_usage

uv run profesor-oak-ai
```

Or start the HTTP API instead of the CLI:
```bash
uv run profesor-oak-ai-api
# or, for auto-reload during development:
uv run uvicorn profesor_oak_ai.agent.api:app --reload

curl -X POST localhost:8000/question \
  -H 'content-type: application/json' \
  -d '{"question": "What are Bulbasaur'"'"'s types and base stats?"}'
```
Interactive Swagger docs are served at `localhost:8000/docs`.

### Or run everything in Docker

```bash
echo "OPENAI_API_KEY=sk-..." >> .env
docker compose up --build
```
The container's `entrypoint.sh` runs the same steps as the manual Quickstart above (fetch the raw dump if `pokemon_raw_data/` is empty, apply migrations, then run the populate scripts, which are idempotent and skip rows already inserted) before starting the API on `localhost:8000`. `data/` and `pokemon_raw_data/` are bind-mounted from the host, so a first run builds the database once and every subsequent `docker compose up` reruns the populate scripts as a fast no-op instead of rebuilding; deleting either directory forces a rebuild, same as the non-Docker workflow. Running the populate scripts unconditionally (rather than gating on `data/pokedex.db` existing) also means a container that's interrupted mid-ingestion resumes correctly on the next start instead of silently skipping the rest.

Run the CLI through the same image instead:
```bash
docker compose run --rm -it app profesor-oak-ai            # interactive
docker compose run --rm app profesor-oak-ai "What are Bulbasaur's types and base stats?"  # one-shot
```

### Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/) for dependency management
- An OpenAI API key

The ingestion scripts are idempotent (safe to re-run; each one skips rows it's already inserted) and offline after the one `fetch_raw_data` step — everything else reads only from the `pokemon_raw_data/` dump, no further network access. `data/pokedex.db` is gitignored and disposable: delete it and re-run the steps above to rebuild from scratch.

## Testing

There is no automated test suite (see [Limitations](#limitations)) — the CLI is the primary way to exercise the application, alongside the evaluation harness below.

Interactive mode:
```bash
uv run profesor-oak-ai
```

One-shot mode (answers a single question and exits, script-friendly):
```bash
uv run profesor-oak-ai "What are Bulbasaur's types and base stats?"
```

Example:
```
> How effective is a Water-type move against a Fire/Rock Pokémon?
Water is 4x effective against a Fire/Rock-type Pokémon...
```

Every conversation, in both interactive and one-shot mode, is also run through the same LLM-as-judge relevance check used by the evaluation harness below, and has its token usage and USD cost tracked (`relevance`, token counts, `cost`, etc. on the `conversations` table) — not just conversations logged during an eval run. The same is true of the HTTP API's `POST /question`, since both interfaces call the same `conversations.ask_and_log()`.

### HTTP API

```bash
uv run profesor-oak-ai-api
```

- `POST /question` — body `{"question": "...", "thread_id": "..."}` (`thread_id` optional, omit to start a new conversation thread), returns `{"conversation_id": "...", "thread_id": "...", "answer": "..."}`.
- `GET /health` — liveness check.
- `GET /dashboard` — a small monitoring page (conversation/cost totals, relevance breakdown, daily activity, recent conversations), reading directly from the `conversations` table. See [Monitoring](#monitoring) below.

## Evaluation

### Retrieval and RAG evaluation

This project's retrieval isn't a single ranked-index lookup (like a vector or TF-IDF search) — the agent *chooses which of 19 tools to call* via OpenAI tool-calling, on top of an automatically-injected baseline context. So the two metrics are adapted accordingly:

- **Retrieval accuracy**: for a ground-truth question with a known expected tool, was that tool actually invoked?
- **RAG evaluation**: an LLM-as-judge call classifies the final answer as `RELEVANT`, `PARTLY_RELEVANT`, or `NON_RELEVANT`.

Ground truth: 18 hand-written questions in [`evaluation/ground_truth.jsonl`](evaluation/ground_truth.jsonl). Run the harness with:
```bash
uv run python -m profesor_oak_ai.evaluation.run_eval
```

[`evaluation/results.csv`](evaluation/results.csv) holds the latest run's output, but it predates several tool changes (it references at least one tool, `get_held_items`, that no longer exists) — re-run the harness above for current numbers rather than trusting that file as-is.

## Monitoring

```bash
uv run profesor-oak-ai-api
# then open http://localhost:8000/dashboard
```

A small server-rendered dashboard, reading live from the same `conversations` table every CLI and API call writes to (`agent/dashboard.py`, no separate ETL or export step):

- Summary cards: total conversations, total cost (USD), average tokens/conversation
- Relevance breakdown (`RELEVANT`/`PARTLY_RELEVANT`/`NON_RELEVANT`/`UNKNOWN`, plus "Not judged" for conversations logged before relevance tracking existed)
- Grounding breakdown: how each answer's subject got confirmed real — `context` (the automatic baseline retrieval), `tool` (a name-resolving tool call), or `none` (never grounded, worth checking for hallucinated subjects that slipped past rule 3), plus "Not tracked" for conversations logged before grounding tracking existed
- Daily activity: conversations and cost per day, last 14 days
- Recent conversations table, with relevance, grounding source, and cost per row

No new service or dependency — it's one FastAPI route rendering plain HTML with inline CSS (see [Decisions and trade-offs](#decisions-and-trade-offs) for why this was chosen over Grafana).

## Decisions and trade-offs

- **SQL/keyword retrieval over vector embeddings**: this project used Qdrant + Ollama embeddings for semantic lore search earlier on, then removed it. The dataset is fully structured (a relational Pokédex, not free-text documents), so exact/fuzzy name and keyword matching against SQL columns covers the real query patterns without the operational overhead of an embedding store.
- **SQLite over Postgres**: conversation logging reuses the same SQLite database the ingestion pipeline already builds, rather than adding a second database engine — nothing else in this project needs Postgres's concurrency/networking features.
- **Gen 1-only ingestion scope** (`--max-species-id 151`): the ingestion pipeline can be pointed at more species, but every design decision (which evolution-condition fields to model, which Pokédexes to store numbers for, which type-chart generation to treat as historical) was scoped and verified against Gen 1 specifically. Raising the scope is possible but would need re-auditing several of those decisions.
- **Types, type-effectiveness, and base stats are all Gen-1-canonical, not "modern is primary"**: a species' type, its full type-effectiveness chart, and its base stats (including a single `special` stat, not the Special Attack/Special Defense split introduced in Gen 2) are all corrected to their real Gen-1 values at ingestion time rather than showing PokeAPI's modern reclassification -- e.g. Clefairy shows as Normal (its real Gen-1 type), not Fairy (its Gen-6 retype); Psychic-types show no Dark-type weakness at all, since Dark didn't exist yet; Charizard shows Special 85, not the modern Sp.Atk 109/Sp.Def 85 split (Game Freak didn't evenly divide the old value when they split it in Gen 2 -- 111 of 151 species diverge). For a Gen-1-only app the *current* PokeAPI value is simply wrong in each of these cases, so ingestion prefers the historical override (`past_damage_relations`/`past_types`/`past_stats`) over the modern one, correcting the primary table directly -- no separate delta table exists anywhere in the schema for this purpose anymore (`PastTypeEfficacy`, `PokemonPastType`, and `PokemonPastStat` were all removed once their data was baked into the primary tables).
- **Movesets are scoped to Red/Blue/Yellow, not every game a move has ever appeared in**: PokeAPI's per-species movepool spans every generation through the present, so ingestion only keeps a `version_group_details` entry when its game version is Gen 1 (`red-blue`/`yellow`) -- e.g. Charizard's level-up moves are exactly its real Gen-1 set (Ember/Growl/Leer/Scratch at 1, Rage at 24, Slash at 36, Flamethrower at 46, Fire Spin at 55), not padded with moves it only learned via a later TM, egg move, or tutor (neither of the latter two existed yet). A handful of species genuinely learn a move at a different level in Yellow than in Red/Blue (Yellow retuned some movesets to match the anime); both values are kept as separate rows rather than picking one arbitrarily.
- **`ask()`/`run_conversation()` kept persistence- and evaluation-agnostic**: the core question-answering functions have no knowledge of conversation logging or evaluation. Persistence, judging, and cost tracking live in `conversations.ask_and_log()`, one shared orchestration function that both `cli.py` and `api.py` call — this is what let the HTTP API get added as a thin new caller instead of a rewrite.
- **FastAPI over Flask for the HTTP API**: the fitness-assistant reference project uses Flask, but this project picked FastAPI instead for built-in request validation (Pydantic) and automatic OpenAPI/Swagger docs (`/docs`), at the cost of diverging from the example's stack.
- **Bind-mounted `data/`/`pokemon_raw_data/` over named Docker volumes**: this is a single-container, single-machine SQLite setup, not a multi-host deployment, so there's no benefit to hiding the database inside Docker-managed storage. Bind-mounting lets a container reuse whatever's already built on the host (instant startup) and lets a fresh build's output be inspected from outside Docker too.
- **One idempotent `entrypoint.sh` for both the API and CLI**: it checks for existing data, fetches/migrates/populates only what's missing (reusing the exact Quickstart command list, not a re-derived one), then `exec`s whatever command was passed in — so `docker compose up` (the API) and `docker compose run app profesor-oak-ai ...` (the CLI) share one bootstrap path instead of two.
- **Built-in HTML dashboard over Grafana**: the fitness-assistant reference project uses Grafana against Postgres. This project's data lives in SQLite, and Grafana's SQLite support is an unsigned community plugin rather than a first-class data source — adding it (plus a new docker-compose service) for a handful of read-only aggregate queries was more infra than the payoff justified. A single FastAPI route querying the existing tables directly avoids that fragility, at the cost of a less polished/interactive UI than Grafana would give. Note that per-tool usage (which of the 19 tools got called) isn't a metric this dashboard can show, since that's never persisted per conversation — only the final answer, relevance, and token/cost counts are.

## Project structure

```text
src/profesor_oak_ai/
  agent/
    cli.py            # Interactive + one-shot CLI
    api.py             # FastAPI HTTP API (/question, /health, /dashboard)
    llm.py             # OpenAI tool-calling loop (run_conversation/ask) + LLM-as-judge
    prompts.py          # System prompt (Professor Oak persona + grounding rules)
    retrieval.py         # Read-only SQLAlchemy queries backing the tools
    tools.py            # 19 LLM-callable tools, wraps retrieval.py/team_builder.py/team_agent.py
    team_builder.py       # Pure data layer for team-building (pervasiveness, liabilities, etc.)
    team_agent.py         # Deterministic team-building pipeline behind the build_team tool
    conversations.py      # ask_and_log() shared by cli.py/api.py, multi-turn thread history
    dashboard.py         # Queries + HTML for GET /dashboard
  db/
    engine.py           # SQLite engine/session setup
    models.py            # SQLAlchemy models
  ingestion/            # 8 scripts that build the database from the raw PokeAPI dump
  evaluation/
    run_eval.py          # Ground-truth-driven retrieval + RAG evaluation harness
evaluation/
  ground_truth.jsonl      # 18 hand-written evaluation questions
  results.csv            # An evaluation run's output (may be stale, see Evaluation above)
pokemon_raw_data/         # Raw PokeAPI dump (fetched once, offline after that) + gen1ou-1760.json
alembic/versions/         # Migrations tracking the schema's evolution
data/pokedex.db          # SQLite database (gitignored, rebuilt from the steps above)
ingestion_gaps.txt        # Detailed field-by-field ingestion audit notes
agent_tool_gaps.txt       # Tracked tool ideas not yet built
Dockerfile               # uv-based image, serves the HTTP API by default
docker-compose.yml        # Bind-mounts data/ + pokemon_raw_data/, publishes port 8000
entrypoint.sh             # Fetches/migrates/populates only what's missing, then execs the CMD
```

## Limitations

- **No automated test suite** — verification throughout development has been direct functional testing (running the CLI, querying the database, and the evaluation harness above) rather than a `pytest` suite.
- **No web UI** — the CLI and the HTTP API (`api.py`) are the only interfaces; no frontend.
- **No per-tool usage tracking** — `GET /dashboard` can't show "most-used tool" or similar, because which of the 19 tools got called per conversation is never persisted (only used transiently during the request); would need a schema change to track.
- **Gen 1 species only** by default (`--max-species-id 151`) — the ingestion pipeline can be pointed at more species, but several data-modeling decisions were specifically scoped and verified against Gen 1 (see [Decisions and trade-offs](#decisions-and-trade-offs)).
- **LLM-as-judge evaluation is itself fallible** — see the Evaluation section above; at least one `PARTLY_RELEVANT` result across evaluation runs has been the judge being factually wrong, not the system under test.
- **No localization** — only English text is stored anywhere in the schema, even though the raw PokeAPI dump has many languages.
- **Team-building is grounded in a single, frozen usage snapshot** — `build_team` reasons from one Smogon Gen1-OU usage-stats snapshot (`pokemon_raw_data/gen1ou-1760.json`, 62 of 151 species covered), not a live or continuously-updated source; its real-usage pool and pervasiveness numbers only reflect that snapshot.
- **No ability data** — abilities weren't introduced as a game mechanic until Generation 3, so a Gen-1-only database doesn't model them; PokeAPI's modern retrofit of abilities onto Gen-1 species was ingested at one point, verified, and then removed once this scope conflict was identified (see `ingestion_gaps.txt`).
- A full, continuously-updated account of known data gaps and scope decisions lives in [`ingestion_gaps.txt`](ingestion_gaps.txt) (data coverage) and [`agent_tool_gaps.txt`](agent_tool_gaps.txt) (tool coverage) — both are more granular and current than this section.
