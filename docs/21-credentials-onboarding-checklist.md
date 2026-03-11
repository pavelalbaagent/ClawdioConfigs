# Credentials and Onboarding Checklist

Last updated: 2026-03-07

## Target

Achieve fast onboarding with minimal moving parts, then progressively enable more integrations without breaking baseline operations.

Bundle presets are documented in [docs/23-provider-bundles-checklist.md](/Users/palba/Projects/Personal/Clawdio/docs/23-provider-bundles-checklist.md).

## Phase A: Baseline (same day)

1. Fill `.env` placeholders in local secure store from [.env.example](/Users/palba/Projects/Personal/Clawdio/.env.example).
2. Configure `bootstrap_command_center` profile in [config/integrations.yaml](/Users/palba/Projects/Personal/Clawdio/config/integrations.yaml).
3. Set and verify:
4. `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_ID`
5. `OPENCLAW_DASHBOARD_TOKEN`
6. `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GOOGLE_CALENDAR_ID`
7. `GEMINI_API_KEY`
8. `PERSONAL_TASK_PROVIDER=todoist`, `TODOIST_API_TOKEN`
9. Optional search path: `BRAVE_SEARCH_API_KEY` or equivalent

## Phase B: Core integrations (after baseline is stable)

1. Switch to `stage_2_comms_google` or `lean_manual` only after the channel/reminder/calendar loop is stable.
2. Set:
3. `GMAIL_USER_EMAIL`, `GOOGLE_DRIVE_ROOT_FOLDER_ID`
4. `GITHUB_TOKEN`, `GITHUB_OWNER`
5. `PERSONAL_TASK_PROVIDER`
6. `AGENT_TASK_PROVIDER`
7. `N8N_BASE_URL`, `N8N_API_KEY`, `N8N_WEBHOOK_SECRET`
8. Recommended operating assumptions:
9. Gmail uses scheduled inbox batch processing with `gmail.modify`, not read-only polling.
10. Drive uses one shared human-owned root folder identified by `GOOGLE_DRIVE_ROOT_FOLDER_ID`.

## Phase C: Productivity (after baseline is stable)

1. Set provider-specific task credentials:
2. Todoist path: `TODOIST_API_TOKEN`
3. Asana path: `ASANA_PERSONAL_ACCESS_TOKEN`, `ASANA_WORKSPACE_GID`
4. Linear path: `LINEAR_API_KEY`, `LINEAR_TEAM_ID`
5. Optional search APIs:
6. `OPENCLAW_SEARCH_API_KEY` or `BRAVE_SEARCH_API_KEY` or `SERPAPI_API_KEY`
7. Optional memory tuning vars:
8. `OPENAI_EMBEDDING_MODEL`
9. `MEMORY_SQLITE_DB_PATH`
10. Optional overflow model path:
11. `OPENROUTER_API_KEY`
12. Optional reserve-design model path:
13. `ANTHROPIC_API_KEY`

## Phase D: Optional/High-Risk

1. Keep LinkedIn off until compliance path is confirmed.
2. If needed later, add LinkedIn OAuth values and run manual-review-only mode first.
3. Keep `addons_off` until baseline is stable, then enable one add-on profile at a time from [config/addons.yaml](/Users/palba/Projects/Personal/Clawdio/config/addons.yaml).

## Validation Gates

1. `python3 scripts/check_env_requirements.py`
2. `python3 scripts/check_env_requirements.py --strict --addons-profile addons_off`
3. `python3 scripts/check_env_requirements.py --env-file /path/to/openclaw.env --strict --addons-profile addons_off`
4. `python3 scripts/check_env_requirements.py --env-file /path/to/openclaw.env --include-optional --addons-profile addons_search_brave`
5. `python3 scripts/validate_configs.py --config-dir config`
6. `python3 scripts/scan_secrets.py`

## Rotation and Hygiene

1. Rotate credentials every 90 days (or faster for exposed scopes).
2. Use one dedicated service identity per major integration domain.
3. Keep write scopes minimal and protected by explicit approval.
4. Never paste raw tokens in chats, docs, or commit history.
