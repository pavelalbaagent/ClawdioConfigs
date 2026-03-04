# Dashboard Control Plane

## Goal

Run a local dashboard that gives you a manual-first control plane for OpenClaw:

1. Activate/deactivate integrations, memory modules, and n8n submodules.
2. Switch integration and memory profiles.
3. Switch model routing mode (`strict_cost`, `balanced_default`, `quality_push`).
4. Apply preset packs to switch multiple knobs at once.
5. Track usage/cost/progress using existing telemetry.
6. See pending reminders, active projects, task board, and to-do queue.
7. Assign tasks to one or more agents (or to yourself) from the UI.
8. Create tasks quickly from reusable templates.
9. Export weekly progress as Markdown and tasks as CSV.
10. Queue task dispatch runs and track execution lifecycle.
11. Gate risky actions behind an approval inbox.

## Files

1. Server: [dashboard/server.py](/Users/palba/Projects/Clawdio/dashboard/server.py)
2. Backend helpers: [dashboard/backend.py](/Users/palba/Projects/Clawdio/dashboard/backend.py)
3. Main UI: [dashboard/static/index.html](/Users/palba/Projects/Clawdio/dashboard/static/index.html)
4. Login UI: [dashboard/static/login.html](/Users/palba/Projects/Clawdio/dashboard/static/login.html)
5. UI scripts: [dashboard/static/app.js](/Users/palba/Projects/Clawdio/dashboard/static/app.js), [dashboard/static/login.js](/Users/palba/Projects/Clawdio/dashboard/static/login.js)
6. UI styles: [dashboard/static/styles.css](/Users/palba/Projects/Clawdio/dashboard/static/styles.css)
7. Dashboard config: [config/dashboard.yaml](/Users/palba/Projects/Clawdio/config/dashboard.yaml)
8. Local project/task store: `data/dashboard-workspace.json` (auto-created)

## Run Locally

```bash
python3 dashboard/server.py --host 127.0.0.1 --port 18789
```

Open `http://127.0.0.1:18789`.

## Token Auth

Token auth is enabled by default.

1. Set token env var before starting server:

```bash
export OPENCLAW_DASHBOARD_TOKEN='<strong-random-token>'
```

2. Open dashboard URL and login at `/login.html`.
3. If env token is not set, server generates a temporary token and prints it to stdout.

Auth settings live in [config/dashboard.yaml](/Users/palba/Projects/Clawdio/config/dashboard.yaml):

1. `dashboard.auth.require_token`
2. `dashboard.auth.token_env_key`
3. `dashboard.auth.session_ttl_minutes`

## Through VPS Tunnel

Use the existing tunnel script:

```bash
bash ops/scripts/openclaw-dashboard-tunnel.sh
```

Then open `http://127.0.0.1:18789` locally.

## What It Controls

1. Profile switching calls [scripts/set_active_profiles.py](/Users/palba/Projects/Clawdio/scripts/set_active_profiles.py).
2. Integration toggles update [config/integrations.yaml](/Users/palba/Projects/Clawdio/config/integrations.yaml).
3. Memory module toggles update [config/memory.yaml](/Users/palba/Projects/Clawdio/config/memory.yaml).
4. n8n module toggles update `integrations.n8n.modules` in [config/integrations.yaml](/Users/palba/Projects/Clawdio/config/integrations.yaml).
5. Routing mode updates `routing_overrides.active_mode` in [config/agents.yaml](/Users/palba/Projects/Clawdio/config/agents.yaml).
6. Adapter/auth flags update [config/dashboard.yaml](/Users/palba/Projects/Clawdio/config/dashboard.yaml).
7. Projects/tasks updates `data/dashboard-workspace.json`.

## Preset Packs

Preset packs are in `dashboard.presets` in [config/dashboard.yaml](/Users/palba/Projects/Clawdio/config/dashboard.yaml).

Each preset can define:

1. `integrations_profile`
2. `memory_profile`
3. `integration_toggles`
4. `memory_module_toggles`
5. `n8n_module_toggles`

Use `POST /api/presets/apply` from UI buttons.

## Tasks And Projects

Task board capabilities:

1. Create task with assignees (human/agent or multiple agents).
2. Update status/progress/assignees.
3. Mark done quickly.
4. Delete task.
5. Create from template (`research_brief`, `build_feature`, `ops_health_check`) with one click.
6. Queue execution runs directly from each task row.

Execution run capabilities:

1. Run statuses: `queued`, `running`, `succeeded`, `failed`, `cancelled`.
2. Start/succeed/fail controls from dashboard.
3. Task status auto-updates based on run outcome.

Approval inbox capabilities:

1. Pending approval queue for external write-like task intents.
2. Approve/reject decisions from dashboard.
3. Dispatch is blocked until approval is granted when required by policy.

Project capabilities:

1. Create project.
2. Update project status.
3. Track computed progress from project task completion.

Task templates are configured in `dashboard.task_templates` in [config/dashboard.yaml](/Users/palba/Projects/Clawdio/config/dashboard.yaml).

## Exports

Dashboard provides file exports for progress tracking:

1. Weekly Markdown report: `GET /api/exports/weekly.md?days=7`
2. Tasks CSV export: `GET /api/exports/tasks.csv`

UI buttons trigger direct downloads so you can attach reports to email/Drive/task systems.

## Dispatch + Approval APIs

1. Queue task dispatch: `POST /api/tasks/dispatch`
2. Update run status/log/output: `POST /api/runs/update`
3. Create manual approval request: `POST /api/approvals/create`
4. Approve/reject request: `POST /api/approvals/decision`
5. Template task creation: `POST /api/tasks/create_from_template`

## Reminder Visibility

Dashboard reads reminder state from `data/reminders-state.json` and shows:

1. Pending/awaiting reminder count.
2. Pending reminder list with due time and follow-up timing.

## Telemetry Sources

1. Local model calls from `telemetry/model-calls*.ndjson` (if enabled).
2. Existing markdown indicators:
- [telemetry/model-usage-latest.md](/Users/palba/Projects/Clawdio/telemetry/model-usage-latest.md)
- [telemetry/ops-snapshot.md](/Users/palba/Projects/Clawdio/telemetry/ops-snapshot.md)
3. Codexbar adapter (optional) via:
- `codexbar cost --format json --provider <provider>`
- `codexbar usage --format json --provider <provider>`

If Codexbar is missing or errors, dashboard continues working and surfaces adapter status only.
