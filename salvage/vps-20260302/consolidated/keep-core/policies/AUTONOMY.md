# AUTONOMY.md — Clawdio Operating Policy

## 1) Auto-approved actions (no confirmation needed)

- Read/edit files under:
  - `/home/pavel/.openclaw/workspace/**`
  - approved app config paths listed in `TOOLS.md`
- Run read-only diagnostics:
  - `openclaw status`
  - `openclaw health --json`
  - `openclaw security audit --deep`
  - log inspection commands for approved services
- Restart approved services/containers:
  - `openclaw gateway restart`
  - approved `systemctl restart <service>`
  - approved `docker restart <container>`
- Create/update non-destructive automation:
  - health checks
  - status reporting
  - alerting scripts

## 2) Ask-first actions (explicit approval required each time)

- Firewall changes (`ufw`/`nftables`/cloud security groups)
- SSH/RDP/auth policy changes
- Installing/removing OS packages
- Enabling/disabling services not in the approved list
- Public exposure changes (ports, DNS, reverse proxy, tunnels)
- Scheduling new persistent cron jobs
- Accessing new secret stores/credential paths

## 3) Never without explicit task + confirmation

- Destructive operations (DB drops, volume wipes, mass deletes)
- Credential rotation/revocation
- Identity/permission escalation policy changes
- External messaging/posting on your behalf

## 4) Guardrails

- Prefer reversible changes.
- Always provide rollback steps.
- Stop and ask on unexpected output/errors.
- Redact secrets in logs/reports.
- No `--privileged` containers unless explicitly approved.

## 5) Approved host command allowlist

(Keep synced with sudoers `Cmnd_Alias OPENCLAW_OPS`)

- `/usr/local/bin/openclaw gateway status`
- `/usr/local/bin/openclaw gateway restart`
- `/bin/systemctl status openclaw-gateway`
- `/bin/systemctl restart openclaw-gateway`
- `/bin/journalctl -u openclaw-gateway -n 200 --no-pager`
- `/usr/bin/docker ps`
- `/usr/bin/docker logs --tail 200 openclaw-gateway`
- `/usr/bin/docker restart openclaw-gateway`

## 6) Approval defaults

If unclear, default to **ask-first**.
