# OpenClaw on Hetzner VPS: Security, Configuration, and Use Cases

Date: 2026-02-26

## I. Comprehensive Security Measures

Security is the top priority when running an autonomous agent with access to personal and business systems.  
Guiding principle: treat OpenClaw as an untrusted virtual assistant by default.

### A. Infrastructure and Network Isolation

1. Dedicated hardware/hosting (`+4`)
   - Run OpenClaw on a dedicated VPS (e.g., Hetzner/Hostinger) or dedicated always-on local hardware (e.g., Mac Mini).
   - Do not run on a daily-driver machine.
2. Private network access via VPN (`+1`)
   - Use Tailscale (or equivalent) to restrict SSH and management access to authorized devices/IPs.
3. Firewall and localhost binding
   - Configure a deny-by-default firewall.
   - Bind the OpenClaw app to `localhost` only.
   - Avoid exposing ports publicly or allowing network-scan visibility.
4. Least privilege runtime user
   - Run OpenClaw as a dedicated non-root user.
   - Prevent system-level access that could disable its own constraints.

### B. Account and Integration Isolation

1. Dedicated service accounts (`+3`)
   - Use separate accounts for agent operations (email, GitHub, Dropbox, etc.).
2. Restricted ingestion paths (`+1`)
   - Forward only trusted senders to the agent inbox to reduce prompt-injection risk from email.
3. Minimal integration permissions
   - Limit write scopes in connected tools (Calendar, Drive, etc.).
   - Require explicit human approval for high-impact actions (sending email, posting public content).

### C. Defending Against Prompt Injection and “Dirty Data”

1. Treat external data as untrusted (`+1`)
   - Internet content, external emails, and third-party skills are all potential prompt-injection vectors.
2. Three-layer defense strategy (`+3`)
   - Layer 1: deterministic sanitization (strip/neutralize instruction-like patterns such as “ignore previous instructions”).
   - Layer 2: “Frontier Scanner” review by a high-capability model in an isolated sandbox.
   - Layer 3: gated execution path for sensitive actions (human approval when needed).
3. Automated redaction (`+1`)
   - Redact secrets, API keys, and PII before logs, analytics, or outbound transmission.

### D. Audits, Key Management, and Backups

1. API key hygiene (`+1`)
   - Never store secrets in Git.
   - Keep keys in local `.env` files and enforce pre-commit secret checks.
2. Automated security reviews (`+2`)
   - Run OpenClaw security audit commands regularly.
   - Add a nightly “security council” process to review code, logs, and configuration drift.
3. Redundant backups (`+3`)
   - Use hourly encrypted backups for SQLite databases to cloud storage (e.g., Google Drive).
   - Sync codebase changes to GitHub continuously.

## II. Core Configuration and Setup

### A. Model Tiering and Cost Optimization

1. Route by task complexity (`+4`)
   - Use high-end models for planning/critical reasoning.
   - Use cheaper/faster models for repetitive coding and routine workflows.
2. Goal
   - Maintain quality while controlling long-running operational costs.

### B. Interfaces and Memory Management

1. Chat interfaces (`+2`)
   - Use Telegram or Slack as primary operator interface.
2. Context compartmentalization (`+4`)
   - Split work into dedicated channels/topics (e.g., coding, accounting, content ideas).
   - Load only relevant context per room to save memory and token usage.
3. System behavior files (`+3`)
   - `identity.md` and `soul.md`: agent persona/tone.
   - `heartbeat.md`: recurring background tasks on schedule.

## III. Primary Workflows and Use Cases

1. Personal CRM and meeting intelligence (`+3`)
   - Scan trusted email/calendar, track relationship history in local SQLite/vector storage, and extract action items from transcript tools (e.g., Fathom).
2. Automated knowledge base (`+2`)
   - Ingest URLs/PDFs/YouTube from a designated channel, summarize and vectorize locally, then query via natural language.
3. Business advisory councils (`+3`)
   - Feed operational data (social, CRM, finance exports) and run specialist sub-agents (marketing, finance, etc.) to produce prioritized daily recommendations.
4. Content production pipeline
   - From a tagged idea in Slack: research trends, prepare script outline, propose titles/thumbnails, and create an Asana task automatically.

## IV. Operating Principle Summary

1. Isolate everything (infrastructure, accounts, permissions).
2. Assume all incoming data is hostile until scanned/sanitized.
3. Keep humans in the loop for high-impact actions.
4. Automate audits and backups so security is continuous, not ad hoc.

## V. Current Baseline Config (Pavel)

### A. Docker Compose Baseline

```yaml
services:
  openclaw:
    image: openclaw/core:latest
    container_name: openclaw-core
    restart: always
    environment:
      - NODE_ENV=production
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    # THIS IS THE SECURITY KEY:
    # Bind only to localhost (or Tailscale interface in alternative setups)
    ports:
      - "127.0.0.1:18789:18789"
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
```

### B. Quick Security Validation

1. Strong choice: `127.0.0.1:18789:18789` prevents public exposure by default.
2. Good baseline: container log rotation reduces disk pressure.
3. Keep firewall default-deny and only allow SSH via Tailscale.
4. Access control in place: `pawork` SSH key is already added for server access.

### C. Hardening Delta (Next Iteration)

1. Pin image version/digest (avoid `:latest`) for reproducibility and supply-chain control.
2. Run container as non-root UID/GID where supported.
3. Add `security_opt: ["no-new-privileges:true"]`.
4. Drop Linux caps: `cap_drop: ["ALL"]` and only add back what is required.
5. Use `read_only: true` plus explicit writable mounts (`/app/data`, `/app/config`).
6. Add healthcheck and alerting for crash loops and hung state.
7. SSH daemon hardening: disable password auth and root login; keep key-based auth only.

