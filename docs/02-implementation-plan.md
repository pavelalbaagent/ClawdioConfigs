# Implementation Plan (Detailed, Sequential)

## Phase 0: Salvage and snapshot

1. Export useful data from old OpenClaw: prompts, integration tokens list, recurring tasks, and successful workflows.
2. Preserve security scripts from `ops/scripts/`.
3. Record current production constraints in one file: rate limits, quotas, uptime needs.
4. Exit criteria: you can wipe old setup without losing critical operational knowledge.

## Phase 1: Repo and baseline structure

1. Initialize git repository in this folder.
2. Add `.gitignore` for env files, logs, and secrets.
3. Keep docs and configs versioned from day one.
4. Exit criteria: reproducible project layout and change tracking enabled.

## Phase 2: VPS hardening and base runtime

1. Keep SSH restricted to Tailscale, and keep break-glass scripts available.
2. Run service accounts with least privilege.
3. Install runtime dependencies needed by OpenClaw and adapters.
4. Exit criteria: secure host ready for app install.

## Phase 3: Declarative configuration pass

1. Fill all `config/*.yaml` files manually before starting services.
2. Define communication style, prompt boundaries, and escalation rules.
3. Define model tiers and budget caps.
4. Exit criteria: zero critical behavior decided at runtime via ad-hoc prompting.

## Phase 4: Core services install (non-container)

1. Install OpenClaw code and dependencies on VPS filesystem.
2. MVP first: create the env-file-backed gateway, Telegram adapter, and dashboard user units, then validate Telegram + dashboard access.
3. Add health endpoints and startup checks.
4. Defer worker/scheduler/watchdog service split until the single-service MVP is stable.
5. Exit criteria: gateway boots, survives reboot, and supports one live human channel.

## Phase 5: Integrations

1. Choose profile in `config/integrations.yaml` (`bootstrap_command_center` first).
2. Keep day-one live scope to: one human channel, dashboard, reminders, Google Calendar, personal tasks, optional browsing.
3. Prewire Gmail and Drive next, but keep them disabled until activation testing day.
4. Add GitHub, task managers, and n8n only as staged unlocks.
5. Add LinkedIn only if terms and auth method are compliant and stable.
6. Exit criteria: each integration has explicit permissions, env vars, health check, and rollback path before enablement.

## Phase 6: Model routing and budget enforcement

1. Apply model routing policy from `docs/03-model-routing-policy.md`.
2. Log every model call with tier, latency, and estimated cost.
3. Add soft and hard budget limits.
4. Keep background automation on API-safe providers only.
5. Treat Codex CLI and Gemini CLI as supervised local tools, not unattended background providers.
6. Exit criteria: predictable cost and graceful degradation when quotas are hit.

## Phase 7: Sub-agent policy rollout

1. Implement spawn rules from `docs/04-agent-ops-and-subagents.md`.
2. Apply session lifecycle controls from `config/session_policy.yaml`.
3. Enforce TTL and result schema for all sub-agent runs.
4. Keep high-cost tasks approval-gated.
5. Exit criteria: no uncontrolled fan-out, no silent cost explosions.

## Phase 8: Validation and go-live

1. Run end-to-end scenario tests on channels, reminders, and tool calls.
2. Simulate API quota exhaustion and verify fallback behavior.
3. Test Tailscale failure and recovery scripts.
4. Exit criteria: pass checklist and cut over from old OpenClaw.
