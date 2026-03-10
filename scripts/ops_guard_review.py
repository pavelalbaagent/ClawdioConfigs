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

from backend import DashboardBackend, ensure_dict  # type: ignore  # noqa: E402
from governance_loop import (  # noqa: E402
    aggregate_model_usage,
    detect_cleanup_candidates,
    governance_paths,
    iso_now_utc,
    read_ndjson,
    write_json,
)


def usage_lookback_hours(mode: str) -> int:
    return 24 if mode == "daily_ops_review" else 24 * 7


def unique_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        clean = ensure_dict(candidate)
        key = str(clean.get("key") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(clean)
    return rows


def make_finding(
    *,
    finding_id: str,
    category: str,
    severity: str,
    summary: str,
    recommendation: str | None = None,
    evidence: dict[str, Any] | None = None,
    directive_candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "id": finding_id,
        "category": category,
        "severity": severity,
        "summary": summary,
        "evidence": ensure_dict(evidence),
    }
    if recommendation:
        row["recommendation"] = recommendation
    if directive_candidate:
        candidate = dict(directive_candidate)
        source_ids = set(candidate.get("source_finding_ids", []))
        source_ids.add(finding_id)
        candidate["source_finding_ids"] = sorted(source_ids)
        row["directive_candidate"] = candidate
    return row


def classify_findings(snapshot: dict[str, Any], *, mode: str, usage: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    recommendations: list[str] = []
    approval_required: list[str] = []
    directive_candidates: list[dict[str, Any]] = []

    provider = ensure_dict(snapshot.get("provider_health"))
    provider_summary = ensure_dict(provider.get("summary"))
    local_ready = int(provider_summary.get("local_ready_count", 0) or 0)
    live_ok = int(provider_summary.get("live_ok_count", 0) or 0)
    if local_ready > 0 and live_ok < local_ready:
        finding = make_finding(
            finding_id="provider_health_degraded",
            category="provider_health",
            severity="warning",
            summary=f"Provider health degraded: only {live_ok} of {local_ready} locally ready providers have a passing live probe.",
            recommendation="Re-run provider smoke checks and inspect failing provider credentials or transports before changing routing.",
            evidence={"local_ready_count": local_ready, "live_ok_count": live_ok},
            directive_candidate={
                "key": "provider_smoke_before_routing_change",
                "scope": "all_agents",
                "text": "Re-run provider smoke checks before changing routing defaults when live probes degrade.",
                "safe_to_promote": True,
                "requires_approval": False,
            },
        )
        findings.append(finding)
        recommendations.append(str(finding["recommendation"]))
        directive_candidates.append(ensure_dict(finding.get("directive_candidate")))

    reminders = ensure_dict(snapshot.get("reminders"))
    reminder_counts = ensure_dict(reminders.get("counts"))
    pending = int(reminder_counts.get("pending", 0) or 0)
    awaiting = int(reminder_counts.get("awaiting_reply", 0) or 0)
    if pending >= 8 or awaiting >= 5:
        finding = make_finding(
            finding_id="reminder_backlog_growing",
            category="reminders",
            severity="warning",
            summary=f"Reminder backlog is growing: pending={pending}, awaiting_reply={awaiting}.",
            recommendation="Review overdue reminders and cleanup follow-up noise before adjusting reminder behavior.",
            evidence={"pending": pending, "awaiting_reply": awaiting},
            directive_candidate={
                "key": "clear_reminder_backlog_before_rule_tuning",
                "scope": "assistant_ops",
                "text": "Clear reminder backlog and follow-up noise before changing reminder rules or widening automation.",
                "safe_to_promote": True,
                "requires_approval": False,
            },
        )
        findings.append(finding)
        recommendations.append(str(finding["recommendation"]))
        directive_candidates.append(ensure_dict(finding.get("directive_candidate")))

    workspace = ensure_dict(snapshot.get("workspace"))
    task_counts = ensure_dict(workspace.get("task_counts"))
    blocked_tasks = int(task_counts.get("blocked", 0) or 0)
    if blocked_tasks > 0:
        finding = make_finding(
            finding_id="blocked_tasks_present",
            category="workspace",
            severity="warning",
            summary=f"Blocked task count is non-zero ({blocked_tasks}).",
            recommendation="Inspect blocked tasks and convert repeated blockers into explicit projects or ops fixes.",
            evidence={"blocked_tasks": blocked_tasks},
            directive_candidate={
                "key": "turn_repeated_blockers_into_explicit_projects",
                "scope": "assistant_builder_ops",
                "text": "Turn repeated blockers into explicit projects or ops fixes instead of leaving them in a blocked queue.",
                "safe_to_promote": True,
                "requires_approval": False,
            },
        )
        findings.append(finding)
        recommendations.append(str(finding["recommendation"]))
        directive_candidates.append(ensure_dict(finding.get("directive_candidate")))

    runtime = ensure_dict(snapshot.get("agent_runtime"))
    activity = ensure_dict(runtime.get("activity"))
    route_counts = ensure_dict(activity.get("counts_by_agent"))
    assistant_routes = int(route_counts.get("assistant", 0) or 0)
    specialist_routes = sum(int(value or 0) for key, value in route_counts.items() if key in {"researcher", "builder", "fitness_coach", "ops_guard"})
    if assistant_routes > 0 and specialist_routes == 0:
        finding = make_finding(
            finding_id="specialist_routing_underused",
            category="routing",
            severity="info",
            summary="All recent routed work is still collapsing into the assistant lane.",
            recommendation="Push repeated research, implementation, fitness, or ops work through specialist surfaces when the workstream is stable.",
            evidence={"assistant_routes": assistant_routes, "specialist_routes": specialist_routes},
            directive_candidate={
                "key": "route_stable_specialist_work_to_specialists",
                "scope": "all_agents",
                "text": "Route stable research, coding, fitness, and ops work through the matching specialist surface instead of collapsing everything into assistant.",
                "safe_to_promote": True,
                "requires_approval": False,
            },
        )
        findings.append(finding)
        recommendations.append(str(finding["recommendation"]))
        directive_candidates.append(ensure_dict(finding.get("directive_candidate")))

    agent_chats = ensure_dict(snapshot.get("agent_chats"))
    chat_rows = [ensure_dict(row) for row in agent_chats.get("agents", []) if isinstance(row, dict)]
    stale_chat_agents = [str(row.get("agent_id") or "") for row in chat_rows if not row.get("available")]
    if stale_chat_agents:
        findings.append(
            make_finding(
                finding_id="missing_chat_state",
                category="agent_runtime",
                severity="info",
                summary=f"Some conversational agents do not have active chat state yet: {', '.join(stale_chat_agents)}.",
                evidence={"agents": stale_chat_agents},
            )
        )

    memory_sync = ensure_dict(snapshot.get("memory_sync_status"))
    if memory_sync.get("available") is not True:
        finding = make_finding(
            finding_id="memory_sync_missing",
            category="memory_sync",
            severity="warning",
            summary="Hybrid memory is enabled but no memory sync status snapshot exists yet.",
            recommendation="Run the memory sync runner and confirm the shared memory files are being indexed before relying on recall-heavy workflows.",
            directive_candidate={
                "key": "run_memory_sync_before_recall_heavy_work",
                "scope": "all_agents",
                "text": "Run memory sync and index shared governance memory before relying on recall-heavy workflows.",
                "safe_to_promote": True,
                "requires_approval": False,
            },
        )
        findings.append(finding)
        recommendations.append(str(finding["recommendation"]))
        directive_candidates.append(ensure_dict(finding.get("directive_candidate")))
    elif memory_sync.get("ok") is not True:
        finding = make_finding(
            finding_id="memory_sync_unhealthy",
            category="memory_sync",
            severity="warning",
            summary="Latest memory sync failed or did not finish cleanly.",
            recommendation="Check memory sync stderr/stdout and fix the indexing inputs before widening memory-dependent behavior.",
            directive_candidate={
                "key": "fix_memory_sync_before_expanding_memory_usage",
                "scope": "all_agents",
                "text": "Fix memory sync failures before expanding workflows that depend on shared memory recall.",
                "safe_to_promote": True,
                "requires_approval": False,
            },
        )
        findings.append(finding)
        recommendations.append(str(finding["recommendation"]))
        directive_candidates.append(ensure_dict(finding.get("directive_candidate")))

    heavy_lane = next((ensure_dict(row) for row in usage.get("by_lane", []) if str(row.get("lane") or "") == "L3_heavy"), {})
    heavy_calls = int(heavy_lane.get("calls", 0) or 0)
    heavy_tokens = int(heavy_lane.get("total_tokens", 0) or 0)
    total_tokens = int(ensure_dict(usage.get("overall")).get("total_tokens", 0) or 0)
    if heavy_calls >= 4 or (total_tokens > 0 and heavy_tokens * 100 >= total_tokens * 35):
        finding = make_finding(
            finding_id="heavy_lane_overuse",
            category="cost",
            severity="warning",
            summary=f"Heavy-lane usage looks elevated: calls={heavy_calls}, tokens={heavy_tokens}.",
            recommendation="Review whether L3-heavy work is routine rather than exceptional and tighten routing if the cost mix is drifting.",
            evidence={"heavy_calls": heavy_calls, "heavy_tokens": heavy_tokens, "total_tokens": total_tokens},
            directive_candidate={
                "key": "reserve_heavy_lane_for_hard_work",
                "scope": "all_agents",
                "text": "Reserve L3_heavy for genuinely hard work; investigate if heavy-lane use becomes routine.",
                "safe_to_promote": True,
                "requires_approval": False,
            },
        )
        findings.append(finding)
        recommendations.append(str(finding["recommendation"]))
        directive_candidates.append(ensure_dict(finding.get("directive_candidate")))

    if mode == "weekly_architecture_review":
        approval_required.append("Review provider order and decide whether builder/researcher should get dedicated heavier model defaults.")
        approval_required.append("Review whether ops_guard should remain a governed runtime only or gain a bounded conversational surface.")

    return findings, recommendations, approval_required, unique_candidates(directive_candidates)


def render_usage_table(title: str, headers: list[str], rows: list[dict[str, Any]], keys: list[str], *, limit: int = 8) -> list[str]:
    lines = [f"### {title}", "", f"| {' | '.join(headers)} |", f"| {' | '.join(['---'] * len(headers))} |"]
    for row in rows[:limit]:
        values = []
        for key in keys:
            value = row.get(key)
            if isinstance(value, float):
                values.append(f"{value:.4f}")
            else:
                values.append(str(value))
        lines.append(f"| {' | '.join(values)} |")
    if not rows:
        lines.append(f"| {' | '.join(['-' for _ in headers])} |")
    lines.append("")
    return lines


def render_markdown(
    *,
    generated_at: str,
    mode: str,
    findings: list[dict[str, Any]],
    recommendations: list[str],
    approval_required: list[str],
    cleanup_candidates: list[dict[str, Any]],
    directive_candidates: list[dict[str, Any]],
    usage: dict[str, Any],
) -> str:
    lines = [
        f"# Ops Guard Review - {mode}",
        "",
        f"Generated at: {generated_at}",
        f"Usage window: last {usage.get('window_hours', 0)}h",
        "",
        "## Observations",
    ]
    if findings:
        lines.extend(f"- [{row.get('severity') or 'info'}] {row.get('summary') or row.get('id')}" for row in findings)
    else:
        lines.append("- No critical findings.")

    lines.extend(["", "## Recommended Changes"])
    lines.extend(f"- {item}" for item in (recommendations or ["No immediate changes recommended."]))

    lines.extend(["", "## Approval Required Changes"])
    lines.extend(f"- {item}" for item in (approval_required or ["None."]))

    lines.extend(["", "## Cleanup Candidates"])
    if cleanup_candidates:
        for row in cleanup_candidates:
            target = row.get("target") or row.get("path") or row.get("id")
            lines.append(f"- [{row.get('kind') or 'artifact'} | age={row.get('age_days', 0)}d] {target}: {row.get('reason') or row.get('summary')}")
    else:
        lines.append("- None.")

    lines.extend(["", "## Directive Candidates"])
    if directive_candidates:
        for row in directive_candidates:
            status = "approval-required" if row.get("requires_approval") else "safe-to-repeat-promote"
            lines.append(f"- [{status}] {row.get('text') or row.get('key')}")
    else:
        lines.append("- None.")

    overall = ensure_dict(usage.get("overall"))
    lines.extend(
        [
            "",
            "## Token Usage Summary",
            "",
            f"- Calls: {overall.get('calls', 0)}",
            f"- Total tokens: {overall.get('total_tokens', 0)}",
            f"- Errors: {overall.get('errors', 0)}",
            f"- Fallbacks: {overall.get('fallbacks', 0)}",
            f"- Estimated cost (USD): {float(overall.get('estimated_cost_usd', 0.0) or 0.0):.4f}",
            "",
        ]
    )
    lines.extend(
        render_usage_table(
            "By Agent",
            ["Agent", "Calls", "Tokens", "Errors", "Fallbacks"],
            [ensure_dict(row) for row in usage.get("by_agent", []) if isinstance(row, dict)],
            ["agent_id", "calls", "total_tokens", "errors", "fallbacks"],
        )
    )
    lines.extend(
        render_usage_table(
            "By Lane",
            ["Lane", "Calls", "Tokens", "Errors", "Fallbacks"],
            [ensure_dict(row) for row in usage.get("by_lane", []) if isinstance(row, dict)],
            ["lane", "calls", "total_tokens", "errors", "fallbacks"],
        )
    )
    lines.extend(
        render_usage_table(
            "By Model",
            ["Model", "Calls", "Tokens", "Errors", "Fallbacks"],
            [ensure_dict(row) for row in usage.get("by_model", []) if isinstance(row, dict)],
            ["model", "calls", "total_tokens", "errors", "fallbacks"],
        )
    )
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate ops_guard review outputs")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--mode", choices=["daily_ops_review", "weekly_architecture_review"], default="daily_ops_review")
    parser.add_argument("--status-file")
    parser.add_argument("--review-dir")
    parser.add_argument("--history-dir")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    paths = governance_paths(root)
    status_path = Path(args.status_file).expanduser().resolve() if args.status_file else Path(paths["latest_status_file"])
    review_dir = Path(args.review_dir).expanduser().resolve() if args.review_dir else Path(paths["review_dir"])
    history_dir = Path(args.history_dir).expanduser().resolve() if args.history_dir else Path(paths["review_history_dir"])

    backend = DashboardBackend(root=root)
    snapshot = backend.build_state()
    telemetry_local = ensure_dict(ensure_dict(snapshot.get("telemetry")).get("local"))
    usage_rows = read_ndjson(Path(str(telemetry_local.get("source") or "")).expanduser()) if telemetry_local.get("source") else []
    usage = aggregate_model_usage(usage_rows, lookback_hours=usage_lookback_hours(args.mode))

    findings, recommendations, approval_required, directive_candidates = classify_findings(snapshot, mode=args.mode, usage=usage)
    cleanup_candidates = detect_cleanup_candidates(
        root=root,
        snapshot=snapshot,
        review_retention_days=int(paths["review_retention_days"]),
        history_retention_days=int(paths["history_retention_days"]),
        temp_retention_days=int(paths["temp_retention_days"]),
        history_dir=history_dir,
        review_dir=review_dir,
    )

    generated_at = iso_now_utc()
    review_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{args.mode}"
    report_path = review_dir / f"{stem}.md"
    history_path = history_dir / f"{stem}.json"

    report_path.write_text(
        render_markdown(
            generated_at=generated_at,
            mode=args.mode,
            findings=findings,
            recommendations=recommendations,
            approval_required=approval_required,
            cleanup_candidates=cleanup_candidates,
            directive_candidates=directive_candidates,
            usage=usage,
        ),
        encoding="utf-8",
    )

    payload = {
        "generated_at": generated_at,
        "mode": args.mode,
        "reviewer_role": "ops_guard",
        "report_path": str(report_path),
        "history_path": str(history_path),
        "findings_count": len(findings),
        "findings": findings,
        "recommended_changes": recommendations,
        "approval_required_changes": approval_required,
        "directive_candidates": directive_candidates,
        "cleanup_candidates": cleanup_candidates,
        "archive_candidates": [str(row.get("target") or row.get("path") or row.get("summary") or row.get("id")) for row in cleanup_candidates],
        "usage": usage,
    }

    write_json(history_path, payload)
    write_json(status_path, payload)

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Ops Guard review written: {report_path}")
        print(f"- Findings: {len(findings)}")
        print(f"- Cleanup candidates: {len(cleanup_candidates)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
