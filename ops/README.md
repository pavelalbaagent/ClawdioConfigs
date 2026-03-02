# Operations Runbooks and Scripts

## Included scripts

1. `scripts/vps-lockdown.sh`: enforce Tailscale-only SSH with `ufw`.
2. `scripts/vps-recover-ssh.sh`: temporary public SSH break-glass access.
3. `scripts/vps-close-emergency-ssh.sh`: remove emergency public SSH rules.
4. `scripts/openclaw-dashboard-tunnel.sh`: local SSH tunnel to OpenClaw dashboard via Tailscale.
5. `scripts/run-codex-safe.sh`: controlled Codex CLI wrapper for agent usage.
6. `scripts/run-gemini-safe.sh`: controlled Gemini CLI wrapper for agent usage.

## Recommended placement on VPS

1. Copy `scripts/vps-*.sh` to `~/scripts/`.
2. Set executable permissions: `chmod +x ~/scripts/vps-*.sh`.
3. Test all scripts in controlled window before production cutover.
