# Modular Optionalization Matrix (What Can Be Safely Optional)

Last updated: 2026-03-03

## Bottom line

Your current stack is modular enough to run in staged mode. The safest optionalization strategy is profile switching, not deleting features.

## Safely Optional Now

1. `calendar` integration: disabled by default, safe to keep off.
2. `linkedin` integration: disabled by default, keep off until compliance path is clear.
3. Search API keys (`BRAVE_SEARCH_API_KEY`, `SERPAPI_API_KEY`, `OPENCLAW_SEARCH_API_KEY`): optional; browser-only mode still works.
4. n8n `news_digest` module: disabled by default.
5. Memory semantic embeddings (`memory profile md_only`): safe to disable for lower cost.
6. Memory SQLite lane (`memory profile md_only`): safe to disable until query-heavy use appears.

## Stage Presets (Integrations)

Defined in [config/integrations.yaml](/Users/palba/Projects/Clawdio/config/integrations.yaml):

1. `bootstrap_minimal`: web browsing only.
2. `stage_2_comms_google`: add Gmail + Drive.
3. `stage_3_comms_dev`: add GitHub.
4. `stage_4_tasks`: add personal + agent task managers.
5. `stage_5_automation`: add n8n.
6. `lean_manual`: full lean manual profile (current default).

## Memory Presets

Defined in [config/memory.yaml](/Users/palba/Projects/Clawdio/config/memory.yaml):

1. `md_only`: cheapest, most stable baseline.
2. `md_plus_embeddings`: semantic recall enabled.
3. `hybrid_124`: markdown + embeddings + SQLite (current default).

## Quick Switch Commands

1. List available integration profiles + required env keys:
2. `python3 scripts/profile_matrix.py`
3. Switch active profiles safely:
4. `python3 scripts/set_active_profiles.py --integrations-profile bootstrap_minimal --memory-profile md_only`
5. Validate required keys for chosen profiles from a secrets file:
6. `python3 scripts/check_env_requirements.py --env-file /path/to/openclaw.env --strict`
7. Show optional key status too (including Brave):
8. `python3 scripts/check_env_requirements.py --env-file /path/to/openclaw.env --include-optional`

## Recommended Low-Risk Starting Mode

1. Integrations: `bootstrap_minimal`
2. Memory: `md_only`
3. Keep reminders enabled.
4. Add one stage at a time only after strict env check passes.

## Rollback

1. Switch back to current baseline instantly:
2. `python3 scripts/set_active_profiles.py --integrations-profile lean_manual --memory-profile hybrid_124`
