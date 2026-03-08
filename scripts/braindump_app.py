#!/usr/bin/env python3
"""Braindump micro-app runtime.

Purpose:
- capture short categorized thoughts fast
- review them later by cadence/category
- promote selected items into task/calendar/project surfaces
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / ".memory" / "braindump.db"
DEFAULT_SCHEMA = ROOT / "contracts" / "braindump" / "sqlite_schema.sql"
DEFAULT_SNAPSHOT = ROOT / "data" / "braindump-snapshot.json"
DEFAULT_WORKSPACE = ROOT / "data" / "dashboard-workspace.json"
DEFAULT_CALENDAR_CANDIDATES = ROOT / "data" / "calendar-candidates.json"

REVIEW_DELTA_DAYS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "seasonal": 90,
    "manual_only": None,
}

DEFAULT_CATEGORY_BUCKETS = {
    "research_topic": "weekly",
    "tool_to_test": "weekly",
    "gift_idea_wife": "weekly",
    "kid_idea": "weekly",
    "purchase_candidate": "monthly",
    "project_idea": "weekly",
    "content_idea": "weekly",
    "personal_note": "weekly",
    "someday_maybe": "monthly",
}

CATEGORY_ALIASES = {
    "gift": "gift_idea_wife",
    "gifts": "gift_idea_wife",
    "wife": "gift_idea_wife",
    "wife_gift": "gift_idea_wife",
    "kid": "kid_idea",
    "kids": "kid_idea",
    "daughter": "kid_idea",
    "tool": "tool_to_test",
    "tools": "tool_to_test",
    "research": "research_topic",
    "buy": "purchase_candidate",
    "purchase": "purchase_candidate",
    "project": "project_idea",
    "projects": "project_idea",
    "content": "content_idea",
    "note": "personal_note",
    "notes": "personal_note",
    "someday": "someday_maybe",
}

CAPTURE_COMMAND_ALIASES = {"bd", "brain", "braindump", "dump", "idea"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def resolve_path(override: str | None, default: Path) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return default


def ensure_db(conn: sqlite3.Connection, schema_path: Path) -> None:
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    seed_category_defaults(conn)
    conn.commit()


def seed_category_defaults(conn: sqlite3.Connection) -> None:
    for category, bucket in DEFAULT_CATEGORY_BUCKETS.items():
        conn.execute(
            """
            INSERT INTO braindump_category_defaults(category, review_bucket, default_tags_json, auto_archive_days, notes)
            VALUES (?, ?, '[]', NULL, '')
            ON CONFLICT(category) DO UPDATE SET review_bucket = excluded.review_bucket
            """,
            (category, bucket),
        )


def review_bucket_for(conn: sqlite3.Connection, category: str, override: str | None) -> str:
    if override:
        return override
    row = conn.execute(
        "SELECT review_bucket FROM braindump_category_defaults WHERE category = ?",
        (category,),
    ).fetchone()
    if row and str(row[0]).strip():
        return str(row[0]).strip()
    return "weekly"


def next_review_at(bucket: str, captured_at: str) -> str | None:
    days = REVIEW_DELTA_DAYS.get(bucket)
    if days is None:
        return None
    base = parse_iso(captured_at) or datetime.now(timezone.utc)
    return (base + timedelta(days=days)).isoformat(timespec="seconds")


def build_item_id(category: str) -> str:
    return f"bd-{category}-{uuid.uuid4().hex[:8]}"


def normalize_tags(value: str | None) -> list[str]:
    if not value:
        return []
    out: list[str] = []
    for part in value.split(","):
        clean = part.strip()
        if clean and clean not in out:
            out.append(clean)
    return out


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", lowered)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_")


def canonicalize_category(value: str, *, allow_custom: bool = True) -> str:
    raw = value.strip().lower().rstrip(":")
    if not raw:
        raise ValueError("category is required")

    if raw in DEFAULT_CATEGORY_BUCKETS:
        return raw
    if raw in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[raw]

    normalized = slugify(raw)
    if not normalized:
        raise ValueError("category is required")

    if normalized in DEFAULT_CATEGORY_BUCKETS:
        return normalized
    if normalized in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[normalized]
    if allow_custom:
        return normalized
    raise ValueError(f"unknown category: {value}")


def normalize_review_bucket(value: str | None) -> str | None:
    if value is None:
        return None
    clean = value.strip().lower()
    if not clean:
        return None
    if clean not in REVIEW_DELTA_DAYS:
        raise ValueError(f"invalid review bucket: {value}")
    return clean


def ensure_category_default(conn: sqlite3.Connection, category: str, review_bucket: str) -> None:
    conn.execute(
        """
        INSERT INTO braindump_category_defaults(category, review_bucket, default_tags_json, auto_archive_days, notes)
        VALUES (?, ?, '[]', NULL, '')
        ON CONFLICT(category) DO NOTHING
        """,
        (category, review_bucket),
    )


def parse_capture_text(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if not text:
        raise ValueError("capture text is required")

    parts = text.split()
    command = parts[0].lstrip("/").lower()
    if command not in CAPTURE_COMMAND_ALIASES:
        raise ValueError("capture text must start with bd, braindump, dump, brain, or idea")

    parts = parts[1:]
    if len(parts) < 2:
        raise ValueError("capture text must include category and item text")

    category = canonicalize_category(parts[0])
    review_bucket: str | None = None
    tags: list[str] = []
    text_parts: list[str] = []

    for token in parts[1:]:
        if token.startswith("#"):
            tag = slugify(token[1:])
            if tag and tag not in tags:
                tags.append(tag)
            continue
        if token.startswith("@"):
            bucket = token[1:].strip().lower()
            if bucket in REVIEW_DELTA_DAYS:
                review_bucket = bucket
                continue
        text_parts.append(token)

    short_text = " ".join(text_parts).strip()
    if not short_text:
        raise ValueError("capture text must include item text after the category")

    return {
        "category": category,
        "text": short_text,
        "tags": tags,
        "review_bucket": review_bucket,
    }


def load_workspace(path: Path) -> dict[str, Any]:
    raw = read_json(path)
    if not isinstance(raw, dict):
        now = now_iso()
        return {
            "projects": [
                {
                    "id": "proj-openclaw-v2",
                    "name": "OpenClaw V2 Rebuild",
                    "status": "active",
                    "description": "Core rebuild and modular control-plane rollout.",
                    "owner": "pavel",
                    "target_date": None,
                    "progress_pct": 0,
                    "created_at": now,
                    "updated_at": now,
                }
            ],
            "tasks": [],
            "runs": [],
            "approvals": [],
        }
    raw.setdefault("projects", [])
    raw.setdefault("tasks", [])
    raw.setdefault("runs", [])
    raw.setdefault("approvals", [])
    return raw


def ensure_braindump_project(workspace: dict[str, Any]) -> str:
    now = now_iso()
    projects = workspace.setdefault("projects", [])
    for item in projects:
        row = item if isinstance(item, dict) else {}
        if str(row.get("id") or "") == "proj-braindump-review":
            return "proj-braindump-review"
    projects.append(
        {
            "id": "proj-braindump-review",
            "name": "Braindump Review",
            "status": "active",
            "description": "Task promotions created from braindump review.",
            "owner": "pavel",
            "target_date": None,
            "progress_pct": 0,
            "created_at": now,
            "updated_at": now,
        }
    )
    return "proj-braindump-review"


def load_calendar_candidates(path: Path) -> dict[str, Any]:
    raw = read_json(path)
    if not isinstance(raw, dict):
        return {"items": []}
    if not isinstance(raw.get("items"), list):
        raw["items"] = []
    return raw


def create_item(
    conn: sqlite3.Connection,
    *,
    category: str,
    text: str,
    tags: list[str] | None = None,
    review_bucket: str | None = None,
    notes: str | None = None,
    source: str = "agent_channel",
) -> dict[str, Any]:
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("braindump text is required")

    canonical_category = canonicalize_category(category)
    clean_review_bucket = normalize_review_bucket(review_bucket)
    bucket = review_bucket_for(conn, canonical_category, clean_review_bucket)
    ensure_category_default(conn, canonical_category, bucket)

    captured = now_iso()
    item_id = build_item_id(canonical_category)
    scheduled_for = next_review_at(bucket, captured)
    clean_tags = [tag for tag in (tags or []) if tag]

    conn.execute(
        """
        INSERT INTO braindump_items(
            id, short_text, category, tags_json, status, review_bucket, source,
            captured_at, updated_at, last_reviewed_at, next_review_at,
            promoted_to_type, promoted_to_id, archived_at, notes
        ) VALUES (?, ?, ?, ?, 'inbox', ?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, ?)
        """,
        (
            item_id,
            clean_text,
            canonical_category,
            json.dumps(clean_tags),
            bucket,
            source,
            captured,
            captured,
            scheduled_for,
            notes or "",
        ),
    )
    conn.commit()
    return fetch_item(conn, item_id)


def capture_item_from_text(
    conn: sqlite3.Connection,
    raw_text: str,
    *,
    source: str = "agent_channel",
    notes: str | None = None,
) -> dict[str, Any]:
    parsed = parse_capture_text(raw_text)
    return create_item(
        conn,
        category=str(parsed["category"]),
        text=str(parsed["text"]),
        tags=list(parsed.get("tags", [])),
        review_bucket=parsed.get("review_bucket"),
        notes=notes,
        source=source,
    )


def fetch_item(conn: sqlite3.Connection, item_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT id, short_text, category, tags_json, status, review_bucket, source,
               captured_at, updated_at, last_reviewed_at, next_review_at,
               promoted_to_type, promoted_to_id, archived_at, notes
          FROM braindump_items
         WHERE id = ?
        """,
        (item_id,),
    ).fetchone()
    if not row:
        raise SystemExit(f"Braindump item not found: {item_id}")
    return {
        "id": str(row[0]),
        "short_text": str(row[1]),
        "category": str(row[2]),
        "tags": json.loads(str(row[3] or "[]")),
        "status": str(row[4]),
        "review_bucket": str(row[5]),
        "source": str(row[6]),
        "captured_at": row[7],
        "updated_at": row[8],
        "last_reviewed_at": row[9],
        "next_review_at": row[10],
        "promoted_to_type": row[11],
        "promoted_to_id": row[12],
        "archived_at": row[13],
        "notes": str(row[14] or ""),
    }


