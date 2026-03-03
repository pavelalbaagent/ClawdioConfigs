#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 scripts/validate_configs.py --config-dir config
python3 scripts/check_env_requirements.py
python3 scripts/scan_secrets.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/model_usage_report.py --input telemetry/model-calls.example.ndjson --output telemetry/model-usage-latest.md
python3 scripts/render_ops_snapshot.py --output telemetry/ops-snapshot.md --reminder-state data/reminders-state.json --model-report telemetry/model-usage-latest.md

echo "all safe checks completed"
