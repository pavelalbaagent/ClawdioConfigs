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
2. Use Telegram long polling for the first VPS cut. It avoids exposing public webhooks and is materially simpler than Slack app setup.
3. Secondary: lightweight web dashboard for review, approvals, and task board.
4. Optional async channel later: Gmail operational inbox for scheduled triage and longer requests.
5. Slack should stay as a deferred candidate until you actually need team-style lanes and richer collaboration surfaces.

## VPS native deployment shape

### MVP live shape

1. `openclaw-gateway.service` as the only required live systemd service.
2. Telegram adapter in long-polling mode.
3. Local dashboard over loopback/Tailscale tunnel.
4. Reminder runtime as an internal module, not a separate service boundary yet.

### Deferred service split

1. `openclaw-worker.service`
2. `openclaw-scheduler.service`
3. `openclaw-watchdog.service`

Only split these out after the MVP path is stable and observable.

## Config-first behavior model

1. `config/core.yaml`: identity, style, timezone, limits.
2. `config/channels.yaml`: inbound/outbound channels and rules.
3. `config/models.yaml`: routing tiers, budgets, fallback.
4. `config/integrations.yaml`: enabled integrations and permission scopes.
5. `config/agents.yaml`: available agents and spawn policy.
6. `config/tasks.yaml`: personal task manager and agent task manager.
7. `config/security.yaml`: allowed tools, secret paths, audit controls.
