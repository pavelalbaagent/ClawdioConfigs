# Personal Task Runtime

Last updated: 2026-03-08

## Purpose

Provide a real external personal-task lane instead of treating all tasks as local dashboard state.

Current MVP provider choice:

1. `todoist`

Current runtime covers:

1. snapshot active personal tasks
2. create a task
3. complete a task
4. defer a task
5. publish a dashboard-readable status snapshot
6. feed assistant-owned morning briefings with current due/overdue task pressure

## Files

1. Runtime script: [personal_task_runtime.py](/Users/palba/Projects/Personal/Clawdio/scripts/personal_task_runtime.py)
2. Runtime status snapshot: `data/personal-task-runtime-status.json`

## Why Todoist First

1. It matches the repo’s recommended post-MVP bundle.
2. It avoids multi-provider complexity for the first live task loop.
3. It is the cleanest path to shipping one useful personal-task integration fast.

Other configured providers remain design options, not current runtime targets:

1. `google_tasks`
2. `asana`

## Commands

Refresh snapshot:

```bash
python3 scripts/personal_task_runtime.py --env-file secrets/openclaw.env snapshot --json
```

Create a task:

```bash
python3 scripts/personal_task_runtime.py --env-file secrets/openclaw.env create \
  --title "Pay insurance" \
  --due-string "tomorrow 6pm" \
  --priority 3 \
  --apply --json
```

Complete a task:

```bash
python3 scripts/personal_task_runtime.py --env-file secrets/openclaw.env complete \
  --task-id "<todoist-task-id>" \
  --apply --json
```

Defer a task:

```bash
python3 scripts/personal_task_runtime.py --env-file secrets/openclaw.env defer \
  --task-id "<todoist-task-id>" \
  --due-date "2026-03-10" \
  --apply --json
```

## Dashboard Surface

The dashboard now exposes:

1. provider
2. open and overdue counts
3. task table
4. create task action
5. complete action
6. defer action
7. sync action

## Current Limits

1. Only Todoist is supported in the live runtime.
2. Task creation UI is intentionally minimal.
3. There is no reminder-link or calendar-link automation yet.
4. Google Tasks and Asana are still future provider-specific expansions.

## Next Gate

1. Decide whether Todoist stays the long-term personal-task provider.
2. Add reminder linkage and optional calendar promotion from personal tasks.
3. If needed later, build separate runtimes for Google Tasks or Asana instead of hiding provider differences behind one weak abstraction.
