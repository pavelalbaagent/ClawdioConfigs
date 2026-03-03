#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${HOME}/.openclaw"
CFG="${STATE_DIR}/openclaw.json"
TS="$(date +%F-%H%M%S)"
BACKUP="${STATE_DIR}/openclaw.json.bak.${TS}"

echo "[1/5] Backing up config -> ${BACKUP}"
cp "${CFG}" "${BACKUP}"

echo "[2/5] Restarting gateway"
if ! openclaw gateway restart; then
  echo "[ERR] Restart command failed. Rolling back..."
  cp "${BACKUP}" "${CFG}"
  openclaw gateway restart || true
  exit 1
fi

echo "[3/5] Waiting for services"
sleep 3

echo "[4/5] Probing channels"
PROBE_OUT="$(openclaw channels status --probe 2>&1 || true)"
echo "$PROBE_OUT"

ok_whatsapp=0
ok_gateway=0

if echo "$PROBE_OUT" | grep -qi "Gateway reachable"; then
  ok_gateway=1
fi
if echo "$PROBE_OUT" | grep -Eqi "WhatsApp .*connected"; then
  ok_whatsapp=1
fi

if [[ $ok_gateway -eq 1 && $ok_whatsapp -eq 1 ]]; then
  echo "[5/5] PASS: Gateway + WhatsApp look healthy."
  echo "Backup kept at: ${BACKUP}"
  exit 0
fi

echo "[FAIL] Health checks failed. Rolling back to ${BACKUP}"
cp "${BACKUP}" "${CFG}"
openclaw gateway restart || true
sleep 2
openclaw channels status --probe || true
exit 2
