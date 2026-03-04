# Credentials and Onboarding Checklist

Last updated: 2026-03-04

## Target

Achieve fast onboarding with minimal moving parts, then progressively enable more integrations without breaking baseline operations.

Bundle presets are documented in [docs/23-provider-bundles-checklist.md](/Users/palba/Projects/Clawdio/docs/23-provider-bundles-checklist.md).

## Phase A: Baseline (same day)

1. Fill `.env` placeholders in local secure store from [.env.example](/Users/palba/Projects/Clawdio/.env.example).
2. Configure `lean_manual` profile in [config/integrations.yaml](/Users/palba/Projects/Clawdio/config/integrations.yaml).
3. Set and verify:
4. `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_ID`
5. `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GMAIL_USER_EMAIL`, `GOOGLE_DRIVE_ROOT_FOLDER_ID`
6. `GITHUB_TOKEN`, `GITHUB_OWNER`
7. `PERSONAL_TASK_PROVIDER`
8. `AGENT_TASK_PROVIDER`
9. `N8N_BASE_URL`, `N8N_API_KEY`, `N8N_WEBHOOK_SECRET`

## Phase B: Productivity (after baseline is stable)

1. Add calendar credentials if needed (`GOOGLE_CALENDAR_ID`).
2. Set provider-specific task credentials:
3. Todoist path: `TODOIST_API_TOKEN`
4. Asana path: `ASANA_PERSONAL_ACCESS_TOKEN`, `ASANA_WORKSPACE_GID`
5. Linear path: `LINEAR_API_KEY`, `LINEAR_TEAM_ID`
6. Optional search APIs:
7. `OPENCLAW_SEARCH_API_KEY` or `BRAVE_SEARCH_API_KEY` or `SERPAPI_API_KEY`
8. Optional memory tuning vars:
9. `OPENAI_EMBEDDING_MODEL`
10. `MEMORY_SQLITE_DB_PATH`
11. Optional overflow model path:
12. `OPENROUTER_API_KEY`
13. Optional reserve-design model path:
14. `ANTHROPIC_API_KEY`

## Phase C: Optional/High-Risk

1. Keep LinkedIn off until compliance path is confirmed.
2. If needed later, add LinkedIn OAuth values and run manual-review-only mode first.
3. Keep `addons_off` until baseline is stable, then enable one add-on profile at a time from [config/addons.yaml](/Users/palba/Projects/Clawdio/config/addons.yaml).

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