## VI. Fresh-Start Runbook (Server Cleanup -> Working OpenClaw)

This section is the implementation plan to restart cleanly on a Hetzner VPS with security-first defaults.

### A. Scope and Assumptions

1. VPS OS: Ubuntu 22.04/24.04.
2. Access: SSH key login already works (`pawork` key present).
3. Goal: clean reset, then deploy OpenClaw reachable only through localhost/Tailscale.
4. Method: execute phase-by-phase and validate each checkpoint before continuing.

### B. Phase 0: Preflight Decisions (5-10 minutes)

1. Decide cleanup mode:
   - Mode A (recommended): keep OS, clean Docker/OpenClaw only.
   - Mode B: rebuild from fresh OS image in Hetzner Cloud Console.
2. Decide whether any current OpenClaw data must be preserved (`./data`, `./config`, `.env`).
3. Define canonical app path: `/opt/openclaw`.

Checkpoint:
- You know if you are preserving old data or fully discarding it.

### C. Phase 1: Safety Snapshot Before Cleanup

Run on VPS:

```bash
mkdir -p ~/preclean-backup
date > ~/preclean-backup/timestamp.txt
docker ps -a > ~/preclean-backup/docker-ps-a.txt 2>/dev/null || true
docker images > ~/preclean-backup/docker-images.txt 2>/dev/null || true
sudo cp -a /etc/ssh/sshd_config ~/preclean-backup/sshd_config.bak
```

If old OpenClaw files exist:

```bash
sudo tar -czf ~/preclean-backup/openclaw-opt-backup.tgz /opt/openclaw 2>/dev/null || true
```

Checkpoint:
- `~/preclean-backup` contains inventory and SSH config backup.

### D. Phase 2: Clean Existing OpenClaw Deployment

If old compose exists:

```bash
cd /opt/openclaw 2>/dev/null || exit 0
docker compose down --remove-orphans || true
```

Remove old app directory:

```bash
sudo rm -rf /opt/openclaw
sudo mkdir -p /opt/openclaw/{data,config,logs}
sudo chown -R $USER:$USER /opt/openclaw
```

Optional deeper Docker cleanup (only if you want a near-blank Docker state):

```bash
docker container prune -f
docker image prune -af
docker volume prune -f
```

Checkpoint:
- `/opt/openclaw` exists fresh with `data`, `config`, `logs`.
- No stale OpenClaw containers are running.

### E. Phase 3: Host Hardening Baseline

Update and base tools:

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install ufw fail2ban ca-certificates curl gnupg
```

UFW (default deny, SSH only via Tailscale interface):

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow in on tailscale0 to any port 22 proto tcp
sudo ufw enable
sudo ufw status verbose
```

SSH hardening in `/etc/ssh/sshd_config`:

```text
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

Then:

```bash
sudo systemctl restart ssh
```

Checkpoint:
- You can still SSH in with key auth.
- UFW is active and restrictive.

### F. Phase 4: Install/Validate Docker and Compose

Install Docker Engine + Compose plugin (if missing), then:

```bash
docker --version
docker compose version
```

Add your user to docker group (if needed):

```bash
sudo usermod -aG docker $USER
newgrp docker
```

Checkpoint:
- `docker ps` works without sudo.

### G. Phase 5: Install and Join Tailscale

Install Tailscale and authenticate the node, then confirm:

```bash
tailscale status
ip -brief addr show tailscale0
```

Checkpoint:
- VPS has a Tailscale IP and appears healthy in your tailnet.

### H. Phase 6: Create OpenClaw Runtime Files

Create `/opt/openclaw/docker-compose.yml`:

```yaml
services:
  openclaw:
    image: openclaw/core:latest
    container_name: openclaw-core
    restart: unless-stopped
    environment:
      - NODE_ENV=production
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    ports:
      - "127.0.0.1:18789:18789"
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

Create `/opt/openclaw/.env` with required OpenClaw keys/settings (do not commit this file).

Checkpoint:
- Compose and `.env` files exist with correct values.

### I. Phase 7: Start Stack and Validate Local Exposure

Start:

```bash
cd /opt/openclaw
docker compose up -d
docker compose ps
docker logs --tail=100 openclaw-core
```

Validate bind scope:

```bash
ss -ltnp | grep 18789
```

Expected:
- Listener should be `127.0.0.1:18789` (not `0.0.0.0:18789`).

Health check from server:

```bash
curl -I http://127.0.0.1:18789
```

Checkpoint:
- Container is up and app responds locally.

### J. Phase 8: Access from Your Laptop via SSH Tunnel

From your local machine:

```bash
ssh -N -L 18789:127.0.0.1:18789 <user>@<tailscale-ip-or-hostname>
```

Then open locally:

```text
http://127.0.0.1:18789
```

Checkpoint:
- OpenClaw UI/API reachable locally through the tunnel.

### K. Phase 9: Post-Deploy Security and Reliability Tasks

1. Pin exact image version or digest (replace `:latest`).
2. Add backup job for `/opt/openclaw/data` and `/opt/openclaw/config`.
3. Add scheduled security audit routine.
4. Add lightweight monitoring:
   - `docker ps` health,
   - disk usage,
   - restart alerts.
5. Review integration scopes before connecting Gmail/Drive/Slack/Telegram.

### L. Guided Execution Mode (How We Work Together)

1. We execute one phase at a time.
2. After each phase, you paste command output.
3. I validate output, diagnose issues, and only then move to next phase.
4. If a step fails, we branch into a targeted fix path and rejoin the main runbook.
