#!/usr/bin/env bash
set -euo pipefail

# Lock SSH to Tailscale-only using UFW.

if ! command -v ufw >/dev/null 2>&1; then
  echo "[+] Installing ufw..."
  sudo apt-get update
  sudo apt-get install -y ufw
fi

echo "[+] Setting defaults..."
sudo ufw default deny incoming
sudo ufw default allow outgoing

echo "[+] Allowing Tailscale interface..."
sudo ufw allow in on tailscale0
sudo ufw allow out on tailscale0
sudo ufw allow in on tailscale0 to any port 22 proto tcp

echo "[+] Enabling UFW..."
sudo ufw --force enable

echo "[+] Removing public SSH rules (Anywhere/Anywhere v6 on 22/tcp)..."
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

echo "[OK] Lockdown complete. SSH should now be Tailscale-only."

