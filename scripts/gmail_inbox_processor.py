#!/usr/bin/env python3
"""Deterministic Gmail inbox processor with SQLite state.

Default behavior is dry-run. Use --apply to execute safe primary actions like
archive/trash. Use --create-placeholder-drafts only if you explicitly want
local deterministic reply drafts created in Gmail.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from env_file_utils import load_env_file
from google_workspace_common import (  # type: ignore
    GoogleApiClient,
    GoogleOAuthClient,
    ensure_dict,
    ensure_string_list,
    get_integration_config,
    load_yaml,
    resolve_repo_path,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "integrations.yaml"
DEFAULT_SCHEMA = ROOT / "contracts" / "gmail" / "sqlite_schema.sql"
DEFAULT_STATUS_PATH = ROOT / "data" / "gmail-inbox-last-run.json"
DEFAULT_WORKSPACE_PATH = ROOT / "data" / "dashboard-workspace.json"
DEFAULT_CALENDAR_CANDIDATES_PATH = ROOT / "data" / "calendar-candidates.json"
DEFAULT_FIXTURE_USER = "me"
PLAIN_TEXT_MIME = "text/plain"
HTML_MIME = "text/html"
LINK_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


LOW_VALUE_KEYWORDS = {
    "newsletter": ["newsletter", "digest", "roundup", "substack", "mailing list"],
    "marketing": ["sale", "deal", "discount", "offer", "promotion", "webinar", "free trial"],
    "receipt": ["receipt", "invoice", "order", "payment received", "payment confirmation", "purchase"],
    "automated_notification": ["notification", "alert", "automated", "no-reply", "noreply", "do not reply"],
}

HIGH_VALUE_KEYWORDS = {
    "human_request": ["can you", "could you", "please", "let me know", "need you", "?"],
    "deadline": ["deadline", "due", "expires", "expiring", "action required", "by tomorrow", "urgent"],
    "meeting_change": ["meeting", "calendar", "invite", "rescheduled", "reschedule", "zoom", "teams", "call moved"],
    "billing_issue": ["payment failed", "card declined", "invoice overdue", "billing issue", "past due", "subscription cancelled"],
    "verification_code": ["verification code", "security code", "one-time code", "otp", "2fa", "login code"],
}

AUTOMATED_LOCAL_PARTS = (
    "noreply",
    "no-reply",
    "do-not-reply",
    "notifications",
    "billing",
    "support",
    "mailer-daemon",
    "hello",
)


@dataclass
class AttachmentMeta:
    part_id: str | None
    filename: str
    mime_type: str
    attachment_id: str | None
    size_bytes: int


class GmailClient:
    def __init__(self, api: GoogleApiClient, user_email: str):
        self.api = api
        self.user_email = user_email or DEFAULT_FIXTURE_USER

    def list_inbox_message_ids(
        self,
        *,
        source_label: str,
        batch_limit: int,
        query_text: str | None = None,
    ) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(refs) < batch_limit:
            max_results = min(100, batch_limit - len(refs))
            payload = self.api.request_json(
                "GET",
                f"https://gmail.googleapis.com/gmail/v1/users/{self.user_email}/messages",
                query={
                    "labelIds": [source_label],
                    "maxResults": max_results,
                    "pageToken": page_token,
                    "q": query_text or None,
                },
            )
            refs.extend([ensure_dict(item) for item in payload.get("messages", []) if isinstance(item, dict)])
            page_token = str(payload.get("nextPageToken") or "").strip() or None
            if not page_token:
                break
        return refs[:batch_limit]

    def get_message(self, message_id: str) -> dict[str, Any]:
        return self.api.request_json(
            "GET",
            f"https://gmail.googleapis.com/gmail/v1/users/{self.user_email}/messages/{message_id}",
            query={"format": "full"},
        )

    def archive_message(self, message_id: str) -> dict[str, Any]:
        return self.api.request_json(
            "POST",
            f"https://gmail.googleapis.com/gmail/v1/users/{self.user_email}/messages/{message_id}/modify",
            payload={"removeLabelIds": ["INBOX"]},
        )

    def trash_message(self, message_id: str) -> dict[str, Any]:
        return self.api.request_json(
            "POST",
            f"https://gmail.googleapis.com/gmail/v1/users/{self.user_email}/messages/{message_id}/trash",
        )

    def create_placeholder_reply_draft(
        self,
        *,
        thread_id: str,
        to_email: str,
        subject: str,
        in_reply_to: str | None,
        references: str | None,
    ) -> dict[str, Any]:
        msg = EmailMessage()
        msg["To"] = to_email
        msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references
        msg.set_content(
            "Received. I have logged this message and will review it before sending a final reply."
        )
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        return self.api.request_json(
            "POST",
            f"https://gmail.googleapis.com/gmail/v1/users/{self.user_email}/drafts",
            payload={"message": {"threadId": thread_id, "raw": raw}},
        )


class FixtureGmailClient:
    def __init__(self, messages: list[dict[str, Any]]):
        self._messages = [ensure_dict(item) for item in messages]
        self.archived: list[str] = []
        self.trashed: list[str] = []
        self.drafts: list[dict[str, Any]] = []

    def list_inbox_message_ids(self, *, source_label: str, batch_limit: int, query_text: str | None = None) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for message in self._messages:
            label_ids = ensure_string_list(message.get("labelIds"))
            if source_label and source_label not in label_ids:
                continue
            if query_text:
                blob = json.dumps(message).lower()
                if query_text.lower() not in blob:
                    continue
            refs.append({"id": str(message.get("id") or ""), "threadId": str(message.get("threadId") or "")})
            if len(refs) >= batch_limit:
                break
        return refs

    def get_message(self, message_id: str) -> dict[str, Any]:
        for message in self._messages:
            if str(message.get("id") or "") == message_id:
                return message
        raise RuntimeError(f"fixture message not found: {message_id}")

    def archive_message(self, message_id: str) -> dict[str, Any]:
        self.archived.append(message_id)
        return {"id": message_id, "archived": True}

    def trash_message(self, message_id: str) -> dict[str, Any]:
        self.trashed.append(message_id)
        return {"id": message_id, "trashed": True}

    def create_placeholder_reply_draft(
        self,
        *,
        thread_id: str,
        to_email: str,
        subject: str,
        in_reply_to: str | None,
        references: str | None,
    ) -> dict[str, Any]:
        draft = {
            "threadId": thread_id,
            "to": to_email,
            "subject": subject,
            "inReplyTo": in_reply_to,
            "references": references,
        }
        self.drafts.append(draft)
        return {"id": f"draft-{len(self.drafts)}", **draft}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def env_get(name: str, env_file_values: dict[str, str]) -> str:
    return env_file_values.get(name, os.environ.get(name, "")).strip()


def resolve_integration(config_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    integration = get_integration_config(config_path, "gmail")
    if integration.get("enabled") is not True:
        raise RuntimeError("gmail integration is disabled in config")
    inbox_cfg = ensure_dict(integration.get("inbox_processing"))
    contract_path = resolve_repo_path(str(inbox_cfg.get("contract_file") or "contracts/gmail/inbox-processing-rules.yaml"))
    contract = ensure_dict(load_yaml(contract_path))
    return integration, inbox_cfg, contract


def resolve_state_db(inbox_cfg: dict[str, Any], override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    rel = str(inbox_cfg.get("state_db_path") or ".memory/inbox_processing.db").strip()
    path = Path(rel)
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def resolve_schema_path(override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_SCHEMA


def resolve_status_path(override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_STATUS_PATH


def resolve_workspace_path(override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_WORKSPACE_PATH


def resolve_calendar_candidates_path(override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_CALENDAR_CANDIDATES_PATH


def ensure_db(conn: sqlite3.Connection, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def parse_headers(headers: Any) -> dict[str, str]:
    output: dict[str, str] = {}
    if not isinstance(headers, list):
        return output
    for item in headers:
        row = ensure_dict(item)
        name = str(row.get("name") or "").strip().lower()
        value = str(row.get("value") or "").strip()
        if name and name not in output:
            output[name] = value
    return output


def decode_body_data(data: str | None) -> str:
    if not data:
        return ""
    padding = "=" * ((4 - len(data) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode((data + padding).encode("utf-8"))
    except Exception:
        return ""
    return raw.decode("utf-8", errors="replace")


def strip_html(text: str) -> str:
    clean = TAG_RE.sub(" ", text)
    clean = SPACE_RE.sub(" ", clean)
    return clean.strip()


def walk_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [payload]
    children = payload.get("parts")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                parts.extend(walk_parts(child))
    return parts


def collect_excerpt_and_attachments(payload: dict[str, Any], snippet: str) -> tuple[str, list[AttachmentMeta]]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[AttachmentMeta] = []

    for part in walk_parts(payload):
        mime_type = str(part.get("mimeType") or "").strip()
        body = ensure_dict(part.get("body"))
        filename = str(part.get("filename") or "").strip()
        body_data = decode_body_data(str(body.get("data") or "").strip() or None)
        attachment_id = str(body.get("attachmentId") or "").strip() or None
        size_bytes = int(body.get("size") or 0)

        if filename:
            attachments.append(
                AttachmentMeta(
                    part_id=str(part.get("partId") or "").strip() or None,
                    filename=filename,
                    mime_type=mime_type or "application/octet-stream",
                    attachment_id=attachment_id,
                    size_bytes=size_bytes,
                )
            )

        if mime_type == PLAIN_TEXT_MIME and body_data:
            text_parts.append(body_data)
        elif mime_type == HTML_MIME and body_data:
            html_parts.append(strip_html(body_data))

    excerpt = "\n".join(part for part in text_parts if part.strip()).strip()
    if not excerpt:
        excerpt = "\n".join(part for part in html_parts if part.strip()).strip()
    if not excerpt:
        excerpt = snippet.strip()
    return excerpt[:1200], attachments


def parse_message_timestamp(internal_date: str | int | None) -> str | None:
    if internal_date is None:
        return None
    try:
        millis = int(str(internal_date))
    except ValueError:
        return None
    dt = datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)
    return dt.isoformat(timespec="seconds")


def detect_sender_type(headers: dict[str, str], from_email: str, text_blob: str) -> str:
    local_part = from_email.split("@", 1)[0].lower()
    precedence = headers.get("precedence", "").lower()
    auto_submitted = headers.get("auto-submitted", "").lower()
    list_unsubscribe = headers.get("list-unsubscribe", "")
    blob = text_blob.lower()

    if list_unsubscribe or precedence in {"bulk", "list", "junk"} or auto_submitted in {"auto-generated", "auto-replied"}:
        return "automated"
    if any(fragment in local_part for fragment in AUTOMATED_LOCAL_PARTS):
        return "automated"
    if "unsubscribe" in blob:
        return "automated"
    return "human_or_unknown"


def detect_intent_tags(text_blob: str, headers: dict[str, str], sender_type: str) -> list[str]:
    blob = text_blob.lower()
    tags: list[str] = []

    for tag, keywords in LOW_VALUE_KEYWORDS.items():
        if any(keyword in blob for keyword in keywords):
            tags.append(tag)
    for tag, keywords in HIGH_VALUE_KEYWORDS.items():
        if any(keyword in blob for keyword in keywords):
            tags.append(tag)

    if headers.get("list-unsubscribe") and "newsletter" not in tags:
        tags.append("newsletter")
    if sender_type == "automated" and "automated_notification" not in tags:
        tags.append("automated_notification")

    ordered: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag not in seen:
            ordered.append(tag)
            seen.add(tag)
    return ordered


def confidence_for(tags: list[str], manual_review: bool) -> float:
    if manual_review and not tags:
        return 0.45
    if "verification_code" in tags or "billing_issue" in tags:
        return 0.95
    if any(tag in tags for tag in ("newsletter", "marketing", "receipt", "automated_notification")):
        return 0.92
    if tags:
        return 0.8
    return 0.55


def choose_actions(
    *,
    sender_type: str,
    intent_tags: list[str],
    from_email: str,
    excerpt: str,
    attachments: list[AttachmentMeta],
) -> dict[str, Any]:
    secondary_actions: list[str] = []
    reasons: list[str] = []
    has_links = bool(LINK_RE.search(excerpt))
    unknown_external = sender_type != "automated" and not from_email

    if any(tag in intent_tags for tag in ("meeting_change", "deadline")):
        secondary_actions.append("promote_calendar_candidate")
    if any(tag in intent_tags for tag in ("human_request", "deadline", "billing_issue")):
        secondary_actions.append("promote_task_candidate")
    if attachments and not any(tag in intent_tags for tag in ("newsletter", "marketing")):
        secondary_actions.append("save_attachment_to_drive")
    if "human_request" in intent_tags and sender_type != "automated":
        secondary_actions.append("draft_reply")

    manual_review = False
    primary_action = "keep_in_inbox"

    if "verification_code" in intent_tags:
        primary_action = "keep_in_inbox"
        manual_review = True
        reasons.append("time-sensitive verification code")
    elif unknown_external and (has_links or attachments):
        primary_action = "mark_for_manual_review"
        manual_review = True
        reasons.append("unknown sender with links or attachments")
    elif "billing_issue" in intent_tags:
        primary_action = "mark_for_manual_review"
        manual_review = True
        reasons.append("billing issues should not be auto-archived")
    elif "human_request" in intent_tags:
        primary_action = "mark_for_manual_review"
        manual_review = True
        reasons.append("human-origin request needs explicit review")
    elif any(tag in intent_tags for tag in ("meeting_change", "deadline")):
        primary_action = "keep_in_inbox"
        reasons.append("calendar or deadline candidate")
    elif any(tag in intent_tags for tag in ("newsletter", "marketing", "receipt", "automated_notification")):
        primary_action = "archive_message"
        reasons.append("low-value or automated mail")
    elif sender_type == "automated":
        primary_action = "archive_message"
        reasons.append("automated sender without high-value signals")
    else:
        primary_action = "mark_for_manual_review"
        manual_review = True
        reasons.append("uncertain message classification")

    if has_links and sender_type != "automated" and manual_review:
        reasons.append("contains links")
    if attachments and manual_review:
        reasons.append("contains attachments")

    dedup_secondary: list[str] = []
    seen_secondary: set[str] = set()
    for action in secondary_actions:
        if action not in seen_secondary:
            dedup_secondary.append(action)
            seen_secondary.add(action)

    return {
        "primary_action": primary_action,
        "secondary_actions": dedup_secondary,
        "manual_review_required": manual_review,
        "model_required": False,
        "confidence": confidence_for(intent_tags, manual_review),
        "reason": "; ".join(reasons) or "default policy",
        "has_links": has_links,
    }


def extract_message_record(message: dict[str, Any], keep_raw_headers: bool) -> dict[str, Any]:
    payload = ensure_dict(message.get("payload"))
    headers = parse_headers(payload.get("headers"))
    from_name, from_email = parseaddr(headers.get("from", ""))
    subject = headers.get("subject", "").strip()
    snippet = str(message.get("snippet") or "").strip()
    excerpt, attachments = collect_excerpt_and_attachments(payload, snippet)
    combined_blob = "\n".join(
        item
        for item in (
            subject,
            snippet,
            excerpt,
            headers.get("from", ""),
            headers.get("to", ""),
            headers.get("cc", ""),
        )
        if item
    )
    sender_type = detect_sender_type(headers, from_email, combined_blob)
    intent_tags = detect_intent_tags(combined_blob, headers, sender_type)
    action = choose_actions(
        sender_type=sender_type,
        intent_tags=intent_tags,
        from_email=from_email,
        excerpt=excerpt,
        attachments=attachments,
    )
    return {
        "message_id": str(message.get("id") or "").strip(),
        "thread_id": str(message.get("threadId") or "").strip(),
        "from_name": from_name,
        "from_email": from_email,
        "subject": subject,
        "snippet": snippet,
        "excerpt": excerpt,
        "label_ids": ensure_string_list(message.get("labelIds")),
        "sender_type": sender_type,
        "intent_tags": intent_tags,
        "has_links": action["has_links"],
        "has_attachments": bool(attachments),
        "attachment_count": len(attachments),
        "attachments": attachments,
        "raw_headers_json": json.dumps(headers, sort_keys=True) if keep_raw_headers else None,
        "message_ts": parse_message_timestamp(message.get("internalDate")),
        "action": action,
        "reply_headers": {
            "message_id_header": headers.get("message-id"),
            "references": headers.get("references"),
        },
    }


def start_run(conn: sqlite3.Connection, *, source_label: str, query_text: str, batch_limit: int, dry_run: bool) -> int:
    cursor = conn.execute(
        """
        INSERT INTO gmail_runs(started_at, source_label, query_text, batch_limit, dry_run)
        VALUES (?, ?, ?, ?, ?)
        """,
        (now_iso(), source_label, query_text, batch_limit, int(dry_run)),
    )
    conn.commit()
    return int(cursor.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, summary: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE gmail_runs
           SET finished_at = ?,
               fetched_count = ?,
               skipped_existing_count = ?,
               processed_count = ?,
               applied_count = ?,
               error_count = ?,
               summary_json = ?
         WHERE id = ?
        """,
        (
            now_iso(),
            int(summary.get("fetched_count", 0)),
            int(summary.get("skipped_existing_count", 0)),
            int(summary.get("processed_count", 0)),
            int(summary.get("applied_count", 0)),
            int(summary.get("error_count", 0)),
            json.dumps(summary, sort_keys=True),
            run_id,
        ),
    )
    conn.commit()


