#!/usr/bin/env python3
"""Deterministic reminder state machine.

Behavior:
- Initial reminder at due time.
- If no reply, exactly one follow-up 1 hour later (treated as a one-time defer).
- No repeated hourly follow-ups after that.
- Natural reply handling without reminder IDs (`done`, `defer until <time>`).

This helper does not call external APIs. It only updates reminder state and
returns actions for an orchestrator (OpenClaw, n8n, etc.) to execute.
"""

from __future__ import annotations

import argparse
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_STATE_FILE = Path("./data/reminders-state.json")
DEFAULT_TIMEZONE = "America/Guayaquil"
DONE_KEYWORDS = {"done"}
DEFER_PREFIX = "defer until "
MAX_AUTO_FOLLOWUPS = 1


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso_maybe(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_when(value: str, timezone_name: str, reference_utc: datetime) -> datetime:
    text = value.strip()
    zone = ZoneInfo(timezone_name)
    reference_local = reference_utc.astimezone(zone)

    # Relative inputs, e.g. "in 1 hour", "in 30 minutes", "in 90m".
    rel = re.fullmatch(r"in\s+(\d+)\s*(hours?|hrs?|h|minutes?|mins?|m)\s*", text, flags=re.IGNORECASE)
    if rel:
        qty = int(rel.group(1))
        unit = rel.group(2).lower()
        if unit in {"hours", "hour", "hrs", "hr", "h"}:
            return reference_utc + timedelta(hours=qty)
        return reference_utc + timedelta(minutes=qty)

    if re.fullmatch(r"in\s+(an?|one)\s+hour\s*", text, flags=re.IGNORECASE):
        return reference_utc + timedelta(hours=1)

    # HH:MM means today or tomorrow in the given timezone.
    hhmm = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if hhmm:
        hour = int(hhmm.group(1))
        minute = int(hhmm.group(2))
        candidate_local = reference_local.replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate_local <= reference_local:
            candidate_local = candidate_local + timedelta(days=1)
        return candidate_local.astimezone(timezone.utc)

    # YYYY-MM-DD HH:MM
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            naive = datetime.strptime(text, fmt)
            local = naive.replace(tzinfo=zone)
            return local.astimezone(timezone.utc)
        except ValueError:
            pass

    # Full ISO with timezone.
    parsed = parse_iso_maybe(text)
    return parsed.astimezone(timezone.utc)


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"reminders": {}}
    data = json.loads(path.read_text())
    if "reminders" not in data or not isinstance(data["reminders"], dict):
        return {"reminders": {}}
    return data


def save_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def require_reminder(state: dict[str, Any], reminder_id: str) -> dict[str, Any]:
    reminder = state["reminders"].get(reminder_id)
    if reminder is None:
        raise SystemExit(f"Reminder not found: {reminder_id}")
    return reminder


def build_id() -> str:
    return f"r-{uuid.uuid4().hex[:10]}"


