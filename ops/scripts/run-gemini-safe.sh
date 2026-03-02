#!/usr/bin/env bash
set -euo pipefail

# Safe wrapper for Gemini CLI calls from OpenClaw.
# Usage: run-gemini-safe.sh <args passed to gemini>

if ! command -v gemini >/dev/null 2>&1; then
  echo "gemini binary not found in PATH" >&2
  exit 127
fi

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 <gemini-args...>" >&2
  exit 2
fi

DENY_FLAGS_REGEX='--danger|--allow-all-tools|--yolo'
for arg in "$@"; do
  if [[ "$arg" =~ $DENY_FLAGS_REGEX ]]; then
    echo "Blocked arg: $arg" >&2
    exit 3
  fi
done

TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-300}"
LOG_DIR="${LOG_DIR:-./logs}"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="$LOG_DIR/gemini-${STAMP}.log"

{
  echo "ts=$STAMP"
  echo "tool=gemini"
  echo "timeout_seconds=$TIMEOUT_SECONDS"
  echo "args=$*"
} >> "$LOG_FILE"

if command -v timeout >/dev/null 2>&1; then
  timeout "$TIMEOUT_SECONDS" gemini "$@" >> "$LOG_FILE" 2>&1
else
  gemini "$@" >> "$LOG_FILE" 2>&1
fi

tail -c 20000 "$LOG_FILE"

