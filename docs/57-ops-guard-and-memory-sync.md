# Ops Guard And Memory Sync

Last updated: 2026-03-09

## Goal

Turn continuous improvement into a bounded operational loop instead of a vague self-improving-agent idea.

Two supporting processes do that:

1. memory sync
2. ops-guard reviews

## Memory sync runner

Main file:

1. [memory_sync_runner.py](/Users/palba/Projects/Clawdio/scripts/memory_sync_runner.py)

Purpose:

1. run [memory_index_sync.py](/Users/palba/Projects/Clawdio/scripts/memory_index_sync.py)
2. persist a dashboard-readable snapshot to `data/memory-sync-status.json`
3. make hybrid-memory health visible without reading raw logs

Typical run:

```bash
python3 scripts/memory_sync_runner.py --env-file secrets/openclaw.env --json
```

## Ops Guard review runtime

Main file:

1. [ops_guard_review.py](/Users/palba/Projects/Clawdio/scripts/ops_guard_review.py)

Supported modes:

1. `daily_ops_review`
2. `weekly_architecture_review`

Outputs:

1. machine-readable status in `data/continuous-improvement-status.json`
2. markdown review reports in `docs/reviews/`

Typical runs:

```bash
python3 scripts/ops_guard_review.py --mode daily_ops_review --json
```

```bash
python3 scripts/ops_guard_review.py --mode weekly_architecture_review --json
```

## Review inputs

The review loop currently checks:

1. provider health degradation
2. reminder backlog
3. blocked tasks
4. assistant-vs-specialist route mix
5. missing conversational agent state
6. memory-sync health
7. paused-project archive candidates

## VPS timers

Systemd units:

1. [openclaw-memory-sync.service](/Users/palba/Projects/Clawdio/ops/systemd/openclaw-memory-sync.service)
2. [openclaw-memory-sync.timer](/Users/palba/Projects/Clawdio/ops/systemd/openclaw-memory-sync.timer)
3. [openclaw-ops-guard-review.service](/Users/palba/Projects/Clawdio/ops/systemd/openclaw-ops-guard-review.service)
4. [openclaw-ops-guard-review.timer](/Users/palba/Projects/Clawdio/ops/systemd/openclaw-ops-guard-review.timer)
5. [openclaw-ops-guard-architecture-review.service](/Users/palba/Projects/Clawdio/ops/systemd/openclaw-ops-guard-architecture-review.service)
6. [openclaw-ops-guard-architecture-review.timer](/Users/palba/Projects/Clawdio/ops/systemd/openclaw-ops-guard-architecture-review.timer)

## Design rule

`ops_guard` can recommend changes.

It cannot silently rewrite core policy.

Structural changes still require:

1. explicit approval
2. normal code/config review
3. visible reports in the dashboard or repo