def existing_processed_ids(conn: sqlite3.Connection, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT message_id FROM gmail_messages WHERE message_id IN ({placeholders}) AND last_processed_at IS NOT NULL",
        ids,
    ).fetchall()
    return {str(row[0]) for row in rows}


def record_message(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    record: dict[str, Any],
    applied: bool,
    dry_run: bool,
    error_text: str | None,
) -> None:
    action = ensure_dict(record.get("action"))
    now = now_iso()
    conn.execute(
        """
        INSERT INTO gmail_messages(
            message_id, thread_id, from_name, from_email, subject, snippet, excerpt,
            label_ids_json, sender_type, intent_tags_json, has_links, has_attachments,
            attachment_count, raw_headers_json, message_ts, first_seen_at, last_seen_at,
            last_processed_at, last_action, last_action_applied, action_reason,
            manual_review_required, model_required
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(message_id) DO UPDATE SET
            thread_id=excluded.thread_id,
            from_name=excluded.from_name,
            from_email=excluded.from_email,
            subject=excluded.subject,
            snippet=excluded.snippet,
            excerpt=excluded.excerpt,
            label_ids_json=excluded.label_ids_json,
            sender_type=excluded.sender_type,
            intent_tags_json=excluded.intent_tags_json,
            has_links=excluded.has_links,
            has_attachments=excluded.has_attachments,
            attachment_count=excluded.attachment_count,
            raw_headers_json=excluded.raw_headers_json,
            message_ts=excluded.message_ts,
            last_seen_at=excluded.last_seen_at,
            last_processed_at=excluded.last_processed_at,
            last_action=excluded.last_action,
            last_action_applied=excluded.last_action_applied,
            action_reason=excluded.action_reason,
            manual_review_required=excluded.manual_review_required,
            model_required=excluded.model_required
        """,
        (
            record["message_id"],
            record["thread_id"],
            record["from_name"],
            record["from_email"],
            record["subject"],
            record["snippet"],
            record["excerpt"],
            json.dumps(record["label_ids"]),
            record["sender_type"],
            json.dumps(record["intent_tags"]),
            int(bool(record["has_links"])),
            int(bool(record["has_attachments"])),
            int(record["attachment_count"]),
            record["raw_headers_json"],
            record["message_ts"],
            now,
            now,
            now,
            action["primary_action"],
            int(applied),
            action["reason"],
            int(bool(action["manual_review_required"])),
            int(bool(action["model_required"])),
        ),
    )

    for attachment in record["attachments"]:
        conn.execute(
            """
            INSERT INTO gmail_attachments(
                message_id, part_id, filename, mime_type, attachment_id, size_bytes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id, part_id, filename, attachment_id) DO UPDATE SET
                mime_type=excluded.mime_type,
                size_bytes=excluded.size_bytes
            """,
            (
                record["message_id"],
                attachment.part_id,
                attachment.filename,
                attachment.mime_type,
                attachment.attachment_id,
                attachment.size_bytes,
                now,
            ),
        )

    conn.execute(
        """
        INSERT INTO gmail_decisions(
            run_id, message_id, decided_at, primary_action, secondary_actions_json,
            sender_type, intent_tags_json, confidence, reason, manual_review_required,
            model_required, applied, dry_run, error_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            record["message_id"],
            now,
            action["primary_action"],
            json.dumps(action["secondary_actions"]),
            record["sender_type"],
            json.dumps(record["intent_tags"]),
            float(action["confidence"]),
            action["reason"],
            int(bool(action["manual_review_required"])),
            int(bool(action["model_required"])),
            int(applied),
            int(dry_run),
            error_text,
        ),
    )
    conn.commit()


def maybe_apply_actions(
    client: Any,
    *,
    record: dict[str, Any],
    apply: bool,
    create_placeholder_drafts: bool,
) -> tuple[bool, str | None]:
    action = ensure_dict(record.get("action"))
    primary_action = str(action.get("primary_action") or "keep_in_inbox")

    if not apply:
        return False, None

    if primary_action == "archive_message":
        client.archive_message(record["message_id"])
        return True, None
    if primary_action == "trash_message":
        client.trash_message(record["message_id"])
        return True, None
    if primary_action in {"keep_in_inbox", "mark_for_manual_review"}:
        applied = False
    else:
        applied = False

    if create_placeholder_drafts and "draft_reply" in ensure_string_list(action.get("secondary_actions")):
        reply_headers = ensure_dict(record.get("reply_headers"))
        client.create_placeholder_reply_draft(
            thread_id=record["thread_id"],
            to_email=record["from_email"],
            subject=record["subject"] or "(no subject)",
            in_reply_to=str(reply_headers.get("message_id_header") or "").strip() or None,
            references=str(reply_headers.get("references") or "").strip() or None,
        )
    return applied, None


def build_summary(results: list[dict[str, Any]], *, fetched_count: int, skipped_existing_count: int) -> dict[str, Any]:
    by_primary: dict[str, int] = {}
    candidate_counts = {
        "task": 0,
        "calendar": 0,
        "drive_attachment": 0,
        "draft": 0,
        "manual_review": 0,
    }
    applied_count = 0
    error_count = 0

    for row in results:
        primary = str(row.get("primary_action") or "unknown")
        by_primary[primary] = by_primary.get(primary, 0) + 1
        secondary = ensure_string_list(row.get("secondary_actions"))
        if "promote_task_candidate" in secondary:
            candidate_counts["task"] += 1
        if "promote_calendar_candidate" in secondary:
            candidate_counts["calendar"] += 1
        if "save_attachment_to_drive" in secondary:
            candidate_counts["drive_attachment"] += 1
        if "draft_reply" in secondary:
            candidate_counts["draft"] += 1
        if row.get("manual_review_required"):
            candidate_counts["manual_review"] += 1
        if row.get("applied"):
            applied_count += 1
        if row.get("error_text"):
            error_count += 1

    return {
        "fetched_count": fetched_count,
        "skipped_existing_count": skipped_existing_count,
        "processed_count": len(results),
        "applied_count": applied_count,
        "error_count": error_count,
        "by_primary_action": by_primary,
        "candidate_counts": candidate_counts,
    }


def load_workspace_data(path: Path) -> dict[str, Any]:
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


def ensure_gmail_project(workspace: dict[str, Any]) -> str:
    now = now_iso()
    projects = workspace.setdefault("projects", [])
    for project in projects:
        row = ensure_dict(project)
        if str(row.get("id") or "") == "proj-gmail-inbox":
            return "proj-gmail-inbox"
    projects.append(
        {
            "id": "proj-gmail-inbox",
            "name": "Gmail Inbox",
            "status": "active",
            "description": "Assistant-owned inbox triage queue populated from the Gmail inbox processor.",
            "owner": "assistant",
            "target_date": None,
            "progress_pct": 0,
            "created_at": now,
            "updated_at": now,
        }
    )
    return "proj-gmail-inbox"


def priority_from_record(record: dict[str, Any]) -> str:
    tags = set(ensure_string_list(record.get("intent_tags")))
    if "billing_issue" in tags or "verification_code" in tags:
        return "urgent"
    if "deadline" in tags or "meeting_change" in tags:
        return "high"
    if "human_request" in tags:
        return "medium"
    return "low"


def task_title_for_record(record: dict[str, Any]) -> str:
    subject = str(record.get("subject") or "").strip()
    from_email = str(record.get("from_email") or "").strip()
    if subject:
        return f"Email follow-up: {subject}"
    if from_email:
        return f"Email follow-up from {from_email}"
    return f"Email follow-up {record.get('message_id')}"


def task_notes_for_record(record: dict[str, Any]) -> str:
    action = ensure_dict(record.get("action"))
    lines = [
        f"From: {record.get('from_email') or '-'}",
        f"Subject: {record.get('subject') or '-'}",
        f"Message ID: {record.get('message_id') or '-'}",
        f"Reason: {action.get('reason') or '-'}",
        "",
        str(record.get("excerpt") or "").strip(),
    ]
    return "\n".join(lines).strip()


def promote_task_candidates(records: list[dict[str, Any]], workspace_path: Path) -> dict[str, int]:
    workspace = load_workspace_data(workspace_path)
    project_id = ensure_gmail_project(workspace)
    tasks = workspace.setdefault("tasks", [])
    existing = {str(ensure_dict(item).get("id") or ""): ensure_dict(item) for item in tasks}
    now = now_iso()
    created = 0
    updated = 0

    for record in records:
        action = ensure_dict(record.get("action"))
        if "promote_task_candidate" not in ensure_string_list(action.get("secondary_actions")):
            continue
        task_id = f"task-gmail-{record['message_id']}"
        row = existing.get(task_id)
        due_at = record.get("message_ts") if "deadline" in ensure_string_list(record.get("intent_tags")) else None
        payload = {
            "id": task_id,
            "title": task_title_for_record(record),
            "status": str((row or {}).get("status") or "todo"),
            "project_id": project_id,
            "assignees": ["assistant"],
            "priority": priority_from_record(record),
            "due_at": due_at,
            "notes": task_notes_for_record(record),
            "source": "gmail_inbox",
            "progress_pct": int((row or {}).get("progress_pct") or 0),
            "requires_approval": False,
            "side_effects": [],
            "created_at": str((row or {}).get("created_at") or now),
            "updated_at": now,
            "source_message_id": record["message_id"],
            "source_thread_id": record["thread_id"],
            "space_key": "general",
            "owner_agent": "assistant",
        }
        if row:
            for index, task in enumerate(tasks):
                if str(ensure_dict(task).get("id") or "") == task_id:
                    tasks[index] = payload
                    updated += 1
                    break
        else:
            tasks.append(payload)
            created += 1
            existing[task_id] = payload

    write_json(workspace_path, workspace)
    return {"created": created, "updated": updated}


def load_calendar_candidates(path: Path) -> dict[str, Any]:
    raw = read_json(path)
    if not isinstance(raw, dict):
        return {"items": []}
    items = raw.get("items")
    if not isinstance(items, list):
        raw["items"] = []
    return raw


def promote_calendar_candidates(records: list[dict[str, Any]], candidates_path: Path) -> dict[str, int]:
    data = load_calendar_candidates(candidates_path)
    items = data.setdefault("items", [])
    existing = {str(ensure_dict(item).get("id") or ""): ensure_dict(item) for item in items}
    now = now_iso()
    created = 0
    updated = 0

    for record in records:
        action = ensure_dict(record.get("action"))
        if "promote_calendar_candidate" not in ensure_string_list(action.get("secondary_actions")):
            continue
        candidate_id = f"cal-gmail-{record['message_id']}"
        row = existing.get(candidate_id)
        payload = {
            "id": candidate_id,
            "status": str((row or {}).get("status") or "proposed"),
            "title": str(record.get("subject") or "").strip() or f"Calendar candidate from {record.get('from_email') or 'gmail'}",
            "source": "gmail_inbox",
            "message_id": record["message_id"],
            "thread_id": record["thread_id"],
            "from_email": record.get("from_email"),
            "subject": record.get("subject"),
            "excerpt": record.get("excerpt"),
            "reason": action.get("reason"),
            "intent_tags": ensure_string_list(record.get("intent_tags")),
            "context_ts": record.get("message_ts"),
            "space_key": "calendar",
            "owner_agent": "assistant",
            "created_at": str((row or {}).get("created_at") or now),
            "updated_at": now,
        }
        if row:
            for index, item in enumerate(items):
                if str(ensure_dict(item).get("id") or "") == candidate_id:
                    items[index] = payload
                    updated += 1
                    break
        else:
            items.append(payload)
            created += 1
            existing[candidate_id] = payload

    write_json(candidates_path, data)
    return {"created": created, "updated": updated}


def load_fixture_messages(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [ensure_dict(item) for item in data]
    payload = ensure_dict(data)
    return [ensure_dict(item) for item in payload.get("messages", []) if isinstance(item, dict)]


def human_output(summary: dict[str, Any], state_db: Path) -> str:
    lines = [
        "Gmail inbox processing summary:",
        f"- DB: {state_db}",
        f"- Fetched refs: {summary['fetched_count']}",
        f"- Skipped existing: {summary['skipped_existing_count']}",
        f"- Processed: {summary['processed_count']}",
        f"- Applied actions: {summary['applied_count']}",
        f"- Errors: {summary['error_count']}",
    ]
    for action, count in sorted(summary["by_primary_action"].items()):
        lines.append(f"- {action}: {count}")
    candidates = summary["candidate_counts"]
    lines.append(
        "- Candidates: "
        + ", ".join(
            [
                f"task={candidates['task']}",
                f"calendar={candidates['calendar']}",
                f"drive_attachment={candidates['drive_attachment']}",
                f"draft={candidates['draft']}",
                f"manual_review={candidates['manual_review']}",
            ]
        )
    )
    return "\n".join(lines)


def run_processor(args: argparse.Namespace) -> int:
    env_file_values: dict[str, str] = {}
    if args.env_file:
        env_file_values = load_env_file(Path(args.env_file).expanduser().resolve())

    integration, inbox_cfg, contract = resolve_integration(Path(args.config).expanduser().resolve())
    storage_cfg = ensure_dict(contract.get("storage"))
    schedule_cfg = ensure_dict(contract.get("schedule"))
    state_db = resolve_state_db(inbox_cfg, args.state_db)
    schema_path = resolve_schema_path(args.schema)
    status_path = resolve_status_path(args.status_file)
    workspace_path = resolve_workspace_path(args.workspace_file)
    calendar_candidates_path = resolve_calendar_candidates_path(args.calendar_candidates_file)
    batch_limit = int(args.limit or schedule_cfg.get("batch_limit") or 50)
    source_label = str(args.source_label or inbox_cfg.get("source_label") or "INBOX")
    query_text = str(args.query or "").strip()
    dry_run = not args.apply

    state_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state_db)
    ensure_db(conn, schema_path)

    run_id = start_run(
        conn,
        source_label=source_label,
        query_text=query_text,
        batch_limit=batch_limit,
        dry_run=dry_run,
    )

    if args.fixtures_file:
        client: Any = FixtureGmailClient(load_fixture_messages(Path(args.fixtures_file).expanduser().resolve()))
    else:
        oauth = GoogleOAuthClient(
            client_id=env_get("GOOGLE_CLIENT_ID", env_file_values),
            client_secret=env_get("GOOGLE_CLIENT_SECRET", env_file_values),
            refresh_token=env_get("GOOGLE_REFRESH_TOKEN", env_file_values),
        )
        user_email = env_get("GMAIL_USER_EMAIL", env_file_values)
        missing = [name for name, value in {
            "GOOGLE_CLIENT_ID": oauth.client_id,
            "GOOGLE_CLIENT_SECRET": oauth.client_secret,
            "GOOGLE_REFRESH_TOKEN": oauth.refresh_token,
            "GMAIL_USER_EMAIL": user_email,
        }.items() if not value]
        if missing:
            print(f"Missing required env for Gmail processing: {', '.join(missing)}")
            return 2
        access_token = oauth.fetch_access_token()
        client = GmailClient(GoogleApiClient(access_token), user_email)

    refs = client.list_inbox_message_ids(source_label=source_label, batch_limit=batch_limit, query_text=query_text or None)
    ids = [str(ensure_dict(ref).get("id") or "").strip() for ref in refs if str(ensure_dict(ref).get("id") or "").strip()]
    processed_ids = set() if args.reprocess else existing_processed_ids(conn, ids)
    pending_ids = [message_id for message_id in ids if message_id not in processed_ids]

    results: list[dict[str, Any]] = []
    for message_id in pending_ids:
        error_text: str | None = None
        applied = False
        try:
            message = client.get_message(message_id)
            record = extract_message_record(message, keep_raw_headers=bool(storage_cfg.get("keep_raw_headers", True)))
            record["excerpt"] = record["excerpt"][: int(storage_cfg.get("keep_body_excerpt_chars") or 1200)]
            applied, error_text = maybe_apply_actions(
                client,
                record=record,
                apply=args.apply,
                create_placeholder_drafts=args.create_placeholder_drafts,
            )
        except Exception as exc:  # noqa: BLE001
            message = {"id": message_id, "threadId": "", "snippet": ""}
            record = {
                "message_id": message_id,
                "thread_id": str(message.get("threadId") or ""),
                "from_name": "",
                "from_email": "",
                "subject": "",
                "snippet": str(message.get("snippet") or ""),
                "excerpt": "",
                "label_ids": [source_label],
                "sender_type": "unknown",
                "intent_tags": [],
                "has_links": False,
                "has_attachments": False,
                "attachment_count": 0,
                "attachments": [],
                "raw_headers_json": None,
                "message_ts": None,
                "reply_headers": {},
                "action": {
                    "primary_action": "mark_for_manual_review",
                    "secondary_actions": [],
                    "manual_review_required": True,
                    "model_required": False,
                    "confidence": 0.0,
                    "reason": "processing error",
                },
            }
            error_text = str(exc)

        record_message(conn, run_id=run_id, record=record, applied=applied, dry_run=dry_run, error_text=error_text)
        action = ensure_dict(record.get("action"))
        results.append(
            {
                "message_id": record["message_id"],
                "subject": record["subject"],
                "from_email": record["from_email"],
                "primary_action": action.get("primary_action"),
                "secondary_actions": action.get("secondary_actions"),
                "manual_review_required": action.get("manual_review_required"),
                "confidence": action.get("confidence"),
                "reason": action.get("reason"),
                "applied": applied,
                "error_text": error_text,
            }
        )

    summary = build_summary(results, fetched_count=len(refs), skipped_existing_count=len(processed_ids))
    promotions = {
        "tasks": {"created": 0, "updated": 0},
        "calendar": {"created": 0, "updated": 0},
    }
    # Reuse the records already persisted from the current run only.
    current_run_records = []
    for message_id in pending_ids:
        message_row = conn.execute(
            """
            SELECT message_id, thread_id, from_email, subject, excerpt, message_ts, intent_tags_json,
                   last_action, action_reason
              FROM gmail_messages
             WHERE message_id = ?
            """,
            (message_id,),
        ).fetchone()
        decision_row = conn.execute(
            """
            SELECT secondary_actions_json, manual_review_required, model_required, confidence
              FROM gmail_decisions
             WHERE run_id = ? AND message_id = ?
             ORDER BY id DESC
             LIMIT 1
            """,
            (run_id, message_id),
        ).fetchone()
        if not message_row or not decision_row:
            continue
        current_run_records.append(
            {
                "message_id": str(message_row[0]),
                "thread_id": str(message_row[1] or ""),
                "from_email": str(message_row[2] or ""),
                "subject": str(message_row[3] or ""),
                "excerpt": str(message_row[4] or ""),
                "message_ts": message_row[5],
                "intent_tags": json.loads(str(message_row[6] or "[]")),
                "action": {
                    "primary_action": str(message_row[7] or ""),
                    "reason": str(message_row[8] or ""),
                    "secondary_actions": json.loads(str(decision_row[0] or "[]")),
                    "manual_review_required": bool(decision_row[1]),
                    "model_required": bool(decision_row[2]),
                    "confidence": float(decision_row[3] or 0.0),
                },
            }
        )

    if args.promote_task_candidates:
        promotions["tasks"] = promote_task_candidates(current_run_records, workspace_path)
    if args.promote_calendar_candidates:
        promotions["calendar"] = promote_calendar_candidates(current_run_records, calendar_candidates_path)

    finish_run(conn, run_id, summary)
    conn.close()

    payload = {
        "ok": True,
        "run_id": run_id,
        "dry_run": dry_run,
        "state_db": str(state_db),
        "summary": summary,
        "promotions": promotions,
        "results": results,
    }
    status_payload = {
        "generated_at": now_iso(),
        "run_id": run_id,
        "dry_run": dry_run,
        "state_db": str(state_db),
        "summary": summary,
        "promotions": promotions,
        "recent_results": results[:20],
    }
    write_json(status_path, status_payload)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(human_output(summary, state_db))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic Gmail inbox processor")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--env-file", help="dotenv-style env file to use without exporting vars")
    parser.add_argument("--state-db", help="override sqlite db path")
    parser.add_argument("--schema", help="override sqlite schema path")
    parser.add_argument("--status-file", help="write latest run summary JSON to this path")
    parser.add_argument("--workspace-file", help="dashboard workspace JSON path for promoted task candidates")
    parser.add_argument("--calendar-candidates-file", help="calendar candidates JSON path for promoted calendar items")
    parser.add_argument("--source-label", help="override Gmail label to process (default from config)")
    parser.add_argument("--query", help="optional Gmail search query")
    parser.add_argument("--limit", type=int, help="maximum number of inbox messages to inspect")
    parser.add_argument("--reprocess", action="store_true", help="reprocess messages already seen in sqlite state")
    parser.add_argument("--apply", action="store_true", help="apply safe primary actions (archive/trash)")
    parser.add_argument(
        "--create-placeholder-drafts",
        action="store_true",
        help="when --apply is set, create placeholder reply drafts for draft candidates",
    )
    parser.add_argument(
        "--promote-task-candidates",
        action="store_true",
        help="promote task candidates into the local dashboard workspace JSON",
    )
    parser.add_argument(
        "--promote-calendar-candidates",
        action="store_true",
        help="promote calendar candidates into the local calendar candidates JSON",
    )
    parser.add_argument("--fixtures-file", help="JSON fixture file containing Gmail message payloads")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(run_processor(args))


if __name__ == "__main__":
    sys.exit(main())