def output(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


def parse_create_text(text: str) -> tuple[str, str] | None:
    normalized = text.strip()

    at_match = re.match(r"^\s*remind\s+me\s+(.+)\s+at\s+(.+)\s*$", normalized, flags=re.IGNORECASE)
    if at_match:
        message = at_match.group(1).strip()
        when_text = at_match.group(2).strip()
        if message and when_text:
            return message, when_text
        return None

    in_match = re.match(r"^\s*remind\s+me\s+(.+)\s+in\s+(.+)\s*$", normalized, flags=re.IGNORECASE)
    if in_match:
        message = in_match.group(1).strip()
        when_text = in_match.group(2).strip()
        if message and when_text:
            return message, f"in {when_text}"
        return None

    return None


def parse_reply_text(text: str) -> tuple[str, str | None]:
    stripped = text.strip()
    lowered = stripped.lower()
    normalized = re.sub(r"[^a-z0-9]", "", lowered)
    if normalized in DONE_KEYWORDS:
        return "done", None

    if lowered.startswith(DEFER_PREFIX):
        remainder = stripped[len(DEFER_PREFIX) :].strip()
        if remainder:
            return "defer", remainder
        return "invalid", None

    return "ignore", None


def find_open_reminders(state: dict[str, Any]) -> list[dict[str, Any]]:
    reminders = list(state["reminders"].values())
    return [r for r in reminders if r.get("status") in {"pending", "awaiting_reply"}]


def choose_target_reminder(state: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    open_reminders = find_open_reminders(state)
    awaiting = [r for r in open_reminders if r.get("status") == "awaiting_reply"]
    if len(awaiting) == 1:
        return awaiting[0], []
    if len(awaiting) > 1:
        return None, [str(r["id"]) for r in awaiting]

    if len(open_reminders) == 1:
        return open_reminders[0], []
    if len(open_reminders) > 1:
        return None, [str(r["id"]) for r in open_reminders]

    return None, []


def apply_done(state: dict[str, Any], reminder: dict[str, Any], current: datetime) -> dict[str, Any]:
    reminder["status"] = "done"
    reminder["updated_at"] = iso_utc(current)
    reminder["next_followup_at"] = None
    return {
        "ok": True,
        "reminder": reminder,
        "actions": [
            {"type": "cancel_followups", "reminder_id": reminder["id"]},
            {"type": "send_ack", "text": "Done. Reminder closed."},
        ],
    }


def apply_defer(state: dict[str, Any], reminder: dict[str, Any], defer_time: str, current: datetime) -> dict[str, Any]:
    new_at = parse_when(defer_time, reminder["timezone"], current)
    reminder["status"] = "pending"
    reminder["remind_at"] = iso_utc(new_at)
    reminder["last_reminded_at"] = None
    reminder["next_followup_at"] = None
    reminder["followup_count"] = 0
    reminder["updated_at"] = iso_utc(current)
    return {
        "ok": True,
        "reminder": reminder,
        "actions": [
            {"type": "cancel_followups", "reminder_id": reminder["id"]},
            {
                "type": "schedule_due",
                "reminder_id": reminder["id"],
                "at": reminder["remind_at"],
                "message": reminder["message"],
            },
            {"type": "send_ack", "text": f"Deferred. New time: {reminder['remind_at']}"},
        ],
    }


def cmd_create(args: argparse.Namespace) -> None:
    state_file = Path(args.state_file)
    state = load_state(state_file)
    current = now_utc()
    try:
        reminder_at = parse_when(args.when, args.timezone, current)
    except Exception:
        output({"ok": False, "error": "invalid_time", "input": args.when})
        raise SystemExit(2)
    reminder_id = args.id or build_id()

    reminder = {
        "id": reminder_id,
        "message": args.message,
        "timezone": args.timezone,
        "status": "pending",
        "created_at": iso_utc(current),
        "updated_at": iso_utc(current),
        "remind_at": iso_utc(reminder_at),
        "last_reminded_at": None,
        "next_followup_at": None,
        "followup_count": 0,
    }
    state["reminders"][reminder_id] = reminder
    save_state(state_file, state)

    output(
        {
            "ok": True,
            "reminder": reminder,
            "actions": [
                {
                    "type": "schedule_due",
                    "reminder_id": reminder_id,
                    "at": reminder["remind_at"],
                    "message": reminder["message"],
                }
            ],
        }
    )


def cmd_create_from_text(args: argparse.Namespace) -> None:
    parsed = parse_create_text(args.text)
    if not parsed:
        output({"ok": False, "error": "invalid_create_text"})
        raise SystemExit(2)

    message, when_text = parsed
    next_args = argparse.Namespace(
        state_file=args.state_file,
        id=args.id,
        message=message,
        when=when_text,
        timezone=args.timezone,
    )
    cmd_create(next_args)


def cmd_due(args: argparse.Namespace) -> None:
    state_file = Path(args.state_file)
    state = load_state(state_file)
    reminder = require_reminder(state, args.id)
    current = parse_iso_maybe(args.now) if args.now else now_utc()
    due_at = parse_iso_maybe(reminder["remind_at"])

    if reminder["status"] != "pending" or current < due_at:
        output({"ok": True, "actions": [], "reason": "not_due"})
        return

    reminder["status"] = "awaiting_reply"
    reminder["last_reminded_at"] = iso_utc(current)
    if int(reminder.get("followup_count", 0)) < MAX_AUTO_FOLLOWUPS:
        reminder["next_followup_at"] = iso_utc(current + timedelta(hours=1))
    else:
        reminder["next_followup_at"] = None
    reminder["updated_at"] = iso_utc(current)
    save_state(state_file, state)

    actions: list[dict[str, Any]] = [
        {
            "type": "send_reminder",
            "reminder_id": reminder["id"],
            "text": (
                f"Reminder: {reminder['message']}\n"
                "Reply `done` to close or `defer until <time>` to reschedule."
            ),
        }
    ]
    if reminder["next_followup_at"] is not None:
        actions.append(
            {
                "type": "schedule_followup",
                "reminder_id": reminder["id"],
                "at": reminder["next_followup_at"],
            }
        )

    output(
        {
            "ok": True,
            "reminder": reminder,
            "actions": actions,
        }
    )


def cmd_respond(args: argparse.Namespace) -> None:
    state_file = Path(args.state_file)
    state = load_state(state_file)
    reminder = require_reminder(state, args.id)
    current = parse_iso_maybe(args.now) if args.now else now_utc()

    command, payload = parse_reply_text(args.text)
    if command == "done":
        response = apply_done(state, reminder, current)
    elif command == "defer":
        try:
            response = apply_defer(state, reminder, str(payload), current)
        except Exception:
            output({"ok": False, "error": "invalid_time", "input": payload})
            raise SystemExit(2)
    elif command == "invalid":
        output({"ok": False, "error": "missing_defer_time"})
        raise SystemExit(2)
    else:
        output({"ok": True, "actions": [], "reason": "no_valid_command"})
        return

    save_state(state_file, state)
    output(response)


def cmd_handle_reply(args: argparse.Namespace) -> None:
    state_file = Path(args.state_file)
    state = load_state(state_file)
    current = parse_iso_maybe(args.now) if args.now else now_utc()

    command, payload = parse_reply_text(args.text)
    if command == "ignore":
        output({"ok": True, "actions": [], "reason": "no_valid_command"})
        return
    if command == "invalid":
        output({"ok": False, "error": "missing_defer_time"})
        raise SystemExit(2)

    if args.id:
        reminder = require_reminder(state, args.id)
    else:
        reminder, ambiguous_ids = choose_target_reminder(state)
        if ambiguous_ids:
            output(
                {
                    "ok": False,
                    "error": "ambiguous_open_reminders",
                    "candidate_ids": ambiguous_ids,
                }
            )
            raise SystemExit(2)
        if reminder is None:
            output({"ok": False, "error": "no_open_reminder"})
            raise SystemExit(2)

    if command == "done":
        response = apply_done(state, reminder, current)
    else:
        try:
            response = apply_defer(state, reminder, str(payload), current)
        except Exception:
            output({"ok": False, "error": "invalid_time", "input": payload})
            raise SystemExit(2)

    save_state(state_file, state)
    output(response)


def cmd_followup(args: argparse.Namespace) -> None:
    state_file = Path(args.state_file)
    state = load_state(state_file)
    reminder = require_reminder(state, args.id)
    current = parse_iso_maybe(args.now) if args.now else now_utc()

    if reminder["status"] != "awaiting_reply" or reminder["next_followup_at"] is None:
        output({"ok": True, "actions": [], "reason": "not_waiting_reply"})
        return

    if int(reminder.get("followup_count", 0)) >= MAX_AUTO_FOLLOWUPS:
        output({"ok": True, "actions": [], "reason": "max_followups_reached"})
        return

    next_followup = parse_iso_maybe(reminder["next_followup_at"])
    if current < next_followup:
        output({"ok": True, "actions": [], "reason": "followup_not_due"})
        return

    # Treat follow-up as a one-time +1h defer then notify once.
    reminder["remind_at"] = iso_utc(next_followup)
    reminder["followup_count"] = int(reminder.get("followup_count", 0)) + 1
    reminder["last_reminded_at"] = iso_utc(current)
    reminder["next_followup_at"] = None
    reminder["updated_at"] = iso_utc(current)
    save_state(state_file, state)

    output(
        {
            "ok": True,
            "reminder": reminder,
            "actions": [
                {
                    "type": "send_followup",
                    "reminder_id": reminder["id"],
                    "text": (
                        f"Reminder follow-up: {reminder['message']}\n"
                        "Reply `done` or `defer until <time>`."
                    ),
                }
            ],
        }
    )


def cmd_list_open(args: argparse.Namespace) -> None:
    state = load_state(Path(args.state_file))
    open_items = find_open_reminders(state)
    open_items.sort(key=lambda item: item.get("updated_at") or "")
    output({"ok": True, "count": len(open_items), "reminders": open_items})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reminder state machine")
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("--id")
    create.add_argument("--message", required=True)
    create.add_argument("--when", required=True)
    create.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    create.set_defaults(func=cmd_create)

    create_text = sub.add_parser("create-from-text")
    create_text.add_argument("--id")
    create_text.add_argument("--text", required=True)
    create_text.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    create_text.set_defaults(func=cmd_create_from_text)

    due = sub.add_parser("due")
    due.add_argument("--id", required=True)
    due.add_argument("--now")
    due.set_defaults(func=cmd_due)

    respond = sub.add_parser("respond")
    respond.add_argument("--id", required=True)
    respond.add_argument("--text", required=True)
    respond.add_argument("--now")
    respond.set_defaults(func=cmd_respond)

    handle_reply = sub.add_parser("handle-reply")
    handle_reply.add_argument("--id")
    handle_reply.add_argument("--text", required=True)
    handle_reply.add_argument("--now")
    handle_reply.set_defaults(func=cmd_handle_reply)

    followup = sub.add_parser("followup")
    followup.add_argument("--id", required=True)
    followup.add_argument("--now")
    followup.set_defaults(func=cmd_followup)

    list_open = sub.add_parser("list-open")
    list_open.set_defaults(func=cmd_list_open)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
