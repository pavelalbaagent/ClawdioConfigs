# Secrets File Onboarding (Fast Path)

Last updated: 2026-03-03

## Goal

Load a single secrets file and validate all required keys (plus optional keys like Brave) without exporting variables manually.

## File format

Use dotenv style (`KEY=value`), one per line.

Example:

```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
GMAIL_USER_EMAIL=...
GOOGLE_DRIVE_ROOT_FOLDER_ID=...
GITHUB_TOKEN=...
GITHUB_OWNER=...
PERSONAL_TASK_PROVIDER=todoist
TODOIST_API_TOKEN=...
AGENT_TASK_PROVIDER=asana
ASANA_PERSONAL_ACCESS_TOKEN=...
ASANA_WORKSPACE_GID=...
N8N_BASE_URL=...
N8N_API_KEY=...
N8N_WEBHOOK_SECRET=...
OPENAI_API_KEY=...
BRAVE_SEARCH_API_KEY=...
```

## Validate uploaded file

1. Required-only check:
2. `python3 scripts/check_env_requirements.py --env-file /path/to/openclaw.env --strict`
3. Required + optional visibility:
4. `python3 scripts/check_env_requirements.py --env-file /path/to/openclaw.env --include-optional`

## Optional search keys

`web_browsing` has no hard required key, but these optional keys are supported:

1. `OPENCLAW_SEARCH_API_KEY`
2. `BRAVE_SEARCH_API_KEY`
3. `SERPAPI_API_KEY`

## VPS placement

Recommended runtime target is `/etc/openclaw/openclaw.env` (keep this file out of git).

After placing the file on VPS, run:

1. `python3 /home/pavel/Projects/Clawdio/scripts/check_env_requirements.py --env-file /etc/openclaw/openclaw.env --strict`
2. `python3 /home/pavel/Projects/Clawdio/scripts/check_env_requirements.py --env-file /etc/openclaw/openclaw.env --include-optional`
