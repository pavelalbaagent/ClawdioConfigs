# Recovered Ops Templates

This folder keeps only recovered operational assets that still provide unique value.

## Keep

1. `vps-20260302/ops/openclaw-ops.sudoers.template`
2. `vps-20260302/ops/safe-restart.sh`
3. `vps-20260302/systemd/`

## Removed

1. Duplicate recovery shell scripts already promoted into `ops/scripts/`
2. Old WhatsApp-specific reminder helpers
3. Quota watcher and other runtime-specific legacy scripts that were tightly coupled to the old instance

## Rule

If a recovered file has a maintained canonical replacement elsewhere in the repo, the recovered duplicate should not stay here.
