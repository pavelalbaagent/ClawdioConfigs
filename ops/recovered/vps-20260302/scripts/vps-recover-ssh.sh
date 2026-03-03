#!/usr/bin/env bash
set -euo pipefail

systemctl restart ssh || systemctl restart sshd || true
ufw allow 22/tcp

if command -v at >/dev/null 2>&1; then
echo "ufw --force delete allow 22/tcp" | at now + 15 minutes || true
echo "[+] Auto-close scheduled in 15 minutes"
else
echo "[!] Install 'at' or close SSH manually after recovery"
fi

ufw status verbose
echo "[OK] Recovery mode enabled."
