#!/usr/bin/env bash
set -euo pipefail

if ! command -v ufw >/dev/null 2>&1; then
apt-get update
apt-get install -y ufw
fi

ufw default deny incoming
ufw default allow outgoing

ufw allow in on tailscale0
ufw allow out on tailscale0
ufw allow in on tailscale0 to any port 22 proto tcp

ufw --force enable

while true; do
RULE_NUM=$(ufw status numbered | awk '/22\/tcp/ && /Anywhere/ && $0 !~ /tailscale0/ {gsub(/\[|\]/, "", $1); print $1; exit}')
if [[ -z "${RULE_NUM:-}" ]]; then
break
fi
ufw --force delete "$RULE_NUM"
done

ufw status verbose
echo "[OK] Lockdown complete."
