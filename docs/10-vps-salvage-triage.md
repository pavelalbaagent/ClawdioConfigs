# VPS Salvage Triage (2026-03-02)

## Snapshot captured

1. Full archive pulled from VPS:
2. `external/vps-salvage-20260302/vps-openclaw-full-20260302.tgz` (~32 MB compressed).
3. Extracted working copy:
4. `external/vps-salvage-20260302/extracted` (~289 MB in `.openclaw`).

## Current VPS baseline observed

1. Host: `clawdio-pbr` (Ubuntu 22.04.5 LTS, kernel `5.15.0-164-generic`).
2. OpenClaw binary present: `/usr/bin/openclaw` version `2026.2.26`.
3. Active user service: `openclaw-gateway.service` (`~/.config/systemd/user/openclaw-gateway.service`).
4. Key listeners:
5. `127.0.0.1:18789` (gateway),
6. `127.0.0.1:8788` (gmail watcher),
7. Tailnet funnel on `:80` and `:443`,
8. SSH open on `0.0.0.0:22`.
9. User cron entries:
10. daily backup script at `05:00 UTC`,
11. hourly quota watcher.
12. Codex CLI, Gemini CLI, and n8n were not found on VPS PATH during inventory.

## Keep now (high value)

These were consolidated into `salvage/vps-20260302/consolidated/keep-core/`:

1. Core operating docs (`AGENTS`, `AUTONOMY`, `MODEL_POLICY`, `FAILOVER_POLICY`, `WORKFLOWS`, `GATEWAY_CHANGE_PROTOCOL`, `VPS_RECOVERY_GUIDE`).
2. Integration/ops docs (`SLACK_STRUCTURE`, `REMINDERS_ARCHITECTURE`, `CONFIG_BASELINE`).
3. Project planning docs (`PROJECTS`, `PROJECT_IDEAS_FROM_OPENCLAW_VIDEOS`, `YTINGEST_V1_PLAN`, pipeline `PLAN/README/TASKS`).
4. Reusable scripts (`quota_watch.py`, `reminder_helper.py`, `reminder_pair.py`, `vps-*.sh`).
5. Systemd runtime definition (`openclaw-gateway.service` and drop-ins), token redacted.
6. Watchlist seeds (`watchlist.yaml`, `youtube-watchlist.md`).

Reference-only items are in `salvage/vps-20260302/consolidated/archive-reference/`.

## Quarantine (do not commit as-is)

1. All `openclaw.json*` files (contain tokens/secrets and sensitive routing data).
2. `.openclaw/credentials/**` (WhatsApp and auth material).
3. Agent session logs `agents/**/sessions/*.jsonl` (highly sensitive chat/runtime history).
4. Device/auth files (`identity/device-auth.json`, similar).
5. `.env` files and oauth token files (for example `YTIngest/.env`, `.secrets/youtube-oauth-token.json`).
6. SQLite memory DBs (`memory/*.sqlite`) unless explicitly needed for migration.

## Probably discard or regenerate

1. `workspace/YTIngest/node_modules` (vendor dependencies, regenerate with `npm install`).
2. Old deleted-session artifacts (`*.deleted.*.jsonl`) unless forensic history is required.
3. Duplicate historical config backups after extracting useful policy patterns.

## Immediate security actions

1. Rotate gateway/hook/channel credentials that existed in historical `openclaw.json` backups.
2. Keep secrets outside repo (`/etc/openclaw/openclaw.env` or equivalent).
3. Keep salvage archive under `external/` only (already gitignored).
