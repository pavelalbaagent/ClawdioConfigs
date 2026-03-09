#!/usr/bin/env python3
"""Run memory sync and persist a dashboard-readable status snapshot."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import model_route_decider
from env_file_utils import load_env_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATUS = ROOT / "data" / "memory-sync-status.json"
DEFAULT_MEMORY_CONFIG = ROOT / "config" / "memory.yaml"


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def ensure_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def iso_now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_summary(stdout: str) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for raw in stdout.splitlines():
        line = raw.strip()
        if line.startswith("Profile:"):
            summary["profile"] = line.split(":", 1)[1].strip()
            continue
        if line.startswith("Enabled modules:"):
            modules = [item.strip() for item in line.split(":", 1)[1].split(",") if item.strip()]
            summary["enabled_modules"] = modules
            continue
        if ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        normalized_key = key.lower().replace(" ", "_")
        if value.isdigit():
            summary[normalized_key] = int(value)
        else:
            summary[normalized_key] = value
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run memory sync and write a status snapshot")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--config", default=str(DEFAULT_MEMORY_CONFIG))
    parser.add_argument("--status-file", default=str(DEFAULT_STATUS))
    parser.add_argument("--env-file", help="optional env file with OPENAI_API_KEY")
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve()
    status_path = Path(args.status_file).expanduser().resolve()
    env = os.environ.copy()
    if args.env_file:
        env.update(load_env_file(Path(args.env_file).expanduser().resolve(), strict=True))

    cmd = [
        "python3",
        str(root / "scripts" / "memory_index_sync.py"),
        "--workspace",
        str(root),
        "--config",
        str(config_path),
    ]
    if isinstance(args.max_files, int) and args.max_files > 0:
        cmd.extend(["--max-files", str(args.max_files)])

    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, env=env)

    config_data = ensure_dict(model_route_decider.load_yaml(config_path)) if config_path.exists() else {}
    profiles = ensure_dict(config_data.get("profiles"))
    definitions = ensure_dict(profiles.get("definitions"))
    active_profile = str(profiles.get("active_profile") or "").strip() or None
    profile_cfg = ensure_dict(definitions.get(active_profile)) if active_profile else {}

    payload = {
        "generated_at": iso_now_utc(),
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "profile": active_profile,
        "enabled_modules": ensure_string_list(profile_cfg.get("enabled_modules", [])),
        "command": cmd,
        "summary": parse_summary(proc.stdout),
        "stdout_tail": "\n".join(proc.stdout.strip().splitlines()[-20:]) if proc.stdout.strip() else "",
        "stderr_tail": "\n".join(proc.stderr.strip().splitlines()[-20:]) if proc.stderr.strip() else "",
    }

    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Memory sync {'ok' if payload['ok'] else 'failed'}")
        print(f"- Profile: {payload['profile'] or '-'}")
        for key in ("files_changed", "chunks_created", "embeddings_created", "embeddings_skipped_missing_key", "embeddings_skipped_budget"):
            if key in payload["summary"]:
                print(f"- {key}: {payload['summary'][key]}")

    return 0 if proc.returncode == 0 else proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
