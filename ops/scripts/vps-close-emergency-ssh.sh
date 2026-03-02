#!/usr/bin/env bash
set -euo pipefail

# Close any public SSH rules after break-glass recovery.

echo "[+] Removing public SSH rules..."
while true; do
  RULE_NUM=$(sudo ufw status numbered | awk '/22\/tcp/ && /Anywhere/ && $0 !~ /tailscale0/ {gsub(/\[|\]/, "", $1); print $1; exit}')
  if [[ -z "${RULE_NUM:-}" ]]; then
    break
  fi
  echo " - deleting rule #$RULE_NUM"
  sudo ufw --force delete "$RULE_NUM"
done

echo "[+] Final UFW status:"
sudo ufw status verbose

echo "[OK] Emergency public SSH closed."

