# Provider Bundle Checklist (Cost-Aware)

Last updated: 2026-03-07

## Recommended Bundle Now

Use this as the current VPS command-center bundle:

1. Core comms: `telegram`
2. Control plane: `web_dashboard`
3. Reminders: enabled
4. Calendar: enabled
5. Personal tasks: enabled
6. Integrations profile: `bootstrap_command_center`
7. Memory profile: `hybrid_124`
8. Optional search API: add later only if browser-only retrieval is insufficient

Fallback bundle for degraded-provider or cost-control windows:

1. Integrations profile: `bootstrap_core`
2. Memory profile: `md_only`

## Recommended Bundle After MVP Stabilizes

Use this as the first post-MVP expansion bundle:

1. Personal tasks: `todoist`
2. Agent tasks: `asana`
3. Core comms: `telegram`
4. Core integrations: `gmail`, `drive`, `github`, `n8n`
5. Optional search API: add later only if browser-only retrieval is insufficient
6. Optional overflow LLM lane: `OPENROUTER_API_KEY` for OpenRouter free fallback
7. Optional reserve LLM lane: `ANTHROPIC_API_KEY` for complex-design overflow only
8. Operational assumptions:
9. Gmail runs as a scheduled inbox-processing lane, not a chat-style email command channel.
10. Drive uses one shared root folder, ideally created by you and shared with the agent account.

For staged optionalization, use profile presets in [config/integrations.yaml](/Users/palba/Projects/Personal/Clawdio/config/integrations.yaml):

1. `bootstrap_core`
2. `bootstrap_minimal`
3. `bootstrap_command_center`
4. `stage_2_comms_google`
5. `stage_3_comms_dev`
6. `stage_4_tasks`
7. `stage_5_automation`

## Required Env For Initial VPS Go-Live

Set these first:

1. `TELEGRAM_BOT_TOKEN`
2. `TELEGRAM_ALLOWED_CHAT_ID`
3. `OPENCLAW_DASHBOARD_TOKEN`
4. `GEMINI_API_KEY`
5. `GOOGLE_CLIENT_ID`
6. `GOOGLE_CLIENT_SECRET`
7. `GOOGLE_REFRESH_TOKEN`
8. `GOOGLE_CALENDAR_ID`
9. `PERSONAL_TASK_PROVIDER=todoist`
10. `TODOIST_API_TOKEN`

## Required Env For Post-MVP Expansion

Set these first:

1. `GMAIL_USER_EMAIL`
2. `GOOGLE_DRIVE_ROOT_FOLDER_ID`
3. `GITHUB_TOKEN`
4. `GITHUB_OWNER`
5. `AGENT_TASK_PROVIDER=asana`
6. `ASANA_PERSONAL_ACCESS_TOKEN`
7. `ASANA_WORKSPACE_GID`
8. `N8N_BASE_URL`
9. `N8N_API_KEY`
10. `N8N_WEBHOOK_SECRET`
11. `OPENROUTER_API_KEY`
12. `ANTHROPIC_API_KEY`
13. `OPENAI_API_KEY`

## Alternative Bundle A (Google-Heavy)

1. Personal tasks: `google_tasks`
2. Agent tasks: `github_projects`
3. Required changes:
4. `PERSONAL_TASK_PROVIDER=google_tasks`
5. `AGENT_TASK_PROVIDER=github_projects`
6. Keep `GITHUB_REPO` set for project routing if using one fixed repo.

## Alternative Bundle B (All-in-Asana)

1. Personal tasks: `asana`
2. Agent tasks: `asana`
3. Required changes:
4. `PERSONAL_TASK_PROVIDER=asana`
5. `AGENT_TASK_PROVIDER=asana`
6. Reuse `ASANA_PERSONAL_ACCESS_TOKEN` and `ASANA_WORKSPACE_GID`.

## Activation Sequence

1. Set bundle env vars in runtime secret file.
2. Run `python3 scripts/check_env_requirements.py --strict`.
3. Run `python3 scripts/validate_configs.py --config-dir config`.
4. For Gmail + Drive activation, confirm:
5. the Gmail OAuth grant includes Gmail modify scope
6. the shared Drive root exists and `GOOGLE_DRIVE_ROOT_FOLDER_ID` points to it
7. Enable only needed n8n modules in `integrations.n8n.modules`.
8. Keep LinkedIn disabled until later compliance pass.
