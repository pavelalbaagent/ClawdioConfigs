# VPS Tailscale-Only SSH Recovery Guide

Use this when your VPS is hardened to Tailscale-only SSH and you need a reliable recovery path.

---

## 0) 60-second emergency flow

If you're locked out and need fast recovery:

1. Open provider web console for the VPS (not SSH).
2. Run:
   ```bash
   sudo bash ~/scripts/vps-recover-ssh.sh
   ```
3. SSH in from your machine and repair Tailscale/keys.
4. Close emergency public SSH:
   ```bash
   sudo bash ~/scripts/vps-close-emergency-ssh.sh
   ```
5. Re-apply hardened mode:
   ```bash
   sudo bash ~/scripts/vps-lockdown.sh
   ```

Keep this section short, printed, and tested once while calm.

---

## 1) Create the scripts directly on VPS (one-time)

SSH to VPS, then run:

```bash
mkdir -p ~/scripts

cat > ~/scripts/vps-lockdown.sh <<'EOF'
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
EOF

cat > ~/scripts/vps-recover-ssh.sh <<'EOF'
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
EOF

cat > ~/scripts/vps-close-emergency-ssh.sh <<'EOF'
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
EOF

chmod +x ~/scripts/vps-*.sh
ls -l ~/scripts/vps-*.sh
```

---

## 2) Normal hardened mode (Tailscale-only)

```bash
sudo bash ~/scripts/vps-lockdown.sh
```

Expected outcome:
- Inbound default deny
- SSH allowed only on `tailscale0`
- No public `22/tcp` allow rules

---

## 3) Emergency recovery (if tailnet path breaks)

Use your VPS provider web console (not SSH), then run:

```bash
sudo bash ~/scripts/vps-recover-ssh.sh
```

This temporarily opens public SSH so you can reconnect and repair Tailscale.

After recovery is complete, close public SSH again:

```bash
sudo bash ~/scripts/vps-close-emergency-ssh.sh
```

---

## 4) Quick health checks

```bash
tailscale status
tailscale netcheck
sudo ufw status verbose
ss -ltnup | grep :22
```

---

## 5) Best practices

- Keep provider console access tested and available.
- Keep SSH keys backed up locally.
- Do not leave public `22/tcp` open after incident recovery.
- Test recovery flow once while calm, not during outage.

---

## 6) Optional alias setup

Add to `~/.bashrc` on VPS:

```bash
alias vps-lockdown='sudo bash ~/scripts/vps-lockdown.sh'
alias vps-recover='sudo bash ~/scripts/vps-recover-ssh.sh'
alias vps-close='sudo bash ~/scripts/vps-close-emergency-ssh.sh'
```

Reload shell:

```bash
source ~/.bashrc
```
