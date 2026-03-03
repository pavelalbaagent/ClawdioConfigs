#!/usr/bin/env bash
set -euo pipefail

while true; do
RULE_NUM=$(ufw status numbered | awk '/22\/tcp/ && /Anywhere/ && $0 !~ /tailscale0/ {gsub(/\[|\]/, "", $1); print $1; exit}')
if [[ -z "${RULE_NUM:-}" ]]; then
break
fi
ufw --force delete "$RULE_NUM"
done

ufw status verbose
echo "[OK] Emergency public SSH closed."