def list_items(
    conn: sqlite3.Connection,
    *,
    status: str | None,
    category: str | None,
    review_bucket: str | None,
    due_only: bool,
    limit: int,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if review_bucket:
        clauses.append("review_bucket = ?")
        params.append(review_bucket)
    if due_only:
        clauses.append("next_review_at IS NOT NULL AND next_review_at <= ?")
        params.append(now_iso())

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT id, short_text, category, tags_json, status, review_bucket, source,
               captured_at, updated_at, last_reviewed_at, next_review_at,
               promoted_to_type, promoted_to_id, archived_at, notes
          FROM braindump_items
          {where}
         ORDER BY COALESCE(next_review_at, captured_at) ASC, captured_at ASC
         LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    out = []
    for row in rows:
        out.append(
            {
                "id": str(row[0]),
                "short_text": str(row[1]),
                "category": str(row[2]),
                "tags": json.loads(str(row[3] or "[]")),
                "status": str(row[4]),
                "review_bucket": str(row[5]),
                "source": str(row[6]),
                "captured_at": row[7],
                "updated_at": row[8],
                "last_reviewed_at": row[9],
                "next_review_at": row[10],
                "promoted_to_type": row[11],
                "promoted_to_id": row[12],
                "archived_at": row[13],
                "notes": str(row[14] or ""),
            }
        )
    return out


def write_snapshot(conn: sqlite3.Connection, snapshot_path: Path, db_path: Path, *, limit: int = 20) -> dict[str, Any]:
    counts_by_status = {
        str(row[0]): int(row[1])
        for row in conn.execute("SELECT status, COUNT(*) FROM braindump_items GROUP BY status")
    }
    counts_by_bucket = {
        str(row[0]): int(row[1])
        for row in conn.execute("SELECT review_bucket, COUNT(*) FROM braindump_items GROUP BY review_bucket")
    }
    counts_by_category = {
        str(row[0]): int(row[1])
        for row in conn.execute("SELECT category, COUNT(*) FROM braindump_items GROUP BY category")
    }
    due_items = list_items(
        conn,
        status=None,
        category=None,
        review_bucket=None,
        due_only=True,
        limit=limit,
    )
    due_count_row = conn.execute(
        "SELECT COUNT(*) FROM braindump_items WHERE next_review_at IS NOT NULL AND next_review_at <= ?",
        (now_iso(),),
    ).fetchone()
    recent_rows = conn.execute(
        """
        SELECT id, short_text, category, tags_json, status, review_bucket, source,
               captured_at, updated_at, last_reviewed_at, next_review_at,
               promoted_to_type, promoted_to_id, archived_at, notes
          FROM braindump_items
         ORDER BY updated_at DESC, captured_at DESC
         LIMIT ?
        """,
        (limit,),
    ).fetchall()
    recent_items = []
    for row in recent_rows:
        recent_items.append(
            {
                "id": str(row[0]),
                "short_text": str(row[1]),
                "category": str(row[2]),
                "tags": json.loads(str(row[3] or "[]")),
                "status": str(row[4]),
                "review_bucket": str(row[5]),
                "source": str(row[6]),
                "captured_at": row[7],
                "updated_at": row[8],
                "last_reviewed_at": row[9],
                "next_review_at": row[10],
                "promoted_to_type": row[11],
                "promoted_to_id": row[12],
                "archived_at": row[13],
                "notes": str(row[14] or ""),
            }
        )
    payload = {
        "generated_at": now_iso(),
        "db_path": str(db_path),
        "snapshot_path": str(snapshot_path),
        "counts_by_status": counts_by_status,
        "counts_by_bucket": counts_by_bucket,
        "counts_by_category": counts_by_category,
        "due_count": int((due_count_row or [0])[0] or 0),
        "due_items": due_items,
        "recent_items": recent_items,
    }
    write_json(snapshot_path, payload)
    return payload


def park_item(
    conn: sqlite3.Connection,
    item_id: str,
    *,
    review_bucket: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    item = fetch_item(conn, item_id)
    if item["status"] in {"archived", "promoted"}:
        raise ValueError(f"Cannot park item in status={item['status']}: {item_id}")

    reviewed_at = now_iso()
    bucket = normalize_review_bucket(review_bucket) or item["review_bucket"]
    scheduled_for = next_review_at(bucket, reviewed_at)
    conn.execute(
        """
        UPDATE braindump_items
           SET status = 'parked',
               review_bucket = ?,
               last_reviewed_at = ?,
               next_review_at = ?,
               updated_at = ?
         WHERE id = ?
        """,
        (bucket, reviewed_at, scheduled_for, reviewed_at, item_id),
    )
    conn.execute(
        """
        INSERT INTO braindump_reviews(item_id, reviewed_at, action, note, next_review_at)
        VALUES (?, ?, 'park', ?, ?)
        """,
        (item_id, reviewed_at, note or "", scheduled_for),
    )
    conn.commit()
    return fetch_item(conn, item_id)


def promote_item(
    conn: sqlite3.Connection,
    item_id: str,
    *,
    target: str,
    workspace_path: Path,
    calendar_path: Path,
    note: str | None = None,
) -> tuple[dict[str, Any], str]:
    item = fetch_item(conn, item_id)
    if target == "task":
        promoted_to_id = promote_to_task(item, workspace_path)
    elif target == "calendar":
        promoted_to_id = promote_to_calendar(item, calendar_path)
    elif target == "project":
        promoted_to_id = promote_to_project(item, workspace_path)
    else:
        raise ValueError(f"unsupported promote target: {target}")

    reviewed_at = now_iso()
    conn.execute(
        """
        UPDATE braindump_items
           SET status = 'promoted',
               promoted_to_type = ?,
               promoted_to_id = ?,
               last_reviewed_at = ?,
               next_review_at = NULL,
               updated_at = ?
         WHERE id = ?
        """,
        (target, promoted_to_id, reviewed_at, reviewed_at, item_id),
    )
    conn.execute(
        """
        INSERT INTO braindump_reviews(item_id, reviewed_at, action, note, next_review_at)
        VALUES (?, ?, ?, ?, NULL)
        """,
        (item_id, reviewed_at, f"promote:{target}", note or ""),
    )
    conn.commit()
    return fetch_item(conn, item_id), promoted_to_id


def archive_item(conn: sqlite3.Connection, item_id: str, *, note: str | None = None) -> dict[str, Any]:
    fetch_item(conn, item_id)
    ts = now_iso()
    conn.execute(
        """
        UPDATE braindump_items
           SET status = 'archived', archived_at = ?, last_reviewed_at = ?, next_review_at = NULL, updated_at = ?
         WHERE id = ?
        """,
        (ts, ts, ts, item_id),
    )
    conn.execute(
        """
        INSERT INTO braindump_reviews(item_id, reviewed_at, action, note, next_review_at)
        VALUES (?, ?, 'archive', ?, NULL)
        """,
        (item_id, ts, note or ""),
    )
    conn.commit()
    return fetch_item(conn, item_id)


def cmd_add(args: argparse.Namespace) -> int:
    db_path = resolve_path(args.db, DEFAULT_DB)
    schema_path = resolve_path(args.schema, DEFAULT_SCHEMA)
    snapshot_path = resolve_path(args.snapshot_file, DEFAULT_SNAPSHOT)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    ensure_db(conn, schema_path)

    item = create_item(
        conn,
        category=args.category,
        text=" ".join(args.text).strip() if isinstance(args.text, list) else str(args.text).strip(),
        tags=normalize_tags(args.tags),
        review_bucket=args.review_bucket,
        notes=args.notes,
        source=args.source,
    )
    snapshot = write_snapshot(conn, snapshot_path, db_path)
    conn.close()

    payload = {"ok": True, "item": item, "snapshot": snapshot}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Added braindump item {item_id} [{args.category}] {text}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    db_path = resolve_path(args.db, DEFAULT_DB)
    schema_path = resolve_path(args.schema, DEFAULT_SCHEMA)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    ensure_db(conn, schema_path)
    items = list_items(
        conn,
        status=args.status,
        category=canonicalize_category(args.category) if args.category else None,
        review_bucket=args.review_bucket,
        due_only=args.due_only,
        limit=args.limit,
    )
    conn.close()
    payload = {"ok": True, "count": len(items), "items": items}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Braindump items: {len(items)}")
        for item in items:
            print(f"- {item['id']} | {item['category']} | {item['status']} | {item['short_text']}")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    args.due_only = True
    args.status = args.status or None
    return cmd_list(args)


def cmd_capture(args: argparse.Namespace) -> int:
    db_path = resolve_path(args.db, DEFAULT_DB)
    schema_path = resolve_path(args.schema, DEFAULT_SCHEMA)
    snapshot_path = resolve_path(args.snapshot_file, DEFAULT_SNAPSHOT)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    ensure_db(conn, schema_path)
    item = capture_item_from_text(
        conn,
        " ".join(args.text).strip() if isinstance(args.text, list) else str(args.text).strip(),
        source=args.source,
        notes=args.notes,
    )
    snapshot = write_snapshot(conn, snapshot_path, db_path)
    conn.close()

    payload = {"ok": True, "item": item, "snapshot": snapshot}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Captured braindump item {item['id']} [{item['category']}] {item['short_text']}")
    return 0


def cmd_park(args: argparse.Namespace) -> int:
    db_path = resolve_path(args.db, DEFAULT_DB)
    schema_path = resolve_path(args.schema, DEFAULT_SCHEMA)
    snapshot_path = resolve_path(args.snapshot_file, DEFAULT_SNAPSHOT)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    ensure_db(conn, schema_path)
    item = park_item(conn, args.id, review_bucket=args.review_bucket, note=args.note)
    snapshot = write_snapshot(conn, snapshot_path, db_path)
    conn.close()

    payload = {"ok": True, "item": item, "snapshot": snapshot}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Parked {args.id} until {item['next_review_at'] or 'manual review'}")
    return 0


def promote_to_task(item: dict[str, Any], workspace_path: Path) -> str:
    workspace = load_workspace(workspace_path)
    project_id = ensure_braindump_project(workspace)
    task_id = f"task-braindump-{item['id']}"
    now = now_iso()
    task = {
        "id": task_id,
        "title": f"Braindump: {item['short_text']}",
        "status": "todo",
        "project_id": project_id,
        "assignees": ["pavel"],
        "priority": "medium",
        "due_at": item.get("next_review_at"),
        "notes": item.get("notes") or item.get("short_text"),
        "source": "braindump",
        "progress_pct": 0,
        "requires_approval": False,
        "side_effects": [],
        "created_at": now,
        "updated_at": now,
        "source_braindump_id": item["id"],
        "category": item.get("category"),
    }
    tasks = workspace.setdefault("tasks", [])
    replaced = False
    for idx, existing in enumerate(tasks):
        row = existing if isinstance(existing, dict) else {}
        if str(row.get("id") or "") == task_id:
            task["status"] = str(row.get("status") or "todo")
            task["progress_pct"] = int(row.get("progress_pct") or 0)
            task["created_at"] = str(row.get("created_at") or now)
            tasks[idx] = task
            replaced = True
            break
    if not replaced:
        tasks.append(task)
    write_json(workspace_path, workspace)
    return task_id


def promote_to_calendar(item: dict[str, Any], calendar_path: Path) -> str:
    data = load_calendar_candidates(calendar_path)
    candidate_id = f"cal-braindump-{item['id']}"
    now = now_iso()
    payload = {
        "id": candidate_id,
        "status": "proposed",
        "title": item["short_text"],
        "source": "braindump",
        "message_id": None,
        "thread_id": None,
        "from_email": None,
        "subject": item["short_text"],
        "excerpt": item.get("notes") or item["short_text"],
        "reason": f"Promoted from braindump category {item['category']}",
        "intent_tags": item.get("tags", []),
        "context_ts": item.get("next_review_at") or item.get("captured_at"),
        "created_at": now,
        "updated_at": now,
        "source_braindump_id": item["id"],
    }
    items = data.setdefault("items", [])
    replaced = False
    for idx, existing in enumerate(items):
        row = existing if isinstance(existing, dict) else {}
        if str(row.get("id") or "") == candidate_id:
            payload["status"] = str(row.get("status") or "proposed")
            payload["created_at"] = str(row.get("created_at") or now)
            items[idx] = payload
            replaced = True
            break
    if not replaced:
        items.append(payload)
    write_json(calendar_path, data)
    return candidate_id


def promote_to_project(item: dict[str, Any], workspace_path: Path) -> str:
    workspace = load_workspace(workspace_path)
    now = now_iso()
    project_id = f"proj-braindump-{item['id']}"
    project = {
        "id": project_id,
        "name": item["short_text"][:80],
        "status": "planned",
        "description": item.get("notes") or item["short_text"],
        "owner": "pavel",
        "target_date": None,
        "progress_pct": 0,
        "created_at": now,
        "updated_at": now,
        "source": "braindump",
        "source_braindump_id": item["id"],
    }
    projects = workspace.setdefault("projects", [])
    replaced = False
    for idx, existing in enumerate(projects):
        row = existing if isinstance(existing, dict) else {}
        if str(row.get("id") or "") == project_id:
            project["status"] = str(row.get("status") or "planned")
            project["created_at"] = str(row.get("created_at") or now)
            projects[idx] = project
            replaced = True
            break
    if not replaced:
        projects.append(project)
    write_json(workspace_path, workspace)
    return project_id


def cmd_promote(args: argparse.Namespace) -> int:
    db_path = resolve_path(args.db, DEFAULT_DB)
    schema_path = resolve_path(args.schema, DEFAULT_SCHEMA)
    snapshot_path = resolve_path(args.snapshot_file, DEFAULT_SNAPSHOT)
    workspace_path = resolve_path(args.workspace_file, DEFAULT_WORKSPACE)
    calendar_path = resolve_path(args.calendar_candidates_file, DEFAULT_CALENDAR_CANDIDATES)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    ensure_db(conn, schema_path)
    item, promoted_to_id = promote_item(
        conn,
        args.id,
        target=args.to,
        workspace_path=workspace_path,
        calendar_path=calendar_path,
        note=args.note,
    )
    snapshot = write_snapshot(conn, snapshot_path, db_path)
    conn.close()

    payload = {"ok": True, "item": item, "promoted_to_id": promoted_to_id, "snapshot": snapshot}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Promoted {args.id} -> {args.to}:{promoted_to_id}")
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    db_path = resolve_path(args.db, DEFAULT_DB)
    schema_path = resolve_path(args.schema, DEFAULT_SCHEMA)
    snapshot_path = resolve_path(args.snapshot_file, DEFAULT_SNAPSHOT)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    ensure_db(conn, schema_path)
    item = archive_item(conn, args.id, note=args.note)
    snapshot = write_snapshot(conn, snapshot_path, db_path)
    conn.close()

    payload = {"ok": True, "item": item, "snapshot": snapshot}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Archived {args.id}")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    db_path = resolve_path(args.db, DEFAULT_DB)
    schema_path = resolve_path(args.schema, DEFAULT_SCHEMA)
    snapshot_path = resolve_path(args.snapshot_file, DEFAULT_SNAPSHOT)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    ensure_db(conn, schema_path)
    payload = write_snapshot(conn, snapshot_path, db_path, limit=args.limit)
    conn.close()
    out = {"ok": True, "snapshot": payload}
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Braindump snapshot written: {snapshot_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Braindump micro-app runtime")
    parser.add_argument("--db", help="override braindump sqlite db path")
    parser.add_argument("--schema", help="override braindump schema path")
    parser.add_argument("--snapshot-file", help="override dashboard snapshot json path")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="add a braindump item")
    add.add_argument("category")
    add.add_argument("text", nargs="+")
    add.add_argument("--tags")
    add.add_argument("--review-bucket", choices=sorted(REVIEW_DELTA_DAYS.keys()))
    add.add_argument("--notes")
    add.add_argument("--source", default="agent_channel")
    add.add_argument("--json", action="store_true")
    add.set_defaults(func=cmd_add)

    dump = sub.add_parser("dump", help="alias for add")
    dump.add_argument("category")
    dump.add_argument("text", nargs="+")
    dump.add_argument("--tags")
    dump.add_argument("--review-bucket", choices=sorted(REVIEW_DELTA_DAYS.keys()))
    dump.add_argument("--notes")
    dump.add_argument("--source", default="agent_channel")
    dump.add_argument("--json", action="store_true")
    dump.set_defaults(func=cmd_add)

    capture = sub.add_parser("capture", help="parse chat-style braindump capture text")
    capture.add_argument("text", nargs="+")
    capture.add_argument("--source", default="agent_channel")
    capture.add_argument("--notes")
    capture.add_argument("--json", action="store_true")
    capture.set_defaults(func=cmd_capture)

    show = sub.add_parser("list", help="list braindump items")
    show.add_argument("--status")
    show.add_argument("--category")
    show.add_argument("--review-bucket")
    show.add_argument("--due-only", action="store_true")
    show.add_argument("--limit", type=int, default=30)
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=cmd_list)

    review = sub.add_parser("review", help="list due braindump items")
    review.add_argument("--status")
    review.add_argument("--category")
    review.add_argument("--review-bucket")
    review.add_argument("--limit", type=int, default=30)
    review.add_argument("--json", action="store_true")
    review.set_defaults(func=cmd_review)

    park = sub.add_parser("park", help="keep a braindump item and reschedule review")
    park.add_argument("--id", required=True)
    park.add_argument("--review-bucket", choices=sorted(REVIEW_DELTA_DAYS.keys()))
    park.add_argument("--note")
    park.add_argument("--json", action="store_true")
    park.set_defaults(func=cmd_park)

    promote = sub.add_parser("promote", help="promote a braindump item")
    promote.add_argument("--id", required=True)
    promote.add_argument("--to", choices=["task", "calendar", "project"], required=True)
    promote.add_argument("--workspace-file")
    promote.add_argument("--calendar-candidates-file")
    promote.add_argument("--note")
    promote.add_argument("--json", action="store_true")
    promote.set_defaults(func=cmd_promote)

    archive = sub.add_parser("archive", help="archive a braindump item")
    archive.add_argument("--id", required=True)
    archive.add_argument("--note")
    archive.add_argument("--json", action="store_true")
    archive.set_defaults(func=cmd_archive)

    snapshot = sub.add_parser("snapshot", help="write dashboard snapshot json")
    snapshot.add_argument("--limit", type=int, default=20)
    snapshot.add_argument("--json", action="store_true")
    snapshot.set_defaults(func=cmd_snapshot)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
