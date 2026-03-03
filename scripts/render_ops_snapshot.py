#!/usr/bin/env python3
"""Render a local ops snapshot markdown from config/state files."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_configs import load_yaml  # type: ignore


ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def count_reminders(state: dict[str, Any] | None) -> dict[str, int]:
    counters = {"pending": 0, "awaiting_reply": 0, "done": 0, "cancelled": 0, "other": 0}
    if not state or not isinstance(state, dict):
        return counters
    for reminder in (state.get("reminders") or {}).values():
        status = str((reminder or {}).get("status", "other"))
        if status in counters:
            counters[status] += 1
        else:
            counters["other"] += 1
    return counters


def main() -> int:
    parser = argparse.ArgumentParser(description="Render local ops snapshot")
    parser.add_argument("--output", default=str(ROOT / "telemetry" / "ops-snapshot.md"))
    parser.add_argument("--reminder-state", default=str(ROOT / "data" / "reminders-state.json"))
    parser.add_argument("--model-report", default=str(ROOT / "telemetry" / "model-usage-latest.md"))
    args = parser.parse_args()

    core = load_yaml(ROOT / "config" / "core.yaml")
    channels = load_yaml(ROOT / "config" / "channels.yaml")
    reminders_cfg = load_yaml(ROOT / "config" / "reminders.yaml")

    reminder_state = read_json(Path(args.reminder_state))
    reminder_counts = count_reminders(reminder_state)

    model_report_path = Path(args.model_report)
    model_report_present = model_report_path.exists()

    now = datetime.now(timezone.utc).isoformat()
    lines: list[str] = []
    lines.append("# Ops Snapshot")
    lines.append("")
    lines.append(f"Generated at: {now}")
    lines.append("")
    lines.append("## Runtime")
    lines.append(f"- Project: {core.get('project', {}).get('name', 'unknown')}")
    lines.append(f"- Environment: {core.get('project', {}).get('environment', 'unknown')}")
    lines.append(f"- Timezone: {core.get('owner', {}).get('timezone', 'unknown')}")
    lines.append("")

    lines.append("## Budget Caps")
    budgets = core.get("budgets", {})
    lines.append(f"- Daily cap (USD): {budgets.get('daily_usd_cap', 'n/a')}")
    lines.append(f"- Monthly cap (USD): {budgets.get('monthly_usd_cap', 'n/a')}")
    lines.append(f"- Hard stop on cap: {budgets.get('hard_stop_on_cap', 'n/a')}")
    lines.append("")

    lines.append("## Channels")
    ch = channels.get("channels", {})
    lines.append(f"- Primary: {ch.get('primary_human_channel', 'n/a')}")
    lines.append(f"- Enabled: {', '.join(ch.get('enabled', [])) if ch.get('enabled') else 'n/a'}")
    lines.append(f"- Disabled: {', '.join(ch.get('disabled', [])) if ch.get('disabled') else 'n/a'}")
    lines.append("")

    lines.append("## Reminders")
    rem = reminders_cfg.get("reminders", {})
    lines.append(f"- Auto follow-up mode: {rem.get('auto_followup_mode', 'n/a')}")
    lines.append(f"- Follow-up interval minutes: {rem.get('followup_interval_minutes', 'n/a')}")
    lines.append(f"- Max auto follow-ups: {rem.get('max_auto_followups', 'n/a')}")
    lines.append(f"- Pending: {reminder_counts['pending']}")
    lines.append(f"- Awaiting reply: {reminder_counts['awaiting_reply']}")
    lines.append(f"- Done: {reminder_counts['done']}")
    lines.append("")

    lines.append("## Telemetry")
    lines.append(f"- Model usage report present: {'yes' if model_report_present else 'no'}")
    if model_report_present:
        lines.append(f"- Report path: {model_report_path}")
    lines.append("")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
