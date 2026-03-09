#!/usr/bin/env python3
"""Generate bounded ops_guard review outputs from current runtime state."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "dashboard") not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT / "dashboard"))

from backend import DashboardBackend, ensure_dict, ensure_string_list  # type: ignore  # noqa: E402

DEFAULT_STATUS = ROOT / "data" / "continuous-improvement-status.json"
DEFAULT_REVIEW_DIR = ROOT / "docs" / "reviews"


def iso_now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_findings(snapshot: dict[str, Any], *, mode: str) -> tuple[list[str], list[str], list[str], list[str]]:
    findings: list[str] = []
    recommendations: list[str] = []
    approval_required: list[str] = []
    archive_candidates: list[str] = []

    provider = ensure_dict(snapshot.get("provider_health"))
    provider_summary = ensure_dict(provider.get("summary"))
    local_ready = int(provider_summary.get("local_ready_count", 0) or 0)
    live_ok = int(provider_summary.get("live_ok_count", 0) or 0)
    if local_ready > 0 and live_ok < local_ready:
        findings.append(f"Provider health degraded: only {live_ok} of {local_ready} locally ready providers have a passing live probe.")
        recommendations.append("Re-run provider smoke checks and inspect failing provider credentials or transports.")

    reminders = ensure_dict(snapshot.get("reminders"))
    reminder_counts = ensure_dict(reminders.get("counts"))
    pending = int(reminder_counts.get("pending", 0) or 0)
    awaiting = int(reminder_counts.get("awaiting_reply", 0) or 0)
    if pending >= 8 or awaiting >= 5:
        findings.append(f"Reminder backlog is growing: pending={pending}, awaiting_reply={awaiting}.")
        recommendations.append("Review overdue reminders and confirm whether assistant scheduling rules need tighter cleanup.")

    workspace = ensure_dict(snapshot.get("workspace"))
    task_counts = ensure_dict(workspace.get("task_counts"))
    blocked_tasks = int(task_counts.get("blocked", 0) or 0)
    if blocked_tasks > 0:
        findings.append(f"Blocked task count is non-zero ({blocked_tasks}).")
        recommendations.append("Inspect blocked tasks and convert recurring blockers into explicit projects or ops fixes.")

    runtime = ensure_dict(snapshot.get("agent_runtime"))
    activity = ensure_dict(runtime.get("activity"))
    route_counts = ensure_dict(activity.get("counts_by_agent"))
    assistant_routes = int(route_counts.get("assistant", 0) or 0)
    specialist_routes = sum(int(value or 0) for key, value in route_counts.items() if key in {"researcher", "builder", "fitness_coach", "ops_guard"})
    if assistant_routes > 0 and specialist_routes == 0:
        findings.append("All recent routed work is still collapsing into the assistant lane.")
        recommendations.append("Push more work through specialist prefixes or surface clearer specialist entry points in the dashboard.")

    agent_chats = ensure_dict(snapshot.get("agent_chats"))
    chat_rows = [ensure_dict(row) for row in agent_chats.get("agents", []) if isinstance(row, dict)]
    stale_chat_agents = [str(row.get("agent_id") or "") for row in chat_rows if not row.get("available")]
    if stale_chat_agents:
        findings.append(f"Some conversational agents do not have active chat state yet: {', '.join(stale_chat_agents)}.")

    memory_sync = ensure_dict(snapshot.get("memory_sync_status"))
    if memory_sync.get("available") is not True:
        findings.append("Hybrid memory is enabled but no memory sync status snapshot exists yet.")
        recommendations.append("Run the memory sync runner once and enable the timer before relying on recall-heavy workflows.")
    elif memory_sync.get("ok") is not True:
        findings.append("Latest memory sync failed or did not finish cleanly.")
        recommendations.append("Check memory sync stderr/stdout and correct the indexing inputs before enabling more memory-dependent behavior.")

    project_counts = ensure_dict(workspace.get("project_counts"))
    if int(project_counts.get("paused", 0) or 0) > 0:
        archive_candidates.append("Review paused projects and archive any that no longer need dedicated spaces.")

    if mode == "weekly_architecture_review":
        approval_required.append("Review provider order and decide whether builder/researcher should get dedicated heavier model defaults.")
        approval_required.append("Review whether fitness_coach should remain structured-only or become a conversational specialist.")

    return findings, recommendations, approval_required, archive_candidates


def render_markdown(
    *,
    generated_at: str,
    mode: str,
    findings: list[str],
    recommendations: list[str],
    approval_required: list[str],
    archive_candidates: list[str],
) -> str:
    lines = [
        f"# Ops Guard Review - {mode}",
        "",
        f"Generated at: {generated_at}",
        "",
        "## Observations",
    ]
    lines.extend(f"- {item}" for item in (findings or ["No critical findings."]))
    lines.extend(["", "## Recommended Changes"])
    lines.extend(f"- {item}" for item in (recommendations or ["No immediate changes recommended."]))
    lines.extend(["", "## Approval Required Changes"])
    lines.extend(f"- {item}" for item in (approval_required or ["None."]))
    lines.extend(["", "## Archive Candidates"])
    lines.extend(f"- {item}" for item in (archive_candidates or ["None."]))
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate ops_guard review outputs")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--mode", choices=["daily_ops_review", "weekly_architecture_review"], default="daily_ops_review")
    parser.add_argument("--status-file", default=str(DEFAULT_STATUS))
    parser.add_argument("--review-dir", default=str(DEFAULT_REVIEW_DIR))
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    backend = DashboardBackend(root=root)
    snapshot = backend.build_state()

    findings, recommendations, approval_required, archive_candidates = classify_findings(snapshot, mode=args.mode)
    generated_at = iso_now_utc()
    report_dir = Path(args.review_dir).expanduser().resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{args.mode}.md"
    report_path.write_text(
        render_markdown(
            generated_at=generated_at,
            mode=args.mode,
            findings=findings,
            recommendations=recommendations,
            approval_required=approval_required,
            archive_candidates=archive_candidates,
        ),
        encoding="utf-8",
    )

    payload = {
        "generated_at": generated_at,
        "mode": args.mode,
        "report_path": str(report_path),
        "findings_count": len(findings),
        "recommended_changes": recommendations,
        "approval_required_changes": approval_required,
        "archive_candidates": archive_candidates,
    }
    status_path = Path(args.status_file).expanduser().resolve()
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Ops Guard review written: {report_path}")
        print(f"- Findings: {len(findings)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
