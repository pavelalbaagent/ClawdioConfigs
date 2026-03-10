#!/usr/bin/env python3
"""Shared helpers for the bounded ops_guard + knowledge_librarian governance loop."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import model_route_decider


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LATEST_STATUS = ROOT / "data" / "continuous-improvement-status.json"
DEFAULT_HISTORY_DIR = ROOT / "data" / "continuous-improvement-history"
DEFAULT_SHARED_DIRECTIVES = ROOT / "memory" / "SHARED_DIRECTIVES.md"
DEFAULT_SHARED_FINDINGS = ROOT / "memory" / "SHARED_FINDINGS.md"
DEFAULT_CONSOLIDATION_STATUS = ROOT / "data" / "knowledge-librarian-status.json"

DEFAULT_PROMOTION_THRESHOLD = 2
DEFAULT_MAX_RECENT_FINDINGS = 10
DEFAULT_MAX_CLEANUP_CANDIDATES = 10
DEFAULT_REVIEW_RETENTION_DAYS = 21
DEFAULT_TEMP_RETENTION_DAYS = 3
DEFAULT_HISTORY_RETENTION_DAYS = 45

TEMP_FILE_SUFFIXES = (".tmp", ".bak", ".old", ".orig", ".rej")
TEMP_FILE_PREFIXES = ("tmp-", "temp-")

STATIC_DIRECTIVES = [
    {
        "key": "repo_source_of_truth",
        "scope": "all_agents",
        "text": "Treat the repo as the source of truth; do not treat chat history as durable memory.",
        "source": "policy",
    },
    {
        "key": "fixed_governance_roles",
        "scope": "all_agents",
        "text": "Keep ops_guard as detector/reviewer and knowledge_librarian as consolidator; do not create a new visible agent for this loop.",
        "source": "policy",
    },
    {
        "key": "no_silent_structural_rewrites",
        "scope": "all_agents",
        "text": "Do not silently rewrite agent structure, provider order, integrations, or other structural policy without explicit approval.",
        "source": "policy",
    },
]

BOUND_RULE_LABELS = {
    "do_not_auto_change_credentials": "Do not auto-change credentials.",
    "do_not_auto_change_provider_order_without_approval": "Do not auto-change provider order without approval.",
    "do_not_auto_enable_new_integrations": "Do not auto-enable integrations.",
    "do_not_auto_create_new_agent_roles_without_approval": "Do not auto-create new agent roles.",
    "all_structural_changes_require_human_approval": "All structural changes require explicit approval.",
    "changing_credentials": "Changing credentials requires approval.",
    "changing_provider_priorities": "Changing provider priorities requires approval.",
    "enabling_integrations": "Enabling integrations requires approval.",
    "creating_persistent_agents": "Creating persistent agents requires approval.",
}


@dataclass
class Totals:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    errors: int = 0
    fallbacks: int = 0
    estimated_cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def ensure_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def dedupe_string_list(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def iso_now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso_safe(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def days_old(path: Path, *, now: datetime) -> int:
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return max(0, int((now - modified).total_seconds() // 86400))


def relative_label(path: Path, *, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def resolve_repo_path(root: Path, raw_path: str | None, default: Path) -> Path:
    text = str(raw_path or "").strip()
    if not text:
        return default
    path = Path(text).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def governance_paths(root: Path) -> dict[str, Any]:
    agents_path = root / "config" / "agents.yaml"
    session_policy_path = root / "config" / "session_policy.yaml"
    agents_data = ensure_dict(model_route_decider.load_yaml(agents_path)) if agents_path.exists() else {}
    session_data = ensure_dict(model_route_decider.load_yaml(session_policy_path)) if session_policy_path.exists() else {}

    improvement = ensure_dict(agents_data.get("continuous_improvement"))
    outputs = ensure_dict(improvement.get("outputs"))
    consolidation = ensure_dict(improvement.get("consolidation"))
    policy = ensure_dict(session_data.get("continuous_improvement_policy"))

    return {
        "latest_status_file": resolve_repo_path(
            root,
            str(outputs.get("latest_status_file") or ""),
            root / DEFAULT_LATEST_STATUS.relative_to(ROOT),
        ),
        "review_dir": resolve_repo_path(
            root,
            str(outputs.get("review_dir") or ""),
            root / "docs" / "reviews",
        ),
        "review_history_dir": resolve_repo_path(
            root,
            str(outputs.get("review_history_dir") or ""),
            root / DEFAULT_HISTORY_DIR.relative_to(ROOT),
        ),
        "shared_directives_file": resolve_repo_path(
            root,
            str(outputs.get("shared_directives_file") or ""),
            root / DEFAULT_SHARED_DIRECTIVES.relative_to(ROOT),
        ),
        "shared_findings_file": resolve_repo_path(
            root,
            str(outputs.get("shared_findings_file") or ""),
            root / DEFAULT_SHARED_FINDINGS.relative_to(ROOT),
        ),
        "consolidation_status_file": resolve_repo_path(
            root,
            str(outputs.get("consolidation_status_file") or ""),
            root / DEFAULT_CONSOLIDATION_STATUS.relative_to(ROOT),
        ),
        "promotion_threshold": int(consolidation.get("promotion_threshold_reviews") or DEFAULT_PROMOTION_THRESHOLD),
        "max_recent_findings": int(consolidation.get("max_recent_findings") or DEFAULT_MAX_RECENT_FINDINGS),
        "max_cleanup_candidates": int(consolidation.get("max_cleanup_candidates") or DEFAULT_MAX_CLEANUP_CANDIDATES),
        "review_retention_days": int(consolidation.get("review_retention_days") or DEFAULT_REVIEW_RETENTION_DAYS),
        "temp_retention_days": int(consolidation.get("temp_retention_days") or DEFAULT_TEMP_RETENTION_DAYS),
        "history_retention_days": int(consolidation.get("history_retention_days") or DEFAULT_HISTORY_RETENTION_DAYS),
        "owner_role": str(consolidation.get("owner_role") or "knowledge_librarian").strip() or "knowledge_librarian",
        "bounded_rules": dedupe_string_list(
            ensure_string_list(improvement.get("bounded_rules")) + ensure_string_list(policy.get("blocked_auto_actions"))
        ),
    }


def accumulate(totals: Totals, entry: dict[str, Any]) -> None:
    totals.calls += 1
    totals.prompt_tokens += int(entry.get("prompt_tokens", 0) or 0)
    totals.completion_tokens += int(entry.get("completion_tokens", 0) or 0)
    totals.latency_ms += int(entry.get("latency_ms", 0) or 0)
    totals.estimated_cost_usd += float(entry.get("estimated_cost_usd", 0.0) or 0.0)
    status = str(entry.get("status", "")).lower()
    if status == "error":
        totals.errors += 1
    if status == "fallback":
        totals.fallbacks += 1


def asdict_totals(totals: Totals) -> dict[str, Any]:
    return {
        "calls": totals.calls,
        "prompt_tokens": totals.prompt_tokens,
        "completion_tokens": totals.completion_tokens,
        "total_tokens": totals.total_tokens,
        "latency_ms": totals.latency_ms,
        "errors": totals.errors,
        "fallbacks": totals.fallbacks,
        "estimated_cost_usd": round(totals.estimated_cost_usd, 6),
    }


def aggregate_model_usage(rows: list[dict[str, Any]], *, lookback_hours: int, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    since = current - timedelta(hours=max(1, int(lookback_hours)))
    filtered = []
    for row in rows:
        ts = parse_iso_safe(row.get("ts"))
        if ts is None:
            continue
        if ts >= since:
            filtered.append(row)

    overall = Totals()
    by_agent: dict[str, Totals] = defaultdict(Totals)
    by_lane: dict[str, Totals] = defaultdict(Totals)
    by_model: dict[str, Totals] = defaultdict(Totals)
    by_lane_model: dict[tuple[str, str], Totals] = defaultdict(Totals)

    for row in filtered:
        agent_id = str(row.get("agent_id") or "unknown").strip() or "unknown"
        lane = str(row.get("lane") or "unknown").strip() or "unknown"
        model = str(row.get("model") or "unknown").strip() or "unknown"
        accumulate(overall, row)
        accumulate(by_agent[agent_id], row)
        accumulate(by_lane[lane], row)
        accumulate(by_model[model], row)
        accumulate(by_lane_model[(lane, model)], row)

    def _sort_rows(rows: list[dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
        return sorted(rows, key=lambda item: (-int(item.get("total_tokens", 0) or 0), str(item.get(key_name) or "")))

    agent_rows = _sort_rows(
        [{"agent_id": key, **asdict_totals(value)} for key, value in by_agent.items()],
        "agent_id",
    )
    lane_rows = _sort_rows(
        [{"lane": key, **asdict_totals(value)} for key, value in by_lane.items()],
        "lane",
    )
    model_rows = _sort_rows(
        [{"model": key, **asdict_totals(value)} for key, value in by_model.items()],
        "model",
    )
    lane_model_rows = sorted(
        [
            {"lane": lane, "model": model, **asdict_totals(value)}
            for (lane, model), value in by_lane_model.items()
        ],
        key=lambda item: (-int(item.get("total_tokens", 0) or 0), str(item.get("lane") or ""), str(item.get("model") or "")),
    )

    return {
        "window_hours": max(1, int(lookback_hours)),
        "window_start": since.isoformat(),
        "window_end": current.isoformat(),
        "overall": asdict_totals(overall),
        "by_agent": agent_rows,
        "by_lane": lane_rows,
        "by_model": model_rows,
        "by_lane_model": lane_model_rows[:20],
    }


def detect_cleanup_candidates(
    *,
    root: Path,
    snapshot: dict[str, Any],
    now: datetime | None = None,
    review_retention_days: int = DEFAULT_REVIEW_RETENTION_DAYS,
    history_retention_days: int = DEFAULT_HISTORY_RETENTION_DAYS,
    temp_retention_days: int = DEFAULT_TEMP_RETENTION_DAYS,
    history_dir: Path | None = None,
    review_dir: Path | None = None,
) -> list[dict[str, Any]]:
    current = now or datetime.now(timezone.utc)
    workspace = ensure_dict(snapshot.get("workspace"))
    projects = [ensure_dict(row) for row in workspace.get("projects", []) if isinstance(row, dict)]
    tasks = [ensure_dict(row) for row in workspace.get("tasks", []) if isinstance(row, dict)]
    review_path = review_dir or (root / "docs" / "reviews")
    review_history_path = history_dir or (root / "data" / "continuous-improvement-history")

    candidates: list[dict[str, Any]] = []
    open_tasks_by_project: dict[str, int] = defaultdict(int)
    for task in tasks:
        if str(task.get("status") or "").strip().lower() == "done":
            continue
        project_id = str(task.get("project_id") or "").strip()
        if project_id:
            open_tasks_by_project[project_id] += 1

    for project in projects:
        status = str(project.get("status") or "").strip().lower()
        if status not in {"paused", "done", "archived"}:
            continue
        project_id = str(project.get("id") or "").strip()
        updated_at = parse_iso_safe(project.get("updated_at")) or parse_iso_safe(project.get("created_at"))
        if updated_at is None:
            continue
        age_days = max(0, int((current - updated_at).total_seconds() // 86400))
        threshold = 7 if status == "paused" else 3
        if age_days < threshold or open_tasks_by_project.get(project_id, 0) > 0:
            continue
        candidates.append(
            {
                "id": f"project-space::{project_id}",
                "kind": "project_space",
                "path": None,
                "target": str(project.get("space_key") or project.get("name") or project_id),
                "summary": f"{project.get('name') or project_id} is {status} with no open tasks.",
                "reason": f"Project has been {status} for {age_days} days without open dashboard tasks.",
                "age_days": age_days,
                "suggested_action": "archive_or_prune_project_space",
            }
        )

    if review_path.exists():
        for path in sorted(review_path.glob("*.md")):
            if path.name == "README.md":
                continue
            age_days = days_old(path, now=current)
            if age_days < max(review_retention_days, 1):
                continue
            candidates.append(
                {
                    "id": f"review-report::{relative_label(path, root=root)}",
                    "kind": "review_report",
                    "path": str(path),
                    "target": relative_label(path, root=root),
                    "summary": f"{relative_label(path, root=root)} is an old generated review report.",
                    "reason": f"Generated review markdown is {age_days} days old and can likely be pruned or archived.",
                    "age_days": age_days,
                    "suggested_action": "prune_generated_review_markdown",
                }
            )

    if review_history_path.exists():
        for path in sorted(review_history_path.glob("*.json")):
            age_days = days_old(path, now=current)
            if age_days < max(history_retention_days, 1):
                continue
            candidates.append(
                {
                    "id": f"review-history::{relative_label(path, root=root)}",
                    "kind": "review_history",
                    "path": str(path),
                    "target": relative_label(path, root=root),
                    "summary": f"{relative_label(path, root=root)} is an old structured review artifact.",
                    "reason": f"Structured review history is {age_days} days old and may be safe to prune after consolidation.",
                    "age_days": age_days,
                    "suggested_action": "prune_old_review_history",
                }
            )

    seen_paths: set[str] = set()
    scan_dirs = [root, root / "data", root / "telemetry", root / "tmp"]
    for base in scan_dirs:
        if not base.exists():
            continue
        iterator = base.glob("*") if base == root else base.rglob("*")
        for path in iterator:
            if not path.is_file():
                continue
            clean_path = str(path.resolve())
            if clean_path in seen_paths:
                continue
            seen_paths.add(clean_path)

            name = path.name.lower()
            if not (
                any(name.endswith(suffix) for suffix in TEMP_FILE_SUFFIXES)
                or any(name.startswith(prefix) for prefix in TEMP_FILE_PREFIXES)
            ):
                continue
            age_days = days_old(path, now=current)
            if age_days < max(temp_retention_days, 1):
                continue
            candidates.append(
                {
                    "id": f"temp-artifact::{relative_label(path, root=root)}",
                    "kind": "temp_artifact",
                    "path": str(path),
                    "target": relative_label(path, root=root),
                    "summary": f"{relative_label(path, root=root)} looks like a stale temp artifact.",
                    "reason": f"Filename matches temp-artifact patterns and the file is {age_days} days old.",
                    "age_days": age_days,
                    "suggested_action": "review_and_delete_temp_artifact",
                }
            )

    return sorted(
        candidates,
        key=lambda row: (-int(row.get("age_days", 0) or 0), str(row.get("kind") or ""), str(row.get("target") or "")),
    )


def load_review_history(history_dir: Path) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    if not history_dir.exists():
        return reviews
    for path in sorted(history_dir.glob("*.json")):
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        payload = dict(payload)
        payload.setdefault("history_path", str(path))
        reviews.append(payload)
    reviews.sort(
        key=lambda row: (
            parse_iso_safe(row.get("generated_at")) or datetime.fromtimestamp(0, tz=timezone.utc),
            str(row.get("mode") or ""),
        ),
        reverse=True,
    )
    return reviews


def directive_buckets(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for review in reviews:
        generated_at = str(review.get("generated_at") or "").strip() or None
        mode = str(review.get("mode") or "").strip() or None
        for raw in review.get("directive_candidates", []):
            candidate = ensure_dict(raw)
            key = str(candidate.get("key") or "").strip()
            if not key:
                continue
            bucket = buckets.setdefault(
                key,
                {
                    "key": key,
                    "text": str(candidate.get("text") or "").strip(),
                    "scope": str(candidate.get("scope") or "all_agents").strip() or "all_agents",
                    "safe_to_promote": bool(candidate.get("safe_to_promote") is True),
                    "requires_approval": bool(candidate.get("requires_approval") is True),
                    "count": 0,
                    "modes": [],
                    "last_seen_at": None,
                    "source_finding_ids": [],
                },
            )
            if str(candidate.get("text") or "").strip():
                bucket["text"] = str(candidate.get("text") or "").strip()
            bucket["count"] += 1
            if mode and mode not in bucket["modes"]:
                bucket["modes"].append(mode)
            if generated_at and (bucket["last_seen_at"] is None or generated_at > bucket["last_seen_at"]):
                bucket["last_seen_at"] = generated_at
            for finding_id in ensure_string_list(candidate.get("source_finding_ids")):
                if finding_id not in bucket["source_finding_ids"]:
                    bucket["source_finding_ids"].append(finding_id)
    return sorted(
        buckets.values(),
        key=lambda row: (-int(row.get("count", 0) or 0), str(row.get("key") or "")),
    )


def build_shared_directives_markdown(
    *,
    generated_at: str,
    promoted_directives: list[dict[str, Any]],
    bounded_rules: list[str],
    promotion_threshold: int,
) -> str:
    lines = [
        "# Shared Directives",
        "",
        "Maintained by knowledge_librarian from bounded ops_guard reviews.",
        "",
        f"Last updated: {generated_at}",
        "",
        "## Active Directives",
    ]
    for row in STATIC_DIRECTIVES:
        lines.append(f"- [{row['scope']}] {row['text']}")
    for row in promoted_directives:
        lines.append(
            f"- [{row.get('scope') or 'all_agents'}] {row.get('text') or row.get('key')} (stable: {row.get('count', 0)} review hits; last seen {row.get('last_seen_at') or '-'})"
        )
    if not promoted_directives:
        lines.append("- No review-derived directives have met the promotion threshold yet.")

    lines.extend(["", "## Approval Boundaries"])
    boundary_lines = [BOUND_RULE_LABELS.get(rule, rule.replace("_", " ")) for rule in bounded_rules]
    for item in boundary_lines or ["No approval boundaries configured."]:
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## Promotion Notes",
            f"- Auto-promotion requires {promotion_threshold} repeated safe directive candidates across review history.",
            "- Candidates that require approval stay in the shared findings file until a human approves the change.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_shared_findings_markdown(
    *,
    generated_at: str,
    source_review: dict[str, Any] | None,
    recent_findings: list[dict[str, Any]],
    pending_candidates: list[dict[str, Any]],
    cleanup_candidates: list[dict[str, Any]],
    promoted_directives: list[dict[str, Any]],
) -> str:
    lines = [
        "# Shared Findings",
        "",
        "Maintained by knowledge_librarian from recent ops_guard review outputs.",
        "",
        f"Last updated: {generated_at}",
        "",
        "## Recent Findings",
    ]
    if recent_findings:
        for row in recent_findings:
            lines.append(
                f"- [{row.get('mode') or '-'} | {row.get('generated_at') or '-'}] {row.get('summary') or row.get('id')}"
            )
    else:
        lines.append("- No recent findings have been consolidated yet.")

    lines.extend(["", "## Directive Candidates"])
    if pending_candidates:
        for row in pending_candidates:
            status = "approval-required" if row.get("requires_approval") else f"repeat {row.get('count', 0)}"
            lines.append(f"- [{status}] {row.get('text') or row.get('key')}")
    else:
        lines.append("- No pending directive candidates.")

    lines.extend(["", "## Cleanup Candidates"])
    if cleanup_candidates:
        for row in cleanup_candidates:
            target = row.get("target") or row.get("path") or row.get("id")
            lines.append(f"- [{row.get('kind') or 'artifact'} | age={row.get('age_days', 0)}d] {target}: {row.get('reason') or row.get('summary')}")
    else:
        lines.append("- No cleanup candidates.")

    lines.extend(["", "## Consolidation Summary"])
    source_label = str(ensure_dict(source_review).get("report_path") or ensure_dict(source_review).get("history_path") or "").strip() or "-"
    lines.append(f"- source_review={source_label}")
    lines.append(f"- promoted_directives={len(promoted_directives)}")
    lines.append(f"- pending_directive_candidates={len(pending_candidates)}")
    return "\n".join(lines) + "\n"


def consolidate_governance(root: Path) -> dict[str, Any]:
    paths = governance_paths(root)
    latest_status_path = Path(paths["latest_status_file"])
    history_dir = Path(paths["review_history_dir"])
    directives_path = Path(paths["shared_directives_file"])
    findings_path = Path(paths["shared_findings_file"])
    consolidation_status_path = Path(paths["consolidation_status_file"])
    promotion_threshold = max(int(paths["promotion_threshold"]), 1)
    max_recent_findings = max(int(paths["max_recent_findings"]), 1)
    max_cleanup_candidates = max(int(paths["max_cleanup_candidates"]), 1)

    latest_review = read_json(latest_status_path) if latest_status_path.exists() else None
    reviews = load_review_history(history_dir)
    if isinstance(latest_review, dict) and str(latest_review.get("history_path") or "").strip():
        latest_history_path = str(latest_review.get("history_path") or "").strip()
        if latest_history_path and all(str(row.get("history_path") or "") != latest_history_path for row in reviews):
            reviews.insert(0, latest_review)

    buckets = directive_buckets(reviews)
    promoted_directives = [
        row
        for row in buckets
        if row.get("safe_to_promote") is True and row.get("requires_approval") is not True and int(row.get("count", 0) or 0) >= promotion_threshold
    ]
    pending_candidates = [
        row
        for row in buckets
        if row not in promoted_directives
    ]

    recent_findings: list[dict[str, Any]] = []
    seen_finding_keys: set[str] = set()
    for review in reviews[:4]:
        mode = str(review.get("mode") or "").strip() or None
        generated_at = str(review.get("generated_at") or "").strip() or None
        for raw in review.get("findings", []):
            finding = ensure_dict(raw)
            key = f"{finding.get('id') or ''}:{finding.get('summary') or ''}"
            if key in seen_finding_keys:
                continue
            seen_finding_keys.add(key)
            recent_findings.append(
                {
                    "id": str(finding.get("id") or "").strip() or None,
                    "summary": str(finding.get("summary") or "").strip() or str(finding.get("id") or "").strip(),
                    "mode": mode,
                    "generated_at": generated_at,
                }
            )
            if len(recent_findings) >= max_recent_findings:
                break
        if len(recent_findings) >= max_recent_findings:
            break

    latest_cleanup = [
        ensure_dict(row)
        for row in ensure_dict(latest_review).get("cleanup_candidates", [])
        if isinstance(row, dict)
    ][:max_cleanup_candidates]

    generated_at = iso_now_utc()
    directives_markdown = build_shared_directives_markdown(
        generated_at=generated_at,
        promoted_directives=promoted_directives,
        bounded_rules=ensure_string_list(paths["bounded_rules"]),
        promotion_threshold=promotion_threshold,
    )
    findings_markdown = build_shared_findings_markdown(
        generated_at=generated_at,
        source_review=latest_review if isinstance(latest_review, dict) else None,
        recent_findings=recent_findings,
        pending_candidates=pending_candidates,
        cleanup_candidates=latest_cleanup,
        promoted_directives=promoted_directives,
    )

    directives_path.parent.mkdir(parents=True, exist_ok=True)
    findings_path.parent.mkdir(parents=True, exist_ok=True)
    previous_directives = directives_path.read_text(encoding="utf-8") if directives_path.exists() else None
    previous_findings = findings_path.read_text(encoding="utf-8") if findings_path.exists() else None
    directives_path.write_text(directives_markdown, encoding="utf-8")
    findings_path.write_text(findings_markdown, encoding="utf-8")

    payload = {
        "generated_at": generated_at,
        "owner_role": str(paths["owner_role"]),
        "ok": True,
        "source_review_path": str(ensure_dict(latest_review).get("report_path") or "") if isinstance(latest_review, dict) else None,
        "source_review_generated_at": str(ensure_dict(latest_review).get("generated_at") or "") if isinstance(latest_review, dict) else None,
        "shared_directives_path": str(directives_path),
        "shared_findings_path": str(findings_path),
        "promotion_threshold_reviews": promotion_threshold,
        "review_history_considered": len(reviews),
        "promoted_directives": promoted_directives,
        "pending_directive_candidates": pending_candidates[:max_recent_findings],
        "recent_findings": recent_findings,
        "cleanup_candidates": latest_cleanup,
        "changed_files": [
            str(path)
            for path, before, after in (
                (directives_path, previous_directives, directives_markdown),
                (findings_path, previous_findings, findings_markdown),
            )
            if before != after
        ],
    }
    write_json(consolidation_status_path, payload)
    return payload
