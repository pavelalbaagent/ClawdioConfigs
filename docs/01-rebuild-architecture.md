# OpenClaw v2 Architecture (VPS Native, Config-First)

## Design principles

1. Manual-first setup: you define behavior in config files, not ad-hoc prompts.
2. Modular boundaries: channels, tools, scheduling, memory, and integrations are independent modules.
3. Reproducibility: one repo, one setup sequence, one runbook.
4. Cost control by design: strict model routing tiers and budget guards.
5. Security default: private network access, least privilege, audited actions.

## Target component map

```text
[Human Channels]
Telegram | Email | Web Dashboard
        |
        v
[Coordinator Agent]
        |
        +--> [Task Router]
        |       |
        |       +--> [Model Router]
        |       +--> [Tool Router: codex/gemini CLI]
        |
        +--> [Task Stores]
                - Personal tasks (reminders for you)
                - Agent tasks (work queue for OpenClaw)
        |
        +--> [Integrations]
                Gmail | Drive | LinkedIn | Calendar | Notes
        |
        +--> [Logs + Audit + Metrics]
```

## Recommended channel strategy (not WhatsApp-only)

1. Primary: Telegram bot for quick interaction and reminders.
2. Secondary: lightweight web dashboard for review, approvals, and task board.
3. Optional async channel: Gmail command inbox for longer requests.

## VPS native deployment shape

1. `openclaw-api.service` for inbound commands.
2. `openclaw-worker.service` for async tasks.
3. `openclaw-scheduler.service` for reminders and recurring jobs.
4. `openclaw-watchdog.service` for health checks and auto-restart.

## Config-first behavior model

1. `config/core.yaml`: identity, style, timezone, limits.
2. `config/channels.yaml`: inbound/outbound channels and rules.
3. `config/models.yaml`: routing tiers, budgets, fallback.
4. `config/integrations.yaml`: enabled integrations and permission scopes.
5. `config/agents.yaml`: available agents and spawn policy.
6. `config/tasks.yaml`: personal task manager and agent task manager.
7. `config/security.yaml`: allowed tools, secret paths, audit controls.

