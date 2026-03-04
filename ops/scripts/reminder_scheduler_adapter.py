#!/usr/bin/env python3
"""Translate reminder state-machine actions into safe scheduler job specs.

Guard rule:
- Any reminder due job targeting main session MUST use payload.kind=systemEvent.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def read_json_input(path_value: str | None) -> Any:
    if not path_value or path_value == "-":
        raw = sys.stdin.read()
        return json.loads(raw)

    path = Path(path_value)
    return json.loads(path.read_text(encoding="utf-8"))


def output(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


def is_main_target(target: str) -> bool:
    normalized = target.strip().lower()
    return normalized in {"main", "agent:main", "session:main"}


def sanitize_fragment(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "item"


def parse_at_timestamp(iso_value: str) -> str:
    text = iso_value.strip()
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc_dt = dt.astimezone(timezone.utc)
    # Keep deterministic compact suffix for job names.
    return utc_dt.strftime("%Y%m%dt%H%M%SZ")


def build_due_payload(message: str, session_target: str, requested_kind: str | None) -> dict[str, Any]:
    main_target = is_main_target(session_target)

    if main_target:
        if requested_kind and requested_kind != "systemEvent":
            raise ValueError(
                f"invalid_payload_kind_for_main:{requested_kind}"
            )
        return {
            "kind": "systemEvent",
            "text": f"Reminder: {message}",
        }

    if requested_kind == "agentTurn":
        return {
            "kind": "agentTurn",
            "message": f"Reminder: {message}",
        }

    return {
        "kind": "systemEvent",
        "text": f"Reminder: {message}",
    }


def action_to_job(action: dict[str, Any], session_target: str, agent_id: str, job_prefix: str) -> dict[str, Any]:
    action_type = str(action.get("type") or "").strip()
    if action_type != "schedule_due":
        raise ValueError(f"unsupported_action:{action_type}")

    reminder_id = str(action.get("reminder_id") or "").strip()
    at_value = str(action.get("at") or "").strip()
    message = str(action.get("message") or "").strip()
    if not reminder_id or not at_value or not message:
        raise ValueError("missing_required_action_fields")

    requested_kind = action.get("payload_kind")
    if requested_kind is not None:
        requested_kind = str(requested_kind).strip()

    payload = build_due_payload(
        message=message,
        session_target=session_target,
        requested_kind=requested_kind,
    )

    ts_fragment = parse_at_timestamp(at_value)
    name = f"{job_prefix}-{sanitize_fragment(reminder_id)}-due-{ts_fragment}"

    return {
        "name": name,
        "agent_id": agent_id,
        "session_target": session_target,
        "schedule": {
            "kind": "at",
            "at": at_value,
        },
        "delete_after_run": True,
        "wake_mode": "now",
        "meta": {
            "is_reminder_due": True,
            "reminder_id": reminder_id,
            "source_action": "schedule_due",
        },
        "payload": payload,
    }


def extract_actions(payload: Any) -> list[dict[str, Any]]:
    data = ensure_dict(payload)
    actions = data.get("actions")
    if isinstance(actions, list):
        return [ensure_dict(item) for item in actions if isinstance(item, dict)]
    if isinstance(data.get("type"), str):
        return [data]
    return []


def cmd_translate(args: argparse.Namespace) -> int:
    try:
        source = read_json_input(args.input)
    except Exception as exc:  # noqa: BLE001
        output({"ok": False, "error": "invalid_input_json", "detail": str(exc)})
        return 2

    actions = extract_actions(source)
    if not actions:
        output({"ok": False, "error": "no_actions"})
        return 2

    jobs: list[dict[str, Any]] = []
    passthrough: list[dict[str, Any]] = []

    for action in actions:
        action_type = str(action.get("type") or "").strip()
        if action_type != "schedule_due":
            passthrough.append(action)
            continue

        try:
            job = action_to_job(
                action=action,
                session_target=args.session_target,
                agent_id=args.agent_id,
                job_prefix=args.job_prefix,
            )
        except ValueError as exc:
            text = str(exc)
            if text.startswith("invalid_payload_kind_for_main:"):
                requested = text.split(":", 1)[1]
                output(
                    {
                        "ok": False,
                        "error": "invalid_payload_kind_for_main",
                        "required": "systemEvent",
                        "requested": requested,
                        "action": action,
                    }
                )
                return 2

            output({"ok": False, "error": text, "action": action})
            return 2

        jobs.append(job)

    output(
        {
            "ok": True,
            "jobs": jobs,
            "passthrough_actions": passthrough,
        }
    )
    return 0


def cmd_validate_job(args: argparse.Namespace) -> int:
    try:
        payload = read_json_input(args.input)
    except Exception as exc:  # noqa: BLE001
        output({"ok": False, "error": "invalid_input_json", "detail": str(exc)})
        return 2

    job = ensure_dict(payload)
    session_target = str(job.get("session_target") or job.get("sessionTarget") or "").strip()
    payload_data = ensure_dict(job.get("payload"))
    payload_kind = str(payload_data.get("kind") or "").strip()

    if is_main_target(session_target) and payload_kind != "systemEvent":
        output(
            {
                "ok": False,
                "error": "invalid_payload_kind_for_main",
                "required": "systemEvent",
                "requested": payload_kind or None,
            }
        )
        return 2

    output({"ok": True})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reminder scheduler adapter guard")
    sub = parser.add_subparsers(dest="command", required=True)

    translate = sub.add_parser("translate", help="translate reminder actions into safe job specs")
    translate.add_argument("--input", help="path to JSON input (or '-' for stdin)")
    translate.add_argument("--session-target", default="main")
    translate.add_argument("--agent-id", default="clawdio-main")
    translate.add_argument("--job-prefix", default="reminder")
    translate.set_defaults(func=cmd_translate)

    validate_job = sub.add_parser("validate-job", help="validate a scheduler job against guard rules")
    validate_job.add_argument("--input", help="path to JSON job input (or '-' for stdin)")
    validate_job.set_defaults(func=cmd_validate_job)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
