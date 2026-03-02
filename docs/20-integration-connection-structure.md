# Integration Connection Structure (Modular + Cost-Aware)

Last updated: 2026-03-02

## Goal

Define one stable integration map so onboarding is simple, services are optional, and each module can be enabled or disabled without redesigning the whole system.

## Control Plane

1. Central config: [config/integrations.yaml](/Users/palba/Projects/Clawdio/config/integrations.yaml)
2. Secret template: [.env.example](/Users/palba/Projects/Clawdio/.env.example)
3. Required-env checker: [scripts/check_env_requirements.py](/Users/palba/Projects/Clawdio/scripts/check_env_requirements.py)
4. Global validator: [scripts/validate_configs.py](/Users/palba/Projects/Clawdio/scripts/validate_configs.py)
5. Provider bundle presets: [docs/23-provider-bundles-checklist.md](/Users/palba/Projects/Clawdio/docs/23-provider-bundles-checklist.md)
6. n8n workflow contracts: [docs/24-n8n-workflow-contract-pack.md](/Users/palba/Projects/Clawdio/docs/24-n8n-workflow-contract-pack.md)

## Profiles

1. `lean_manual`: default. Lowest-risk onboarding, manual approval before external writes.
2. `standard_productive`: adds calendar and higher automation convenience.
3. `full_auto_candidate`: includes LinkedIn and broader automation. Keep off until compliance and observability are stable.

## Integration Modules

1. `web_browsing`: search/open/extract actions. Keep write actions disabled.
2. `gmail`: read, classify, draft, send-with-approval.
3. `drive`: read/write working files under a dedicated root folder.
4. `github`: issues/PR/code read, controlled writes for repo workflows.
5. `personal_task_manager`: your reminders/tasks (`todoist`, `google_tasks`, or `asana`).
6. `agent_task_manager`: agent work queue (`asana`, `github_projects`, or `linear`).
7. `n8n`: external automation bridge via authenticated webhooks.
8. `calendar`: optional schedule sync and reminder alignment.
9. `linkedin`: disabled by default, manual-review mode only.

## n8n Contract Link

1. Contract file path is `integrations.n8n.workflow_contracts_file`.
2. Individual workflow toggles are under `integrations.n8n.modules`.

## Platform-Agnostic Event Flow

1. Input arrives from Telegram, web dashboard, email, or other adapter.
2. Input is normalized to canonical event schema.
3. Coordinator routes to deterministic action, low-cost model lane, or supervised heavy lane.
4. External write actions require explicit approval gate.
5. Result is posted back to the channel adapter and logged for audit.

## Cost Control Hooks

1. Keep high-volume tasks in deterministic logic or `L1_low_cost`.
2. Use profile toggles to disable non-essential integrations during heavy periods.
3. Keep LinkedIn and other uncertain-value connectors disabled until they prove ROI.
4. Use n8n for deterministic glue and scheduling, not model-heavy reasoning.

## Run Commands

1. Validate config: `python3 scripts/validate_configs.py --config-dir config`
2. Check required secrets for active profile: `python3 scripts/check_env_requirements.py`
3. Strict env readiness check: `python3 scripts/check_env_requirements.py --strict`
