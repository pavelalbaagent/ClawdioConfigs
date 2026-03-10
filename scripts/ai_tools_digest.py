#!/usr/bin/env python3
"""Publish a simple daily AI tools digest sourced from AIToolsDB."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from env_file_utils import load_env_file
from knowledge_source_search import load_config, resolve_source_config, resolve_source_root


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "knowledge_sources.yaml"
DEFAULT_STATUS_PATH = ROOT / "data" / "ai-tools-digest-status.json"
TELEGRAM_MESSAGE_CHUNK_LIMIT = 3500


def env_get(name: str, env_values: dict[str, str]) -> str:
    return env_values.get(name, os.environ.get(name, "")).strip()


def split_telegram_text(text: str, *, limit: int = TELEGRAM_MESSAGE_CHUNK_LIMIT) -> list[str]:
    clean = str(text or "").strip()
    if len(clean) <= limit:
        return [clean]
    parts: list[str] = []
    remaining = clean
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
        if cut < max(200, limit // 4):
            cut = limit
        chunk = remaining[:cut].strip()
        parts.append(chunk)
        remaining = remaining[cut:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


class TelegramClient:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"

    def send_message(self, *, chat_id: str, text: str) -> dict[str, Any]:
        payload = urllib.parse.urlencode(
            {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
        ).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/sendMessage", data=payload, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=40) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"telegram api http {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"telegram api request failed: {exc.reason}") from exc
        if not isinstance(data, dict) or data.get("ok") is not True:
            raise RuntimeError(f"telegram api error: {data}")
        return data

    def send_long_message(self, *, chat_id: str, text: str) -> list[dict[str, Any]]:
        return [self.send_message(chat_id=chat_id, text=part) for part in split_telegram_text(text)]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def source_kind(path: Path) -> str:
    name = path.name.lower()
    if name.startswith("yt_"):
        return "YouTube"
    if name.startswith("blog_"):
        return "Blog"
    if name.startswith("gh_"):
        return "GitHub"
    return "Other"


def first_content_line(path: Path) -> str:
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip().strip("#").strip()
        if line:
            return line[:140]
    return path.stem.replace("_", " ")


def collect_recent_items(*, source_root: Path, lookback_hours: int, limit: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(lookback_hours, 1))
    items: list[dict[str, Any]] = []
    for path in source_root.rglob("*.md"):
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        if modified < cutoff:
            continue
        items.append(
            {
                "path": str(path),
                "title": first_content_line(path),
                "kind": source_kind(path),
                "modified_at": modified.isoformat(timespec="seconds"),
            }
        )
    items.sort(key=lambda row: str(row.get("modified_at") or ""), reverse=True)
    return items[:limit]


def render_digest(*, items: list[dict[str, Any]], source_label: str) -> str:
    lines = [f"AI tools digest ({source_label})"]
    if not items:
        lines.append("- No recent corpus updates in the lookback window.")
        return "\n".join(lines)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item.get("kind") or "Other"), []).append(item)
    for kind in sorted(grouped):
        lines.append(f"\n{kind}")
        for item in grouped[kind]:
            lines.append(f"- {item.get('title')} | {item.get('modified_at')}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a daily AI tools digest sourced from AIToolsDB.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--env-file", help="env file with telegram token/chat bindings")
    parser.add_argument("--status-file", default=str(DEFAULT_STATUS_PATH))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    env_values: dict[str, str] = {}
    if args.env_file:
        env_values = load_env_file(Path(args.env_file).expanduser().resolve())

    config = load_config(Path(args.config).expanduser().resolve())
    source_cfg = resolve_source_config(config, "ai_tools_db")
    digest_cfg = source_cfg.get("digest") or {}
    source_root = resolve_source_root(source_cfg)
    if source_root is None:
        payload = {"ok": False, "generated_at": now_iso(), "reason": "source_root_missing", "delivered": False}
        write_json(Path(args.status_file).expanduser().resolve(), payload)
        if args.json:
            print(json.dumps(payload, indent=2))
        return 2

    items = collect_recent_items(
        source_root=source_root,
        lookback_hours=int(digest_cfg.get("lookback_hours", 36) or 36),
        limit=int(digest_cfg.get("max_items", 8) or 8),
    )
    digest_text = render_digest(items=items, source_label=str(source_root))
    payload = {
        "ok": True,
        "generated_at": now_iso(),
        "source_root": str(source_root),
        "item_count": len(items),
        "delivered": False,
        "preview": digest_text,
    }

    if args.apply:
        token = env_get("TELEGRAM_BOT_TOKEN", env_values)
        chat_env = str(digest_cfg.get("chat_id_env") or "TELEGRAM_RESEARCH_CHAT_ID").strip()
        chat_id = env_get(chat_env, env_values)
        if not token or not chat_id:
            raise RuntimeError("missing TELEGRAM_BOT_TOKEN or research chat binding env")
        client = TelegramClient(token)
        responses = client.send_long_message(chat_id=chat_id, text=digest_text)
        payload["delivered"] = True
        payload["telegram_messages_sent"] = len(responses)

    write_json(Path(args.status_file).expanduser().resolve(), payload)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(digest_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
