# Provider Bundle Checklist (Cost-Aware)

Last updated: 2026-03-02

## Recommended Bundle Now

Use this as the default onboarding bundle:

1. Personal tasks: `todoist`
2. Agent tasks: `asana`
3. Core comms: `telegram`
4. Core integrations: `gmail`, `drive`, `github`, `n8n`
5. Optional search API: add later only if browser-only retrieval is insufficient
6. Optional overflow LLM lane: `OPENROUTER_API_KEY` for OpenRouter free fallback
7. Optional reserve LLM lane: `ANTHROPIC_API_KEY` for complex-design overflow only

For staged optionalization, use profile presets in [config/integrations.yaml](/Users/palba/Projects/Clawdio/config/integrations.yaml):

1. `bootstrap_minimal`
2. `stage_2_comms_google`
3. `stage_3_comms_dev`
4. `stage_4_tasks`
5. `stage_5_automation`

## Required Env for Recommended Bundle

Set these first:

1. `TELEGRAM_BOT_TOKEN`
2. `TELEGRAM_ALLOWED_CHAT_ID`
3. `GOOGLE_CLIENT_ID`
4. `GOOGLE_CLIENT_SECRET`
5. `GOOGLE_REFRESH_TOKEN`
6. `GMAIL_USER_EMAIL`
7. `GOOGLE_DRIVE_ROOT_FOLDER_ID`
8. `GITHUB_TOKEN`
9. `GITHUB_OWNER`
10. `PERSONAL_TASK_PROVIDER=todoist`
11. `TODOIST_API_TOKEN`
12. `AGENT_TASK_PROVIDER=asana`
13. `ASANA_PERSONAL_ACCESS_TOKEN`
14. `ASANA_WORKSPACE_GID`
15. `N8N_BASE_URL`
16. `N8N_API_KEY`
17. `N8N_WEBHOOK_SECRET`

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
4. Enable only needed n8n modules in `integrations.n8n.modules`.
5. Keep LinkedIn disabled until later compliance pass.
