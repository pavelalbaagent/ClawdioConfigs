# Hybrid Memory Runbook (Options 1 + 2 + 4)

Last updated: 2026-03-03

## Goal

Use a practical hybrid memory stack that balances quality and cost:

1. Option 1: structured markdown memory files.
2. Option 2: semantic recall with OpenAI embeddings.
3. Option 4: SQLite structured memory/state layer.

## Architecture

1. Lane 1 (`structured_markdown`): source of truth files (`MEMORY.md`, `memory/*.md`, etc.).
2. Lane 2 (`semantic_embeddings`): embedding index over markdown chunks for retrieval.
3. Lane 4 (`sqlite_state`): durable DB for chunks, embeddings, state keys, and recall logs.

Primary config: [config/memory.yaml](/Users/palba/Projects/Personal/Clawdio/config/memory.yaml)
Schema: [contracts/memory/sqlite_schema.sql](/Users/palba/Projects/Personal/Clawdio/contracts/memory/sqlite_schema.sql)

## Profiles (Cost Toggles)

1. `md_only`: lane 1 only, cheapest mode.
2. `md_plus_embeddings`: lane 1 + lane 2.
3. `hybrid_124`: lane 1 + lane 2 + lane 4 (default).

Switch by editing `profiles.active_profile` in [config/memory.yaml](/Users/palba/Projects/Personal/Clawdio/config/memory.yaml).

## Setup

1. Validate config pack:
2. `python3 scripts/validate_configs.py --config-dir config`
3. Verify env requirements:
4. `python3 scripts/check_env_requirements.py`
5. Bootstrap memory files in target workspace (if needed):
6. `python3 scripts/bootstrap_agent_md.py --target /path/to/workspace`

## Indexing Flow

1. Sync markdown memory into SQLite and embeddings:
2. `python3 scripts/memory_index_sync.py --workspace /path/to/workspace`
3. Dry run first (no writes/API calls):
4. `python3 scripts/memory_index_sync.py --workspace /path/to/workspace --dry-run`

## Retrieval Flow

1. Auto mode (semantic first, keyword fallback):
2. `python3 scripts/memory_search.py --workspace /path/to/workspace --query "what are my current priorities"`
3. Force keyword mode:
4. `python3 scripts/memory_search.py --workspace /path/to/workspace --query "tailscale" --mode keyword`
5. Force semantic mode:
6. `python3 scripts/memory_search.py --workspace /path/to/workspace --query "session restart rule" --mode semantic`

## Cost Controls

Tune these fields in `memory_modules.semantic_embeddings`:

1. `budget_controls.max_new_embeddings_per_run`
2. `budget_controls.max_embedding_chars_per_day`
3. `chunking.max_chars_per_chunk`
4. `retrieval.top_k_default`

Recommended operational pattern:

1. Keep `hybrid_124` as default.
2. Switch to `md_only` during heavy ingestion windows.
3. Re-enable embeddings for planning/research phases where recall quality matters.

## Session Hygiene (Memory + Cost)

1. Update `SESSION.md` and `TODO.md` every milestone.
2. Promote durable facts into `MEMORY.md` and structured files (`memory/PROFILE.md`, `memory/PROJECTS.md`, etc.).
3. Run `memory_index_sync.py` at end of major work blocks, not every message.
4. Use `session_policy.yaml` summarize/restart thresholds to prevent bloated context.
