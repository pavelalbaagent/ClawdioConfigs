# VPS Bootstrap Dry Run

## Goal

Generate a deterministic VPS setup sequence without making live changes.

## Script

1. [bootstrap_vps_dry_run.sh](/Users/palba/Projects/Clawdio/ops/scripts/bootstrap_vps_dry_run.sh)

## Run

```bash
ops/scripts/bootstrap_vps_dry_run.sh
```

Optional overrides:

```bash
OPENCLAW_USER=pavel OPENCLAW_BASE=/opt/clawdio ops/scripts/bootstrap_vps_dry_run.sh
```

The script only prints planned commands. It does not execute installs, systemd changes, or firewall actions.
