Absolutely. Here is the exact text you can save as a file on your computer.

---

VPS TAILSCALE SSH RECOVERY NOTES
================================

Goal
----
Keep SSH locked to Tailscale only, but recover quickly if Tailscale access fails.

How to detect the problem
-------------------------
You likely have a Tailscale access failure if:

1) From your Mac, this fails:
ssh <user>@100.119.27.8

2) And Tailscale host/alias also fails:
ssh clawdio-vps

3) But VPS is still running in provider dashboard.

What to do immediately
----------------------
1) Open your VPS provider web console (serial/VNC console).
2) Log in directly in that console.
3) Run the recovery script to temporarily open public SSH.
4) SSH in from your Mac using VPS public IP.
5) Repair Tailscale.
6) Re-lock SSH to Tailscale-only (close public SSH again).

Exact commands during incident
------------------------------

A) In provider web console (on VPS):
sudo bash ~/scripts/vps-recover-ssh.sh

B) On your Mac (local terminal):
ssh <user>@<VPS_PUBLIC_IP>

C) On VPS (after reconnecting), repair/check Tailscale:
sudo systemctl enable tailscaled
sudo systemctl restart tailscaled
tailscale status
tailscale netcheck

D) On your Mac (verify tailnet path works again):
ssh <user>@100.119.27.8

E) On VPS (close emergency public SSH):
sudo bash ~/scripts/vps-close-emergency-ssh.sh

F) On VPS (final verify):
sudo ufw status verbose
ss -ltnup | grep ':22' || true
tailscale status

Normal hardening command (non-incident)
---------------------------------------
Run on VPS when you want to enforce Tailscale-only SSH:

sudo bash ~/scripts/vps-lockdown.sh

Full scripts
============

File: ~/scripts/vps-lockdown.sh
--------------------------------
#!/usr/bin/env bash
set -euo pipefail

# Lock SSH to Tailscale-only using UFW

if ! command -v ufw >/dev/null 2>&1; then
echo "[+] Installing ufw..."
apt-get update
apt-get install -y ufw
fi

echo "[+] Setting defaults..."
ufw default deny incoming
ufw default allow outgoing

echo "[+] Allowing Tailscale interface..."
ufw allow in on tailscale0
ufw allow out on tailscale0
ufw allow in on tailscale0 to any port 22 proto tcp

echo "[+] Enabling UFW..."
ufw --force enable

echo "[+] Removing public SSH rules (Anywhere/Anywhere v6 on 22/tcp)..."
while true; do
RULE_NUM=$(ufw status numbered | awk '/22\/tcp/ && /Anywhere/ && $0 !~ /tailscale0/ {gsub(/\[|\]/, "", $1); print $1; exit}')
if [[ -z "${RULE_NUM:-}" ]]; then
break
fi
echo " - deleting rule #$RULE_NUM"
ufw --force delete "$RULE_NUM"
done

echo "[+] Final UFW status:"
ufw status verbose

echo "[OK] Lockdown complete. SSH should now be Tailscale-only."

File: ~/scripts/vps-recover-ssh.sh
----------------------------------
#!/usr/bin/env bash
set -euo pipefail

# Break-glass: temporarily re-open public SSH

echo "[+] Restarting SSH service..."
systemctl restart ssh || systemctl restart sshd || true

echo "[+] Opening temporary public SSH..."
ufw allow 22/tcp

# Optional auto-close in 15 min if `at` exists
if command -v at >/dev/null 2>&1; then
echo "ufw --force delete allow 22/tcp" | at now + 15 minutes || true
echo "[+] Auto-close scheduled in 15 minutes."
else
echo "[!] 'at' not installed. Close public SSH manually after recovery."
fi

echo "[+] Current UFW status:"
ufw status verbose

echo "[OK] Recovery mode enabled."

File: ~/scripts/vps-close-emergency-ssh.sh
-------------------------------------------
#!/usr/bin/env bash
set -euo pipefail

# Close any public SSH rules again

echo "[+] Removing public SSH rules..."
while true; do
RULE_NUM=$(ufw status numbered | awk '/22\/tcp/ && /Anywhere/ && $0 !~ /tailscale0/ {gsub(/\[|\]/, "", $1); print $1; exit}')
if [[ -z "${RULE_NUM:-}" ]]; then
break
fi
echo " - deleting rule #$RULE_NUM"
ufw --force delete "$RULE_NUM"
done

echo "[+] Final UFW status:"
ufw status verbose

echo "[OK] Emergency public SSH closed."

One-time script install (if missing)
====================================
Run on VPS:

mkdir -p ~/scripts
nano ~/scripts/vps-lockdown.sh
nano ~/scripts/vps-recover-ssh.sh
nano ~/scripts/vps-close-emergency-ssh.sh
chmod +x ~/scripts/vps-*.sh

(Then paste each full script above into its file.)

---

If you want, next message I can give you one final tiny “print and stick on desk” version (10 lines max).
