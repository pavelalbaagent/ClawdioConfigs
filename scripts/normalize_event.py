#!/usr/bin/env python3
"""Normalize platform-specific inbound payloads into canonical event format."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_ts(value: Any) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    if isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            return utc_now_iso()
    return utc_now_iso()


def normalize_slack(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": "slack",
        "channel_id": str(payload.get("channel", "")),
        "user_id": str(payload.get("user", "")),
        "message_id": str(payload.get("client_msg_id") or payload.get("ts") or ""),
        "thread_id": str(payload.get("thread_ts")) if payload.get("thread_ts") else None,
        "text": str(payload.get("text", "")),
        "ts_utc": parse_ts(payload.get("ts")),
        "attachments": [],
        "metadata": {"raw_type": payload.get("type", "message")},
    }


def normalize_telegram(payload: dict[str, Any]) -> dict[str, Any]:
    msg = payload.get("message", payload)
    chat = msg.get("chat", {}) if isinstance(msg, dict) else {}
    sender = msg.get("from", {}) if isinstance(msg, dict) else {}
    return {
        "platform": "telegram",
        "channel_id": str(chat.get("id", "")),
        "user_id": str(sender.get("id", "")),
        "message_id": str(msg.get("message_id", "")),
        "thread_id": None,
        "text": str(msg.get("text", "")),
        "ts_utc": parse_ts(msg.get("date")),
        "attachments": [],
        "metadata": {"chat_type": chat.get("type")},
    }


def normalize_whatsapp(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": "whatsapp",
        "channel_id": str(payload.get("chatId", payload.get("chat_id", ""))),
        "user_id": str(payload.get("from", payload.get("sender", ""))),
        "message_id": str(payload.get("id", payload.get("message_id", ""))),
        "thread_id": None,
        "text": str(payload.get("text", payload.get("body", ""))),
        "ts_utc": parse_ts(payload.get("timestamp")),
        "attachments": [],
        "metadata": {"source": payload.get("source", "unknown")},
    }


def normalize_email(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": "email",
        "channel_id": str(payload.get("mailbox", payload.get("to", "email"))),
        "user_id": str(payload.get("from", "")),
        "message_id": str(payload.get("message_id", payload.get("id", ""))),
        "thread_id": str(payload.get("thread_id")) if payload.get("thread_id") else None,
        "text": str(payload.get("body", payload.get("snippet", ""))),
        "ts_utc": parse_ts(payload.get("date")),
        "attachments": [],
        "metadata": {"subject": payload.get("subject", "")},
    }


def normalize_web(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": "web",
        "channel_id": str(payload.get("channel_id", "web")),
        "user_id": str(payload.get("user_id", "")),
        "message_id": str(payload.get("message_id", "")),
        "thread_id": str(payload.get("thread_id")) if payload.get("thread_id") else None,
        "text": str(payload.get("text", "")),
        "ts_utc": parse_ts(payload.get("ts_utc")),
        "attachments": payload.get("attachments", []) if isinstance(payload.get("attachments"), list) else [],
        "metadata": payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {},
    }


def infer_platform(payload: dict[str, Any]) -> str:
    if "channel" in payload and "user" in payload:
        return "slack"
    if "message" in payload and isinstance(payload.get("message"), dict) and "chat" in payload["message"]:
        return "telegram"
    if "chatId" in payload or "chat_id" in payload:
        return "whatsapp"
    if "mailbox" in payload or "subject" in payload:
        return "email"
    return "web"


def normalize(payload: dict[str, Any], platform: str | None) -> dict[str, Any]:
    platform_name = platform or infer_platform(payload)
    if platform_name == "slack":
        return normalize_slack(payload)
    if platform_name == "telegram":
        return normalize_telegram(payload)
    if platform_name == "whatsapp":
        return normalize_whatsapp(payload)
    if platform_name == "email":
        return normalize_email(payload)
    return normalize_web(payload)


def load_payload(path: str | None) -> dict[str, Any]:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return json.load(sys.stdin)  # type: ignore[name-defined]


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize platform payload to canonical event")
    parser.add_argument("--input", help="input JSON file path (default: stdin)")
    parser.add_argument("--platform", choices=["slack", "telegram", "whatsapp", "email", "web"])
    parser.add_argument("--output", help="optional output file path")
    args = parser.parse_args()

    payload = load_payload(args.input)
    canonical = normalize(payload, args.platform)

    text = json.dumps(canonical, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
