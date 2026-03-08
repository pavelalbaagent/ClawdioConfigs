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

## Recommended placement on VPS

1. Copy `scripts/vps-*.sh` to `~/scripts/`.
2. Set executable permissions: `chmod +x ~/scripts/vps-*.sh`.
3. Copy any needed user-mode unit files from `ops/systemd/` into `~/.config/systemd/user/`.
4. Test all scripts and timers in a controlled window before production cutover.
