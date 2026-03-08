# Modular Optionalization Matrix (What Can Be Safely Optional)

Last updated: 2026-03-07

## Bottom line

Your current stack is modular enough to run in staged mode. The safest optionalization strategy is profile switching, not deleting features.

## Safely Optional Now

1. `gmail` integration: safe to keep off until you are ready to activate scheduled inbox processing.
2. `drive` integration: safe to keep off until you create the shared root workspace.
3. `linkedin` integration: disabled by default, keep off until compliance path is clear.
4. Search API keys (`BRAVE_SEARCH_API_KEY`, `SERPAPI_API_KEY`, `OPENCLAW_SEARCH_API_KEY`): optional; browser-only mode still works.
5. n8n `news_digest` module: disabled by default.
6. Memory semantic embeddings (`memory profile md_only`): safe to disable for lower cost.
7. Memory SQLite lane (`memory profile md_only`): safe to disable until query-heavy use appears.

## Stage Presets (Integrations)

Defined in [config/integrations.yaml](/Users/palba/Projects/Clawdio/config/integrations.yaml):

1. `bootstrap_minimal`: web browsing plus Google Calendar.
2. `stage_2_comms_google`: add Gmail + Drive.
3. `stage_3_comms_dev`: add GitHub.
4. `stage_4_tasks`: add personal + agent task managers.
5. `stage_5_automation`: add n8n.
6. `lean_manual`: full prewired manual profile, kept for one-step expansion after MVP.

## Memory Presets

Defined in [config/memory.yaml](/Users/palba/Projects/Clawdio/config/memory.yaml):

1. `md_only`: cheapest, most stable baseline.
2. `md_plus_embeddings`: semantic recall enabled.
3. `hybrid_124`: markdown + embeddings + SQLite (current default).

## Add-on Presets (External Skills)

Defined in [config/addons.yaml](/Users/palba/Projects/Clawdio/config/addons.yaml):

1. `addons_off`: baseline, all external skill add-ons disabled.
2. `addons_core_recommended`: deterministic utility add-ons (`markdown_converter`, `video_transcript_downloader`, `summarize`, `model_usage`, `github`, `gemini`).
3. `addons_search_brave`: core set plus `brave_search`.
4. `addons_collab_planning`: core set plus `slack` and `trello`.

## Quick Switch Commands

1. List available integration profiles + required env keys:
2. `python3 scripts/profile_matrix.py`
3. Switch active profiles safely:
4. `python3 scripts/set_active_profiles.py --integrations-profile bootstrap_minimal --memory-profile md_only --addons-profile addons_off`
5. Validate required keys for chosen profiles from a secrets file:
6. `python3 scripts/check_env_requirements.py --env-file /path/to/openclaw.env --strict --addons-profile addons_off`
7. Show optional key status too (including Brave):
8. `python3 scripts/check_env_requirements.py --env-file /path/to/openclaw.env --include-optional --addons-profile addons_search_brave`

## Recommended Low-Risk Starting Mode

1. Integrations: `bootstrap_minimal`
2. Memory: `md_only`
3. Keep reminders and calendar enabled.
4. Add one stage at a time only after strict env check passes.

## Rollback

1. Switch back to MVP baseline instantly:
2. `python3 scripts/set_active_profiles.py --integrations-profile bootstrap_minimal --memory-profile md_only --addons-profile addons_off`
