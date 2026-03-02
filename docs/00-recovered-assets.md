# Recovered Assets Before Scrapping Old OpenClaw

## Sources reviewed

1. `VPS_TAILSCALE_SSH_RECOVERY_NOTES.md`
2. `commands.md`

## Assets extracted into reusable files

1. `ops/scripts/vps-lockdown.sh`
2. `ops/scripts/vps-recover-ssh.sh`
3. `ops/scripts/vps-close-emergency-ssh.sh`
4. `ops/scripts/openclaw-dashboard-tunnel.sh`

## Why these are worth keeping

1. They preserve your Tailscale-only SSH hardening model.
2. They preserve your break-glass recovery path when Tailscale fails.
3. They preserve dashboard access without exposing public ports.

## Recovery checklist before wiping old instance

1. Copy `ops/scripts/vps-*.sh` to `~/scripts/` on VPS.
2. Run `chmod +x ~/scripts/vps-*.sh`.
3. Verify `sudo bash ~/scripts/vps-lockdown.sh` works.
4. In a safe test window, run `sudo bash ~/scripts/vps-recover-ssh.sh`.
5. Confirm SSH from public IP works.
6. Run `sudo bash ~/scripts/vps-close-emergency-ssh.sh`.
7. Confirm `ufw` no longer exposes public `22/tcp`.
