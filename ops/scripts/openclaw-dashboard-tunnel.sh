#!/usr/bin/env bash
set -euo pipefail

# Local tunnel to OpenClaw dashboard through Tailscale.
# Override defaults with env vars when needed.

SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519_pawork}"
REMOTE_USER="${REMOTE_USER:-pavel}"
TAILSCALE_IP="${TAILSCALE_IP:-100.119.27.8}"
LOCAL_PORT="${LOCAL_PORT:-18789}"
REMOTE_PORT="${REMOTE_PORT:-18789}"

exec ssh \
  -i "$SSH_KEY" \
  -o IdentitiesOnly=yes \
  -N \
  -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" \
  "${REMOTE_USER}@${TAILSCALE_IP}"

