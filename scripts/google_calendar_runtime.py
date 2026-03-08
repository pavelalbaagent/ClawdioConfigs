#!/usr/bin/env python3
"""Google Calendar runtime for snapshotting and explicit write operations."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from google_workspace_common import (  # type: ignore
    GoogleApiClient,
    GoogleOAuthClient,
    ensure_dict,
    ensure_string_list,
    get_integration_config,
    load_yaml,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "integrations.yaml"
DEFAULT_STATUS_PATH = ROOT / "data" / "calendar-runtime-status.json"
DEFAULT_CANDIDATES_PATH = ROOT / "data" / "calendar-candidates.json"

READY_CANDIDATE_STATUSES = {"ready", "approved"}
PENDING_CANDIDATE_STATUSES = {"proposed", "ready", "approved", "needs_details"}


@dataclass
class EventSpec:
    payload: dict[str, Any]
    time_mode: str


class CalendarClient:
    def __init__(self, api: GoogleApiClient):
        self.api = api

    def list_upcoming_events(
        self,
        calendar_id: str,
        *,
        time_min: str,
        time_max: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        payload = self.api.request_json(
            "GET",
            f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id, safe='')}/events",
            query={
                "singleEvents": "true",
                "orderBy": "startTime",
                "timeMin": time_min,
                "timeMax": time_max,
                "maxResults": max(1, min(limit, 250)),
                "fields": (
                    "items(id,status,summary,description,location,htmlLink,created,updated,"
                    "start,end,organizer(email),attendees(email,responseStatus))"
                ),
            },
        )
        return [ensure_dict(item) for item in payload.get("items", []) if isinstance(item, dict)]

    def create_event(self, calendar_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.api.request_json(
            "POST",
            f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id, safe='')}/events",
            payload=payload,
        )

    def update_event(self, calendar_id: str, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.api.request_json(
            "PATCH",
            f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}",
            payload=payload,
        )


class FixtureCalendarClient:
    def __init__(self, *, events: list[dict[str, Any]]):
        self.events = [ensure_dict(item) for item in events]
        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []

    def list_upcoming_events(
        self,
        calendar_id: str,
        *,
        time_min: str,
        time_max: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        lower = parse_datetime_text(time_min, "UTC")
        upper = parse_datetime_text(time_max, "UTC") if time_max else None
        rows: list[tuple[datetime, dict[str, Any]]] = []
        for event in self.events:
            normalized = normalize_event(event)
            start_value = normalized.get("start_value")
            if not isinstance(start_value, str) or not start_value:
                continue
            if normalized.get("all_day"):
                try:
                    start_dt = datetime.combine(date.fromisoformat(start_value), datetime.min.time(), tzinfo=timezone.utc)
                except ValueError:
                    continue
            else:
                start_dt = parse_datetime_text(start_value, "UTC")
            if start_dt < lower:
                continue
            if upper is not None and start_dt > upper:
                continue
            rows.append((start_dt, event))
        rows.sort(key=lambda item: item[0])
        return [ensure_dict(item[1]) for item in rows[:limit]]

    def create_event(self, calendar_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        item = {
            "id": f"evt-{len(self.events) + len(self.created) + 1}",
            "status": "confirmed",
            "summary": str(payload.get("summary") or "").strip(),
            "description": str(payload.get("description") or "").strip(),
            "location": str(payload.get("location") or "").strip(),
            "htmlLink": f"https://calendar.google.test/event/{len(self.events) + len(self.created) + 1}",
            "created": now_iso(),
            "updated": now_iso(),
            "start": ensure_dict(payload.get("start")),
            "end": ensure_dict(payload.get("end")),
            "attendees": [ensure_dict(item) for item in payload.get("attendees", []) if isinstance(item, dict)],
        }
        self.events.append(item)
        self.created.append(item)
        return item

    def update_event(self, calendar_id: str, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        for index, existing in enumerate(self.events):
            if str(existing.get("id") or "") != event_id:
                continue
            updated = dict(existing)
            for key, value in payload.items():
                if value in ("", None, []):
                    continue
                updated[key] = value
            updated["updated"] = now_iso()
            self.events[index] = updated
            self.updated.append(updated)
            return updated
        raise RuntimeError(f"fixture event not found: {event_id}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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


def resolve_calendar_integration(config_path: Path) -> dict[str, Any]:
    integration = get_integration_config(config_path, "calendar")
    if integration.get("enabled") is not True:
        raise RuntimeError("calendar integration is disabled in config")
    return integration


def resolve_default_timezone(env_file_values: dict[str, str], root: Path = ROOT) -> str:
    env_value = env_get("OPENCLAW_TIMEZONE", env_file_values)
    if env_value:
        return env_value
    core_path = root / "config" / "core.yaml"
    core = ensure_dict(load_yaml(core_path)) if core_path.exists() else {}
    owner = ensure_dict(core.get("owner"))
    value = str(owner.get("timezone") or "").strip()
    return value or "UTC"


def resolve_calendar_id(
    *,
    env_file_values: dict[str, str],
    override: str | None,
) -> str:
    if override:
        return override.strip()
    calendar_id = env_get("GOOGLE_CALENDAR_ID", env_file_values)
    if not calendar_id:
        raise RuntimeError("missing required calendar env: GOOGLE_CALENDAR_ID")
    return calendar_id


def resolve_status_path(override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_STATUS_PATH


def resolve_candidates_path(override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_CANDIDATES_PATH


def parse_datetime_text(value: str | None, default_timezone: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("datetime value is required")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(default_timezone))
    return parsed.astimezone(timezone.utc)


def canonicalize_datetime(value: str | None, default_timezone: str) -> str:
    return parse_datetime_text(value, default_timezone).isoformat(timespec="seconds")


def parse_date_text(value: str | None) -> date:
    text = str(value or "").strip()
    if not text:
        raise ValueError("date value is required")
    return date.fromisoformat(text)


def build_event_times(
    *,
    start_at: str | None,
    end_at: str | None,
    start_date: str | None,
    end_date: str | None,
    timezone_name: str,
) -> EventSpec:
    if start_at or end_at:
        if not start_at or not end_at:
            raise ValueError("both start_at and end_at are required for timed events")
        start_dt = parse_datetime_text(start_at, timezone_name)
        end_dt = parse_datetime_text(end_at, timezone_name)
        if end_dt <= start_dt:
            raise ValueError("end_at must be later than start_at")
        return EventSpec(
            payload={
                "start": {"dateTime": start_dt.isoformat(timespec="seconds"), "timeZone": timezone_name},
                "end": {"dateTime": end_dt.isoformat(timespec="seconds"), "timeZone": timezone_name},
            },
            time_mode="timed",
        )

    if start_date:
        start_day = parse_date_text(start_date)
        end_day = parse_date_text(end_date) if end_date else (start_day + timedelta(days=1))
        if end_day <= start_day:
            raise ValueError("end_date must be later than start_date for all-day events")
        return EventSpec(
            payload={
                "start": {"date": start_day.isoformat()},
                "end": {"date": end_day.isoformat()},
            },
            time_mode="all_day",
        )

    raise ValueError("event requires either start_at/end_at or start_date[/end_date]")


def build_event_payload(
    *,
    title: str,
    description: str | None,
    location: str | None,
    attendees: list[str] | None,
    start_at: str | None,
    end_at: str | None,
    start_date: str | None,
    end_date: str | None,
    timezone_name: str,
) -> EventSpec:
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("title is required")

    event_times = build_event_times(
        start_at=start_at,
        end_at=end_at,
        start_date=start_date,
        end_date=end_date,
        timezone_name=timezone_name,
    )
    payload: dict[str, Any] = {
        "summary": clean_title,
        "description": (description or "").strip(),
        "location": (location or "").strip(),
        **event_times.payload,
    }
    clean_attendees = [item.strip() for item in (attendees or []) if isinstance(item, str) and item.strip()]
    if clean_attendees:
        payload["attendees"] = [{"email": item} for item in clean_attendees]
    return EventSpec(payload=payload, time_mode=event_times.time_mode)


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    start = ensure_dict(event.get("start"))
    end = ensure_dict(event.get("end"))
    attendees = [ensure_dict(item) for item in event.get("attendees", []) if isinstance(item, dict)]
    start_value = str(start.get("dateTime") or start.get("date") or "").strip() or None
    end_value = str(end.get("dateTime") or end.get("date") or "").strip() or None
    return {
        "id": str(event.get("id") or "").strip(),
        "status": str(event.get("status") or "").strip() or "confirmed",
        "summary": str(event.get("summary") or "").strip() or "(untitled event)",
        "description": str(event.get("description") or "").strip() or None,
        "location": str(event.get("location") or "").strip() or None,
        "html_link": str(event.get("htmlLink") or "").strip() or None,
        "created_at": str(event.get("created") or "").strip() or None,
        "updated_at": str(event.get("updated") or "").strip() or None,
        "start_value": start_value,
        "end_value": end_value,
        "all_day": bool(start.get("date") and not start.get("dateTime")),
        "timezone": str(start.get("timeZone") or end.get("timeZone") or "").strip() or None,
        "organizer_email": str(ensure_dict(event.get("organizer")).get("email") or "").strip() or None,
        "attendees_count": len(attendees),
        "attendee_emails": [str(item.get("email") or "").strip() for item in attendees if str(item.get("email") or "").strip()],
    }


def list_upcoming(
    client: Any,
    *,
    calendar_id: str,
    default_timezone: str,
    limit: int,
    window_days: int,
) -> list[dict[str, Any]]:
    now_dt = datetime.now(ZoneInfo(default_timezone))
    max_dt = now_dt + timedelta(days=window_days)
    events = client.list_upcoming_events(
        calendar_id,
        time_min=now_dt.astimezone(timezone.utc).isoformat(timespec="seconds"),
        time_max=max_dt.astimezone(timezone.utc).isoformat(timespec="seconds"),
        limit=limit,
    )
    normalized = [normalize_event(ensure_dict(item)) for item in events]
    normalized.sort(key=lambda row: str(row.get("start_value") or ""))
    return normalized


def load_candidates(path: Path) -> dict[str, Any]:
    raw = read_json(path)
    if not isinstance(raw, dict):
        return {"items": []}
    if not isinstance(raw.get("items"), list):
        raw["items"] = []
    return raw


def _candidate_title(candidate: dict[str, Any]) -> str:
    return str(candidate.get("title") or candidate.get("summary") or "").strip()


def build_event_from_candidate(candidate: dict[str, Any], default_timezone: str) -> EventSpec:
    title = _candidate_title(candidate)
    if not title:
        raise ValueError("candidate missing title")
    timezone_name = str(candidate.get("timezone") or "").strip() or default_timezone
    attendees: list[str] = []
    raw_attendees = candidate.get("attendees")
    if isinstance(raw_attendees, list):
        for item in raw_attendees:
            if isinstance(item, str) and item.strip():
                attendees.append(item.strip())
            elif isinstance(item, dict):
                email = str(item.get("email") or "").strip()
                if email:
                    attendees.append(email)
    return build_event_payload(
        title=title,
        description=str(candidate.get("description") or candidate.get("excerpt") or "").strip() or None,
        location=str(candidate.get("location") or "").strip() or None,
        attendees=attendees,
        start_at=str(candidate.get("start_at") or "").strip() or None,
        end_at=str(candidate.get("end_at") or "").strip() or None,
        start_date=str(candidate.get("start_date") or "").strip() or None,
        end_date=str(candidate.get("end_date") or "").strip() or None,
        timezone_name=timezone_name,
    )


def apply_calendar_candidates(
    client: Any,
    *,
    calendar_id: str,
    candidates_path: Path,
    default_timezone: str,
    apply: bool,
) -> dict[str, Any]:
    data = load_candidates(candidates_path)
    items = [ensure_dict(item) for item in data.get("items", []) if isinstance(item, dict)]
    now = now_iso()
    results: list[dict[str, Any]] = []
    created_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0

    for item in items:
        status = str(item.get("status") or "proposed").strip().lower() or "proposed"
        candidate_id = str(item.get("id") or "").strip() or "candidate"
        title = _candidate_title(item) or candidate_id

        if status not in READY_CANDIDATE_STATUSES:
            results.append(
                {
                    "candidate_id": candidate_id,
                    "title": title,
                    "action": "skip",
                    "status": "skipped",
                    "reason": f"candidate status {status} is not ready",
                }
            )
            skipped_count += 1
            if apply:
                item["last_apply_at"] = now
                item["last_apply_status"] = "skipped"
                item["last_apply_reason"] = f"candidate status {status} is not ready"
            continue

        try:
            event_spec = build_event_from_candidate(item, default_timezone)
        except ValueError as exc:
            results.append(
                {
                    "candidate_id": candidate_id,
                    "title": title,
                    "action": "skip",
                    "status": "skipped",
                    "reason": str(exc),
                }
            )
            skipped_count += 1
            if apply:
                item["last_apply_at"] = now
                item["last_apply_status"] = "skipped"
                item["last_apply_reason"] = str(exc)
            continue

        action = "update_event" if str(item.get("event_id") or "").strip() else "create_event"
        result_row = {
            "candidate_id": candidate_id,
            "title": title,
            "action": action,
            "status": "preview" if not apply else "scheduled",
            "time_mode": event_spec.time_mode,
        }

        if not apply:
            result_row["payload"] = event_spec.payload
            results.append(result_row)
            continue

        try:
            if action == "create_event":
                event = client.create_event(calendar_id, event_spec.payload)
                created_count += 1
            else:
                event = client.update_event(calendar_id, str(item.get("event_id") or ""), event_spec.payload)
                updated_count += 1
            normalized = normalize_event(ensure_dict(event))
            item["status"] = "scheduled"
            item["event_id"] = normalized.get("id")
            item["event_html_link"] = normalized.get("html_link")
            item["scheduled_at"] = now
            item["updated_at"] = now
            item["last_apply_at"] = now
            item["last_apply_status"] = "scheduled"
            item["last_apply_reason"] = action
            results.append(
                {
                    **result_row,
                    "status": "scheduled",
                    "event_id": normalized.get("id"),
                    "event_html_link": normalized.get("html_link"),
                }
            )
        except Exception as exc:  # pragma: no cover - exercised in integration failure paths
            error_count += 1
            item["last_apply_at"] = now
            item["last_apply_status"] = "error"
            item["last_apply_reason"] = str(exc)
            results.append(
                {
                    **result_row,
                    "status": "error",
                    "reason": str(exc),
                }
            )

    if apply:
        data["items"] = items
        write_json(candidates_path, data)

    pending_candidate_count = len(
        [
            item
            for item in items
            if str(item.get("status") or "proposed").strip().lower() in PENDING_CANDIDATE_STATUSES
        ]
    )
    return {
        "results": results,
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "pending_candidate_count": pending_candidate_count,
    }


def build_status_payload(
    *,
    calendar_id: str,
    action: str,
    dry_run: bool,
    upcoming_events: list[dict[str, Any]],
    recent_results: list[dict[str, Any]],
    window_days: int,
    pending_candidate_count: int | None = None,
    created_count: int = 0,
    updated_count: int = 0,
    skipped_count: int = 0,
    error_count: int = 0,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "action": action,
        "dry_run": dry_run,
        "window_days": window_days,
        "upcoming_count": len(upcoming_events),
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
    }
    if pending_candidate_count is not None:
        summary["pending_candidate_count"] = pending_candidate_count

    return {
        "generated_at": now_iso(),
        "calendar_id": calendar_id,
        "summary": summary,
        "recent_results": recent_results[:20],
        "upcoming_events": upcoming_events[:25],
    }


def human_output(payload: dict[str, Any]) -> str:
    summary = ensure_dict(payload.get("summary"))
    lines = [
        "Google Calendar runtime summary:",
        f"- Action: {summary.get('action') or '-'}",
        f"- Dry run: {'yes' if summary.get('dry_run') else 'no'}",
        f"- Upcoming events: {summary.get('upcoming_count') or 0}",
        f"- Created: {summary.get('created_count') or 0}",
        f"- Updated: {summary.get('updated_count') or 0}",
        f"- Skipped: {summary.get('skipped_count') or 0}",
        f"- Errors: {summary.get('error_count') or 0}",
    ]
    if "pending_candidate_count" in summary:
        lines.append(f"- Pending candidates: {summary.get('pending_candidate_count') or 0}")
    return "\n".join(lines)


def build_client(
    *,
    env_file_values: dict[str, str],
    fixtures_file: str | None,
) -> Any:
    if fixtures_file:
        data = ensure_dict(json.loads(Path(fixtures_file).expanduser().resolve().read_text(encoding="utf-8")))
        events = [ensure_dict(item) for item in data.get("events", []) if isinstance(item, dict)]
        return FixtureCalendarClient(events=events)

    oauth = GoogleOAuthClient(
        client_id=env_get("GOOGLE_CLIENT_ID", env_file_values),
        client_secret=env_get("GOOGLE_CLIENT_SECRET", env_file_values),
        refresh_token=env_get("GOOGLE_REFRESH_TOKEN", env_file_values),
    )
    missing = [
        name
        for name, value in {
            "GOOGLE_CLIENT_ID": oauth.client_id,
            "GOOGLE_CLIENT_SECRET": oauth.client_secret,
            "GOOGLE_REFRESH_TOKEN": oauth.refresh_token,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError("missing required Google OAuth env: " + ", ".join(missing))
    access_token = oauth.fetch_access_token()
    return CalendarClient(GoogleApiClient(access_token))


def run_snapshot(args: argparse.Namespace) -> int:
    env_file_values = load_env_file(Path(args.env_file).expanduser().resolve()) if args.env_file else {}
    resolve_calendar_integration(Path(args.config).expanduser().resolve())
    default_timezone = resolve_default_timezone(env_file_values)
    calendar_id = resolve_calendar_id(env_file_values=env_file_values, override=args.calendar_id)
    client = build_client(env_file_values=env_file_values, fixtures_file=args.fixtures_file)
    status_path = resolve_status_path(args.status_file)

    upcoming_events = list_upcoming(
        client,
        calendar_id=calendar_id,
        default_timezone=default_timezone,
        limit=int(args.upcoming_limit or 20),
        window_days=int(args.window_days or 14),
    )
    payload = build_status_payload(
        calendar_id=calendar_id,
        action="snapshot",
        dry_run=False,
        upcoming_events=upcoming_events,
        recent_results=[],
        window_days=int(args.window_days or 14),
    )
    write_json(status_path, payload)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(human_output(payload))
    return 0


def run_create(args: argparse.Namespace) -> int:
    env_file_values = load_env_file(Path(args.env_file).expanduser().resolve()) if args.env_file else {}
    resolve_calendar_integration(Path(args.config).expanduser().resolve())
    default_timezone = str(args.timezone or "").strip() or resolve_default_timezone(env_file_values)
    calendar_id = resolve_calendar_id(env_file_values=env_file_values, override=args.calendar_id)
    client = build_client(env_file_values=env_file_values, fixtures_file=args.fixtures_file)
    status_path = resolve_status_path(args.status_file)
    event_spec = build_event_payload(
        title=args.title,
        description=args.description,
        location=args.location,
        attendees=args.attendee,
        start_at=args.start_at,
        end_at=args.end_at,
        start_date=args.start_date,
        end_date=args.end_date,
        timezone_name=default_timezone,
    )

    result: dict[str, Any]
    if args.apply:
        event = client.create_event(calendar_id, event_spec.payload)
        normalized = normalize_event(ensure_dict(event))
        result = {
            "action": "create_event",
            "status": "scheduled",
            "time_mode": event_spec.time_mode,
            "event_id": normalized.get("id"),
            "event_html_link": normalized.get("html_link"),
            "title": normalized.get("summary"),
        }
    else:
        result = {
            "action": "create_event",
            "status": "preview",
            "time_mode": event_spec.time_mode,
            "payload": event_spec.payload,
            "title": args.title.strip(),
        }

    upcoming_events = list_upcoming(
        client,
        calendar_id=calendar_id,
        default_timezone=default_timezone,
        limit=int(args.upcoming_limit or 20),
        window_days=int(args.window_days or 14),
    )
    payload = build_status_payload(
        calendar_id=calendar_id,
        action="create_event",
        dry_run=not args.apply,
        upcoming_events=upcoming_events,
        recent_results=[result],
        window_days=int(args.window_days or 14),
        created_count=1 if args.apply else 0,
    )
    write_json(status_path, payload)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(human_output(payload))
    return 0


def run_update(args: argparse.Namespace) -> int:
    env_file_values = load_env_file(Path(args.env_file).expanduser().resolve()) if args.env_file else {}
    resolve_calendar_integration(Path(args.config).expanduser().resolve())
    default_timezone = str(args.timezone or "").strip() or resolve_default_timezone(env_file_values)
    calendar_id = resolve_calendar_id(env_file_values=env_file_values, override=args.calendar_id)
    client = build_client(env_file_values=env_file_values, fixtures_file=args.fixtures_file)
    status_path = resolve_status_path(args.status_file)

    payload: dict[str, Any] = {}
    if args.title:
        payload["summary"] = args.title.strip()
    if args.description is not None:
        payload["description"] = args.description.strip()
    if args.location is not None:
        payload["location"] = args.location.strip()
    if args.attendee:
        payload["attendees"] = [{"email": item.strip()} for item in args.attendee if item.strip()]
    if args.start_at or args.end_at or args.start_date or args.end_date:
        event_times = build_event_times(
            start_at=args.start_at,
            end_at=args.end_at,
            start_date=args.start_date,
            end_date=args.end_date,
            timezone_name=default_timezone,
        )
        payload.update(event_times.payload)
        time_mode = event_times.time_mode
    else:
        time_mode = None

    if not payload:
        raise ValueError("update requires at least one field to change")

    result: dict[str, Any]
    if args.apply:
        event = client.update_event(calendar_id, args.event_id.strip(), payload)
        normalized = normalize_event(ensure_dict(event))
        result = {
            "action": "update_event",
            "status": "scheduled",
            "time_mode": time_mode,
            "event_id": normalized.get("id"),
            "event_html_link": normalized.get("html_link"),
            "title": normalized.get("summary"),
        }
    else:
        result = {
            "action": "update_event",
            "status": "preview",
            "time_mode": time_mode,
            "event_id": args.event_id.strip(),
            "payload": payload,
        }

    upcoming_events = list_upcoming(
        client,
        calendar_id=calendar_id,
        default_timezone=default_timezone,
        limit=int(args.upcoming_limit or 20),
        window_days=int(args.window_days or 14),
    )
    payload_status = build_status_payload(
        calendar_id=calendar_id,
        action="update_event",
        dry_run=not args.apply,
        upcoming_events=upcoming_events,
        recent_results=[result],
        window_days=int(args.window_days or 14),
        updated_count=1 if args.apply else 0,
    )
    write_json(status_path, payload_status)
    if args.json:
        print(json.dumps(payload_status, indent=2))
    else:
        print(human_output(payload_status))
    return 0


def run_apply_candidates(args: argparse.Namespace) -> int:
    env_file_values = load_env_file(Path(args.env_file).expanduser().resolve()) if args.env_file else {}
    resolve_calendar_integration(Path(args.config).expanduser().resolve())
    default_timezone = resolve_default_timezone(env_file_values)
    calendar_id = resolve_calendar_id(env_file_values=env_file_values, override=args.calendar_id)
    client = build_client(env_file_values=env_file_values, fixtures_file=args.fixtures_file)
    status_path = resolve_status_path(args.status_file)
    candidates_path = resolve_candidates_path(args.candidates_file)

    outcome = apply_calendar_candidates(
        client,
        calendar_id=calendar_id,
        candidates_path=candidates_path,
        default_timezone=default_timezone,
        apply=args.apply,
    )
    upcoming_events = list_upcoming(
        client,
        calendar_id=calendar_id,
        default_timezone=default_timezone,
        limit=int(args.upcoming_limit or 20),
        window_days=int(args.window_days or 14),
    )
    payload = build_status_payload(
        calendar_id=calendar_id,
        action="apply_candidates",
        dry_run=not args.apply,
        upcoming_events=upcoming_events,
        recent_results=outcome["results"],
        window_days=int(args.window_days or 14),
        pending_candidate_count=int(outcome["pending_candidate_count"]),
        created_count=int(outcome["created_count"]),
        updated_count=int(outcome["updated_count"]),
        skipped_count=int(outcome["skipped_count"]),
        error_count=int(outcome["error_count"]),
    )
    write_json(status_path, payload)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(human_output(payload))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="path to integrations config file")
    parser.add_argument("--env-file", help="env file containing Google OAuth values")
    parser.add_argument("--calendar-id", help="override GOOGLE_CALENDAR_ID")
    parser.add_argument("--status-file", help="write runtime status JSON to this path")
    parser.add_argument("--fixtures-file", help="JSON fixture file with calendar events for offline tests")
    parser.add_argument("--json", action="store_true")

    subparsers = parser.add_subparsers(dest="command")

    sync_parser = subparsers.add_parser("snapshot", help="refresh upcoming events snapshot")
    sync_parser.add_argument("--upcoming-limit", type=int, default=20)
    sync_parser.add_argument("--window-days", type=int, default=14)
    sync_parser.set_defaults(func=run_snapshot)

    create_parser = subparsers.add_parser("create", help="create a calendar event")
    create_parser.add_argument("--title", required=True)
    create_parser.add_argument("--description")
    create_parser.add_argument("--location")
    create_parser.add_argument("--attendee", action="append", default=[])
    create_parser.add_argument("--start-at")
    create_parser.add_argument("--end-at")
    create_parser.add_argument("--start-date")
    create_parser.add_argument("--end-date")
    create_parser.add_argument("--timezone")
    create_parser.add_argument("--upcoming-limit", type=int, default=20)
    create_parser.add_argument("--window-days", type=int, default=14)
    create_parser.add_argument("--apply", action="store_true")
    create_parser.set_defaults(func=run_create)

    update_parser = subparsers.add_parser("update", help="update a calendar event")
    update_parser.add_argument("--event-id", required=True)
    update_parser.add_argument("--title")
    update_parser.add_argument("--description")
    update_parser.add_argument("--location")
    update_parser.add_argument("--attendee", action="append", default=[])
    update_parser.add_argument("--start-at")
    update_parser.add_argument("--end-at")
    update_parser.add_argument("--start-date")
    update_parser.add_argument("--end-date")
    update_parser.add_argument("--timezone")
    update_parser.add_argument("--upcoming-limit", type=int, default=20)
    update_parser.add_argument("--window-days", type=int, default=14)
    update_parser.add_argument("--apply", action="store_true")
    update_parser.set_defaults(func=run_update)

    apply_parser = subparsers.add_parser("apply-candidates", help="apply ready calendar candidates to Google Calendar")
    apply_parser.add_argument("--candidates-file", help="calendar candidates JSON path")
    apply_parser.add_argument("--upcoming-limit", type=int, default=20)
    apply_parser.add_argument("--window-days", type=int, default=14)
    apply_parser.add_argument("--apply", action="store_true")
    apply_parser.set_defaults(func=run_apply_candidates)

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
