#!/usr/bin/env python3
"""Personal task manager runtime with Todoist-first MVP support."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google_workspace_common import ensure_dict, get_integration_config  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "integrations.yaml"
DEFAULT_STATUS_PATH = ROOT / "data" / "personal-task-runtime-status.json"


class TodoistClient:
    def __init__(self, token: str):
        self.token = token

    def list_tasks(self, *, filter_text: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        payload = self._request_json(
            "GET",
            "https://api.todoist.com/api/v1/tasks",
            query={"filter": filter_text or None, "limit": limit},
        )
        results = payload.get("results")
        if not isinstance(results, list):
            return []
        return [ensure_dict(item) for item in results if isinstance(item, dict)]

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", "https://api.todoist.com/api/v1/tasks", payload=payload)

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"https://api.todoist.com/api/v1/tasks/{urllib.parse.quote(task_id, safe='')}")

    def update_task(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._request_json(
            "POST",
            f"https://api.todoist.com/api/v1/tasks/{urllib.parse.quote(task_id, safe='')}",
            payload=payload,
        )
        if result:
            return result
        return self.get_task(task_id)

    def close_task(self, task_id: str) -> dict[str, Any]:
        self._request_json(
            "POST",
            f"https://api.todoist.com/api/v1/tasks/{urllib.parse.quote(task_id, safe='')}/close",
        )
        return {"id": task_id, "status": "completed"}

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        query: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if query:
            encoded = urllib.parse.urlencode({k: v for k, v in query.items() if v not in (None, "")}, doseq=True)
            if encoded:
                joiner = "&" if "?" in url else "?"
                url = f"{url}{joiner}{encoded}"
        data = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, method=method.upper(), data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"todoist api http {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"todoist api request failed: {exc.reason}") from exc

        if not body.strip():
            return {}
        parsed = json.loads(body)
        return ensure_dict(parsed)


class FixtureTodoistClient:
    def __init__(self, *, tasks: list[dict[str, Any]]):
        self.tasks = [ensure_dict(item) for item in tasks]
        self.created: list[dict[str, Any]] = []
        self.closed: list[str] = []
        self.updated: list[dict[str, Any]] = []

    def list_tasks(self, *, filter_text: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        rows = list(self.tasks)
        if filter_text:
            lowered = filter_text.lower()
            rows = [row for row in rows if lowered in json.dumps(row).lower()]
        return rows[:limit]

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = {
            "id": str(len(self.tasks) + len(self.created) + 1),
            "content": str(payload.get("content") or "").strip(),
            "description": str(payload.get("description") or "").strip(),
            "priority": int(payload.get("priority") or 1),
            "project_id": str(payload.get("project_id") or "").strip() or None,
            "section_id": None,
            "parent_id": None,
            "labels": [],
            "created_at": now_iso(),
            "url": f"https://todoist.test/task/{len(self.tasks) + len(self.created) + 1}",
        }
        due_payload = build_due_object(payload)
        if due_payload:
            task["due"] = due_payload
        self.tasks.append(task)
        self.created.append(task)
        return task

    def get_task(self, task_id: str) -> dict[str, Any]:
        for task in self.tasks:
            if str(task.get("id") or "") == task_id:
                return task
        raise RuntimeError(f"fixture task not found: {task_id}")

    def update_task(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        for index, task in enumerate(self.tasks):
            if str(task.get("id") or "") != task_id:
                continue
            updated = dict(task)
            for key, value in payload.items():
                if key in {"due_string", "due_datetime", "due_date"}:
                    continue
                updated[key] = value
            due_payload = build_due_object(payload)
            if due_payload:
                updated["due"] = due_payload
            updated["updated_at"] = now_iso()
            self.tasks[index] = updated
            self.updated.append(updated)
            return updated
        raise RuntimeError(f"fixture task not found: {task_id}")

    def close_task(self, task_id: str) -> dict[str, Any]:
        for index, task in enumerate(self.tasks):
            if str(task.get("id") or "") != task_id:
                continue
            self.closed.append(task_id)
            self.tasks.pop(index)
            return {"id": task_id, "status": "completed"}
        raise RuntimeError(f"fixture task not found: {task_id}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def env_get(name: str, env_file_values: dict[str, str]) -> str:
    return env_file_values.get(name, os.environ.get(name, "")).strip()


def resolve_personal_task_integration(config_path: Path) -> dict[str, Any]:
    integration = get_integration_config(config_path, "personal_task_manager")
    if integration.get("enabled") is not True:
        raise RuntimeError("personal_task_manager integration is disabled in config")
    return integration


def resolve_provider(*, env_file_values: dict[str, str], override: str | None, fixtures_file: str | None) -> str:
    if override:
        return override.strip().lower()
    provider = env_get("PERSONAL_TASK_PROVIDER", env_file_values).lower()
    if provider:
        return provider
    if fixtures_file:
        return "todoist"
    raise RuntimeError("missing required personal task env: PERSONAL_TASK_PROVIDER")


def resolve_status_path(override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_STATUS_PATH


def build_due_object(payload: dict[str, Any]) -> dict[str, Any] | None:
    if str(payload.get("due_datetime") or "").strip():
        return {
            "datetime": str(payload.get("due_datetime")).strip(),
            "string": str(payload.get("due_string") or "").strip() or None,
        }
    if str(payload.get("due_date") or "").strip():
        return {
            "date": str(payload.get("due_date")).strip(),
            "string": str(payload.get("due_string") or "").strip() or None,
        }
    if str(payload.get("due_string") or "").strip():
        return {
            "string": str(payload.get("due_string")).strip(),
        }
    return None


def normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    due = ensure_dict(task.get("due"))
    due_value = str(due.get("datetime") or due.get("date") or "").strip() or None
    if due.get("datetime"):
        due_mode = "datetime"
    elif due.get("date"):
        due_mode = "date"
    elif due.get("string"):
        due_mode = "string"
    else:
        due_mode = None
    return {
        "id": str(task.get("id") or "").strip(),
        "title": str(task.get("content") or "").strip() or "(untitled task)",
        "description": str(task.get("description") or "").strip() or None,
        "priority": int(task.get("priority") or 1),
        "project_id": str(task.get("project_id") or "").strip() or None,
        "section_id": str(task.get("section_id") or "").strip() or None,
        "parent_id": str(task.get("parent_id") or "").strip() or None,
        "labels": [str(item).strip() for item in task.get("labels", []) if str(item).strip()],
        "due_value": due_value,
        "due_mode": due_mode,
        "due_string": str(due.get("string") or "").strip() or None,
        "due_lang": str(due.get("lang") or "").strip() or None,
        "due_is_recurring": bool(due.get("is_recurring") is True),
        "url": str(task.get("url") or "").strip() or None,
        "created_at": str(task.get("created_at") or "").strip() or None,
    }


def list_personal_tasks(client: Any, *, limit: int, filter_text: str | None) -> list[dict[str, Any]]:
    rows = client.list_tasks(filter_text=filter_text, limit=limit)
    normalized = [normalize_task(ensure_dict(item)) for item in rows]
    normalized.sort(key=lambda row: (str(row.get("due_value") or "9999-12-31"), str(row.get("title") or "")))
    return normalized


def build_status_payload(
    *,
    provider: str,
    action: str,
    dry_run: bool,
    tasks: list[dict[str, Any]],
    recent_results: list[dict[str, Any]],
) -> dict[str, Any]:
    overdue = 0
    today = datetime.now(timezone.utc).date()
    for task in tasks:
        due_value = str(task.get("due_value") or "").strip()
        due_mode = str(task.get("due_mode") or "").strip()
        if not due_value:
            continue
        try:
            if due_mode == "datetime":
                dt = datetime.fromisoformat(due_value.replace("Z", "+00:00")).astimezone(timezone.utc)
                if dt.date() < today:
                    overdue += 1
            elif due_mode == "date":
                if datetime.fromisoformat(f"{due_value}T00:00:00+00:00").date() < today:
                    overdue += 1
        except ValueError:
            continue
    return {
        "generated_at": now_iso(),
        "provider": provider,
        "summary": {
            "action": action,
            "dry_run": dry_run,
            "open_count": len(tasks),
            "overdue_count": overdue,
        },
        "recent_results": recent_results[:20],
        "tasks": tasks[:50],
    }


def build_client(
    *,
    provider: str,
    env_file_values: dict[str, str],
    fixtures_file: str | None,
) -> Any:
    if provider != "todoist":
        raise RuntimeError(
            f"unsupported PERSONAL_TASK_PROVIDER for MVP runtime: {provider}. Supported now: todoist."
        )

    if fixtures_file:
        payload = ensure_dict(json.loads(Path(fixtures_file).expanduser().resolve().read_text(encoding="utf-8")))
        tasks = [ensure_dict(item) for item in payload.get("tasks", []) if isinstance(item, dict)]
        return FixtureTodoistClient(tasks=tasks)

    token = env_get("TODOIST_API_TOKEN", env_file_values)
    if not token:
        raise RuntimeError("missing required personal task env: TODOIST_API_TOKEN")
    return TodoistClient(token)


def build_create_payload(
    *,
    title: str,
    description: str | None,
    priority: int | None,
    due_string: str | None,
    due_datetime: str | None,
    due_date: str | None,
) -> dict[str, Any]:
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("title is required")
    payload: dict[str, Any] = {"content": clean_title}
    if description and description.strip():
        payload["description"] = description.strip()
    if priority is not None:
        if priority < 1 or priority > 4:
            raise ValueError("priority must be between 1 and 4")
        payload["priority"] = priority
    if due_string and due_string.strip():
        payload["due_string"] = due_string.strip()
    if due_datetime and due_datetime.strip():
        payload["due_datetime"] = due_datetime.strip()
    if due_date and due_date.strip():
        payload["due_date"] = due_date.strip()
    return payload


def build_defer_payload(*, due_string: str | None, due_datetime: str | None, due_date: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if due_string and due_string.strip():
        payload["due_string"] = due_string.strip()
    if due_datetime and due_datetime.strip():
        payload["due_datetime"] = due_datetime.strip()
    if due_date and due_date.strip():
        payload["due_date"] = due_date.strip()
    if not payload:
        raise ValueError("defer requires due_string, due_datetime, or due_date")
    return payload


def human_output(payload: dict[str, Any]) -> str:
    summary = ensure_dict(payload.get("summary"))
    return "\n".join(
        [
            "Personal task runtime summary:",
            f"- Provider: {payload.get('provider') or '-'}",
            f"- Action: {summary.get('action') or '-'}",
            f"- Dry run: {'yes' if summary.get('dry_run') else 'no'}",
            f"- Open tasks: {summary.get('open_count') or 0}",
            f"- Overdue: {summary.get('overdue_count') or 0}",
        ]
    )


def run_snapshot(args: argparse.Namespace) -> int:
    env_values = load_env_file(Path(args.env_file).expanduser().resolve()) if args.env_file else {}
    resolve_personal_task_integration(Path(args.config).expanduser().resolve())
    provider = resolve_provider(env_file_values=env_values, override=args.provider, fixtures_file=args.fixtures_file)
    client = build_client(provider=provider, env_file_values=env_values, fixtures_file=args.fixtures_file)
    tasks = list_personal_tasks(client, limit=int(args.limit or 50), filter_text=args.filter)
    payload = build_status_payload(provider=provider, action="snapshot", dry_run=False, tasks=tasks, recent_results=[])
    write_json(resolve_status_path(args.status_file), payload)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(human_output(payload))
    return 0


def run_create(args: argparse.Namespace) -> int:
    env_values = load_env_file(Path(args.env_file).expanduser().resolve()) if args.env_file else {}
    resolve_personal_task_integration(Path(args.config).expanduser().resolve())
    provider = resolve_provider(env_file_values=env_values, override=args.provider, fixtures_file=args.fixtures_file)
    client = build_client(provider=provider, env_file_values=env_values, fixtures_file=args.fixtures_file)
    task_payload = build_create_payload(
        title=args.title,
        description=args.description,
        priority=args.priority,
        due_string=args.due_string,
        due_datetime=args.due_datetime,
        due_date=args.due_date,
    )
    if args.apply:
        created = normalize_task(client.create_task(task_payload))
        result = {"action": "create_task", "status": "created", "task_id": created["id"], "title": created["title"]}
    else:
        result = {"action": "create_task", "status": "preview", "payload": task_payload}
    tasks = list_personal_tasks(client, limit=int(args.limit or 50), filter_text=args.filter)
    payload = build_status_payload(
        provider=provider,
        action="create_task",
        dry_run=not args.apply,
        tasks=tasks,
        recent_results=[result],
    )
    write_json(resolve_status_path(args.status_file), payload)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(human_output(payload))
    return 0


def run_complete(args: argparse.Namespace) -> int:
    env_values = load_env_file(Path(args.env_file).expanduser().resolve()) if args.env_file else {}
    resolve_personal_task_integration(Path(args.config).expanduser().resolve())
    provider = resolve_provider(env_file_values=env_values, override=args.provider, fixtures_file=args.fixtures_file)
    client = build_client(provider=provider, env_file_values=env_values, fixtures_file=args.fixtures_file)
    task_id = args.task_id.strip()
    if not task_id:
        raise ValueError("task_id is required")
    if args.apply:
        result = client.close_task(task_id)
        recent = {"action": "complete_task", "status": "completed", "task_id": str(result.get("id") or task_id)}
    else:
        recent = {"action": "complete_task", "status": "preview", "task_id": task_id}
    tasks = list_personal_tasks(client, limit=int(args.limit or 50), filter_text=args.filter)
    payload = build_status_payload(
        provider=provider,
        action="complete_task",
        dry_run=not args.apply,
        tasks=tasks,
        recent_results=[recent],
    )
    write_json(resolve_status_path(args.status_file), payload)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(human_output(payload))
    return 0


def run_defer(args: argparse.Namespace) -> int:
    env_values = load_env_file(Path(args.env_file).expanduser().resolve()) if args.env_file else {}
    resolve_personal_task_integration(Path(args.config).expanduser().resolve())
    provider = resolve_provider(env_file_values=env_values, override=args.provider, fixtures_file=args.fixtures_file)
    client = build_client(provider=provider, env_file_values=env_values, fixtures_file=args.fixtures_file)
    task_id = args.task_id.strip()
    if not task_id:
        raise ValueError("task_id is required")
    defer_payload = build_defer_payload(
        due_string=args.due_string,
        due_datetime=args.due_datetime,
        due_date=args.due_date,
    )
    if args.apply:
        updated = normalize_task(client.update_task(task_id, defer_payload))
        recent = {
            "action": "defer_task",
            "status": "updated",
            "task_id": updated["id"],
            "title": updated["title"],
            "due_value": updated["due_value"],
        }
    else:
        recent = {"action": "defer_task", "status": "preview", "task_id": task_id, "payload": defer_payload}
    tasks = list_personal_tasks(client, limit=int(args.limit or 50), filter_text=args.filter)
    payload = build_status_payload(
        provider=provider,
        action="defer_task",
        dry_run=not args.apply,
        tasks=tasks,
        recent_results=[recent],
    )
    write_json(resolve_status_path(args.status_file), payload)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(human_output(payload))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="path to integrations config file")
    parser.add_argument("--env-file", help="env file containing task provider credentials")
    parser.add_argument("--provider", help="override PERSONAL_TASK_PROVIDER")
    parser.add_argument("--status-file", help="write runtime status JSON to this path")
    parser.add_argument("--fixtures-file", help="JSON fixture file with provider task payloads")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--filter", help="provider filter query for listing tasks")
    parser.add_argument("--json", action="store_true")

    subparsers = parser.add_subparsers(dest="command")

    snapshot_parser = subparsers.add_parser("snapshot", help="refresh personal tasks snapshot")
    snapshot_parser.set_defaults(func=run_snapshot)

    create_parser = subparsers.add_parser("create", help="create a personal task")
    create_parser.add_argument("--title", required=True)
    create_parser.add_argument("--description")
    create_parser.add_argument("--priority", type=int)
    create_parser.add_argument("--due-string")
    create_parser.add_argument("--due-datetime")
    create_parser.add_argument("--due-date")
    create_parser.add_argument("--apply", action="store_true")
    create_parser.set_defaults(func=run_create)

    complete_parser = subparsers.add_parser("complete", help="complete a personal task")
    complete_parser.add_argument("--task-id", required=True)
    complete_parser.add_argument("--apply", action="store_true")
    complete_parser.set_defaults(func=run_complete)

    defer_parser = subparsers.add_parser("defer", help="defer or reschedule a personal task")
    defer_parser.add_argument("--task-id", required=True)
    defer_parser.add_argument("--due-string")
    defer_parser.add_argument("--due-datetime")
    defer_parser.add_argument("--due-date")
    defer_parser.add_argument("--apply", action="store_true")
    defer_parser.set_defaults(func=run_defer)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv if argv is not None else sys.argv[1:])
    parser = build_parser()
    args = parser.parse_args(raw_argv)
    if not getattr(args, "command", None):
        args = parser.parse_args(["snapshot", *raw_argv])
    try:
        return int(args.func(args))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
