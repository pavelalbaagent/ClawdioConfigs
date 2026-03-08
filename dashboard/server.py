#!/usr/bin/env python3
"""Local dashboard server for OpenClaw config and telemetry control."""

from __future__ import annotations

import argparse
import hmac
import json
import mimetypes
import os
import secrets
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from backend import DashboardBackend, ensure_dict


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
SESSION_COOKIE_NAME = "openclaw_dash_session"


class DashboardAuthManager:
    def __init__(self, backend: DashboardBackend) -> None:
        self.backend = backend
        self.sessions: dict[str, dict[str, Any]] = {}
        self.generated_tokens: dict[str, str] = {}

    def _settings(self) -> dict[str, Any]:
        cfg = self.backend.read_dashboard_config()
        dash = ensure_dict(cfg.get("dashboard"))
        auth = ensure_dict(dash.get("auth"))

        require_token = bool(auth.get("require_token", True))
        token_env_key = str(auth.get("token_env_key", "OPENCLAW_DASHBOARD_TOKEN")).strip()
        if not token_env_key:
            token_env_key = "OPENCLAW_DASHBOARD_TOKEN"

        ttl = auth.get("session_ttl_minutes", 720)
        ttl_minutes = int(ttl) if isinstance(ttl, int) else 720
        if ttl_minutes <= 0:
            ttl_minutes = 720

        return {
            "require_token": require_token,
            "token_env_key": token_env_key,
            "session_ttl_minutes": ttl_minutes,
            "allow_generated_token": bool(auth.get("allow_generated_token", False)),
        }

    def _cleanup_sessions(self) -> None:
        now = time.time()
        stale = [sid for sid, row in self.sessions.items() if float(row.get("expires_at", 0)) <= now]
        for sid in stale:
            self.sessions.pop(sid, None)

    def _expected_token(self, settings: dict[str, Any]) -> tuple[str, str]:
        env_key = settings["token_env_key"]
        token = os.environ.get(env_key, "").strip()
        if token:
            return token, "env"

        if bool(settings.get("require_token")) and bool(settings.get("allow_generated_token")):
            cached = self.generated_tokens.get(env_key)
            if cached:
                return cached, "generated"

            generated = secrets.token_urlsafe(24)
            self.generated_tokens[env_key] = generated
            print(f"[dashboard] generated temporary token for {env_key}: {generated}")
            return generated, "generated"

        if bool(settings.get("require_token")):
            return "", "missing"

        return "", "none"

    def startup_status(self) -> dict[str, Any]:
        settings = self._settings()
        token, source = self._expected_token(settings)
        configured = (not settings["require_token"]) or bool(token)
        return {
            "settings": settings,
            "token": token,
            "token_source": source,
            "configured": configured,
        }

    @staticmethod
    def _parse_cookie_header(header_value: str | None) -> dict[str, str]:
        if not header_value:
            return {}
        jar = SimpleCookie()
        jar.load(header_value)
        return {key: morsel.value for key, morsel in jar.items()}

    def _session_valid(self, session_id: str | None, expected_token: str) -> bool:
        if not session_id:
            return False

        self._cleanup_sessions()
        row = self.sessions.get(session_id)
        if not row:
            return False
        if float(row.get("expires_at", 0)) <= time.time():
            self.sessions.pop(session_id, None)
            return False

        session_token = str(row.get("token", ""))
        return bool(session_token) and hmac.compare_digest(session_token, expected_token)

    def check_request(self, handler: SimpleHTTPRequestHandler) -> tuple[bool, dict[str, Any], str, str, str | None]:
        settings = self._settings()
        expected_token, source = self._expected_token(settings)

        if not settings["require_token"]:
            return True, settings, expected_token, source, None
        if not expected_token:
            return False, settings, "", source, None

        header_token = handler.headers.get("X-Dashboard-Token", "").strip()
        if header_token and hmac.compare_digest(header_token, expected_token):
            return True, settings, expected_token, source, None

        auth_header = handler.headers.get("Authorization", "").strip()
        if auth_header.startswith("Bearer "):
            bearer = auth_header[7:].strip()
            if bearer and hmac.compare_digest(bearer, expected_token):
                return True, settings, expected_token, source, None

        cookies = self._parse_cookie_header(handler.headers.get("Cookie"))
        session_id = cookies.get(SESSION_COOKIE_NAME)
        if self._session_valid(session_id, expected_token):
            return True, settings, expected_token, source, session_id

        return False, settings, expected_token, source, session_id

    def login(self, token: str) -> dict[str, Any]:
        settings = self._settings()
        expected_token, source = self._expected_token(settings)

        if not settings["require_token"]:
            return {
                "ok": True,
                "session_id": None,
                "max_age": 0,
                "token_source": source,
                "required": False,
            }

        if not token:
            return {
                "ok": False,
                "error": "token is required",
            }

        if not expected_token:
            return {
                "ok": False,
                "error": f"dashboard token is not configured in env var {settings['token_env_key']}",
            }

        if not expected_token or not hmac.compare_digest(token, expected_token):
            return {
                "ok": False,
                "error": "invalid token",
            }

        session_id = secrets.token_urlsafe(32)
        max_age = int(settings["session_ttl_minutes"]) * 60
        self.sessions[session_id] = {
            "token": expected_token,
            "expires_at": time.time() + max_age,
        }
        self._cleanup_sessions()

        return {
            "ok": True,
            "session_id": session_id,
            "max_age": max_age,
            "token_source": source,
            "required": True,
        }

    def logout(self, session_id: str | None) -> None:
        if not session_id:
            return
        self.sessions.pop(session_id, None)

    def status_for_request(self, handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
        auth_ok, settings, expected_token, source, _ = self.check_request(handler)
        return {
            "required": bool(settings["require_token"]),
            "authenticated": bool(auth_ok),
            "token_env_key": settings["token_env_key"],
            "token_source": source,
            "session_ttl_minutes": settings["session_ttl_minutes"],
            "allow_generated_token": bool(settings["allow_generated_token"]),
            "configured": (not settings["require_token"]) or bool(expected_token),
        }


class DashboardHandler(SimpleHTTPRequestHandler):
    backend = DashboardBackend(ROOT)
    auth = DashboardAuthManager(backend)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/auth/status":
            self._json_response(HTTPStatus.OK, {"ok": True, "auth": self.auth.status_for_request(self)})
            return

        if path == "/login.html":
            auth_ok, _, _, _, _ = self.auth.check_request(self)
            if auth_ok:
                self._redirect("/")
                return
            super().do_GET()
            return

        if not self._authorize(path):
            return

        if path == "/api/state":
            self._json_response(HTTPStatus.OK, self.backend.build_state())
            return

        if path == "/api/exports/weekly.md":
            days_raw = parsed.query
            days = 7
            if "days=" in days_raw:
                try:
                    days = int(days_raw.split("days=", 1)[1].split("&", 1)[0])
                except Exception:
                    days = 7
            content = self.backend.build_weekly_markdown_report(days=days)
            self._text_response(
                HTTPStatus.OK,
                content,
                content_type="text/markdown; charset=utf-8",
                extra_headers={
                    "Content-Disposition": 'attachment; filename="openclaw-weekly-report.md"',
                },
            )
            return

        if path == "/api/exports/tasks.csv":
            content = self.backend.build_tasks_csv_report()
            self._text_response(
                HTTPStatus.OK,
                content,
                content_type="text/csv; charset=utf-8",
                extra_headers={
                    "Content-Disposition": 'attachment; filename="openclaw-tasks.csv"',
                },
            )
            return

        if path == "/api/health":
            self._json_response(HTTPStatus.OK, {"ok": True})
            return

        if path == "/api":
            self._json_response(
                HTTPStatus.OK,
                {
                    "endpoints": [
                        "GET /api/state",
                        "GET /api/auth/status",
                        "POST /api/auth/login",
                        "POST /api/auth/logout",
                        "POST /api/profiles",
                        "POST /api/presets/apply",
                        "POST /api/integrations/toggle",
                        "POST /api/memory/toggle",
                        "POST /api/n8n/toggle",
                        "POST /api/dashboard/settings",
                        "POST /api/projects/create",
                        "POST /api/projects/update",
                        "POST /api/projects/promote_task",
                        "POST /api/spaces/route_text",
                        "POST /api/tasks/create",
                        "POST /api/tasks/create_from_template",
                        "POST /api/tasks/dispatch",
                        "POST /api/tasks/move_to_project_space",
                        "POST /api/tasks/update",
                        "POST /api/tasks/delete",
                        "POST /api/calendar_candidates/assign_project",
                        "POST /api/runs/update",
                        "POST /api/approvals/create",
                        "POST /api/approvals/decision",
                        "POST /api/braindump/create",
                        "POST /api/braindump/capture",
                        "POST /api/braindump/park",
                        "POST /api/braindump/promote",
                        "POST /api/braindump/archive",
                        "GET /api/exports/weekly.md?days=7",
                        "GET /api/exports/tasks.csv",
                    ]
                },
            )
            return

        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._json_response(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        if path == "/api/auth/login":
            token = self._require_string(payload, "token")
            result = self.auth.login(token)
            if not result.get("ok"):
                self._json_response(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": result.get("error")})
                return

            headers: dict[str, str] = {}
            session_id = result.get("session_id")
            max_age = int(result.get("max_age", 0) or 0)
            if session_id and max_age > 0:
                headers["Set-Cookie"] = (
                    f"{SESSION_COOKIE_NAME}={session_id}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax"
                )

            self._json_response(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "required": bool(result.get("required", True)),
                    "token_source": result.get("token_source", "unknown"),
                },
                extra_headers=headers,
            )
            return

        if path == "/api/auth/logout":
            cookies = self.auth._parse_cookie_header(self.headers.get("Cookie"))
            session_id = cookies.get(SESSION_COOKIE_NAME)
            self.auth.logout(session_id)
            self._json_response(
                HTTPStatus.OK,
                {"ok": True},
                extra_headers={
                    "Set-Cookie": f"{SESSION_COOKIE_NAME}=deleted; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
                },
            )
            return

        if not self._authorize(path):
            return

        try:
            if path == "/api/profiles":
                result = self.backend.switch_profiles(
                    integrations_profile=self._optional_str(payload, "integrations_profile"),
                    memory_profile=self._optional_str(payload, "memory_profile"),
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "result": result})
                return

            if path == "/api/presets/apply":
                name = self._require_string(payload, "name")
                result = self.backend.apply_preset(name)
                self._json_response(HTTPStatus.OK, {"ok": True, "result": result})
                return

            if path == "/api/integrations/toggle":
                name = self._require_string(payload, "name")
                enabled = self._require_bool(payload, "enabled")
                self.backend.set_integration_enabled(name, enabled)
                self._json_response(HTTPStatus.OK, {"ok": True})
                return

            if path == "/api/memory/toggle":
                name = self._require_string(payload, "name")
                enabled = self._require_bool(payload, "enabled")
                self.backend.set_memory_module_enabled(name, enabled)
                self._json_response(HTTPStatus.OK, {"ok": True})
                return

            if path == "/api/n8n/toggle":
                name = self._require_string(payload, "name")
                enabled = self._require_bool(payload, "enabled")
                self.backend.set_n8n_module_enabled(name, enabled)
                self._json_response(HTTPStatus.OK, {"ok": True})
                return

            if path == "/api/dashboard/settings":
                cfg = self.backend.set_dashboard_flags(
                    local_telemetry_enabled=self._optional_bool(payload, "local_telemetry_enabled"),
                    codexbar_cost_enabled=self._optional_bool(payload, "codexbar_cost_enabled"),
                    codexbar_usage_enabled=self._optional_bool(payload, "codexbar_usage_enabled"),
                    codexbar_provider=self._optional_str(payload, "codexbar_provider"),
                    codexbar_timeout_seconds=self._optional_int(payload, "codexbar_timeout_seconds"),
                    auto_refresh_seconds=self._optional_int(payload, "auto_refresh_seconds"),
                    auth_require_token=self._optional_bool(payload, "auth_require_token"),
                    auth_token_env_key=self._optional_str(payload, "auth_token_env_key"),
                    auth_session_ttl_minutes=self._optional_int(payload, "auth_session_ttl_minutes"),
                    auth_allow_generated_token=self._optional_bool(payload, "auth_allow_generated_token"),
                    routing_mode=self._optional_str(payload, "routing_mode"),
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "config": cfg})
                return

            if path == "/api/projects/create":
                result = self.backend.create_project(
                    name=self._require_string(payload, "name"),
                    description=self._optional_str(payload, "description"),
                    owner=self._optional_str(payload, "owner"),
                    target_date=self._optional_str(payload, "target_date"),
                    status=self._optional_str(payload, "status") or "active",
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "project": result})
                return

            if path == "/api/projects/update":
                result = self.backend.update_project(
                    project_id=self._require_string(payload, "project_id"),
                    name=self._optional_str(payload, "name"),
                    description=self._optional_str(payload, "description"),
                    owner=self._optional_str(payload, "owner"),
                    target_date=self._optional_str(payload, "target_date"),
                    status=self._optional_str(payload, "status"),
                    progress_pct=self._optional_int(payload, "progress_pct"),
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "project": result})
                return

            if path == "/api/projects/promote_task":
                result = self.backend.promote_task_to_project(
                    task_id=self._require_string(payload, "task_id"),
                    name=self._optional_str(payload, "name"),
                    description=self._optional_str(payload, "description"),
                    owner=self._optional_str(payload, "owner"),
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "result": result})
                return

            if path == "/api/spaces/route_text":
                result = self.backend.route_text_to_space(
                    text=self._require_string(payload, "text"),
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "result": {"route": result}})
                return

            if path == "/api/tasks/create":
                result = self.backend.create_task(
                    title=self._require_string(payload, "title"),
                    assignees=self._require_list_of_strings(payload, "assignees"),
                    project_id=self._optional_str(payload, "project_id"),
                    status=self._optional_str(payload, "status") or "todo",
                    priority=self._optional_str(payload, "priority") or "medium",
                    due_at=self._optional_str(payload, "due_at"),
                    notes=self._optional_str(payload, "notes"),
                    progress_pct=self._optional_int(payload, "progress_pct"),
                    source=self._optional_str(payload, "source") or "dashboard",
                    side_effects=self._optional_list_of_strings(payload, "side_effects"),
                    requires_approval=self._optional_bool(payload, "requires_approval") or False,
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "task": result})
                return

            if path == "/api/tasks/create_from_template":
                result = self.backend.create_task_from_template(
                    template_name=self._require_string(payload, "template_name"),
                    title=self._optional_str(payload, "title"),
                    assignees=self._optional_list_of_strings(payload, "assignees"),
                    project_id=self._optional_str(payload, "project_id"),
                    status=self._optional_str(payload, "status"),
                    priority=self._optional_str(payload, "priority"),
                    due_at=self._optional_str(payload, "due_at"),
                    notes=self._optional_str(payload, "notes"),
                    side_effects=self._optional_list_of_strings(payload, "side_effects"),
                    requires_approval=self._optional_bool(payload, "requires_approval"),
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "result": result})
                return

            if path == "/api/tasks/dispatch":
                result = self.backend.dispatch_task(
                    task_id=self._require_string(payload, "task_id"),
                    assignee=self._optional_str(payload, "assignee"),
                    requested_by=self._optional_str(payload, "requested_by") or "pavel",
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "result": result})
                return

            if path == "/api/tasks/move_to_project_space":
                result = self.backend.assign_task_to_project_space(
                    task_id=self._require_string(payload, "task_id"),
                    project_id=self._require_string(payload, "project_id"),
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "result": result})
                return

            if path == "/api/tasks/update":
                result = self.backend.update_task(
                    task_id=self._require_string(payload, "task_id"),
                    title=self._optional_str(payload, "title"),
                    status=self._optional_str(payload, "status"),
                    project_id=self._optional_str(payload, "project_id"),
                    assignees=self._optional_list_of_strings(payload, "assignees"),
                    priority=self._optional_str(payload, "priority"),
                    due_at=self._optional_str(payload, "due_at"),
                    notes=self._optional_str(payload, "notes"),
                    progress_pct=self._optional_int(payload, "progress_pct"),
                    side_effects=self._optional_list_of_strings(payload, "side_effects"),
                    requires_approval=self._optional_bool(payload, "requires_approval"),
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "task": result})
                return

            if path == "/api/tasks/delete":
                result = self.backend.delete_task(self._require_string(payload, "task_id"))
                self._json_response(HTTPStatus.OK, {"ok": True, "result": result})
                return

            if path == "/api/calendar_candidates/assign_project":
                result = self.backend.assign_calendar_candidate_to_project(
                    candidate_id=self._require_string(payload, "candidate_id"),
                    project_id=self._require_string(payload, "project_id"),
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "result": result})
                return

            if path == "/api/runs/update":
                result = self.backend.update_run(
                    run_id=self._require_string(payload, "run_id"),
                    status=self._optional_str(payload, "status"),
                    log_message=self._optional_str(payload, "log_message"),
                    output_summary=self._optional_str(payload, "output_summary"),
                    error=self._optional_str(payload, "error"),
                    actor=self._optional_str(payload, "actor") or "pavel",
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "run": result})
                return

            if path == "/api/approvals/create":
                result = self.backend.create_approval_request(
                    task_id=self._optional_str(payload, "task_id"),
                    action_type=self._optional_str(payload, "action_type") or "external_write",
                    target=self._optional_str(payload, "target"),
                    reason=self._optional_str(payload, "reason"),
                    requested_by=self._optional_str(payload, "requested_by") or "pavel",
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "approval": result})
                return

            if path == "/api/approvals/decision":
                result = self.backend.decide_approval(
                    approval_id=self._require_string(payload, "approval_id"),
                    decision=self._require_string(payload, "decision"),
                    decided_by=self._optional_str(payload, "decided_by") or "pavel",
                    decision_note=self._optional_str(payload, "decision_note"),
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "approval": result})
                return

            if path == "/api/braindump/create":
                result = self.backend.create_braindump_item(
                    category=self._require_string(payload, "category"),
                    text=self._require_string(payload, "text"),
                    tags=self._optional_list_of_strings(payload, "tags"),
                    review_bucket=self._optional_str(payload, "review_bucket"),
                    notes=self._optional_str(payload, "notes"),
                    source=self._optional_str(payload, "source") or "dashboard",
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "result": result})
                return

            if path == "/api/braindump/capture":
                result = self.backend.capture_braindump_text(
                    text=self._require_string(payload, "text"),
                    source=self._optional_str(payload, "source") or "channel_text",
                    notes=self._optional_str(payload, "notes"),
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "result": result})
                return

            if path == "/api/braindump/park":
                result = self.backend.park_braindump_item(
                    item_id=self._require_string(payload, "item_id"),
                    review_bucket=self._optional_str(payload, "review_bucket"),
                    note=self._optional_str(payload, "note"),
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "result": result})
                return

            if path == "/api/braindump/promote":
                result = self.backend.promote_braindump_item(
                    item_id=self._require_string(payload, "item_id"),
                    target=self._require_string(payload, "target"),
                    note=self._optional_str(payload, "note"),
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "result": result})
                return

            if path == "/api/braindump/archive":
                result = self.backend.archive_braindump_item(
                    item_id=self._require_string(payload, "item_id"),
                    note=self._optional_str(payload, "note"),
                )
                self._json_response(HTTPStatus.OK, {"ok": True, "result": result})
                return

        except ValueError as exc:
            self._json_response(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        self._json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "unknown endpoint"})

    def _authorize(self, path: str) -> bool:
        public_static = {
            "/login.html",
            "/login.js",
            "/styles.css",
            "/favicon.ico",
        }
        public_api = {
            "/api/auth/status",
            "/api/auth/login",
        }

        if path in public_static or path in public_api:
            return True

        auth_ok, _, _, _, _ = self.auth.check_request(self)
        if auth_ok:
            return True

        if path.startswith("/api/"):
            self._json_response(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
            return False

        self._redirect("/login.html")
        return False

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _read_json_body(self) -> dict[str, Any]:
        length_header = self.headers.get("Content-Length", "0")
        try:
            length = int(length_header)
        except ValueError:
            raise ValueError("invalid Content-Length header") from None

        raw = self.rfile.read(length) if length > 0 else b"{}"
        if not raw.strip():
            raw = b"{}"

        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            raise ValueError("invalid JSON payload") from None

        if not isinstance(parsed, dict):
            raise ValueError("JSON payload must be an object")
        return parsed

    def _json_response(self, status: int, payload: dict[str, Any], extra_headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, indent=2, sort_keys=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _text_response(
        self,
        status: int,
        text: str,
        *,
        content_type: str = "text/plain; charset=utf-8",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def guess_type(self, path: str) -> str:
        if path.endswith(".js"):
            return "application/javascript"
        return mimetypes.guess_type(path)[0] or "application/octet-stream"

    @staticmethod
    def _require_string(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _optional_str(payload: dict[str, Any], key: str) -> str | None:
        if key not in payload:
            return None
        value = payload.get(key)
        if not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
        return value

    @staticmethod
    def _require_bool(payload: dict[str, Any], key: str) -> bool:
        value = payload.get(key)
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
        return value

    @staticmethod
    def _optional_bool(payload: dict[str, Any], key: str) -> bool | None:
        if key not in payload:
            return None
        value = payload.get(key)
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
        return value

    @staticmethod
    def _optional_int(payload: dict[str, Any], key: str) -> int | None:
        if key not in payload:
            return None
        value = payload.get(key)
        if not isinstance(value, int):
            raise ValueError(f"{key} must be an integer")
        return value

    @staticmethod
    def _require_list_of_strings(payload: dict[str, Any], key: str) -> list[str]:
        value = payload.get(key)
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list of strings")
        out = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if not out:
            raise ValueError(f"{key} must include at least one assignee")
        return out

    @staticmethod
    def _optional_list_of_strings(payload: dict[str, Any], key: str) -> list[str] | None:
        if key not in payload:
            return None
        value = payload.get(key)
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list of strings")
        out = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the OpenClaw local dashboard server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18789)
    args = parser.parse_args()

    startup = DashboardHandler.auth.startup_status()
    settings = ensure_dict(startup.get("settings"))
    if bool(settings.get("require_token")) and not bool(startup.get("configured")):
        env_key = str(settings.get("token_env_key", "OPENCLAW_DASHBOARD_TOKEN"))
        print(
            "Dashboard auth is enabled but no token is configured. "
            f"Set {env_key} or enable dashboard.auth.allow_generated_token for explicit dev mode."
        )
        return 1

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"OpenClaw dashboard listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
