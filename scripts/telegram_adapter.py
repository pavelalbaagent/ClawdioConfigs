#!/usr/bin/env python3
"""Telegram long-polling adapter for the manual-first OpenClaw MVP.

Scope:
- private-chat Telegram ingress only
- reminder creation and reply handling
- reminder due/follow-up delivery from the same long-poll loop
- braindump capture
- simple personal task create/list
- simple calendar read
- project-space text -> local project task capture
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "ops" / "scripts"))

from backend import DashboardBackend, ensure_dict  # type: ignore  # noqa: E402
import assistant_chat_runtime  # type: ignore  # noqa: E402
import braindump_app as braindump_runtime  # type: ignore  # noqa: E402
from check_env_requirements import load_env_file  # type: ignore  # noqa: E402
import google_calendar_runtime as calendar_runtime  # type: ignore  # noqa: E402
from normalize_event import normalize_telegram  # type: ignore  # noqa: E402
import personal_task_runtime  # type: ignore  # noqa: E402
import reminder_state_machine as reminder_sm  # type: ignore  # noqa: E402
from validate_configs import load_yaml  # type: ignore  # noqa: E402


DEFAULT_ENV = Path("/etc/openclaw/openclaw.env")
DEFAULT_STATE = ROOT / "data" / "telegram-adapter-state.json"
HELP_TEXT = "\n".join(
    [
        "Commands:",
        "- remind me <message> at <time>",
        "- remind me <message> in <duration>",
        "- done",
        "- defer until <time>",
        "- bd <category> <text> [#tag] [@review_bucket]",
        "- add-task <title> :: <optional due string>",
        "- tasks",
        "- calendar today",
        "- calendar next",
        "- status",
        "- assistant: <text>",
        "- any other plain text -> assistant general chat",
        "- reminders: <text>",
        "- research: <text>   -> Researcher chat",
        "- fitness: <text>",
        "- coding: <text>     -> Builder chat",
        "- ops: <text>",
        "- [project:slug] <text>  -> capture as project task",
    ]
)

CONVERSATIONAL_SPECIALISTS = {"assistant", "researcher", "builder"}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_yaml_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return ensure_dict(load_yaml(path))


def env_get(name: str, env_values: dict[str, str]) -> str:
    return str(env_values.get(name, "")).strip()


def load_env_values(env_file: Path | None) -> dict[str, str]:
    if env_file is None or not env_file.exists():
        return {}
    return load_env_file(env_file)


def parse_command_text(text: str) -> tuple[str, str]:
    clean = text.strip()
    if not clean:
        return "", ""
    if clean.startswith("/"):
        body = clean[1:]
        cmd, _, rest = body.partition(" ")
        cmd = cmd.split("@", 1)[0].strip().lower()
        return cmd, rest.strip()
    return "", clean


def is_calendar_today_request(text: str) -> bool:
    clean = text.strip().lower()
    return clean in {"calendar today", "today calendar", "calendar", "today"} or clean.startswith("/calendar")


def is_calendar_next_request(text: str) -> bool:
    clean = text.strip().lower()
    return clean in {"calendar next", "calendar upcoming", "upcoming calendar", "next calendar"}


def parse_task_create_text(text: str) -> tuple[str, str | None] | None:
    clean = text.strip()
    lowered = clean.lower()
    prefixes = ("add-task ", "task ", "todo ")
    body = None
    for prefix in prefixes:
        if lowered.startswith(prefix):
            body = clean[len(prefix) :].strip()
            break
    if body is None:
        return None
    if not body:
        return None
    if "::" in body:
        title, due = body.split("::", 1)
        return title.strip(), due.strip() or None
    return body, None


def is_task_list_request(text: str) -> bool:
    return text.strip().lower() in {"tasks", "task list", "todo list", "/tasks"}


def short_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def format_dt(value: str | None, timezone_name: str) -> str:
    if not value:
        return "-"
    text = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(ZoneInfo(timezone_name))
        return local.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return value


def event_local_date(event: dict[str, Any], timezone_name: str) -> date | None:
    start_value = str(event.get("start_value") or "").strip()
    if not start_value:
        return None
    if len(start_value) == 10 and start_value[4] == "-" and start_value[7] == "-":
        try:
            return date.fromisoformat(start_value)
        except ValueError:
            return None
    try:
        dt = datetime.fromisoformat(start_value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(timezone_name)).date()
    except ValueError:
        return None


def format_calendar_lines(events: list[dict[str, Any]], timezone_name: str, *, heading: str) -> str:
    if not events:
        return f"{heading}\n- none"
    lines = [heading]
    for event in events[:8]:
        summary = str(event.get("summary") or "(untitled event)")
        if event.get("all_day"):
            when = str(event.get("start_value") or "")
        else:
            when = format_dt(str(event.get("start_value") or ""), timezone_name)
        lines.append(f"- {when} | {summary}")
    return "\n".join(lines)


class TelegramAPI:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"

    def _request(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/{method}", data=body, method="POST")
        with urllib.request.urlopen(req, timeout=40) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, dict) or data.get("ok") is not True:
            raise RuntimeError(f"telegram api error for {method}: {data}")
        return ensure_dict(data)

    def get_updates(self, *, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": max(int(timeout), 1)}
        if offset is not None:
            payload["offset"] = int(offset)
        data = self._request("getUpdates", payload)
        result = data.get("result")
        return [ensure_dict(item) for item in result if isinstance(item, dict)] if isinstance(result, list) else []

    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = int(reply_to_message_id)
        data = self._request("sendMessage", payload)
        return ensure_dict(data.get("result"))


@dataclass
class ReminderDispatchResult:
    reminder: dict[str, Any]
    outbound_text: str
    reminder_id: str
    message_kind: str


class TelegramAdapter:
    def __init__(
        self,
        *,
        root: Path,
        backend: DashboardBackend,
        client: Any,
        allowed_chat_id: str,
        env_values: dict[str, str],
        state_path: Path,
        reminder_state_path: Path,
        default_timezone: str,
    ) -> None:
        self.root = root
        self.backend = backend
        self.client = client
        self.allowed_chat_id = allowed_chat_id.strip()
        self.env_values = env_values
        self.state_path = state_path
        self.reminder_state_path = reminder_state_path
        self.default_timezone = default_timezone
        self.agent_chats = {
            agent_id: assistant_chat_runtime.AgentChatRuntime(
                root=root,
                backend=backend,
                env_values=env_values,
                agent_id=agent_id,
            )
            for agent_id in sorted(CONVERSATIONAL_SPECIALISTS)
        }
        self.assistant_chat = self.agent_chats["assistant"]

    def load_adapter_state(self) -> dict[str, Any]:
        data = read_json(self.state_path)
        links = ensure_dict(data.get("reminder_message_links"))
        data["reminder_message_links"] = {
            str(chat_id): ensure_dict(value) for chat_id, value in links.items()
        }
        if "last_update_id" not in data:
            data["last_update_id"] = 0
        return data

    def save_adapter_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = short_now_iso()
        write_json(self.state_path, state)

    def _remember_reminder_message(
        self,
        state: dict[str, Any],
        *,
        chat_id: str,
        message_id: int | None,
        reminder_id: str,
        message_kind: str,
    ) -> None:
        if message_id is None:
            return
        links = ensure_dict(state.setdefault("reminder_message_links", {}))
        chat_links = ensure_dict(links.setdefault(str(chat_id), {}))
        chat_links[str(message_id)] = {
            "reminder_id": reminder_id,
            "kind": message_kind,
            "linked_at": short_now_iso(),
        }
        if len(chat_links) > 200:
            oldest = sorted(chat_links.items(), key=lambda item: str(ensure_dict(item[1]).get("linked_at") or ""))[:50]
            for key, _ in oldest:
                chat_links.pop(key, None)

    def _reply_linked_reminder_id(self, state: dict[str, Any], *, chat_id: str, reply_to_message_id: int | None) -> str | None:
        if reply_to_message_id is None:
            return None
        links = ensure_dict(state.get("reminder_message_links"))
        chat_links = ensure_dict(links.get(str(chat_id)))
        row = ensure_dict(chat_links.get(str(reply_to_message_id)))
        reminder_id = str(row.get("reminder_id") or "").strip()
        return reminder_id or None

    def _load_reminder_state(self) -> dict[str, Any]:
        return reminder_sm.load_state(self.reminder_state_path)

    def _save_reminder_state(self, state: dict[str, Any]) -> None:
        reminder_sm.save_state(self.reminder_state_path, state)

    def _create_reminder_from_text(self, text: str) -> tuple[dict[str, Any], str]:
        parsed = reminder_sm.parse_create_text(text)
        if not parsed:
            raise ValueError("invalid reminder request")
        message, when_text = parsed
        current = reminder_sm.now_utc()
        try:
            remind_at = reminder_sm.parse_when(when_text, self.default_timezone, current)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"invalid reminder time: {when_text}") from exc
        state = self._load_reminder_state()
        reminder_id = reminder_sm.build_id()
        reminder = {
            "id": reminder_id,
            "message": message,
            "timezone": self.default_timezone,
            "status": "pending",
            "created_at": reminder_sm.iso_utc(current),
            "updated_at": reminder_sm.iso_utc(current),
            "remind_at": reminder_sm.iso_utc(remind_at),
            "last_reminded_at": None,
            "next_followup_at": None,
            "followup_count": 0,
        }
        state.setdefault("reminders", {})[reminder_id] = reminder
        self._save_reminder_state(state)
        return reminder, f"Reminder created for {format_dt(reminder['remind_at'], self.default_timezone)}: {message}"

    def _handle_reminder_reply(self, text: str, *, reminder_id: str | None) -> str:
        state = self._load_reminder_state()
        current = reminder_sm.now_utc()
        command, payload = reminder_sm.parse_reply_text(text)
        if command == "ignore":
            raise ValueError("not a reminder reply")
        if command == "invalid":
            return "Missing defer time. Use `defer until <time>`."

        reminder: dict[str, Any] | None = None
        if reminder_id:
            reminder = reminder_sm.require_reminder(state, reminder_id)
        else:
            reminder, ambiguous_ids = reminder_sm.choose_target_reminder(state)
            if ambiguous_ids:
                return "More than one reminder is open. Reply directly to the reminder message, or close one first."
            if reminder is None:
                return "No open reminder matched."

        if command == "done":
            result = reminder_sm.apply_done(state, reminder, current)
        else:
            try:
                result = reminder_sm.apply_defer(state, reminder, str(payload), current)
            except Exception:
                return f"Could not parse defer time: {payload}"

        self._save_reminder_state(state)
        for action in result.get("actions", []):
            row = ensure_dict(action)
            if row.get("type") == "send_ack":
                return str(row.get("text") or "Reminder updated.")
        return "Reminder updated."

    def _collect_due_dispatches(self, *, current: datetime) -> tuple[dict[str, Any], list[ReminderDispatchResult]]:
        state = self._load_reminder_state()
        reminders = ensure_dict(state.get("reminders"))
        dispatches: list[ReminderDispatchResult] = []

        for reminder_id, row in reminders.items():
            reminder = ensure_dict(row)
            status = str(reminder.get("status") or "").strip()
            if status == "pending":
                remind_at_text = str(reminder.get("remind_at") or "").strip()
                if not remind_at_text:
                    continue
                try:
                    remind_at = reminder_sm.parse_iso_maybe(remind_at_text)
                except Exception:
                    continue
                if current < remind_at:
                    continue
                reminder["status"] = "awaiting_reply"
                reminder["last_reminded_at"] = reminder_sm.iso_utc(current)
                if int(reminder.get("followup_count", 0)) < reminder_sm.MAX_AUTO_FOLLOWUPS:
                    reminder["next_followup_at"] = reminder_sm.iso_utc(current + timedelta(hours=1))
                else:
                    reminder["next_followup_at"] = None
                reminder["updated_at"] = reminder_sm.iso_utc(current)
                dispatches.append(
                    ReminderDispatchResult(
                        reminder=reminder,
                        reminder_id=reminder_id,
                        message_kind="reminder",
                        outbound_text=(
                            f"Reminder: {reminder.get('message')}\n"
                            "Reply `done` to close or `defer until <time>` to reschedule."
                        ),
                    )
                )
                continue

            if status != "awaiting_reply":
                continue
            next_followup_text = str(reminder.get("next_followup_at") or "").strip()
            if not next_followup_text:
                continue
            if int(reminder.get("followup_count", 0)) >= reminder_sm.MAX_AUTO_FOLLOWUPS:
                continue
            try:
                next_followup = reminder_sm.parse_iso_maybe(next_followup_text)
            except Exception:
                continue
            if current < next_followup:
                continue
            reminder["remind_at"] = reminder_sm.iso_utc(next_followup)
            reminder["followup_count"] = int(reminder.get("followup_count", 0)) + 1
            reminder["last_reminded_at"] = reminder_sm.iso_utc(current)
            reminder["next_followup_at"] = None
            reminder["updated_at"] = reminder_sm.iso_utc(current)
            dispatches.append(
                ReminderDispatchResult(
                    reminder=reminder,
                    reminder_id=reminder_id,
                    message_kind="followup",
                    outbound_text=(
                        f"Reminder follow-up: {reminder.get('message')}\n"
                        "Reply `done` or `defer until <time>`."
                    ),
                )
            )

        return state, dispatches

    def scan_and_dispatch_due_reminders(self, *, state: dict[str, Any], chat_id: str, current: datetime | None = None) -> int:
        now = current or reminder_sm.now_utc()
        reminder_state, dispatches = self._collect_due_dispatches(current=now)
        sent = 0
        if not dispatches:
            return sent
        for item in dispatches:
            response = self.client.send_message(chat_id=chat_id, text=item.outbound_text)
            self._remember_reminder_message(
                state,
                chat_id=chat_id,
                message_id=int(response.get("message_id")) if response.get("message_id") is not None else None,
                reminder_id=item.reminder_id,
                message_kind=item.message_kind,
            )
            sent += 1
        self._save_reminder_state(reminder_state)
        return sent

    def _calendar_client(self) -> tuple[Any, str]:
        calendar_runtime.resolve_calendar_integration(self.root / "config" / "integrations.yaml")
        default_timezone = calendar_runtime.resolve_default_timezone(self.env_values, self.root)
        calendar_id = calendar_runtime.resolve_calendar_id(env_file_values=self.env_values, override=None)
        client = calendar_runtime.build_client(env_file_values=self.env_values, fixtures_file=None)
        return client, default_timezone

    def _personal_task_client(self) -> tuple[str, Any]:
        personal_task_runtime.resolve_personal_task_integration(self.root / "config" / "integrations.yaml")
        provider = personal_task_runtime.resolve_provider(
            env_file_values=self.env_values,
            override=None,
            fixtures_file=None,
        )
        client = personal_task_runtime.build_client(
            provider=provider,
            env_file_values=self.env_values,
            fixtures_file=None,
        )
        return provider, client

    def _handle_calendar_today(self) -> str:
        try:
            client, timezone_name = self._calendar_client()
            calendar_id = calendar_runtime.resolve_calendar_id(env_file_values=self.env_values, override=None)
            events = calendar_runtime.list_upcoming(
                client,
                calendar_id=calendar_id,
                default_timezone=timezone_name,
                limit=12,
                window_days=7,
            )
            today_local = datetime.now(ZoneInfo(timezone_name)).date()
            today_events = [row for row in events if event_local_date(row, timezone_name) == today_local]
            return format_calendar_lines(today_events, timezone_name, heading="Calendar today")
        except Exception:
            return "Calendar is not configured yet."

    def _handle_calendar_next(self) -> str:
        try:
            client, timezone_name = self._calendar_client()
            calendar_id = calendar_runtime.resolve_calendar_id(env_file_values=self.env_values, override=None)
            events = calendar_runtime.list_upcoming(
                client,
                calendar_id=calendar_id,
                default_timezone=timezone_name,
                limit=6,
                window_days=14,
            )
            return format_calendar_lines(events, timezone_name, heading="Upcoming calendar items")
        except Exception:
            return "Calendar is not configured yet."

    def _handle_tasks_list(self) -> str:
        try:
            _, client = self._personal_task_client()
            tasks = personal_task_runtime.list_personal_tasks(client, limit=8, filter_text=None)
            if not tasks:
                return "Open tasks\n- none"
            lines = ["Open tasks"]
            for task in tasks[:8]:
                due = str(task.get("due_value") or "").strip() or "-"
                lines.append(f"- {task.get('title')} | due={due}")
            return "\n".join(lines)
        except Exception:
            return "Personal task provider is not configured yet."

    def _handle_task_create(self, text: str) -> str:
        parsed = parse_task_create_text(text)
        if not parsed:
            raise ValueError("invalid task create text")
        title, due_string = parsed
        try:
            result = self.backend.create_personal_task_runtime(
                title=title,
                due_string=due_string,
                apply=True,
            )
            recent = ensure_dict(ensure_dict(result.get("status")).get("recent_results", [{}])[0])
            due_note = f" | due={due_string}" if due_string else ""
            return f"Created personal task: {recent.get('title') or title}{due_note}"
        except Exception:
            return "Personal task provider is not configured yet."

    def _handle_status(self) -> str:
        snapshot = self.backend.build_state()
        agent_runtime = ensure_dict(snapshot.get("agent_runtime"))
        activity = ensure_dict(agent_runtime.get("activity"))
        last_route = ensure_dict(activity.get("last_route"))
        reminders = ensure_dict(snapshot.get("reminders"))
        calendar_runtime_state = ensure_dict(snapshot.get("calendar_runtime"))
        personal_tasks = ensure_dict(snapshot.get("personal_tasks"))
        braindump = ensure_dict(snapshot.get("braindump"))
        workspace = ensure_dict(snapshot.get("workspace"))
        lines = [
            "OpenClaw status",
            f"- Reminders pending: {ensure_dict(reminders.get('counts')).get('pending', 0)}",
            f"- Reminders awaiting reply: {ensure_dict(reminders.get('counts')).get('awaiting_reply', 0)}",
            f"- Calendar upcoming: {ensure_dict(calendar_runtime_state.get('summary')).get('upcoming_count', 0)}",
            f"- Personal tasks open: {ensure_dict(personal_tasks.get('summary')).get('open_count', 0)}",
            f"- Braindump due: {ensure_dict(braindump.get('counts')).get('due_for_review', 0)}",
            f"- Active projects: {ensure_dict(workspace.get('project_counts')).get('active', 0)}",
            f"- Front door agent: {agent_runtime.get('default_user_facing_agent') or 'assistant'}",
        ]
        if last_route:
            lines.append(
                f"- Last route: {last_route.get('agent_id')} -> {last_route.get('space_key')} ({last_route.get('route_mode')})"
            )
        return "\n".join(lines)

    def _handle_project_capture(self, text: str) -> str:
        result = self.backend.create_agent_routed_task(text=text, source="telegram")
        route = ensure_dict(result.get("route"))
        task = ensure_dict(result.get("task"))
        agent_label = str(ensure_dict(route.get("agent")).get("label", route.get("agent_id", "assistant"))).strip()
        return f"Project task captured for {agent_label}: {task.get('title')}"

    def _record_agent_activity(
        self,
        *,
        agent_id: str,
        space_key: str,
        action: str,
        text: str | None = None,
        route_mode: str = "default_front_door",
        lane: str | None = None,
    ) -> None:
        self.backend.record_agent_activity(
            agent_id=agent_id,
            space_key=space_key,
            source="telegram",
            action=action,
            text=text,
            route_mode=route_mode,
            lane=lane,
        )

    def _handle_specialist_capture(self, text: str, route: dict[str, Any]) -> str:
        try:
            result = self.backend.create_agent_routed_task(text=text, source="telegram")
        except ValueError as exc:
            if route.get("kind") == "project" and route.get("matched") and not route.get("resolved"):
                return self._format_unknown_project_route(route)
            raise exc
        task = ensure_dict(result.get("task"))
        resolved_route = ensure_dict(result.get("route"))
        agent = ensure_dict(resolved_route.get("agent"))
        label = str(agent.get("label", resolved_route.get("agent_id", "assistant"))).strip() or "assistant"
        space_key = str(resolved_route.get("space_key") or "general").strip()
        project_note = (
            f" in project {resolved_route.get('project_name')}"
            if str(resolved_route.get("project_name") or "").strip()
            else ""
        )
        return f"Routed to {label} in {space_key}{project_note}. Task created: {task.get('title')}"

    def _format_unknown_project_route(self, route: dict[str, Any]) -> str:
        requested = str(route.get("space_key") or "project").strip()
        suggestions = [ensure_dict(item) for item in route.get("suggested_projects", []) if isinstance(item, dict)]
        if suggestions:
            suggestion_text = " | ".join(
                f"{row.get('name')} -> {row.get('entry_command_hint') or row.get('space_key')}"
                for row in suggestions[:3]
            )
            return f"Project space not found: {requested}. Closest matches: {suggestion_text}"
        return f"Project space not found: {requested}. Create the project first or use an existing [project:slug]."

    def _handle_agent_chat(self, *, agent_id: str, text: str, route: dict[str, Any]) -> str:
        runtime = self.agent_chats.get(agent_id)
        if runtime is None:
            return f"{agent_id} chat is not enabled."
        try:
            result = runtime.reply(text=text, route=route)
        except Exception as exc:  # noqa: BLE001
            return f"{agent_id} chat is not ready for that request: {exc}"
        lane = str(result.get("lane") or "").strip() or None
        provider = str(result.get("provider") or "").strip() or None
        model = str(result.get("model") or "").strip() or None
        self._record_agent_activity(
            agent_id=agent_id,
            space_key=str(result.get("space_key") or route.get("space_key") or "general"),
            action="agent_chat",
            text=text,
            route_mode=str(route.get("route_mode") or "default_front_door"),
            lane=lane,
        )
        runtime_state = self.backend._load_agent_runtime_state()
        last_route = ensure_dict(runtime_state.get("last_route"))
        if last_route:
            if lane:
                last_route["lane"] = lane
            if provider:
                last_route["provider"] = provider
            if model:
                last_route["model"] = model
            recent = [ensure_dict(item) for item in runtime_state.get("recent_routes", [])]
            if recent:
                recent[-1] = last_route
                runtime_state["recent_routes"] = recent
            runtime_state["last_route"] = last_route
            self.backend._save_agent_runtime_state(runtime_state)
        return str(result.get("reply_text") or "").strip()

    def handle_message(self, message: dict[str, Any], *, state: dict[str, Any]) -> list[str]:
        event = normalize_telegram({"message": message})
        chat_id = str(event.get("channel_id") or "").strip()
        if not chat_id or chat_id != self.allowed_chat_id:
            return []

        text = str(event.get("text") or "").strip()
        if not text:
            return []

        route = self.backend.route_text_to_space(text=text)
        routed_text = str(route.get("stripped_text") or "").strip() or text.strip()
        explicit_specialist = bool(route.get("explicit_agent")) and str(route.get("agent_id")) != "assistant"
        explicit_assistant_space = bool(route.get("explicit_space")) and str(route.get("agent_id")) == "assistant"
        agent_id = str(route.get("agent_id") or "assistant").strip() or "assistant"

        command_name, body = parse_command_text(routed_text)
        reply_to_message_id = message.get("reply_to_message", {}).get("message_id") if isinstance(message.get("reply_to_message"), dict) else None

        if command_name in {"start", "help"} or routed_text.strip().lower() == "help":
            return [HELP_TEXT]

        if command_name == "status" or routed_text.strip().lower() == "status":
            self._record_agent_activity(
                agent_id="assistant",
                space_key="general",
                action="status",
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_status()]

        if explicit_specialist:
            if route.get("kind") == "project" and not route.get("resolved"):
                return [self._format_unknown_project_route(route)]
            if agent_id in CONVERSATIONAL_SPECIALISTS:
                return [self._handle_agent_chat(agent_id=agent_id, text=routed_text, route=route)]
            return [self._handle_specialist_capture(text, route)]

        if command_name == "calendar":
            if body.lower() in {"", "today"}:
                self._record_agent_activity(
                    agent_id="assistant",
                    space_key="calendar",
                    action="calendar_today",
                    route_mode=str(route.get("route_mode") or "default_front_door"),
                )
                return [self._handle_calendar_today()]
            if body.lower() in {"next", "upcoming"}:
                self._record_agent_activity(
                    agent_id="assistant",
                    space_key="calendar",
                    action="calendar_next",
                    route_mode=str(route.get("route_mode") or "default_front_door"),
                )
                return [self._handle_calendar_next()]

        if is_calendar_today_request(routed_text):
            self._record_agent_activity(
                agent_id="assistant",
                space_key="calendar",
                action="calendar_today",
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_calendar_today()]
        if is_calendar_next_request(routed_text):
            self._record_agent_activity(
                agent_id="assistant",
                space_key="calendar",
                action="calendar_next",
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_calendar_next()]

        if command_name == "tasks" or is_task_list_request(routed_text):
            self._record_agent_activity(
                agent_id="assistant",
                space_key="tasks",
                action="tasks_list",
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_tasks_list()]

        if command_name in {"task", "add-task"}:
            self._record_agent_activity(
                agent_id="assistant",
                space_key="tasks",
                action="task_create",
                text=body,
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_task_create(f"task {body}")]

        if parse_task_create_text(routed_text):
            self._record_agent_activity(
                agent_id="assistant",
                space_key="tasks",
                action="task_create",
                text=routed_text,
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_task_create(routed_text)]

        try:
            braindump_runtime.parse_capture_text(routed_text)
            result = self.backend.capture_braindump_text(text=text, source="telegram")
            item = ensure_dict(result.get("item"))
            self._record_agent_activity(
                agent_id="assistant",
                space_key="braindump",
                action="braindump_capture",
                text=str(item.get("short_text") or routed_text),
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [f"Braindump captured: [{item.get('category')}] {item.get('short_text')}"]
        except ValueError as exc:
            if route.get("kind") == "project" and route.get("matched") and not route.get("resolved"):
                return [self._format_unknown_project_route(route)]
            if str(exc).startswith("project space not found:"):
                return [self._format_unknown_project_route(route)]
            pass

        reply_candidate = reminder_sm.parse_reply_text(routed_text)
        if reply_candidate[0] != "ignore":
            reminder_id = self._reply_linked_reminder_id(
                state,
                chat_id=chat_id,
                reply_to_message_id=int(reply_to_message_id) if reply_to_message_id is not None else None,
            )
            self._record_agent_activity(
                agent_id="assistant",
                space_key="reminders",
                action="reminder_reply",
                text=routed_text,
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_reminder_reply(routed_text, reminder_id=reminder_id)]

        if reminder_sm.parse_create_text(routed_text):
            _, confirmation = self._create_reminder_from_text(routed_text)
            self._record_agent_activity(
                agent_id="assistant",
                space_key="reminders",
                action="reminder_create",
                text=routed_text,
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [confirmation]

        if route.get("kind") == "project":
            if not route.get("resolved"):
                return [self._format_unknown_project_route(route)]
            return [self._handle_project_capture(text)]

        if explicit_assistant_space or str(route.get("agent_id") or "assistant") == "assistant":
            return [self._handle_agent_chat(agent_id="assistant", text=routed_text, route=route)]

        return ["I did not match that to a supported command.\n" + HELP_TEXT]

    def process_updates(self, updates: list[dict[str, Any]], *, state: dict[str, Any]) -> int:
        handled = 0
        for update in updates:
            update_id = int(update.get("update_id") or 0)
            message = ensure_dict(update.get("message"))
            if not message:
                state["last_update_id"] = max(int(state.get("last_update_id") or 0), update_id)
                continue
            chat = ensure_dict(message.get("chat"))
            chat_id = str(chat.get("id") or "").strip()
            if chat_id != self.allowed_chat_id:
                state["last_update_id"] = max(int(state.get("last_update_id") or 0), update_id)
                continue
            try:
                responses = self.handle_message(message, state=state)
            except Exception as exc:  # noqa: BLE001
                responses = [f"Request failed: {exc}"]
            for response in responses:
                self.client.send_message(chat_id=chat_id, text=response)
            state["last_update_id"] = max(int(state.get("last_update_id") or 0), update_id)
            handled += 1
        self.save_adapter_state(state)
        return handled

    def poll_once(self, *, timeout: int) -> dict[str, Any]:
        state = self.load_adapter_state()
        offset = int(state.get("last_update_id") or 0) + 1
        updates = self.client.get_updates(offset=offset, timeout=timeout)
        processed = self.process_updates(updates, state=state)
        due_sent = self.scan_and_dispatch_due_reminders(state=state, chat_id=self.allowed_chat_id)
        self.save_adapter_state(state)
        return {
            "ok": True,
            "processed_updates": processed,
            "due_messages_sent": due_sent,
            "last_update_id": int(state.get("last_update_id") or 0),
        }

    def run_forever(self, *, timeout: int, interval_seconds: int) -> int:
        while True:
            try:
                self.poll_once(timeout=timeout)
            except urllib.error.URLError as exc:
                print(f"[telegram-adapter] network error: {exc}", file=sys.stderr)
                time.sleep(max(interval_seconds, 5))
            except KeyboardInterrupt:
                return 0
            except Exception as exc:  # noqa: BLE001
                print(f"[telegram-adapter] unexpected error: {exc}", file=sys.stderr)
                time.sleep(max(interval_seconds, 5))


def resolve_default_timezone(root: Path, env_values: dict[str, str]) -> str:
    env_tz = env_get("OPENCLAW_TIMEZONE", env_values)
    if env_tz:
        return env_tz
    reminders_cfg = load_yaml_dict(root / "config" / "reminders.yaml")
    reminders = ensure_dict(reminders_cfg.get("reminders"))
    return str(reminders.get("default_timezone") or "America/Guayaquil")


def resolve_reminder_state_path(root: Path, *, configured_file: str | None, prefer_configured: bool) -> Path:
    fallback = root / "data" / "reminders-state.json"
    if configured_file:
        path = Path(configured_file).expanduser()
        if not path.is_absolute():
            return (root / path).resolve()
        if prefer_configured or path.exists():
            return path

    cfg = load_yaml_dict(root / "config" / "reminders.yaml")
    storage = ensure_dict(cfg.get("storage"))
    configured = str(storage.get("state_file") or "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            return (root / path).resolve()
        if prefer_configured or path.exists():
            return path
    return fallback


def resolve_env_path(root: Path, arg_value: str | None) -> Path | None:
    if arg_value:
        path = Path(arg_value).expanduser()
        return path.resolve() if path.exists() else path
    local = root / "secrets" / "openclaw.env"
    if local.exists():
        return local
    if DEFAULT_ENV.exists():
        return DEFAULT_ENV
    return None


def build_adapter(args: argparse.Namespace) -> TelegramAdapter:
    root = Path(args.root).expanduser().resolve()
    backend = DashboardBackend(root=root)
    env_path = resolve_env_path(root, args.env_file)
    env_values = load_env_values(env_path)
    token = env_get("TELEGRAM_BOT_TOKEN", env_values)
    allowed_chat_id = env_get("TELEGRAM_ALLOWED_CHAT_ID", env_values)
    if not token:
        raise RuntimeError("missing TELEGRAM_BOT_TOKEN")
    if not allowed_chat_id:
        raise RuntimeError("missing TELEGRAM_ALLOWED_CHAT_ID")
    client = TelegramAPI(token)
    state_path = Path(args.state_file).expanduser().resolve() if args.state_file else (root / "data" / "telegram-adapter-state.json")
    reminder_state_path = resolve_reminder_state_path(
        root,
        configured_file=args.reminder_state_file,
        prefer_configured=True,
    )
    default_timezone = resolve_default_timezone(root, env_values)
    return TelegramAdapter(
        root=root,
        backend=backend,
        client=client,
        allowed_chat_id=allowed_chat_id,
        env_values=env_values,
        state_path=state_path,
        reminder_state_path=reminder_state_path,
        default_timezone=default_timezone,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram long-polling adapter for OpenClaw MVP")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--env-file", help="env file path (defaults to secrets/openclaw.env or /etc/openclaw/openclaw.env)")
    parser.add_argument("--state-file", help="adapter state file path")
    parser.add_argument("--reminder-state-file", help="override reminder state file path")
    parser.add_argument("--poll-timeout", type=int, default=20)
    parser.add_argument("--interval-seconds", type=int, default=5)
    parser.add_argument("--once", action="store_true", help="poll once then exit")
    parser.add_argument("--json", action="store_true", help="emit JSON on --once")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    adapter = build_adapter(args)
    if args.once:
        payload = adapter.poll_once(timeout=args.poll_timeout)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                "\n".join(
                    [
                        "Telegram adapter poll summary:",
                        f"- Processed updates: {payload['processed_updates']}",
                        f"- Due messages sent: {payload['due_messages_sent']}",
                        f"- Last update id: {payload['last_update_id']}",
                    ]
                )
            )
        return 0
    return adapter.run_forever(timeout=args.poll_timeout, interval_seconds=args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
