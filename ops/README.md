# Operations Runbooks and Scripts

## Included scripts

1. `scripts/vps-lockdown.sh`: enforce Tailscale-only SSH with `ufw`.
2. `scripts/vps-recover-ssh.sh`: temporary public SSH break-glass access.
3. `scripts/vps-close-emergency-ssh.sh`: remove emergency public SSH rules.
4. `scripts/openclaw-dashboard-tunnel.sh`: local SSH tunnel to OpenClaw dashboard via Tailscale.
5. `scripts/run-codex-safe.sh`: controlled Codex CLI wrapper for agent usage.
6. `scripts/run-gemini-safe.sh`: controlled Gemini CLI wrapper for agent usage.
7. `scripts/reminder_scheduler_adapter.py`: reminder scheduling guard that enforces `payload.kind=systemEvent` for main-session due reminders.
8. `systemd/openclaw-gmail-processor.service` + `systemd/openclaw-gmail-processor.timer`: user-mode Gmail batch processor timer for the VPS.
9. `systemd/openclaw-telegram-adapter.service`: user-mode Telegram long-polling adapter that also drives reminder due/follow-up delivery.
10. `systemd/openclaw-gateway.service`: gateway unit backed by `/etc/openclaw/gateway.env` so it stays isolated from the main app secrets file.
11. `systemd/openclaw-dashboard.service`: user-mode dashboard service on loopback port `18890` so it can run in parallel with the legacy gateway on `18789` during migration and replace it cleanly afterward.
12. `systemd/openclaw-memory-sync.service` + `systemd/openclaw-memory-sync.timer`: bounded hybrid-memory sync loop with dashboard-readable status output.
13. `systemd/openclaw-ops-guard-review.service` + `systemd/openclaw-ops-guard-review.timer`: daily ops-guard review output.
14. `systemd/openclaw-ops-guard-architecture-review.service` + `systemd/openclaw-ops-guard-architecture-review.timer`: weekly architecture/governance review output.

## Recommended placement on VPS

1. Copy `scripts/vps-*.sh` to `~/scripts/`.
2. Set executable permissions: `chmod +x ~/scripts/vps-*.sh`.
3. Copy any needed user-mode unit files from `ops/systemd/` into `~/.config/systemd/user/`.
4. Enable the Telegram adapter for MVP chat ingress: `systemctl --user enable --now openclaw-telegram-adapter.service`
5. Enable the dashboard service: `systemctl --user enable --now openclaw-dashboard.service`
6. Enable memory sync and ops review timers once hybrid memory is live: `systemctl --user enable --now openclaw-memory-sync.timer openclaw-ops-guard-review.timer openclaw-ops-guard-architecture-review.timer`
7. Test all scripts and timers in a controlled window before production cutover.
