#!/usr/bin/env python3
"""ResearchFlow orchestration for the researcher surface."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from env_file_utils import load_env_file
from validate_configs import ensure_dict, load_yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "research_flow.yaml"
DEFAULT_STATUS_PATH = ROOT / "data" / "research-flow-status.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def env_get(name: str, env_values: dict[str, str]) -> str:
    return env_values.get(name, os.environ.get(name, "")).strip()


def load_config(path: Path) -> dict[str, Any]:
    raw = ensure_dict(load_yaml(path))
    config = ensure_dict(raw.get("research_flow"))
    if not config:
        raise RuntimeError(f"research_flow config missing in {path}")
    return config


def resolve_repo_path(path_value: str) -> Path:
    path = Path(str(path_value))
    if not path.is_absolute():
        path = ROOT / path
    return path


def extract_artifact_paths(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    candidates: list[str] = []
    for key in (
        "summary_json",
        "summary_markdown",
        "latest_status",
        "discovery_status",
        "digest_json",
        "digest_markdown",
        "status_file",
    ):
        value = str(payload.get(key) or "").strip()
        if value:
            candidates.append(value)
    seen: set[str] = set()
    ordered: list[str] = []
    for value in candidates:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def extract_preview_text(payload: Any, *, fallback: str = "") -> str:
    if isinstance(payload, dict):
        delivery = ensure_dict(payload.get("delivery"))
        preview = str(delivery.get("preview") or payload.get("preview") or "").strip()
        if preview:
            return preview
    return fallback.strip()


def stable_dropzone_record_paths(config: dict[str, Any], workflow_name: str) -> list[str]:
    paths: list[str] = []
    for dropzone in ensure_string_list(config.get("shared_dropzones")):
        root = resolve_repo_path(dropzone)
        paths.append(str(root / f"{workflow_name}-latest.json"))
        paths.append(str(root / f"{workflow_name}-latest.md"))
    return paths


def write_dropzone_records(
    *,
    config: dict[str, Any],
    workflow_name: str,
    workflow: dict[str, Any],
    result: dict[str, Any],
) -> list[str]:
    written: list[str] = []
    preview = extract_preview_text(result.get("payload"), fallback=str(result.get("stderr") or result.get("stdout") or ""))
    preview = preview.strip()
    if len(preview) > 2400:
        preview = preview[:2397].rstrip() + "..."
    artifacts = extract_artifact_paths(result.get("payload"))
    summary = {
        "generated_at": now_iso(),
        "workflow": workflow_name,
        "output_label": str(workflow.get("output_label") or workflow_name).strip() or workflow_name,
        "ok": bool(result.get("ok")),
        "executed_at": str(result.get("executed_at") or "").strip() or None,
        "returncode": result.get("returncode"),
        "status_file": str(resolve_repo_path(str(workflow.get("status_file") or ""))),
        "artifacts": artifacts,
        "dropzone_records": stable_dropzone_record_paths(config, workflow_name),
        "preview": preview or None,
        "error": str(result.get("stderr") or "").strip() or None,
    }
    markdown_lines = [
        f"# {summary['output_label']}",
        "",
        f"- Workflow: `{workflow_name}`",
        f"- OK: `{summary['ok']}`",
        f"- Executed at: `{summary['executed_at'] or '-'}`",
        f"- Status file: `{summary['status_file']}`",
    ]
    if artifacts:
        markdown_lines.append("- Artifacts:")
        markdown_lines.extend(f"  - `{path}`" for path in artifacts)
    else:
        markdown_lines.append("- Artifacts: none")
    if summary["error"]:
        markdown_lines.extend(["", "## Error", summary["error"]])
    if summary["preview"]:
        markdown_lines.extend(["", "## Preview", summary["preview"]])

    for dropzone in ensure_string_list(config.get("shared_dropzones")):
        root = resolve_repo_path(dropzone)
        root.mkdir(parents=True, exist_ok=True)
        json_path = root / f"{workflow_name}-latest.json"
        md_path = root / f"{workflow_name}-latest.md"
        write_json(json_path, summary)
        md_path.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")
        written.extend([str(json_path), str(md_path)])
    return written


def workflow_catalog(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = ensure_dict(config.get("workflows"))
    return {str(name): ensure_dict(row) for name, row in raw.items() if isinstance(name, str)}


def workflow_status(config: dict[str, Any], workflow_name: str) -> dict[str, Any]:
    workflow = ensure_dict(workflow_catalog(config).get(workflow_name))
    if not workflow:
        raise RuntimeError(f"unknown workflow: {workflow_name}")
    status_file = resolve_repo_path(str(workflow.get("status_file") or ""))
    payload = read_json(status_file)
    schedule = ensure_dict(workflow.get("schedule"))
    return {
        "name": workflow_name,
        "enabled": bool(workflow.get("enabled") is True),
        "kind": str(workflow.get("kind") or "").strip() or "unknown",
        "output_label": str(workflow.get("output_label") or workflow_name).strip(),
        "status_file": str(status_file),
        "schedule": {
            "enabled": bool(schedule.get("enabled") is True),
            "timezone": str(schedule.get("timezone") or "").strip() or None,
            "delivery_time_local": str(schedule.get("delivery_time_local") or "").strip() or None,
        },
        "artifact_paths": extract_artifact_paths(payload),
        "shared_records": stable_dropzone_record_paths(config, workflow_name),
        "last_status": payload,
    }


def build_status(config: dict[str, Any]) -> dict[str, Any]:
    workflows = workflow_catalog(config)
    rows = [workflow_status(config, name) for name in sorted(workflows)]
    return {
        "ok": True,
        "generated_at": now_iso(),
        "enabled": bool(config.get("enabled") is True),
        "owner_agent": str(config.get("owner_agent") or "researcher").strip() or "researcher",
        "default_space": str(config.get("default_space") or "research").strip() or "research",
        "delivery_chat_env": str(config.get("delivery_chat_env") or "TELEGRAM_RESEARCH_CHAT_ID").strip()
        or "TELEGRAM_RESEARCH_CHAT_ID",
        "shared_dropzones": ensure_string_list(config.get("shared_dropzones")),
        "workflows": rows,
    }


def execute_workflow(
    *,
    config: dict[str, Any],
    workflow_name: str,
    env_file: Path | None,
    apply: bool,
) -> dict[str, Any]:
    workflow = ensure_dict(workflow_catalog(config).get(workflow_name))
    if not workflow:
        raise RuntimeError(f"unknown workflow: {workflow_name}")
    if workflow.get("enabled") is not True:
        return {
            "workflow": workflow_name,
            "ok": True,
            "skipped": True,
            "reason": "disabled",
        }

    command = ensure_dict(workflow.get("command"))
    script = resolve_repo_path(str(command.get("script") or ""))
    args = [str(item) for item in ensure_string_list(command.get("args"))]
    cmd = [sys.executable, str(script), *args]
    if env_file is not None:
        cmd.extend(["--env-file", str(env_file)])
    if apply:
        cmd.append("--apply")
    if command.get("supports_json_flag") is not False:
        cmd.append("--json")

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    result: dict[str, Any] = {
        "workflow": workflow_name,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": cmd,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "executed_at": now_iso(),
    }
    if proc.stdout.strip():
        try:
            result["payload"] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass
    result["artifact_paths"] = extract_artifact_paths(result.get("payload"))
    result["dropzone_records"] = write_dropzone_records(
        config=config,
        workflow_name=workflow_name,
        workflow=workflow,
        result=result,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="ResearchFlow orchestration runtime.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--env-file", help="env file for downstream workflows")
    parser.add_argument("--status-file", default=str(DEFAULT_STATUS_PATH))

    parser.add_argument("--json", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--json", action="store_true")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--workflow", choices=["job_search_digest", "ai_tools_watch", "all"], required=True)
    run_parser.add_argument("--apply", action="store_true")
    run_parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    config = load_config(Path(args.config).expanduser().resolve())
    env_file = Path(args.env_file).expanduser().resolve() if args.env_file else None
    if env_file and env_file.exists():
        load_env_file(env_file)

    status_path = Path(args.status_file).expanduser().resolve()

    if args.command == "status":
        payload = build_status(config)
        write_json(status_path, payload)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(json.dumps(payload))
        return 0

    workflow_names = ["job_search_digest", "ai_tools_watch"] if args.workflow == "all" else [args.workflow]
    results = [execute_workflow(config=config, workflow_name=name, env_file=env_file, apply=args.apply) for name in workflow_names]
    payload = build_status(config)
    payload["last_run"] = {
        "executed_at": now_iso(),
        "workflow": args.workflow,
        "apply": bool(args.apply),
        "results": results,
    }
    write_json(status_path, payload)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload))
    return 0 if all(result.get("ok") for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
