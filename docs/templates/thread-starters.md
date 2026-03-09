# Thread Starters

Use these to start new threads without re-explaining the whole project.

## Rule

Always treat the repo as source of truth.

Point the new thread to:

1. [docs/52-development-threading-policy.md](/Users/palba/Projects/Clawdio/docs/52-development-threading-policy.md)
2. the main module doc
3. the main config/runtime files for that module

## Minimal small-feature starter

Use this when the change is small and stays inside one module.

```md
Continue Clawdio work on `<module>`.

Use the repo as source of truth, especially:
- [docs/52-development-threading-policy.md](/Users/palba/Projects/Clawdio/docs/52-development-threading-policy.md)
- <module doc>
- <main files>

Task:
- <small change>

Constraints:
- keep current architecture/profile assumptions unless the repo says otherwise
- keep it modular
- do not broaden scope

Definition of done:
- <observable outcome>
- tests/validation updated if needed
```

## Full feature starter

Use this for a real feature milestone.

```md
Continue Clawdio work on `<module>`.

Use the repo as source of truth, especially:
- [docs/52-development-threading-policy.md](/Users/palba/Projects/Clawdio/docs/52-development-threading-policy.md)
- <module doc>
- <main files>

Goal:
- <what should exist at the end>

Scope:
- in: <what is included>
- out: <what is explicitly not included>

Constraints:
- <cost / security / manual approval constraints>

Definition of done:
- <outcome 1>
- <outcome 2>
- <verification>
```

## Bug / incident starter

Use this when something broke.

```md
Investigate and fix a Clawdio issue in `<module>`.

Use the repo as source of truth, especially:
- [docs/52-development-threading-policy.md](/Users/palba/Projects/Clawdio/docs/52-development-threading-policy.md)
- <module doc>
- <main files>

Problem:
- <what is broken>

Observed behavior:
- <symptom>
- <error/log if known>

Expected behavior:
- <what should happen>

Goal:
- identify root cause
- implement the smallest correct fix
- validate it
```

## Best docs to point to by module

1. Orchestration / general policy
   - [README.md](/Users/palba/Projects/Clawdio/README.md)
   - [docs/52-development-threading-policy.md](/Users/palba/Projects/Clawdio/docs/52-development-threading-policy.md)
   - [docs/40-runtime-status-matrix.md](/Users/palba/Projects/Clawdio/docs/40-runtime-status-matrix.md)
2. Telegram
   - [docs/50-telegram-adapter-runtime.md](/Users/palba/Projects/Clawdio/docs/50-telegram-adapter-runtime.md)
   - [scripts/telegram_adapter.py](/Users/palba/Projects/Clawdio/scripts/telegram_adapter.py)
3. Dashboard
   - [docs/33-dashboard-control-plane.md](/Users/palba/Projects/Clawdio/docs/33-dashboard-control-plane.md)
   - [dashboard/backend.py](/Users/palba/Projects/Clawdio/dashboard/backend.py)
   - [dashboard/server.py](/Users/palba/Projects/Clawdio/dashboard/server.py)
4. Model routing / providers
   - [docs/34-model-routing-playbook.md](/Users/palba/Projects/Clawdio/docs/34-model-routing-playbook.md)
   - [docs/51-provider-smoke-checks.md](/Users/palba/Projects/Clawdio/docs/51-provider-smoke-checks.md)
   - [config/models.yaml](/Users/palba/Projects/Clawdio/config/models.yaml)
5. Memory
   - [docs/29-memory-hybrid-124-runbook.md](/Users/palba/Projects/Clawdio/docs/29-memory-hybrid-124-runbook.md)
   - [config/memory.yaml](/Users/palba/Projects/Clawdio/config/memory.yaml)
6. Calendar
   - [docs/48-google-calendar-runtime.md](/Users/palba/Projects/Clawdio/docs/48-google-calendar-runtime.md)
   - [scripts/google_calendar_runtime.py](/Users/palba/Projects/Clawdio/scripts/google_calendar_runtime.py)
7. Tasks
   - [docs/49-personal-task-runtime.md](/Users/palba/Projects/Clawdio/docs/49-personal-task-runtime.md)
   - [scripts/personal_task_runtime.py](/Users/palba/Projects/Clawdio/scripts/personal_task_runtime.py)
8. Gmail / Drive
   - [docs/43-gmail-inbox-processing-plan.md](/Users/palba/Projects/Clawdio/docs/43-gmail-inbox-processing-plan.md)
   - [docs/44-drive-shared-workspace-plan.md](/Users/palba/Projects/Clawdio/docs/44-drive-shared-workspace-plan.md)
9. Project spaces / thread separation
   - [docs/47-project-spaces-and-session-agent-strategy.md](/Users/palba/Projects/Clawdio/docs/47-project-spaces-and-session-agent-strategy.md)

## Practical shortcut

For most small features, you only need:

1. one sentence for the task
2. one module doc
3. one or two main files

Do not restate the whole project unless the work changes architecture.
