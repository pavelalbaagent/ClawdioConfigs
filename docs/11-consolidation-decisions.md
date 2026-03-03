# Consolidation Decisions (Run 2)

Date: 2026-03-02

## Outcome

1. Full VPS snapshot captured under `external/vps-salvage-20260302/`.
2. Consolidated salvage set created under `salvage/vps-20260302/consolidated/`.
3. Structure now split into:
4. `keep-core`: direct migration candidates.
5. `archive-reference`: contextual/reference-only assets.

## Keep-Core (directly useful)

Path: `salvage/vps-20260302/consolidated/keep-core/`

1. `policies/`:
2. `AGENTS.md`, `AUTONOMY.md`, `MODEL_POLICY.md`, `FAILOVER_POLICY.md`.
3. `GATEWAY_CHANGE_PROTOCOL.md`, `CONFIG_BASELINE.md`, `WORKFLOWS.md`.
4. `VPS_RECOVERY_GUIDE.md`, `REMINDERS_ARCHITECTURE.md`, `YTINGEST_V1_PLAN.md`.
5. `scripts/`:
6. `quota_watch.py`, `reminder_helper.py`, `reminder_pair.py`, `vps-*.sh`.
7. `systemd/`:
8. `openclaw-gateway.service`, `override.conf`, `20-gmail-keyring.conf`.
9. `watchlist/`:
10. `watchlist.yaml`.
11. `ops/`:
12. `safe-restart.sh`, `openclaw-ops.sudoers.template`.

## Archive-Reference (keep for context)

Path: `salvage/vps-20260302/consolidated/archive-reference/`

1. `docs/`:
2. `PROJECTS.md`, `PROJECT_IDEAS_FROM_OPENCLAW_VIDEOS.md`.
3. `SLACK_STRUCTURE.md` (rewritten as platform-agnostic communication template).
4. `TOOLS.md`, `youtube-watchlist.md`.
5. `projects/`:
6. `PLAN.md`, `README.md`, `TASKS.md` (youtube-watchlist-pipeline planning context).

## Explicitly excluded from consolidation

1. Raw `openclaw.json*` files.
2. Credentials and auth stores under `.openclaw/credentials/`.
3. Session logs (`*.jsonl`) and deleted session artifacts.
4. SQLite memories (`memory/*.sqlite`).
5. `.env` and OAuth token files from `YTIngest`.
6. Dependency/vendor trees (for example `YTIngest/node_modules`).

## Decisions applied from your guidance

1. Historical `REMINDERS.md` was removed from the consolidated archive.
2. Reminder behavior was preserved as a clean deterministic spec:
3. [docs/12-reminder-v2-spec.md](/Users/palba/Projects/Clawdio/docs/12-reminder-v2-spec.md)
4. A deterministic state-machine helper was added:
5. [reminder_state_machine.py](/Users/palba/Projects/Clawdio/ops/scripts/reminder_state_machine.py)
6. `SLACK_STRUCTURE.md` was kept and rewritten as platform-agnostic.
