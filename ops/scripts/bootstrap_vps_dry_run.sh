#!/usr/bin/env bash
set -euo pipefail

# Dry-run planner only. Prints the commands that would be used for bootstrap.
# It does not execute package installs, service changes, or firewall changes.

OPENCLAW_USER="${OPENCLAW_USER:-pavel}"
OPENCLAW_HOME="${OPENCLAW_HOME:-/home/${OPENCLAW_USER}}"
OPENCLAW_BASE="${OPENCLAW_BASE:-/opt/openclaw}"
OPENCLAW_ENV="${OPENCLAW_ENV:-/etc/openclaw/openclaw.env}"

say() {
  printf '%s\n' "$*"
}

step() {
  printf '\n[%s] %s\n' "$1" "$2"
}

cmd() {
  printf '  - %s\n' "$*"
}

say "OpenClaw VPS bootstrap dry-run"
say "User: ${OPENCLAW_USER}"
say "Base: ${OPENCLAW_BASE}"
say "Env : ${OPENCLAW_ENV}"

step "01" "System prerequisites"
cmd "sudo apt-get update"
cmd "sudo apt-get install -y git curl ca-certificates nodejs npm python3"
cmd "node --version && npm --version && python3 --version"

step "02" "Filesystem layout"
cmd "sudo mkdir -p ${OPENCLAW_BASE} ${OPENCLAW_BASE}/logs ${OPENCLAW_BASE}/data"
cmd "sudo mkdir -p /etc/openclaw"
cmd "sudo chown -R ${OPENCLAW_USER}:${OPENCLAW_USER} ${OPENCLAW_BASE}"

step "03" "Environment/secrets"
cmd "sudo touch ${OPENCLAW_ENV}"
cmd "sudo chmod 600 ${OPENCLAW_ENV}"
cmd "sudo chown ${OPENCLAW_USER}:${OPENCLAW_USER} ${OPENCLAW_ENV}"
cmd "echo '# add runtime secrets here' | sudo tee -a ${OPENCLAW_ENV}"

step "04" "App/config sync"
cmd "rsync -av --exclude '.git' ./ ${OPENCLAW_BASE}/"
cmd "python3 ${OPENCLAW_BASE}/scripts/validate_configs.py --config-dir ${OPENCLAW_BASE}/config"

step "05" "Systemd units (user-mode templates)"
cmd "mkdir -p ${OPENCLAW_HOME}/.config/systemd/user"
cmd "cp ${OPENCLAW_BASE}/salvage/vps-20260302/consolidated/keep-core/systemd/openclaw-gateway.service ${OPENCLAW_HOME}/.config/systemd/user/"
cmd "systemctl --user daemon-reload"
cmd "systemctl --user enable openclaw-gateway.service"
cmd "systemctl --user start openclaw-gateway.service"

step "06" "Operational safeguards"
cmd "git -C ${OPENCLAW_BASE} config core.hooksPath .githooks"
cmd "python3 ${OPENCLAW_BASE}/scripts/scan_secrets.py"
cmd "python3 ${OPENCLAW_BASE}/scripts/model_usage_report.py --input ${OPENCLAW_BASE}/telemetry/model-calls.ndjson --output ${OPENCLAW_BASE}/telemetry/model-usage-latest.md"

step "07" "Manual checks"
cmd "systemctl --user status openclaw-gateway.service --no-pager"
cmd "ss -ltnup | grep -E ':18789|:8788' || true"
cmd "curl -sS http://127.0.0.1:18789/health || true"

say "\nDry-run complete. No changes were executed."
