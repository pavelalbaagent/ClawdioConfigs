#!/usr/bin/env bash
set -euo pipefail

# Break-glass: temporarily re-open public SSH.

echo "[+] Restarting SSH service..."
sudo systemctl restart ssh || sudo systemctl restart sshd || true

echo "[+] Opening temporary public SSH..."
sudo ufw allow 22/tcp

if command -v at >/dev/null 2>&1; then
  echo "sudo ufw --force delete allow 22/tcp" | at now + 15 minutes || true
  echo "[+] Auto-close scheduled in 15 minutes."
else
  echo "[!] 'at' not installed. Close public SSH manually after recovery."
fi

echo "[+] Current UFW status:"
sudo ufw status verbose

echo "[OK] Recovery mode enabled."

