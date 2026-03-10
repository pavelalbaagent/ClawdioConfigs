#!/usr/bin/env python3
"""Backend helpers for the local OpenClaw dashboard."""

from __future__ import annotations

import csv
import difflib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_configs import load_yaml  # type: ignore  # noqa: E402
import braindump_app as braindump_runtime  # type: ignore  # noqa: E402
import fitness_runtime as fitness_runtime  # type: ignore  # noqa: E402
import google_calendar_runtime as calendar_runtime  # type: ignore  # noqa: E402
import personal_task_runtime as personal_task_runtime  # type: ignore  # noqa: E402
import provider_smoke_check as provider_smoke_runtime  # type: ignore  # noqa: E402
import research_flow_runtime as research_flow_runtime  # type: ignore  # noqa: E402
from space_router import route_text as route_space_text  # type: ignore  # noqa: E402


TASK_STATUSES = {"todo", "in_progress", "blocked", "done"}
PRIORITY_LEVELS = {"low", "medium", "high", "urgent"}
PROJECT_STATUSES = {"active", "planned", "paused", "blocked", "done", "archived"}
RUN_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}
APPROVAL_STATUSES = {"pending", "approved", "rejected", "cancelled"}
CALENDAR_CANDIDATE_STATUSES = {"proposed", "needs_details", "ready", "approved", "scheduled", "archived", "error"}
SPACE_KINDS = {"project"}
SPACE_SESSION_STRATEGIES = {"shared_session", "separate_session", "checkpointed_session"}
SPACE_AGENT_STRATEGIES = {"coordinator_only", "existing_surface_only", "dedicated_specialist"}


@dataclass
class Totals:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    errors: int = 0
    fallbacks: int = 0
    estimated_cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def ensure_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def dedupe_string_list(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def accumulate(totals: Totals, entry: dict[str, Any]) -> None:
    totals.calls += 1
    totals.prompt_tokens += int(entry.get("prompt_tokens", 0) or 0)
    totals.completion_tokens += int(entry.get("completion_tokens", 0) or 0)
    totals.latency_ms += int(entry.get("latency_ms", 0) or 0)
    totals.estimated_cost_usd += float(entry.get("estimated_cost_usd", 0.0) or 0.0)
    status = str(entry.get("status", "")).lower()
    if status == "error":
        totals.errors += 1
    if status == "fallback":
        totals.fallbacks += 1


def asdict_totals(totals: Totals) -> dict[str, Any]:
    return {
        "calls": totals.calls,
        "prompt_tokens": totals.prompt_tokens,
        "completion_tokens": totals.completion_tokens,
        "total_tokens": totals.total_tokens,
        "latency_ms": totals.latency_ms,
        "errors": totals.errors,
        "fallbacks": totals.fallbacks,
        "estimated_cost_usd": round(totals.estimated_cost_usd, 6),
    }


def iso_now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso_safe(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def minutes_until(ts: str | None) -> int | None:
    dt = parse_iso_safe(ts)
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    delta = dt - now
    return int(delta.total_seconds() // 60)


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned.strip("-") or "item"


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def yaml_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9_./:@+-]+", text):
        return text
    return json.dumps(text)


def dump_yaml(data: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent
    lines: list[str] = []

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(dump_yaml(value, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {yaml_scalar(value)}")
        return lines

    if isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                nested = dump_yaml(item, indent + 2)
                lines.extend(nested)
            else:
                lines.append(f"{prefix}- {yaml_scalar(item)}")
        return lines

    lines.append(f"{prefix}{yaml_scalar(data)}")
    return lines


def parse_markdown_todos(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    out: list[dict[str, Any]] = []
    checkbox_re = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.+)\s*$")
    bullet_re = re.compile(r"^\s*[-*]\s+(.+)\s*$")

    for line_no, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        row = raw.strip()
        if not row:
            continue

        match = checkbox_re.match(raw)
        if match:
            done = match.group(1).lower() == "x"
            text = match.group(2).strip()
            out.append(
                {
                    "id": f"md:{path}:{line_no}",
                    "title": text,
                    "done": done,
                    "source": "markdown",
                    "path": str(path),
                    "line": line_no,
                }
            )
            continue

        bullet = bullet_re.match(raw)
        if bullet and not raw.strip().startswith("#"):
            text = bullet.group(1).strip()
            out.append(
                {
                    "id": f"md:{path}:{line_no}",
                    "title": text,
                    "done": False,
                    "source": "markdown",
                    "path": str(path),
                    "line": line_no,
                }
            )

    return out


class DashboardBackend:
    """Load dashboard state and apply safe config toggles."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or ROOT).resolve()
        self.config_dir = self.root / "config"
        self.integrations_path = self.config_dir / "integrations.yaml"
        self.memory_path = self.config_dir / "memory.yaml"
        self.models_path = self.config_dir / "models.yaml"
        self.core_path = self.config_dir / "core.yaml"
        self.channels_path = self.config_dir / "channels.yaml"
        self.reminders_path = self.config_dir / "reminders.yaml"
        self.agents_path = self.config_dir / "agents.yaml"
        self.session_policy_path = self.config_dir / "session_policy.yaml"
        self.dashboard_path = self.config_dir / "dashboard.yaml"
        self.workspace_path = self.root / "data" / "dashboard-workspace.json"
        self.agent_runtime_state_path = self.root / "data" / "agent-runtime-state.json"
        self.telegram_adapter_state_path = self._resolve_telegram_adapter_state_path()
        self.assistant_chat_state_path = self.root / "data" / "assistant-chat-state.json"
        self.continuous_improvement_status_path = self.root / "data" / "continuous-improvement-status.json"
        self.memory_sync_status_path = self.root / "data" / "memory-sync-status.json"
        self.todo_sources = [
            self.root / "TODO.md",
            self.root / "baselines" / "agent_md" / "TODO.md",
            self.root / "baselines" / "agent_md" / "MEMORY.md",
        ]
        self.telemetry_dir = self.root / "telemetry"
        self.ops_snapshot_path = self.telemetry_dir / "ops-snapshot.md"
        self.model_usage_report_path = self.telemetry_dir / "model-usage-latest.md"
        self.reminder_state_path = self._resolve_reminder_state_path(prefer_configured=False)
        self.gmail_status_path = self.root / "data" / "gmail-inbox-last-run.json"
        self.calendar_runtime_status_path = self.root / "data" / "calendar-runtime-status.json"
        self.calendar_candidates_path = self.root / "data" / "calendar-candidates.json"
        self.personal_task_status_path = self.root / "data" / "personal-task-runtime-status.json"
        self.fitness_runtime_status_path = self.root / "data" / "fitness-runtime-status.json"
        self.drive_workspace_status_path = self.root / "data" / "drive-workspace-status.json"
        self.research_flow_config_path = self.config_dir / "research_flow.yaml"
        self.research_flow_status_path = self.root / "data" / "research-flow-status.json"
        self.research_flow_script = self.root / "scripts" / "research_flow_runtime.py"
        self.braindump_snapshot_path = self.root / "data" / "braindump-snapshot.json"
        self.provider_smoke_status_path = self.root / "data" / "provider-smoke-status.json"
        self.gmail_db_path = self.root / ".memory" / "inbox_processing.db"
        self.braindump_db_path = self.root / ".memory" / "braindump.db"
        self.fitness_db_path = self.root / ".memory" / "fitness.db"
        self.braindump_schema_path = self.root / "contracts" / "braindump" / "sqlite_schema.sql"
        self.set_profiles_script = self.root / "scripts" / "set_active_profiles.py"

    def _resolve_reminder_state_path(self, *, prefer_configured: bool) -> Path:
        fallback = self.root / "data" / "reminders-state.json"
        data = self.load_yaml_dict(self.reminders_path)
        storage = ensure_dict(data.get("storage"))
        configured = str(storage.get("state_file", "")).strip()
        if not configured:
            return fallback

        configured_path = Path(configured).expanduser()
        if not configured_path.is_absolute():
            return (self.root / configured_path).resolve()

        if prefer_configured or configured_path.exists():
            return configured_path
        return fallback

    def _resolve_telegram_adapter_state_path(self) -> Path:
        configured = Path("/var/lib/openclaw/telegram-adapter-state.json")
        if configured.exists():
            return configured
        return self.root / "data" / "telegram-adapter-state.json"

    def _integration_env_file_path(self) -> Path | None:
        local_env = self.root / "secrets" / "openclaw.env"
        if local_env.exists():
            return local_env

        integrations_data = self.load_yaml_dict(self.integrations_path)
        secrets = ensure_dict(integrations_data.get("secrets"))
        configured = str(secrets.get("env_file_path", "")).strip()
        if configured:
            configured_path = Path(configured).expanduser()
            if configured_path.exists():
                return configured_path
        return None

    def load_yaml_dict(self, path: Path) -> dict[str, Any]:
        return ensure_dict(load_yaml(path)) if path.exists() else {}

    @staticmethod
    def _display_label(value: str) -> str:
        clean = value.strip().replace("_", " ").replace("-", " ")
        return clean.title() if clean else "Unknown"

    @staticmethod
    def _space_entry_command_hint(space_key: str) -> str:
        key = space_key.strip().lower()
        if key == "general":
            return "assistant: <text>"
        if key == "reminders":
            return "reminders: <text>"
        if key == "calendar":
            return "calendar: <text>"
        if key == "tasks":
            return "tasks: <text>"
        if key == "braindump":
            return "braindump: <text>"
        if key == "research":
            return "research: <text>"
        if key == "job-search":
            return "job: <text>"
        if key == "fitness":
            return "fitness: <text>"
        if key == "coding":
            return "coding: <text>"
        if key == "ops":
            return "ops: <text>"
        return f"[{key}] <text>"

    def _load_agent_runtime_state(self) -> dict[str, Any]:
        raw = read_json(self.agent_runtime_state_path)
        if not isinstance(raw, dict):
            return {"last_route": None, "recent_routes": []}

        recent_rows = []
        for item in raw.get("recent_routes", []):
            row = ensure_dict(item)
            if not row:
                continue
            recent_rows.append(row)

        last_route = ensure_dict(raw.get("last_route"))
        return {
            "last_route": last_route or None,
            "recent_routes": recent_rows[-40:],
        }

    def _save_agent_runtime_state(self, state: dict[str, Any]) -> None:
        payload = {
            "updated_at": iso_now_utc(),
            "last_route": ensure_dict(state.get("last_route")) or None,
            "recent_routes": [ensure_dict(item) for item in state.get("recent_routes", [])][-40:],
        }
        write_json(self.agent_runtime_state_path, payload)

    def _agent_runtime_snapshot(self) -> dict[str, Any]:
        agents_data = self.load_yaml_dict(self.agents_path)
        session_data = self.load_yaml_dict(self.session_policy_path)

        agents_cfg = ensure_dict(agents_data.get("agents"))
        internal_cfg = ensure_dict(agents_data.get("internal_roles"))
        surfaces = ensure_dict(agents_data.get("surfaces"))
        routing = ensure_dict(agents_data.get("routing_overrides"))
        improvement = ensure_dict(agents_data.get("continuous_improvement"))

        space_registry = ensure_dict(session_data.get("space_registry"))
        route_rules = ensure_dict(space_registry.get("route_rules"))
        lifecycle = ensure_dict(session_data.get("session_lifecycle"))
        improvement_policy = ensure_dict(session_data.get("continuous_improvement_policy"))

        def build_role(name: str, row: dict[str, Any], *, kind: str) -> dict[str, Any]:
            rule = ensure_dict(route_rules.get(name))
            allowed_spaces = ensure_string_list(rule.get("allowed_spaces", []))
            owned_spaces = ensure_string_list(row.get("owned_spaces", [])) or allowed_spaces
            responsibilities = ensure_string_list(
                row.get("primary_responsibilities", row.get("responsibilities", []))
            )
            tools = ensure_string_list(row.get("allowed_tools", []))
            return {
                "id": name,
                "label": self._display_label(name),
                "kind": kind,
                "enabled": bool(row.get("enabled") is True),
                "interaction_mode": str(row.get("interaction_mode", "")).strip() or ("internal" if kind == "internal_role" else "structured"),
                "default_lane": str(row.get("default_lane", "")).strip() or None,
                "default_space": str(rule.get("default_space", "")).strip() or None,
                "owned_spaces": owned_spaces,
                "allowed_spaces": allowed_spaces,
                "responsibilities": responsibilities,
                "allowed_tools": tools,
                "can_spawn_subagents": bool(row.get("can_spawn_subagents") is True),
            }

        visible_order = ensure_string_list(surfaces.get("visible_agents", []))
        hidden_order = ensure_string_list(surfaces.get("hidden_internal_roles", []))
        default_user_facing_agent = str(surfaces.get("default_user_facing_agent", "assistant")).strip() or "assistant"

        visible_agents: list[dict[str, Any]] = []
        for name in visible_order:
            row = ensure_dict(agents_cfg.get(name))
            if row:
                visible_agents.append(build_role(name, row, kind="visible_agent"))
        for name, row in sorted(agents_cfg.items(), key=lambda kv: kv[0]):
            if name in visible_order:
                continue
            visible_agents.append(build_role(str(name), ensure_dict(row), kind="visible_agent"))

        internal_roles: list[dict[str, Any]] = []
        for name in hidden_order:
            row = ensure_dict(internal_cfg.get(name))
            if row:
                internal_roles.append(build_role(name, row, kind="internal_role"))
        for name, row in sorted(internal_cfg.items(), key=lambda kv: kv[0]):
            if name in hidden_order:
                continue
            internal_roles.append(build_role(str(name), ensure_dict(row), kind="internal_role"))

        space_defaults: dict[str, str | None] = {}
        for role_name, rule in route_rules.items():
            rule_row = ensure_dict(rule)
            for allowed in ensure_string_list(rule_row.get("allowed_spaces", [])):
                if "*" in allowed:
                    continue
                space_defaults.setdefault(allowed, str(role_name))

        core_spaces = ensure_string_list(space_registry.get("core_spaces", []))
        space_catalog = [
            {
                "key": key,
                "name": self._display_label(key),
                "kind": "core",
                "default_agent": space_defaults.get(key),
                "entry_command_hint": self._space_entry_command_hint(key),
                "session_strategy": "shared_session",
                "agent_strategy": "coordinator_only" if space_defaults.get(key) == "assistant" else "existing_surface_only",
            }
            for key in core_spaces
        ]

        runtime_state = self._load_agent_runtime_state()
        recent_routes = [ensure_dict(item) for item in runtime_state.get("recent_routes", [])]
        counts_by_agent: dict[str, int] = defaultdict(int)
        counts_by_space: dict[str, int] = defaultdict(int)
        for row in recent_routes:
            agent_id = str(row.get("agent_id", "")).strip()
            space_key = str(row.get("space_key", "")).strip()
            if agent_id:
                counts_by_agent[agent_id] += 1
            if space_key:
                counts_by_space[space_key] += 1

        return {
            "default_user_facing_agent": default_user_facing_agent,
            "visible_agents": visible_agents,
            "internal_roles": internal_roles,
            "active_routing_mode": str(routing.get("active_mode", "")).strip() or None,
            "space_registry": {
                "default_space": str(space_registry.get("default_space", "general")).strip() or "general",
                "core_spaces": core_spaces,
                "dynamic_space_prefixes": ensure_string_list(space_registry.get("dynamic_space_prefixes", [])),
                "catalog": space_catalog,
            },
            "session_policy": {
                "default_context_window_tokens": lifecycle.get("default_context_window_tokens"),
                "summarize_when_context_tokens_over": lifecycle.get("summarize_when_context_tokens_over"),
                "checkpoint_every_turns": lifecycle.get("checkpoint_every_turns"),
                "checkpoint_every_minutes": lifecycle.get("checkpoint_every_minutes"),
                "idle_reset_minutes": lifecycle.get("idle_reset_minutes"),
                "preserve_on_restart": ensure_string_list(lifecycle.get("preserve_on_restart", [])),
            },
            "continuous_improvement": {
                "enabled": bool(improvement.get("enabled") is True),
                "mode": str(improvement.get("mode", "")).strip() or None,
                "owner_role": str(improvement.get("owner_role", "")).strip() or None,
                "reviewer_roles": ensure_string_list(improvement.get("reviewer_roles", [])),
                "cadence": ensure_dict(improvement.get("cadence")),
                "daily_review_inputs": ensure_string_list(improvement_policy.get("daily_review_inputs", [])),
                "weekly_review_inputs": ensure_string_list(improvement_policy.get("weekly_review_inputs", [])),
                "output_sections": ensure_string_list(improvement_policy.get("output_sections", [])),
                "blocked_auto_actions": ensure_string_list(improvement_policy.get("blocked_auto_actions", [])),
            },
            "activity": {
                "last_route": ensure_dict(runtime_state.get("last_route")) or None,
                "recent_routes": recent_routes[-12:],
                "counts_by_agent": dict(sorted(counts_by_agent.items(), key=lambda item: (-item[1], item[0]))),
                "counts_by_space": dict(sorted(counts_by_space.items(), key=lambda item: (-item[1], item[0]))),
            },
        }

    def record_agent_activity(
        self,
        *,
        agent_id: str,
        space_key: str,
        source: str,
        action: str,
        text: str | None = None,
        route_mode: str | None = None,
        space_kind: str = "core",
        project_id: str | None = None,
        project_name: str | None = None,
        lane: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        clean_agent = agent_id.strip().lower() or "assistant"
        clean_space = space_key.strip().lower() or "general"
        registry = self._agent_runtime_snapshot()
        agent_lookup = {
            row["id"]: row for row in registry.get("visible_agents", []) + registry.get("internal_roles", [])
        }
        role = ensure_dict(agent_lookup.get(clean_agent))
        entry = {
            "ts": iso_now_utc(),
            "source": source.strip().lower() or "unknown",
            "action": action.strip().lower() or "route",
            "agent_id": clean_agent,
            "agent_label": role.get("label") or self._display_label(clean_agent),
            "space_key": clean_space,
            "space_kind": space_kind.strip().lower() or "core",
            "route_mode": (route_mode or "").strip() or "default",
            "project_id": (project_id or "").strip() or None,
            "project_name": (project_name or "").strip() or None,
            "lane": (lane or role.get("default_lane") or "").strip() or None,
            "task_id": (task_id or "").strip() or None,
            "excerpt": (text or "").strip()[:160] or None,
        }

        state = self._load_agent_runtime_state()
        recent_routes = [ensure_dict(item) for item in state.get("recent_routes", [])]
        recent_routes.append(entry)
        state["recent_routes"] = recent_routes[-40:]
        state["last_route"] = entry
        self._save_agent_runtime_state(state)
        return entry

    def _default_dashboard_config(self) -> dict[str, Any]:
        return {
            "dashboard": {
                "adapters": {
                    "local_telemetry_enabled": True,
                    "codexbar_cost_enabled": False,
                    "codexbar_usage_enabled": False,
                },
                "codexbar": {
                    "provider": "all",
                    "timeout_seconds": 20,
                },
                "ui": {
                    "auto_refresh_seconds": 20,
                },
                "auth": {
                    "require_token": True,
                    "token_env_key": "OPENCLAW_DASHBOARD_TOKEN",
                    "session_ttl_minutes": 720,
                    "allow_generated_token": False,
                },
                "presets": {
                    "manual_min_cost": {
                        "description": "Lean manual approvals with MVP channel, reminders, and calendar enabled.",
                        "integrations_profile": "bootstrap_minimal",
                        "memory_profile": "md_only",
                        "integration_toggles": {
                            "gmail": False,
                            "drive": False,
                            "github": False,
                            "personal_task_manager": False,
                            "agent_task_manager": False,
                            "n8n": False,
                            "calendar": True,
                            "linkedin": False,
                        },
                        "memory_module_toggles": {
                            "semantic_embeddings": False,
                            "sqlite_state": False,
                        },
                        "n8n_module_toggles": {
                            "news_digest": False,
                        },
                    },
                    "standard_daily": {
                        "description": "Balanced daily profile with hybrid memory and productivity modules.",
                        "integrations_profile": "standard_productive",
                        "memory_profile": "hybrid_124",
                        "integration_toggles": {
                            "gmail": True,
                            "drive": True,
                            "github": True,
                            "personal_task_manager": True,
                            "agent_task_manager": True,
                            "n8n": True,
                        },
                        "memory_module_toggles": {
                            "structured_markdown": True,
                            "semantic_embeddings": True,
                            "sqlite_state": True,
                        },
                        "n8n_module_toggles": {
                            "inbox_router": True,
                            "personal_reminders": True,
                            "agent_task_sync": True,
                            "news_digest": False,
                        },
                    },
                    "research_push": {
                        "description": "Research-heavy mode with broader integrations and news ingestion.",
                        "integrations_profile": "full_auto_candidate",
                        "memory_profile": "hybrid_124",
                        "integration_toggles": {
                            "n8n": True,
                            "calendar": True,
                            "web_browsing": True,
                        },
                        "memory_module_toggles": {
                            "structured_markdown": True,
                            "semantic_embeddings": True,
                            "sqlite_state": True,
                        },
                        "n8n_module_toggles": {
                            "inbox_router": True,
                            "personal_reminders": True,
                            "agent_task_sync": True,
                            "news_digest": True,
                        },
                    },
                },
                "task_templates": {
                    "research_brief": {
                        "title": "Research brief: ",
                        "description": "Gather findings and synthesize key insights.",
                        "priority": "medium",
                        "status": "todo",
                        "default_assignees": ["researcher"],
                        "due_in_hours": 24,
                        "notes": "Deliver concise findings with key sources and actionable recommendations.",
                    },
                    "build_feature": {
                        "title": "Build: ",
                        "description": "Implement code changes and validation checks.",
                        "priority": "high",
                        "status": "todo",
                        "default_assignees": ["builder"],
                        "due_in_hours": 48,
                        "notes": "Implement changes, run tests, and summarize risks + next steps.",
                    },
                    "ops_health_check": {
                        "title": "Ops check: ",
                        "description": "Inspect runtime health, reminders, and telemetry anomalies.",
                        "priority": "medium",
                        "status": "todo",
                        "default_assignees": ["ops_guard"],
                        "due_in_hours": 12,
                        "notes": "Review service health, pending reminders, and critical integration issues.",
                    },
                },
                "approvals": {
                    "require_for_external_writes": True,
                    "external_write_keywords": [
                        "send",
                        "email",
                        "post",
                        "publish",
                        "delete",
                        "push",
                        "trigger",
                        "workflow",
                        "create event",
                        "comment pr",
                    ],
                    "auto_expire_hours": 72,
                },
            }
        }

    def _default_workspace_data(self) -> dict[str, Any]:
        now = iso_now_utc()
        default_project = {
            "id": "proj-openclaw-v2",
            "name": "OpenClaw V2 Rebuild",
            "status": "active",
            "description": "Core rebuild and modular control-plane rollout.",
            "owner": "pavel",
            "target_date": None,
            "progress_pct": 0,
            "created_at": now,
            "updated_at": now,
        }
        return {
            "projects": [default_project],
            "spaces": [self._project_space_template(default_project)],
            "tasks": [],
            "runs": [],
            "approvals": [],
        }

    def _normalize_project(self, row: dict[str, Any]) -> dict[str, Any]:
        name = str(row.get("name", "Project")).strip() or "Project"
        project_id = str(row.get("id", "")).strip() or f"proj-{slugify(name)}-{uuid.uuid4().hex[:6]}"
        status = str(row.get("status", "active")).strip().lower()
        if status not in PROJECT_STATUSES:
            status = "active"

        progress = row.get("progress_pct")
        if isinstance(progress, (int, float)):
            progress_pct = max(0, min(100, int(progress)))
        else:
            progress_pct = 0

        return {
            "id": project_id,
            "name": name,
            "status": status,
            "description": str(row.get("description", "")).strip(),
            "owner": str(row.get("owner", "pavel")).strip().lower() or "pavel",
            "target_date": str(row.get("target_date", "")).strip() or None,
            "progress_pct": progress_pct,
            "created_at": str(row.get("created_at", "")).strip() or iso_now_utc(),
            "updated_at": str(row.get("updated_at", "")).strip() or iso_now_utc(),
        }

    def _normalize_space(self, row: dict[str, Any]) -> dict[str, Any]:
        name = str(row.get("name", "Space")).strip() or "Space"
        kind = str(row.get("kind", "project")).strip().lower()
        if kind not in SPACE_KINDS:
            kind = "project"

        project_id = optional_str(row.get("project_id"))
        space_id = str(row.get("id", "")).strip() or f"space-{slugify(name)}-{uuid.uuid4().hex[:6]}"
        key = str(row.get("key", "")).strip() or f"{kind}/{slugify(name)}"

        status = str(row.get("status", "active")).strip().lower()
        if status not in PROJECT_STATUSES:
            status = "active"

        session_strategy = str(row.get("session_strategy", "separate_session")).strip().lower()
        if session_strategy not in SPACE_SESSION_STRATEGIES:
            session_strategy = "separate_session"

        agent_strategy = str(row.get("agent_strategy", "existing_surface_only")).strip().lower()
        if agent_strategy not in SPACE_AGENT_STRATEGIES:
            agent_strategy = "existing_surface_only"

        return {
            "id": space_id,
            "key": key,
            "kind": kind,
            "project_id": project_id,
            "name": name,
            "status": status,
            "summary": str(row.get("summary", "")).strip(),
            "target_channel": str(row.get("target_channel", "projects")).strip() or "projects",
            "entry_command_hint": str(row.get("entry_command_hint", "")).strip() or None,
            "session_strategy": session_strategy,
            "agent_strategy": agent_strategy,
            "compaction_strategy": str(row.get("compaction_strategy", "milestone_summary")).strip()
            or "milestone_summary",
            "template_version": str(row.get("template_version", "project_space_v1")).strip() or "project_space_v1",
            "source_task_id": optional_str(row.get("source_task_id")),
            "last_checkpoint_at": optional_str(row.get("last_checkpoint_at")),
            "created_at": str(row.get("created_at", "")).strip() or iso_now_utc(),
            "updated_at": str(row.get("updated_at", "")).strip() or iso_now_utc(),
        }

    def _project_space_template(
        self,
        project: dict[str, Any],
        *,
        source_task_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_project = self._normalize_project(project)
        slug = slugify(str(normalized_project.get("name", "")) or "project")
        return self._normalize_space(
            {
                "id": f"space-{normalized_project['id']}",
                "key": f"projects/{slug}",
                "kind": "project",
                "project_id": normalized_project["id"],
                "name": normalized_project["name"],
                "status": normalized_project["status"],
                "summary": normalized_project["description"],
                "target_channel": "projects",
                "entry_command_hint": f"[project:{slug}]",
                "session_strategy": "separate_session",
                "agent_strategy": "existing_surface_only",
                "compaction_strategy": "milestone_summary",
                "template_version": "project_space_v1",
                "source_task_id": source_task_id,
                "created_at": normalized_project["created_at"],
                "updated_at": normalized_project["updated_at"],
            }
        )

    def _ensure_project_spaces_in_workspace(self, workspace: dict[str, Any]) -> dict[str, Any]:
        projects = [self._normalize_project(ensure_dict(item)) for item in workspace.get("projects", [])]
        raw_spaces = workspace.get("spaces") if isinstance(workspace.get("spaces"), list) else []
        normalized_existing = [self._normalize_space(ensure_dict(item)) for item in raw_spaces]

        existing_by_project = {
            str(row.get("project_id")): row for row in normalized_existing if str(row.get("project_id", "")).strip()
        }
        retained_non_project = [row for row in normalized_existing if not str(row.get("project_id", "")).strip()]

        ensured_spaces: list[dict[str, Any]] = []
        for project in projects:
            template = self._project_space_template(project)
            existing = existing_by_project.get(project["id"])
            if existing:
                merged = dict(template)
                for key in (
                    "id",
                    "summary",
                    "target_channel",
                    "entry_command_hint",
                    "session_strategy",
                    "agent_strategy",
                    "compaction_strategy",
                    "template_version",
                    "source_task_id",
                    "last_checkpoint_at",
                    "created_at",
                ):
                    if existing.get(key) not in {None, ""}:
                        merged[key] = existing.get(key)
                merged["updated_at"] = project["updated_at"]
                ensured_spaces.append(self._normalize_space(merged))
            else:
                ensured_spaces.append(template)

        workspace["projects"] = projects
        workspace["spaces"] = retained_non_project + ensured_spaces
        return workspace

    def _normalize_task(self, row: dict[str, Any]) -> dict[str, Any]:
        title = str(row.get("title", "Task")).strip() or "Task"
        task_id = str(row.get("id", "")).strip() or f"task-{slugify(title)}-{uuid.uuid4().hex[:6]}"

        status = str(row.get("status", "todo")).strip().lower()
        if status not in TASK_STATUSES:
            status = "todo"

        priority = str(row.get("priority", "medium")).strip().lower()
        if priority not in PRIORITY_LEVELS:
            priority = "medium"

        progress = row.get("progress_pct")
        if isinstance(progress, (int, float)):
            progress_pct = max(0, min(100, int(progress)))
        else:
            progress_pct = 100 if status == "done" else 0

        assignees = dedupe_string_list(ensure_string_list(row.get("assignees", [])))
        side_effects = dedupe_string_list(ensure_string_list(row.get("side_effects", [])))
        requires_approval = bool(row.get("requires_approval") is True or side_effects)

        return {
            "id": task_id,
            "title": title,
            "status": status,
            "project_id": optional_str(row.get("project_id")),
            "assignees": assignees,
            "priority": priority,
            "due_at": optional_str(row.get("due_at")),
            "notes": str(row.get("notes", "")).strip(),
            "source": str(row.get("source", "dashboard")).strip() or "dashboard",
            "progress_pct": progress_pct,
            "requires_approval": requires_approval,
            "side_effects": side_effects,
            "created_at": str(row.get("created_at", "")).strip() or iso_now_utc(),
            "updated_at": str(row.get("updated_at", "")).strip() or iso_now_utc(),
        }

    def _normalize_run(self, row: dict[str, Any]) -> dict[str, Any]:
        run_id = str(row.get("id", "")).strip() or f"run-{uuid.uuid4().hex[:10]}"
        status = str(row.get("status", "queued")).strip().lower()
        if status not in RUN_STATUSES:
            status = "queued"

        logs = row.get("logs")
        clean_logs: list[dict[str, str]] = []
        if isinstance(logs, list):
            for item in logs:
                log_row = ensure_dict(item)
                message = str(log_row.get("message", "")).strip()
                if not message:
                    continue
                clean_logs.append(
                    {
                        "ts": str(log_row.get("ts", "")).strip() or iso_now_utc(),
                        "message": message,
                    }
                )

        return {
            "id": run_id,
            "task_id": str(row.get("task_id", "")).strip(),
            "assignee": str(row.get("assignee", "")).strip().lower() or "unassigned",
            "status": status,
            "queued_at": str(row.get("queued_at", "")).strip() or iso_now_utc(),
            "started_at": str(row.get("started_at", "")).strip() or None,
            "finished_at": str(row.get("finished_at", "")).strip() or None,
            "output_summary": str(row.get("output_summary", "")).strip(),
            "error": str(row.get("error", "")).strip(),
            "logs": clean_logs,
            "updated_at": str(row.get("updated_at", "")).strip() or iso_now_utc(),
        }

    def _normalize_approval(self, row: dict[str, Any]) -> dict[str, Any]:
        approval_id = str(row.get("id", "")).strip() or f"appr-{uuid.uuid4().hex[:10]}"
        status = str(row.get("status", "pending")).strip().lower()
        if status not in APPROVAL_STATUSES:
            status = "pending"

        return {
            "id": approval_id,
            "task_id": str(row.get("task_id", "")).strip() or None,
            "action_type": str(row.get("action_type", "external_write")).strip() or "external_write",
            "target": str(row.get("target", "")).strip(),
            "reason": str(row.get("reason", "")).strip(),
            "requested_by": str(row.get("requested_by", "pavel")).strip().lower() or "pavel",
            "requested_at": str(row.get("requested_at", "")).strip() or iso_now_utc(),
            "status": status,
            "decided_by": str(row.get("decided_by", "")).strip() or None,
            "decided_at": str(row.get("decided_at", "")).strip() or None,
            "decision_note": str(row.get("decision_note", "")).strip(),
            "updated_at": str(row.get("updated_at", "")).strip() or iso_now_utc(),
        }

    def read_dashboard_config(self) -> dict[str, Any]:
        defaults = self._default_dashboard_config()
        cfg = json.loads(json.dumps(defaults))
        if not self.dashboard_path.exists():
            return cfg

        data = self.load_yaml_dict(self.dashboard_path)
        deep_merge(cfg, data)
        return cfg

    def write_dashboard_config(self, cfg: dict[str, Any]) -> None:
        self.dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        lines = dump_yaml(cfg)
        self.dashboard_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def load_workspace_data(self) -> dict[str, Any]:
        if not self.workspace_path.exists():
            data = self._default_workspace_data()
            self.save_workspace_data(data)
            return data

        raw = read_json(self.workspace_path)
        if not isinstance(raw, dict):
            data = self._default_workspace_data()
            self.save_workspace_data(data)
            return data

        projects = raw.get("projects") if isinstance(raw.get("projects"), list) else []
        spaces = raw.get("spaces") if isinstance(raw.get("spaces"), list) else []
        tasks = raw.get("tasks") if isinstance(raw.get("tasks"), list) else []
        runs = raw.get("runs") if isinstance(raw.get("runs"), list) else []
        approvals = raw.get("approvals") if isinstance(raw.get("approvals"), list) else []

        normalized_projects = [self._normalize_project(ensure_dict(item)) for item in projects]
        normalized_spaces = [self._normalize_space(ensure_dict(item)) for item in spaces]
        normalized_tasks = [self._normalize_task(ensure_dict(item)) for item in tasks]
        normalized_runs = [self._normalize_run(ensure_dict(item)) for item in runs]
        normalized_approvals = [self._normalize_approval(ensure_dict(item)) for item in approvals]

        if not normalized_projects:
            defaults = self._default_workspace_data()
            normalized_projects = defaults["projects"]
            normalized_spaces = defaults["spaces"]

        data = {
            "projects": normalized_projects,
            "spaces": normalized_spaces,
            "tasks": normalized_tasks,
            "runs": normalized_runs,
            "approvals": normalized_approvals,
        }
        data = self._ensure_project_spaces_in_workspace(data)
        if raw != data:
            self.save_workspace_data(data)
        return data

    def save_workspace_data(self, data: dict[str, Any]) -> None:
        data = self._ensure_project_spaces_in_workspace(data)
        self.workspace_path.parent.mkdir(parents=True, exist_ok=True)
        self.workspace_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def _open_braindump_conn(self) -> sqlite3.Connection:
        self.braindump_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.braindump_db_path)
        braindump_runtime.ensure_db(conn, self.braindump_schema_path)
        return conn

    def _write_braindump_snapshot(self, conn: sqlite3.Connection) -> dict[str, Any]:
        return braindump_runtime.write_snapshot(conn, self.braindump_snapshot_path, self.braindump_db_path)

    def braindump_category_catalog(self) -> dict[str, Any]:
        return {
            "curated_categories": sorted(braindump_runtime.DEFAULT_CATEGORY_BUCKETS.keys()),
            "aliases": dict(sorted(braindump_runtime.CATEGORY_ALIASES.items())),
            "review_buckets": sorted(braindump_runtime.REVIEW_DELTA_DAYS.keys()),
        }

    def route_text_to_space(self, *, text: str) -> dict[str, Any]:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("text is required")

        workspace = self.load_workspace_data()
        spaces = [self._normalize_space(ensure_dict(item)) for item in workspace.get("spaces", [])]
        registry = self._agent_runtime_snapshot()
        route = route_space_text(
            clean_text,
            spaces,
            default_agent=str(registry.get("default_user_facing_agent", "assistant")).strip() or "assistant",
        )

        matched_space = next((row for row in spaces if str(row.get("id")) == str(route.get("space_id") or "")), None)
        if matched_space is not None:
            route["space"] = {
                "id": matched_space.get("id"),
                "key": matched_space.get("key"),
                "kind": matched_space.get("kind"),
                "name": matched_space.get("name"),
                "project_id": matched_space.get("project_id"),
                "session_strategy": matched_space.get("session_strategy"),
                "agent_strategy": matched_space.get("agent_strategy"),
                "entry_command_hint": matched_space.get("entry_command_hint"),
            }
        else:
            if route.get("kind") == "project":
                route["space"] = None
            else:
                space_key = str(route.get("space_key", "")).strip() or "general"
                catalog = {
                    str(item.get("key")): ensure_dict(item)
                    for item in ensure_dict(registry.get("space_registry")).get("catalog", [])
                    if isinstance(item, dict)
                }
                catalog_row = ensure_dict(catalog.get(space_key))
                route["space"] = {
                    "id": None,
                    "key": space_key,
                    "kind": "core",
                    "project_id": None,
                    "name": catalog_row.get("name") or self._display_label(space_key),
                    "session_strategy": catalog_row.get("session_strategy") or "shared_session",
                    "agent_strategy": catalog_row.get("agent_strategy") or "coordinator_only",
                    "entry_command_hint": catalog_row.get("entry_command_hint")
                    or self._space_entry_command_hint(space_key),
                }
        route["agent"] = next(
            (
                row
                for row in registry.get("visible_agents", []) + registry.get("internal_roles", [])
                if str(row.get("id")) == str(route.get("agent_id"))
            ),
            None,
        )
        if route.get("explicit_agent"):
            route["route_mode"] = "explicit_agent_prefix"
        elif route.get("kind") == "project" and route.get("matched"):
            route["route_mode"] = "project_hint"
        elif route.get("explicit_space"):
            route["route_mode"] = "explicit_space"
        else:
            route["route_mode"] = "default_front_door"
        if route.get("kind") == "project" and route.get("matched") and not route.get("resolved"):
            route["suggested_projects"] = self._suggest_project_spaces(
                requested_space_key=str(route.get("space_key") or ""),
                spaces=spaces,
            )
        else:
            route["suggested_projects"] = []
        return route

    def _suggest_project_spaces(self, *, requested_space_key: str, spaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
        requested = requested_space_key.strip().lower()
        if not requested:
            return []

        project_spaces = [
            self._normalize_space(ensure_dict(row))
            for row in spaces
            if str(ensure_dict(row).get("kind") or "").strip().lower() == "project"
        ]
        if not project_spaces:
            return []

        project_by_key = {str(row.get("key") or "").strip(): row for row in project_spaces}
        key_matches = difflib.get_close_matches(requested, list(project_by_key.keys()), n=3, cutoff=0.35)
        if not key_matches:
            requested_slug = requested.split("/", 1)[-1]
            slug_matches = difflib.get_close_matches(
                requested_slug,
                [str(row.get("key") or "").strip().split("/", 1)[-1] for row in project_spaces],
                n=3,
                cutoff=0.35,
            )
            for slug in slug_matches:
                key = f"projects/{slug}"
                if key in project_by_key and key not in key_matches:
                    key_matches.append(key)
        if not key_matches:
            scored = []
            requested_slug = requested.split("/", 1)[-1]
            for row in project_spaces:
                key = str(row.get("key") or "").strip()
                name = str(row.get("name") or "").strip().lower()
                slug = key.split("/", 1)[-1] if "/" in key else key
                score = max(
                    difflib.SequenceMatcher(a=requested, b=key.lower()).ratio(),
                    difflib.SequenceMatcher(a=requested_slug, b=slug.lower()).ratio(),
                    difflib.SequenceMatcher(a=requested_slug, b=name).ratio(),
                )
                if score >= 0.2:
                    scored.append((score, key))
            scored.sort(key=lambda item: (-item[0], item[1]))
            key_matches = [key for _, key in scored[:3]]

        out: list[dict[str, Any]] = []
        for key in key_matches[:3]:
            row = ensure_dict(project_by_key.get(key))
            if not row:
                continue
            out.append(
                {
                    "project_id": row.get("project_id"),
                    "space_key": row.get("key"),
                    "name": row.get("name"),
                    "entry_command_hint": row.get("entry_command_hint"),
                }
            )
        return out

    def create_agent_routed_task(
        self,
        *,
        text: str,
        source: str = "telegram",
    ) -> dict[str, Any]:
        route = self.route_text_to_space(text=text)
        if route.get("kind") == "project" and route.get("matched") and not route.get("resolved"):
            raise ValueError(f"project space not found: {route.get('space_key')}")

        stripped = str(route.get("stripped_text") or "").strip()
        if not stripped:
            raise ValueError("routed task text is required")

        agent_id = str(route.get("agent_id") or "assistant").strip().lower() or "assistant"
        notes_parts = [
            f"Captured from {source}",
            f"agent={agent_id}",
            f"space={route.get('space_key')}",
        ]
        if route.get("project_name"):
            notes_parts.append(f"project={route.get('project_name')}")

        task = self.create_task(
            title=stripped,
            assignees=[agent_id],
            project_id=str(route.get("project_id") or "").strip() or None,
            notes=" | ".join(notes_parts),
            source=source,
            assign_default_project=False,
        )
        activity = self.record_agent_activity(
            agent_id=agent_id,
            space_key=str(route.get("space_key") or "general"),
            space_kind=str(route.get("kind") or "core"),
            source=source,
            action="captured_request",
            text=stripped,
            route_mode=str(route.get("route_mode") or "default_front_door"),
            project_id=str(route.get("project_id") or "").strip() or None,
            project_name=str(route.get("project_name") or "").strip() or None,
            lane=str(ensure_dict(route.get("agent")).get("default_lane", "")).strip() or None,
            task_id=str(task.get("id") or "").strip() or None,
        )
        return {
            "route": route,
            "task": task,
            "activity": activity,
        }

    def create_braindump_item(
        self,
        *,
        category: str,
        text: str,
        tags: list[str] | None = None,
        review_bucket: str | None = None,
        notes: str | None = None,
        source: str = "dashboard",
    ) -> dict[str, Any]:
        conn = self._open_braindump_conn()
        try:
            item = braindump_runtime.create_item(
                conn,
                category=category,
                text=text,
                tags=tags or [],
                review_bucket=review_bucket,
                notes=notes,
                source=source,
            )
            snapshot = self._write_braindump_snapshot(conn)
            return {"item": item, "snapshot": snapshot}
        finally:
            conn.close()

    def capture_braindump_text(
        self,
        *,
        text: str,
        source: str = "channel_text",
        notes: str | None = None,
    ) -> dict[str, Any]:
        route = self.route_text_to_space(text=text)
        if route.get("kind") == "project" and route.get("matched") and not route.get("resolved"):
            raise ValueError(f"project space not found: {route.get('space_key')}")

        routed_text = (
            str(route.get("stripped_text", "")).strip()
            if route.get("kind") == "project" and route.get("resolved")
            else text.strip()
        )
        route_note = None
        if route.get("kind") == "project" and route.get("resolved"):
            route_note = f"space={route.get('space_key')}"
        combined_notes = "\n".join(part for part in [notes, route_note] if part and part.strip()) or None

        conn = self._open_braindump_conn()
        try:
            parsed = braindump_runtime.parse_capture_text(routed_text)
            item = braindump_runtime.capture_item_from_text(conn, routed_text, source=source, notes=combined_notes)
            snapshot = self._write_braindump_snapshot(conn)
            return {"route": route, "parsed": parsed, "item": item, "snapshot": snapshot}
        finally:
            conn.close()

    def park_braindump_item(
        self,
        *,
        item_id: str,
        review_bucket: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        conn = self._open_braindump_conn()
        try:
            item = braindump_runtime.park_item(conn, item_id, review_bucket=review_bucket, note=note)
            snapshot = self._write_braindump_snapshot(conn)
            return {"item": item, "snapshot": snapshot}
        finally:
            conn.close()

    def promote_braindump_item(
        self,
        *,
        item_id: str,
        target: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        conn = self._open_braindump_conn()
        try:
            item, promoted_to_id = braindump_runtime.promote_item(
                conn,
                item_id,
                target=target,
                workspace_path=self.workspace_path,
                calendar_path=self.calendar_candidates_path,
                note=note,
            )
            snapshot = self._write_braindump_snapshot(conn)
            return {"item": item, "promoted_to_id": promoted_to_id, "snapshot": snapshot}
        finally:
            conn.close()

    def archive_braindump_item(self, *, item_id: str, note: str | None = None) -> dict[str, Any]:
        conn = self._open_braindump_conn()
        try:
            item = braindump_runtime.archive_item(conn, item_id, note=note)
            snapshot = self._write_braindump_snapshot(conn)
            return {"item": item, "snapshot": snapshot}
        finally:
            conn.close()

    def set_dashboard_flags(
        self,
        *,
        local_telemetry_enabled: bool | None = None,
        codexbar_cost_enabled: bool | None = None,
        codexbar_usage_enabled: bool | None = None,
        codexbar_provider: str | None = None,
        codexbar_timeout_seconds: int | None = None,
        auto_refresh_seconds: int | None = None,
        auth_require_token: bool | None = None,
        auth_token_env_key: str | None = None,
        auth_session_ttl_minutes: int | None = None,
        auth_allow_generated_token: bool | None = None,
        routing_mode: str | None = None,
    ) -> dict[str, Any]:
        cfg = self.read_dashboard_config()
        dash = ensure_dict(cfg.setdefault("dashboard", {}))
        adapters = ensure_dict(dash.setdefault("adapters", {}))
        codexbar = ensure_dict(dash.setdefault("codexbar", {}))
        ui = ensure_dict(dash.setdefault("ui", {}))
        auth = ensure_dict(dash.setdefault("auth", {}))

        if local_telemetry_enabled is not None:
            adapters["local_telemetry_enabled"] = local_telemetry_enabled
        if codexbar_cost_enabled is not None:
            adapters["codexbar_cost_enabled"] = codexbar_cost_enabled
        if codexbar_usage_enabled is not None:
            adapters["codexbar_usage_enabled"] = codexbar_usage_enabled

        if codexbar_provider is not None:
            value = codexbar_provider.strip().lower()
            if value not in {"openai", "anthropic", "google", "all"}:
                raise ValueError("codexbar_provider must be one of: openai, anthropic, google, all")
            codexbar["provider"] = value

        if codexbar_timeout_seconds is not None:
            if codexbar_timeout_seconds <= 0:
                raise ValueError("codexbar_timeout_seconds must be > 0")
            codexbar["timeout_seconds"] = codexbar_timeout_seconds

        if auto_refresh_seconds is not None:
            if auto_refresh_seconds <= 0:
                raise ValueError("auto_refresh_seconds must be > 0")
            ui["auto_refresh_seconds"] = auto_refresh_seconds

        if auth_require_token is not None:
            auth["require_token"] = auth_require_token
        if auth_token_env_key is not None:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", auth_token_env_key):
                raise ValueError("auth_token_env_key must be a valid env variable name")
            auth["token_env_key"] = auth_token_env_key
        if auth_session_ttl_minutes is not None:
            if auth_session_ttl_minutes <= 0:
                raise ValueError("auth_session_ttl_minutes must be > 0")
            auth["session_ttl_minutes"] = auth_session_ttl_minutes
        if auth_allow_generated_token is not None:
            auth["allow_generated_token"] = auth_allow_generated_token

        if routing_mode is not None:
            self.set_routing_mode(routing_mode)

        self.write_dashboard_config(cfg)
        return cfg

    def apply_preset(self, name: str) -> dict[str, Any]:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("preset name is required")

        cfg = self.read_dashboard_config()
        presets = ensure_dict(ensure_dict(cfg.get("dashboard")).get("presets"))
        preset = ensure_dict(presets.get(clean_name))
        if not preset:
            raise ValueError(f"unknown preset: {clean_name}")

        actions: list[str] = []

        integrations_profile = preset.get("integrations_profile")
        memory_profile = preset.get("memory_profile")
        if isinstance(integrations_profile, str) or isinstance(memory_profile, str):
            self.switch_profiles(
                integrations_profile=integrations_profile if isinstance(integrations_profile, str) else None,
                memory_profile=memory_profile if isinstance(memory_profile, str) else None,
            )
            actions.append("profiles updated")

        for integration_name, enabled in ensure_dict(preset.get("integration_toggles")).items():
            if not isinstance(enabled, bool):
                continue
            self.set_integration_enabled(str(integration_name), enabled)
            actions.append(f"integration:{integration_name}={enabled}")

        for module_name, enabled in ensure_dict(preset.get("memory_module_toggles")).items():
            if not isinstance(enabled, bool):
                continue
            self.set_memory_module_enabled(str(module_name), enabled)
            actions.append(f"memory:{module_name}={enabled}")

        for module_name, enabled in ensure_dict(preset.get("n8n_module_toggles")).items():
            if not isinstance(enabled, bool):
                continue
            self.set_n8n_module_enabled(str(module_name), enabled)
            actions.append(f"n8n:{module_name}={enabled}")

        return {
            "ok": True,
            "preset": clean_name,
            "actions": actions,
        }

    def _find_model_log_path(self) -> Path | None:
        candidates = [
            self.telemetry_dir / "model-calls.ndjson",
            self.telemetry_dir / "model-calls.latest.ndjson",
            self.telemetry_dir / "model-calls.example.ndjson",
        ]
        for path in candidates:
            if path.exists():
                return path
        dynamic = sorted(self.telemetry_dir.glob("model-calls*.ndjson"))
        return dynamic[0] if dynamic else None

    def _local_usage(self) -> dict[str, Any]:
        log_path = self._find_model_log_path()
        if not log_path:
            return {
                "available": False,
                "source": None,
                "overall": asdict_totals(Totals()),
                "by_lane": [],
                "by_model": [],
                "recent_calls": [],
            }

        rows = read_ndjson(log_path)
        overall = Totals()
        by_lane: dict[str, Totals] = defaultdict(Totals)
        by_model: dict[str, Totals] = defaultdict(Totals)

        for row in rows:
            lane = str(row.get("lane", "unknown"))
            model = str(row.get("model", "unknown"))
            accumulate(overall, row)
            accumulate(by_lane[lane], row)
            accumulate(by_model[model], row)

        recent = sorted(rows, key=lambda r: str(r.get("ts", "")), reverse=True)[:30]
        recent_calls = [
            {
                "ts": str(item.get("ts", "")),
                "task_id": str(item.get("task_id", "")),
                "lane": str(item.get("lane", "unknown")),
                "provider": str(item.get("provider", "unknown")),
                "model": str(item.get("model", "unknown")),
                "status": str(item.get("status", "unknown")),
                "tokens": int(item.get("prompt_tokens", 0) or 0)
                + int(item.get("completion_tokens", 0) or 0),
                "estimated_cost_usd": float(item.get("estimated_cost_usd", 0.0) or 0.0),
            }
            for item in recent
        ]

        lane_rows = [
            {
                "lane": lane,
                **asdict_totals(totals),
                "avg_latency_ms": int(totals.latency_ms / totals.calls) if totals.calls else 0,
            }
            for lane, totals in sorted(by_lane.items(), key=lambda kv: kv[0])
        ]

        model_rows = [
            {
                "model": model,
                **asdict_totals(totals),
            }
            for model, totals in sorted(by_model.items(), key=lambda kv: (-kv[1].calls, kv[0]))
        ]

        return {
            "available": True,
            "source": str(log_path),
            "overall": asdict_totals(overall),
            "by_lane": lane_rows,
            "by_model": model_rows[:20],
            "recent_calls": recent_calls,
        }

    def _run_codexbar(self, command: str, provider: str, timeout_seconds: int) -> dict[str, Any]:
        cmd = ["codexbar", command, "--format", "json", "--provider", provider]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env={"PATH": os.environ.get("PATH", "")},
            )
        except FileNotFoundError:
            return {"available": False, "error": "codexbar not installed"}
        except subprocess.TimeoutExpired:
            return {"available": False, "error": "codexbar command timed out"}

        if proc.returncode != 0:
            message = proc.stderr.strip() or proc.stdout.strip() or "codexbar command failed"
            return {"available": False, "error": message}

        output = proc.stdout.strip()
        if not output:
            return {"available": True, "rows": []}

        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return {"available": False, "error": "codexbar returned invalid JSON"}

        rows = payload if isinstance(payload, list) else [payload]
        clean_rows = [row for row in rows if isinstance(row, dict)]
        return {"available": True, "rows": clean_rows}

    def _codexbar_usage(self, cfg: dict[str, Any]) -> dict[str, Any]:
        dash = ensure_dict(cfg.get("dashboard"))
        adapters = ensure_dict(dash.get("adapters"))
        codexbar = ensure_dict(dash.get("codexbar"))

        provider = str(codexbar.get("provider", "all"))
        timeout_seconds = int(codexbar.get("timeout_seconds", 20) or 20)

        out: dict[str, Any] = {
            "provider": provider,
            "cost": {
                "enabled": bool(adapters.get("codexbar_cost_enabled", False)),
                "available": False,
            },
            "usage": {
                "enabled": bool(adapters.get("codexbar_usage_enabled", False)),
                "available": False,
            },
        }

        if out["cost"]["enabled"]:
            out["cost"] = {
                "enabled": True,
                **self._run_codexbar("cost", provider, timeout_seconds),
            }

        if out["usage"]["enabled"]:
            out["usage"] = {
                "enabled": True,
                **self._run_codexbar("usage", provider, timeout_seconds),
            }

        return out

    def _count_reminders(self) -> dict[str, int]:
        state = read_json(self.reminder_state_path)
        counters = {
            "pending": 0,
            "awaiting_reply": 0,
            "done": 0,
            "cancelled": 0,
            "other": 0,
        }
        if not isinstance(state, dict):
            return counters

        reminders = ensure_dict(state.get("reminders"))
        for reminder in reminders.values():
            row = ensure_dict(reminder)
            status = str(row.get("status", "other"))
            if status in counters:
                counters[status] += 1
            else:
                counters["other"] += 1
        return counters

    def _pending_reminders(self) -> list[dict[str, Any]]:
        state = read_json(self.reminder_state_path)
        if not isinstance(state, dict):
            return []

        rows: list[dict[str, Any]] = []
        reminders = ensure_dict(state.get("reminders"))
        for reminder in reminders.values():
            row = ensure_dict(reminder)
            status = str(row.get("status", "")).strip()
            if status not in {"pending", "awaiting_reply"}:
                continue

            remind_at = str(row.get("remind_at", "")).strip() or None
            rows.append(
                {
                    "id": str(row.get("id", "")),
                    "message": str(row.get("message", "")).strip(),
                    "status": status,
                    "timezone": str(row.get("timezone", "")),
                    "remind_at": remind_at,
                    "minutes_until": minutes_until(remind_at),
                    "next_followup_at": str(row.get("next_followup_at", "")).strip() or None,
                    "last_reminded_at": str(row.get("last_reminded_at", "")).strip() or None,
                    "followup_count": int(row.get("followup_count", 0) or 0),
                }
            )

        rows.sort(key=lambda item: item.get("remind_at") or "")
        return rows

    def _gmail_inbox_status(self) -> dict[str, Any]:
        raw = read_json(self.gmail_status_path)
        if not isinstance(raw, dict):
            return {
                "available": False,
                "path": str(self.gmail_status_path),
                "state_db": str(self.gmail_db_path),
                "summary": {},
                "promotions": {},
                "recent_results": [],
                "manual_review_open": 0,
            }

        summary = ensure_dict(raw.get("summary"))
        promotions = ensure_dict(raw.get("promotions"))
        recent_results = [ensure_dict(item) for item in raw.get("recent_results", []) if isinstance(item, dict)]
        manual_review_open = 0
        if self.gmail_db_path.exists():
            conn: sqlite3.Connection | None = None
            try:
                conn = sqlite3.connect(self.gmail_db_path)
                row = conn.execute(
                    """
                    SELECT COUNT(*)
                      FROM gmail_messages
                     WHERE manual_review_required = 1
                       AND last_action IN ('mark_for_manual_review', 'keep_in_inbox')
                    """
                ).fetchone()
                manual_review_open = int((row or [0])[0] or 0)
            except sqlite3.DatabaseError:
                manual_review_open = 0
            finally:
                if conn is not None:
                    conn.close()

        return {
            "available": True,
            "path": str(self.gmail_status_path),
            "generated_at": str(raw.get("generated_at", "")).strip() or None,
            "run_id": raw.get("run_id"),
            "dry_run": bool(raw.get("dry_run") is True),
            "state_db": str(raw.get("state_db") or self.gmail_db_path),
            "summary": summary,
            "promotions": promotions,
            "recent_results": recent_results[:20],
            "manual_review_open": manual_review_open,
        }

    def _calendar_candidates(self) -> dict[str, Any]:
        raw = read_json(self.calendar_candidates_path)
        if not isinstance(raw, dict):
            return {
                "available": False,
                "path": str(self.calendar_candidates_path),
                "items": [],
                "count": 0,
                "status_counts": {},
            }

        items = [ensure_dict(item) for item in raw.get("items", []) if isinstance(item, dict)]
        items.sort(key=lambda row: str(row.get("updated_at", "")), reverse=True)
        status_counts: dict[str, int] = defaultdict(int)
        for item in items:
            status_counts[str(item.get("status", "proposed"))] += 1

        return {
            "available": True,
            "path": str(self.calendar_candidates_path),
            "items": items[:40],
            "count": len(items),
            "status_counts": dict(status_counts),
        }

    def _personal_task_runtime_status(self) -> dict[str, Any]:
        raw = read_json(self.personal_task_status_path)
        if not isinstance(raw, dict):
            return {
                "available": False,
                "path": str(self.personal_task_status_path),
                "provider": None,
                "summary": {},
                "recent_results": [],
                "tasks": [],
            }

        tasks = [ensure_dict(item) for item in raw.get("tasks", []) if isinstance(item, dict)]
        tasks.sort(key=lambda row: (str(row.get("due_value") or "9999-12-31"), str(row.get("title") or "")))
        return {
            "available": True,
            "path": str(self.personal_task_status_path),
            "generated_at": str(raw.get("generated_at", "")).strip() or None,
            "provider": str(raw.get("provider", "")).strip() or None,
            "summary": ensure_dict(raw.get("summary")),
            "recent_results": [ensure_dict(item) for item in raw.get("recent_results", []) if isinstance(item, dict)][:20],
            "tasks": tasks[:40],
        }

    def _calendar_runtime_status(self) -> dict[str, Any]:
        raw = read_json(self.calendar_runtime_status_path)
        if not isinstance(raw, dict):
            return {
                "available": False,
                "path": str(self.calendar_runtime_status_path),
                "calendar_id": None,
                "summary": {},
                "recent_results": [],
                "upcoming_events": [],
            }

        summary = ensure_dict(raw.get("summary"))
        recent_results = [ensure_dict(item) for item in raw.get("recent_results", []) if isinstance(item, dict)]
        upcoming_events = [ensure_dict(item) for item in raw.get("upcoming_events", []) if isinstance(item, dict)]
        upcoming_events.sort(key=lambda row: str(row.get("start_value") or ""))
        return {
            "available": True,
            "path": str(self.calendar_runtime_status_path),
            "generated_at": str(raw.get("generated_at", "")).strip() or None,
            "calendar_id": str(raw.get("calendar_id", "")).strip() or None,
            "summary": summary,
            "recent_results": recent_results[:20],
            "upcoming_events": upcoming_events[:20],
        }

    def _fitness_runtime(self) -> fitness_runtime.FitnessRuntime:
        return fitness_runtime.FitnessRuntime(
            root=self.root,
            status_path=self.fitness_runtime_status_path,
        )

    def _fitness_runtime_status(self) -> dict[str, Any]:
        raw = read_json(self.fitness_runtime_status_path)
        if not isinstance(raw, dict):
            try:
                raw = ensure_dict(self._fitness_runtime().snapshot(action="status"))
            except Exception:
                raw = {}
        if not isinstance(raw, dict) or not raw:
            return {
                "available": False,
                "path": str(self.fitness_runtime_status_path),
                "db_path": str(self.fitness_db_path),
                "today_plan": {},
                "active_session": None,
                "active_session_summary": [],
                "last_session": None,
                "last_session_summary": [],
                "weekly_volume": {},
                "progression_flags": [],
                "recent_results": [],
                "settings": {},
            }

        today_plan = ensure_dict(raw.get("today_plan"))
        active_session_summary = [
            ensure_dict(item) for item in (raw.get("active_session_summary") or []) if isinstance(item, dict)
        ]
        last_session_summary = [
            ensure_dict(item) for item in (raw.get("last_session_summary") or []) if isinstance(item, dict)
        ]
        progression_flags = [
            ensure_dict(item) for item in (raw.get("progression_flags") or []) if isinstance(item, dict)
        ]
        recent_results = [ensure_dict(item) for item in (raw.get("recent_results") or []) if isinstance(item, dict)]
        return {
            "available": True,
            "path": str(self.fitness_runtime_status_path),
            "generated_at": str(raw.get("generated_at", "")).strip() or None,
            "db_path": str(raw.get("db_path") or self.fitness_db_path),
            "action": str(raw.get("action", "")).strip() or None,
            "timezone": str(raw.get("timezone", "")).strip() or None,
            "settings": ensure_dict(raw.get("settings")),
            "today_plan": today_plan,
            "active_session": ensure_dict(raw.get("active_session")) if isinstance(raw.get("active_session"), dict) else None,
            "active_session_summary": active_session_summary[:20],
            "last_session": ensure_dict(raw.get("last_session")) if isinstance(raw.get("last_session"), dict) else None,
            "last_session_summary": last_session_summary[:20],
            "weekly_volume": ensure_dict(raw.get("weekly_volume")),
            "progression_flags": progression_flags[:20],
            "recent_results": recent_results[:20],
        }

    def _drive_workspace_status(self) -> dict[str, Any]:
        raw = read_json(self.drive_workspace_status_path)
        if not isinstance(raw, dict):
            return {
                "available": False,
                "path": str(self.drive_workspace_status_path),
                "summary": {},
            }

        return {
            "available": True,
            "path": str(self.drive_workspace_status_path),
            "generated_at": str(raw.get("generated_at", "")).strip() or None,
            "summary": ensure_dict(raw.get("summary")),
        }

    def _research_flow_status(self) -> dict[str, Any]:
        if not self.research_flow_config_path.exists():
            return {
                "available": False,
                "path": str(self.research_flow_status_path),
                "config_path": str(self.research_flow_config_path),
                "owner_agent": None,
                "default_space": None,
                "workflows": [],
                "last_run": None,
            }

        try:
            config = research_flow_runtime.load_config(self.research_flow_config_path)
            payload = read_json(self.research_flow_status_path)
            if not isinstance(payload, dict):
                payload = research_flow_runtime.build_status(config)
        except Exception as exc:
            return {
                "available": False,
                "path": str(self.research_flow_status_path),
                "config_path": str(self.research_flow_config_path),
                "error": str(exc),
                "owner_agent": None,
                "default_space": None,
                "workflows": [],
                "last_run": None,
            }

        workflows = [ensure_dict(item) for item in payload.get("workflows", []) if isinstance(item, dict)]
        workflows.sort(key=lambda row: str(row.get("name") or ""))
        return {
            "available": True,
            "path": str(self.research_flow_status_path),
            "config_path": str(self.research_flow_config_path),
            "generated_at": str(payload.get("generated_at") or "").strip() or None,
            "enabled": bool(payload.get("enabled") is True),
            "owner_agent": str(payload.get("owner_agent") or "").strip() or None,
            "default_space": str(payload.get("default_space") or "").strip() or None,
            "delivery_chat_env": str(payload.get("delivery_chat_env") or "").strip() or None,
            "shared_dropzones": ensure_string_list(payload.get("shared_dropzones", [])),
            "workflows": workflows[:20],
            "last_run": ensure_dict(payload.get("last_run")),
        }

    def _braindump_status(self) -> dict[str, Any]:
        catalog = self.braindump_category_catalog()
        raw = read_json(self.braindump_snapshot_path)
        if not isinstance(raw, dict):
            return {
                "available": False,
                "path": str(self.braindump_snapshot_path),
                "db_path": str(self.braindump_db_path),
                "category_catalog": catalog,
                "counts_by_status": {},
                "counts_by_bucket": {},
                "counts_by_category": {},
                "due_count": 0,
                "due_items": [],
                "recent_items": [],
            }

        due_items = [ensure_dict(item) for item in raw.get("due_items", []) if isinstance(item, dict)]
        recent_items = [ensure_dict(item) for item in raw.get("recent_items", []) if isinstance(item, dict)]
        due_items.sort(key=lambda row: str(row.get("next_review_at") or row.get("captured_at") or ""))
        recent_items.sort(key=lambda row: str(row.get("updated_at") or row.get("captured_at") or ""), reverse=True)

        return {
            "available": True,
            "path": str(self.braindump_snapshot_path),
            "generated_at": str(raw.get("generated_at", "")).strip() or None,
            "db_path": str(raw.get("db_path") or self.braindump_db_path),
            "category_catalog": catalog,
            "counts_by_status": ensure_dict(raw.get("counts_by_status")),
            "counts_by_bucket": ensure_dict(raw.get("counts_by_bucket")),
            "counts_by_category": ensure_dict(raw.get("counts_by_category")),
            "due_count": int(raw.get("due_count", len(due_items)) or 0),
            "due_items": due_items[:20],
            "recent_items": recent_items[:20],
        }

    def _profile_env_requirements(self) -> dict[str, Any]:
        integrations_data = self.load_yaml_dict(self.integrations_path)
        memory_data = self.load_yaml_dict(self.memory_path)

        profiles = ensure_dict(integrations_data.get("profiles"))
        definitions = ensure_dict(profiles.get("definitions"))
        active_profile_name = str(profiles.get("active_profile", ""))
        active_profile = ensure_dict(definitions.get(active_profile_name))

        integrations = ensure_dict(integrations_data.get("integrations"))
        tool_clis = ensure_dict(integrations_data.get("tool_clis"))

        required: list[str] = []

        for module_name in ensure_string_list(active_profile.get("enabled_integrations")):
            module = ensure_dict(integrations.get(module_name))
            if module.get("enabled") is not True:
                continue
            module_required = ensure_string_list(module.get("required_env"))
            provider_priority = ensure_string_list(module.get("provider_priority"))
            provider_env = ensure_dict(module.get("provider_env_requirements"))

            selected_provider = None
            for env_var in module_required:
                if env_var.endswith("_PROVIDER") and os.environ.get(env_var, "").strip():
                    selected_provider = os.environ.get(env_var, "").strip()
                    break
            if not selected_provider and provider_priority:
                selected_provider = provider_priority[0]
            if selected_provider:
                module_required.extend(ensure_string_list(provider_env.get(selected_provider)))

            required.extend(module_required)

        for cli_name in ensure_string_list(active_profile.get("enabled_tool_clis")):
            cli = ensure_dict(tool_clis.get(cli_name))
            if cli.get("enabled") is not True:
                continue
            required.extend(ensure_string_list(cli.get("required_env")))

        memory_profiles = ensure_dict(memory_data.get("profiles"))
        memory_definitions = ensure_dict(memory_profiles.get("definitions"))
        memory_active_name = str(memory_profiles.get("active_profile", ""))
        memory_active = ensure_dict(memory_definitions.get(memory_active_name))
        memory_modules = ensure_dict(memory_data.get("memory_modules"))

        for module_name in ensure_string_list(memory_active.get("enabled_modules")):
            module = ensure_dict(memory_modules.get(module_name))
            if module.get("enabled") is not True:
                continue
            required.extend(ensure_string_list(module.get("required_env")))

        required_unique = sorted(set(required))
        missing = [name for name in required_unique if not os.environ.get(name, "").strip()]
        return {
            "required": required_unique,
            "missing": missing,
            "ok": len(missing) == 0,
        }

    def _provider_health_status(self) -> dict[str, Any]:
        env_path = self._integration_env_file_path()
        status = provider_smoke_runtime.collect_status(
            models_path=self.models_path,
            memory_path=self.memory_path,
            integrations_path=self.integrations_path,
            agents_path=self.agents_path,
            env_file=env_path,
            live=False,
        )
        status["path"] = str(self.provider_smoke_status_path)

        snapshot = read_json(self.provider_smoke_status_path)
        if not isinstance(snapshot, dict):
            status["last_snapshot_generated_at"] = None
            return status

        snapshot_providers = {
            str(row.get("provider", "")).strip(): ensure_dict(row)
            for row in snapshot.get("providers", [])
            if isinstance(row, dict) and str(row.get("provider", "")).strip()
        }
        for row in status.get("providers", []):
            if not isinstance(row, dict):
                continue
            provider_name = str(row.get("provider", "")).strip()
            snap_row = snapshot_providers.get(provider_name)
            if not snap_row:
                continue
            live_probe = ensure_dict(snap_row.get("live_probe"))
            if live_probe:
                row["live_probe"] = live_probe

        status["last_snapshot_generated_at"] = str(snapshot.get("generated_at", "")).strip() or None
        summary = ensure_dict(status.get("summary"))
        summary["live_ok_count"] = sum(
            1 for row in status.get("providers", []) if ensure_dict(ensure_dict(row).get("live_probe")).get("ok") is True
        )
        status["summary"] = summary
        return status

    def _assistant_chat_status(self) -> dict[str, Any]:
        return self._agent_chat_status("assistant")

    def _agent_chat_state_path(self, agent_id: str) -> Path:
        clean_agent = agent_id.strip().lower().replace("_", "-") or "assistant"
        return self.root / "data" / f"{clean_agent}-chat-state.json"

    def _agent_chat_status(self, agent_id: str) -> dict[str, Any]:
        path = self._agent_chat_state_path(agent_id)
        raw = read_json(path)
        if not isinstance(raw, dict):
            return {
                "available": False,
                "agent_id": agent_id,
                "path": str(path),
                "updated_at": None,
                "spaces": [],
            }

        rows: list[dict[str, Any]] = []
        spaces = ensure_dict(raw.get("spaces"))
        for space_key, item in sorted(spaces.items(), key=lambda kv: kv[0]):
            row = ensure_dict(item)
            turns = [ensure_dict(turn) for turn in row.get("turns", []) if isinstance(turn, dict)]
            rows.append(
                {
                    "space_key": space_key,
                    "turn_count": len(turns),
                    "summary_present": bool(str(row.get("summary") or "").strip()),
                    "last_lane": str(row.get("last_lane") or "").strip() or None,
                    "last_provider": str(row.get("last_provider") or "").strip() or None,
                    "last_model": str(row.get("last_model") or "").strip() or None,
                    "updated_at": str(row.get("updated_at") or "").strip() or None,
                }
            )
        rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return {
            "available": True,
            "agent_id": agent_id,
            "path": str(path),
            "updated_at": str(raw.get("updated_at") or "").strip() or None,
            "spaces": rows[:12],
        }

    def _agent_chats_status(self) -> dict[str, Any]:
        runtime = self._agent_runtime_snapshot()
        chat_agents = [
            ensure_dict(row)
            for row in runtime.get("visible_agents", [])
            if str(ensure_dict(row).get("interaction_mode") or "").strip() == "chat"
        ]
        rows = [self._agent_chat_status(str(row.get("id") or "")) for row in chat_agents]
        rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return {
            "available": any(bool(row.get("available")) for row in rows),
            "agents": rows,
        }

    def _telegram_adapter_status(self) -> dict[str, Any]:
        raw = read_json(self.telegram_adapter_state_path)
        channels_data = self.load_yaml_dict(self.channels_path)
        telegram_cfg = ensure_dict(ensure_dict(channels_data.get("channels")).get("telegram"))
        bindings_cfg = ensure_dict(telegram_cfg.get("chat_bindings"))
        env_values: dict[str, str] = {}
        env_path = self._integration_env_file_path()
        if env_path and env_path.exists():
            try:
                env_values = calendar_runtime.load_env_file(env_path)
            except Exception:
                env_values = {}

        bindings: list[dict[str, Any]] = []
        for binding_id, raw_binding in bindings_cfg.items():
            binding = ensure_dict(raw_binding)
            env_key = str(binding.get("chat_id_env") or "").strip()
            chat_id = str(env_values.get(env_key, "")).strip() if env_key else str(binding.get("chat_id") or "").strip()
            if not chat_id and str(binding_id) == "assistant_main":
                chat_id = str(env_values.get("TELEGRAM_ALLOWED_CHAT_ID", "")).strip()
            masked = chat_id[-4:] if len(chat_id) >= 4 else chat_id
            bindings.append(
                {
                    "binding_id": str(binding_id),
                    "label": str(binding.get("label") or binding_id).strip() or str(binding_id),
                    "default_agent": str(binding.get("default_agent") or "assistant").strip() or "assistant",
                    "default_space": str(binding.get("default_space") or "general").strip() or "general",
                    "chat_id_env": env_key or None,
                    "configured": bool(chat_id),
                    "chat_id_mask": (f"...{masked}" if masked else None),
                }
            )

        if not isinstance(raw, dict) or not raw:
            return {
                "available": False,
                "path": str(self.telegram_adapter_state_path),
                "bindings": bindings,
                "default_binding_id": str(telegram_cfg.get("default_binding") or "assistant_main").strip() or "assistant_main",
                "reminder_binding_id": str(telegram_cfg.get("reminder_binding") or "assistant_main").strip() or "assistant_main",
                "focus": None,
                "updated_at": None,
                "last_update_id": None,
            }
        focus = ensure_dict(raw.get("conversation_focus"))
        if not focus:
            focus = {"agent_id": "assistant", "space_key": "general"}
        return {
            "available": True,
            "path": str(self.telegram_adapter_state_path),
            "bindings": bindings,
            "default_binding_id": str(telegram_cfg.get("default_binding") or "assistant_main").strip() or "assistant_main",
            "reminder_binding_id": str(telegram_cfg.get("reminder_binding") or "assistant_main").strip() or "assistant_main",
            "focus": {
                "agent_id": str(focus.get("agent_id") or "assistant").strip() or "assistant",
                "space_key": str(focus.get("space_key") or "general").strip() or "general",
                "set_at": str(focus.get("set_at") or "").strip() or None,
            },
            "updated_at": str(raw.get("updated_at") or "").strip() or None,
            "last_update_id": raw.get("last_update_id"),
        }

    def _continuous_improvement_status(self) -> dict[str, Any]:
        raw = read_json(self.continuous_improvement_status_path)
        if not isinstance(raw, dict):
            return {
                "available": False,
                "path": str(self.continuous_improvement_status_path),
                "mode": None,
                "generated_at": None,
                "report_path": None,
                "findings_count": 0,
                "recommended_changes": [],
            }
        return {
            "available": True,
            "path": str(self.continuous_improvement_status_path),
            "mode": str(raw.get("mode") or "").strip() or None,
            "generated_at": str(raw.get("generated_at") or "").strip() or None,
            "report_path": str(raw.get("report_path") or "").strip() or None,
            "findings_count": int(raw.get("findings_count", 0) or 0),
            "recommended_changes": ensure_string_list(raw.get("recommended_changes", [])),
            "approval_required_changes": ensure_string_list(raw.get("approval_required_changes", [])),
            "archive_candidates": ensure_string_list(raw.get("archive_candidates", [])),
        }

    def _memory_sync_status(self) -> dict[str, Any]:
        raw = read_json(self.memory_sync_status_path)
        if not isinstance(raw, dict):
            return {
                "available": False,
                "path": str(self.memory_sync_status_path),
                "ok": None,
                "generated_at": None,
                "profile": None,
                "files_scanned": 0,
                "embeddings_created": 0,
            }
        summary = ensure_dict(raw.get("summary"))
        return {
            "available": True,
            "path": str(self.memory_sync_status_path),
            "ok": bool(raw.get("ok") is True),
            "generated_at": str(raw.get("generated_at") or "").strip() or None,
            "profile": str(raw.get("profile") or "").strip() or None,
            "files_scanned": int(summary.get("files_scanned", 0) or 0),
            "embeddings_created": int(summary.get("embeddings_created", 0) or 0),
            "stdout_tail": str(raw.get("stdout_tail") or "").strip() or None,
            "stderr_tail": str(raw.get("stderr_tail") or "").strip() or None,
        }

    def run_provider_smoke_check(self, *, live: bool = False) -> dict[str, Any]:
        env_path = self._integration_env_file_path()
        payload = provider_smoke_runtime.collect_status(
            models_path=self.models_path,
            memory_path=self.memory_path,
            integrations_path=self.integrations_path,
            agents_path=self.agents_path,
            env_file=env_path,
            live=live,
        )
        write_json(self.provider_smoke_status_path, payload)
        return payload

    def run_research_flow_runtime(
        self,
        *,
        workflow: str,
        apply: bool = True,
    ) -> dict[str, Any]:
        clean_workflow = workflow.strip()
        if clean_workflow not in {"job_search_digest", "ai_tools_watch", "all"}:
            raise ValueError("workflow must be one of: job_search_digest, ai_tools_watch, all")
        if not self.research_flow_script.exists():
            raise ValueError("research_flow_runtime.py is missing")
        if not self.research_flow_config_path.exists():
            raise ValueError("research_flow.yaml is missing")

        env_path = self._integration_env_file_path()
        cmd = [
            "python3",
            str(self.research_flow_script),
            "--config",
            str(self.research_flow_config_path),
            "--status-file",
            str(self.research_flow_status_path),
        ]
        if env_path is not None:
            cmd.extend(["--env-file", str(env_path)])
        cmd.extend(["run", "--workflow", clean_workflow])
        if apply:
            cmd.append("--apply")
        cmd.append("--json")

        proc = subprocess.run(cmd, cwd=str(self.root), capture_output=True, text=True)
        stdout = proc.stdout.strip()
        payload: dict[str, Any] = {}
        if stdout:
            try:
                parsed = json.loads(stdout)
                if isinstance(parsed, dict):
                    payload = parsed
            except json.JSONDecodeError:
                payload = {}
        if proc.returncode != 0:
            message = (stdout + "\n" + proc.stderr.strip()).strip()
            raise ValueError(message or "Failed to run ResearchFlow workflow")
        return {"status": payload or self._research_flow_status()}

    def _find_section_start(self, lines: list[str], section: str) -> int:
        needle = f"{section}:"
        for idx, line in enumerate(lines):
            if line.strip() == needle and not line.startswith(" "):
                return idx
        raise ValueError(f"Section not found: {section}")

    def _find_entry_block(self, lines: list[str], section_start: int, entry_name: str) -> tuple[int, int]:
        section_indent = len(lines[section_start]) - len(lines[section_start].lstrip(" "))
        entry_start = -1
        entry_indent = section_indent + 2

        for idx in range(section_start + 1, len(lines)):
            line = lines[idx]
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            if indent <= section_indent:
                break
            if indent == entry_indent and line.strip() == f"{entry_name}:":
                entry_start = idx
                break

        if entry_start == -1:
            raise ValueError(f"Entry not found: {entry_name}")

        entry_end = len(lines)
        for idx in range(entry_start + 1, len(lines)):
            line = lines[idx]
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            if indent <= entry_indent:
                entry_end = idx
                break

        return entry_start, entry_end

    def _replace_block_bool(
        self,
        *,
        path: Path,
        top_section: str,
        entry_name: str,
        key_name: str,
        value: bool,
        key_indent: int = 4,
    ) -> None:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()

        section_start = self._find_section_start(lines, top_section)
        entry_start, entry_end = self._find_entry_block(lines, section_start, entry_name)

        key_prefix = " " * key_indent + f"{key_name}:"
        for idx in range(entry_start + 1, entry_end):
            if lines[idx].startswith(key_prefix):
                suffix_match = re.match(r"^\s*[^#]+(\s+#.*)?$", lines[idx])
                suffix = suffix_match.group(1) if suffix_match else ""
                lines[idx] = f"{key_prefix} {str(value).lower()}{suffix or ''}"
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return

        insert_at = entry_start + 1
        lines.insert(insert_at, f"{key_prefix} {str(value).lower()}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _replace_section_scalar(
        self,
        *,
        path: Path,
        section: str,
        key_name: str,
        value: str,
    ) -> None:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()

        section_start = self._find_section_start(lines, section)
        section_indent = len(lines[section_start]) - len(lines[section_start].lstrip(" "))
        key_indent = section_indent + 2
        key_prefix = " " * key_indent + f"{key_name}:"

        section_end = len(lines)
        for idx in range(section_start + 1, len(lines)):
            line = lines[idx]
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            if indent <= section_indent:
                section_end = idx
                break

        for idx in range(section_start + 1, section_end):
            if lines[idx].startswith(key_prefix):
                lines[idx] = f"{key_prefix} {value}"
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return

        lines.insert(section_start + 1, f"{key_prefix} {value}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _set_n8n_module_enabled(self, module_name: str, enabled: bool) -> None:
        path = self.integrations_path
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()

        integrations_start = self._find_section_start(lines, "integrations")
        n8n_start, n8n_end = self._find_entry_block(lines, integrations_start, "n8n")

        modules_start = -1
        for idx in range(n8n_start + 1, n8n_end):
            if lines[idx].strip() == "modules:":
                modules_start = idx
                break
        if modules_start == -1:
            raise ValueError("n8n modules block not found")

        modules_indent = len(lines[modules_start]) - len(lines[modules_start].lstrip(" "))
        item_indent = modules_indent + 2

        insert_at = modules_start + 1
        found = False
        for idx in range(modules_start + 1, n8n_end):
            line = lines[idx]
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            if indent <= modules_indent:
                insert_at = idx
                break
            insert_at = idx + 1
            if indent == item_indent and line.strip().startswith(f"{module_name}:"):
                lines[idx] = " " * item_indent + f"{module_name}: {str(enabled).lower()}"
                found = True
                break

        if not found:
            lines.insert(insert_at, " " * item_indent + f"{module_name}: {str(enabled).lower()}")

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def switch_profiles(
        self,
        integrations_profile: str | None = None,
        memory_profile: str | None = None,
    ) -> dict[str, Any]:
        if not integrations_profile and not memory_profile:
            raise ValueError("Provide integrations_profile and/or memory_profile")

        cmd = ["python3", str(self.set_profiles_script)]
        if integrations_profile:
            cmd.extend(["--integrations-profile", integrations_profile])
        if memory_profile:
            cmd.extend(["--memory-profile", memory_profile])

        proc = subprocess.run(cmd, cwd=str(self.root), capture_output=True, text=True)
        if proc.returncode != 0:
            message = (proc.stdout + "\n" + proc.stderr).strip()
            raise ValueError(message or "Failed to switch profile")

        return {
            "ok": True,
            "message": proc.stdout.strip(),
        }

    def set_integration_enabled(self, name: str, enabled: bool) -> None:
        self._replace_block_bool(
            path=self.integrations_path,
            top_section="integrations",
            entry_name=name,
            key_name="enabled",
            value=enabled,
            key_indent=4,
        )

    def set_memory_module_enabled(self, name: str, enabled: bool) -> None:
        self._replace_block_bool(
            path=self.memory_path,
            top_section="memory_modules",
            entry_name=name,
            key_name="enabled",
            value=enabled,
            key_indent=4,
        )

    def set_n8n_module_enabled(self, name: str, enabled: bool) -> None:
        self._set_n8n_module_enabled(name, enabled)

    def _routing_modes(self) -> tuple[list[dict[str, Any]], str]:
        models_data = self.load_yaml_dict(self.models_path)
        usage_modes = ensure_dict(ensure_dict(models_data.get("routing")).get("usage_modes"))
        rows: list[dict[str, Any]] = []

        for name, raw in sorted(usage_modes.items(), key=lambda kv: kv[0]):
            row = ensure_dict(raw)
            rows.append(
                {
                    "name": str(name),
                    "description": str(row.get("description", "")).strip(),
                }
            )

        agents_data = self.load_yaml_dict(self.agents_path)
        active_mode = str(ensure_dict(agents_data.get("routing_overrides")).get("active_mode", "")).strip()
        if not active_mode:
            names = [item["name"] for item in rows]
            active_mode = "balanced_default" if "balanced_default" in names else (names[0] if names else "")

        return rows, active_mode

    def set_routing_mode(self, mode: str) -> None:
        clean_mode = mode.strip()
        if not clean_mode:
            raise ValueError("routing_mode is required")

        modes, _ = self._routing_modes()
        allowed = {item["name"] for item in modes}
        if clean_mode not in allowed:
            raise ValueError(f"unknown routing_mode: {clean_mode}")

        self._replace_section_scalar(
            path=self.agents_path,
            section="routing_overrides",
            key_name="active_mode",
            value=clean_mode,
        )

    def _assignable_entities(self) -> list[dict[str, Any]]:
        agents_data = self.load_yaml_dict(self.agents_path)
        agents = ensure_dict(agents_data.get("agents"))

        out = [
            {
                "id": "pavel",
                "label": "Pavel",
                "kind": "human",
                "default_lane": None,
            }
        ]

        for name, row in sorted(agents.items(), key=lambda kv: kv[0]):
            item = ensure_dict(row)
            if item.get("enabled") is not True:
                continue
            out.append(
                {
                    "id": str(name),
                    "label": str(name),
                    "kind": "agent",
                    "default_lane": str(item.get("default_lane", "")) or None,
                }
            )

        return out

    def _side_effect_catalog(self) -> list[str]:
        integrations_data = self.load_yaml_dict(self.integrations_path)
        integrations = ensure_dict(integrations_data.get("integrations"))
        tool_clis = ensure_dict(integrations_data.get("tool_clis"))

        effects = {"custom:external_write"}
        for integration_name, integration_data in integrations.items():
            row = ensure_dict(integration_data)
            for action in ensure_string_list(row.get("write_actions", [])):
                effects.add(f"{integration_name}:{action}")

        for cli_name, cli_data in tool_clis.items():
            row = ensure_dict(cli_data)
            for action in ensure_string_list(row.get("approval_required_for", [])):
                effects.add(f"tool_cli:{cli_name}:{action}")

        return sorted(effects)

    def _normalize_side_effects(self, side_effects: list[str] | None) -> list[str]:
        clean = dedupe_string_list(
            [item.strip().lower() for item in (side_effects or []) if isinstance(item, str) and item.strip()]
        )
        if not clean:
            return []

        allowed = set(self._side_effect_catalog())
        invalid = [item for item in clean if item not in allowed]
        if invalid:
            raise ValueError(
                "unknown side_effects: "
                + ", ".join(invalid)
                + ". Use one of the catalog values from integrations/tool CLIs or custom:external_write."
            )
        return clean

    def _task_templates(self) -> list[dict[str, Any]]:
        cfg = self.read_dashboard_config()
        templates = ensure_dict(ensure_dict(cfg.get("dashboard")).get("task_templates"))

        rows: list[dict[str, Any]] = []
        for name, raw in sorted(templates.items(), key=lambda kv: kv[0]):
            row = ensure_dict(raw)
            priority = str(row.get("priority", "medium")).strip().lower()
            if priority not in PRIORITY_LEVELS:
                priority = "medium"

            status = str(row.get("status", "todo")).strip().lower()
            if status not in TASK_STATUSES:
                status = "todo"

            due_in_hours: int | None = None
            value = row.get("due_in_hours")
            if isinstance(value, int) and value > 0:
                due_in_hours = value

            rows.append(
                {
                    "name": name,
                    "title": str(row.get("title", "")).strip() or "Task: ",
                    "description": str(row.get("description", "")).strip(),
                    "priority": priority,
                    "status": status,
                    "default_assignees": ensure_string_list(row.get("default_assignees", [])),
                    "due_in_hours": due_in_hours,
                    "notes": str(row.get("notes", "")).strip(),
                    "side_effects": self._normalize_side_effects(ensure_string_list(row.get("side_effects", []))),
                    "requires_approval": bool(row.get("requires_approval") is True),
                }
            )
        return rows

    def _approval_settings(self) -> dict[str, Any]:
        cfg = self.read_dashboard_config()
        approvals = ensure_dict(ensure_dict(cfg.get("dashboard")).get("approvals"))
        keywords = [item.lower() for item in ensure_string_list(approvals.get("external_write_keywords", []))]
        return {
            "require_for_external_writes": bool(approvals.get("require_for_external_writes", True)),
            "external_write_keywords": keywords,
            "auto_expire_hours": int(approvals.get("auto_expire_hours", 72) or 72),
        }

    def _task_requires_approval(self, task: dict[str, Any]) -> bool:
        settings = self._approval_settings()
        if not settings["require_for_external_writes"]:
            return False

        if bool(task.get("requires_approval") is True):
            return True

        if ensure_string_list(task.get("side_effects", [])):
            return True

        source = f"{task.get('title', '')} {task.get('notes', '')}".lower()
        for keyword in settings["external_write_keywords"]:
            if keyword and keyword in source:
                return True

        return False

    def create_task_from_template(
        self,
        *,
        template_name: str,
        title: str | None = None,
        assignees: list[str] | None = None,
        project_id: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        due_at: str | None = None,
        notes: str | None = None,
        side_effects: list[str] | None = None,
        requires_approval: bool | None = None,
    ) -> dict[str, Any]:
        clean_template = template_name.strip()
        if not clean_template:
            raise ValueError("template_name is required")

        templates = {row["name"]: row for row in self._task_templates()}
        template = templates.get(clean_template)
        if not template:
            raise ValueError(f"unknown task template: {clean_template}")

        resolved_title = (title or "").strip() or str(template.get("title", "Task: ")).strip() or "Task: "
        resolved_priority = (priority or "").strip().lower() or str(template.get("priority", "medium"))
        resolved_status = (status or "").strip().lower() or str(template.get("status", "todo"))
        resolved_notes = (notes or "").strip() or str(template.get("notes", "")).strip() or None
        resolved_side_effects = (
            self._normalize_side_effects(side_effects)
            if side_effects is not None
            else self._normalize_side_effects(ensure_string_list(template.get("side_effects", [])))
        )
        resolved_requires_approval = (
            bool(requires_approval)
            if requires_approval is not None
            else bool(template.get("requires_approval") is True or resolved_side_effects)
        )

        resolved_assignees = [item.strip().lower() for item in (assignees or []) if item.strip()]
        if not resolved_assignees:
            resolved_assignees = [item.strip().lower() for item in template.get("default_assignees", []) if item.strip()]
        if not resolved_assignees:
            resolved_assignees = ["pavel"]

        resolved_due_at = (due_at or "").strip() or None
        if not resolved_due_at:
            due_in_hours = template.get("due_in_hours")
            if isinstance(due_in_hours, int) and due_in_hours > 0:
                resolved_due_at = (datetime.now(timezone.utc) + timedelta(hours=due_in_hours)).isoformat()

        task = self.create_task(
            title=resolved_title,
            assignees=resolved_assignees,
            project_id=(project_id or "").strip() or None,
            status=resolved_status,
            priority=resolved_priority,
            due_at=resolved_due_at,
            notes=resolved_notes,
            progress_pct=0,
            source="template",
            side_effects=resolved_side_effects,
            requires_approval=resolved_requires_approval,
        )

        return {
            "template": clean_template,
            "task": task,
        }

    def create_project(
        self,
        *,
        name: str,
        description: str | None = None,
        owner: str | None = None,
        target_date: str | None = None,
        status: str = "active",
    ) -> dict[str, Any]:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("project name is required")

        clean_status = status.strip().lower()
        if clean_status not in PROJECT_STATUSES:
            raise ValueError(f"invalid project status: {status}")

        now = iso_now_utc()
        project = self._normalize_project(
            {
                "id": f"proj-{slugify(clean_name)}-{uuid.uuid4().hex[:6]}",
                "name": clean_name,
                "description": (description or "").strip(),
                "owner": (owner or "pavel").strip().lower(),
                "target_date": (target_date or "").strip() or None,
                "status": clean_status,
                "progress_pct": 0,
                "created_at": now,
                "updated_at": now,
            }
        )

        workspace = self.load_workspace_data()
        workspace["projects"].append(project)
        self.save_workspace_data(workspace)
        return project

    def promote_task_to_project(
        self,
        *,
        task_id: str,
        name: str | None = None,
        description: str | None = None,
        owner: str | None = None,
    ) -> dict[str, Any]:
        clean_task_id = task_id.strip()
        if not clean_task_id:
            raise ValueError("task_id is required")

        workspace = self.load_workspace_data()
        tasks = workspace["tasks"]

        target_task: dict[str, Any] | None = None
        for row in tasks:
            if str(row.get("id")) == clean_task_id:
                target_task = row
                break

        if target_task is None:
            raise ValueError(f"task not found: {clean_task_id}")

        project_name = (name or "").strip() or str(target_task.get("title", "Project")).strip() or "Project"
        project_description = (description or "").strip() or str(target_task.get("notes", "")).strip() or project_name
        project_owner = (owner or "").strip().lower() or (
            ensure_string_list(target_task.get("assignees", []))[0] if ensure_string_list(target_task.get("assignees", [])) else "pavel"
        )

        now = iso_now_utc()
        project = self._normalize_project(
            {
                "id": f"proj-{slugify(project_name)}-{uuid.uuid4().hex[:6]}",
                "name": project_name,
                "description": project_description,
                "owner": project_owner,
                "target_date": None,
                "status": "active",
                "progress_pct": 0,
                "created_at": now,
                "updated_at": now,
            }
        )
        workspace["projects"].append(project)

        target_task["project_id"] = project["id"]
        target_task["updated_at"] = now
        if not str(target_task.get("notes", "")).strip() and project_description:
            target_task["notes"] = project_description

        workspace = self._ensure_project_spaces_in_workspace(workspace)
        for idx, row in enumerate(workspace["spaces"]):
            if str(row.get("project_id")) == project["id"]:
                merged = dict(row)
                merged["source_task_id"] = clean_task_id
                merged["summary"] = project_description
                merged["updated_at"] = now
                workspace["spaces"][idx] = self._normalize_space(merged)
                break

        self.save_workspace_data(workspace)

        normalized_task = self._normalize_task(target_task)
        normalized_space = next(
            (self._normalize_space(ensure_dict(row)) for row in workspace["spaces"] if str(row.get("project_id")) == project["id"]),
            self._project_space_template(project, source_task_id=clean_task_id),
        )
        return {
            "project": project,
            "task": normalized_task,
            "space": normalized_space,
        }

    def assign_task_to_project_space(
        self,
        *,
        task_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        clean_task_id = task_id.strip()
        clean_project_id = project_id.strip()
        if not clean_task_id:
            raise ValueError("task_id is required")
        if not clean_project_id:
            raise ValueError("project_id is required")

        workspace = self.load_workspace_data()
        workspace = self._ensure_project_spaces_in_workspace(workspace)

        tasks = workspace["tasks"]
        target_task = next((row for row in tasks if str(row.get("id")) == clean_task_id), None)
        if target_task is None:
            raise ValueError(f"task not found: {clean_task_id}")

        project = next((self._normalize_project(ensure_dict(row)) for row in workspace["projects"] if str(row.get("id")) == clean_project_id), None)
        if project is None:
            raise ValueError(f"project not found: {clean_project_id}")

        space = next((self._normalize_space(ensure_dict(row)) for row in workspace["spaces"] if str(row.get("project_id")) == clean_project_id), None)
        if space is None:
            raise ValueError(f"project space not found: {clean_project_id}")

        now = iso_now_utc()
        target_task["project_id"] = clean_project_id
        target_task["updated_at"] = now

        for idx, row in enumerate(tasks):
            if str(row.get("id")) == clean_task_id:
                tasks[idx] = self._normalize_task(target_task)
                break

        self.save_workspace_data(workspace)
        return {
            "task": self._normalize_task(target_task),
            "project": project,
            "space": space,
        }

    def update_project(
        self,
        *,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        target_date: str | None = None,
        status: str | None = None,
        progress_pct: int | None = None,
    ) -> dict[str, Any]:
        clean_id = project_id.strip()
        if not clean_id:
            raise ValueError("project_id is required")

        workspace = self.load_workspace_data()
        projects = workspace["projects"]

        target: dict[str, Any] | None = None
        for row in projects:
            if row.get("id") == clean_id:
                target = row
                break

        if target is None:
            raise ValueError(f"project not found: {clean_id}")

        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("project name cannot be empty")
            target["name"] = clean_name
        if description is not None:
            target["description"] = description.strip()
        if owner is not None:
            clean_owner = owner.strip().lower()
            if not clean_owner:
                raise ValueError("project owner cannot be empty")
            target["owner"] = clean_owner
        if target_date is not None:
            target["target_date"] = target_date.strip() or None
        if status is not None:
            clean_status = status.strip().lower()
            if clean_status not in PROJECT_STATUSES:
                raise ValueError(f"invalid project status: {status}")
            target["status"] = clean_status
        if progress_pct is not None:
            if progress_pct < 0 or progress_pct > 100:
                raise ValueError("progress_pct must be between 0 and 100")
            target["progress_pct"] = int(progress_pct)

        target["updated_at"] = iso_now_utc()
        self.save_workspace_data(workspace)
        return self._normalize_project(target)

    def create_task(
        self,
        *,
        title: str,
        assignees: list[str],
        project_id: str | None = None,
        status: str = "todo",
        priority: str = "medium",
        due_at: str | None = None,
        notes: str | None = None,
        progress_pct: int | None = None,
        source: str = "dashboard",
        side_effects: list[str] | None = None,
        requires_approval: bool = False,
        assign_default_project: bool = True,
    ) -> dict[str, Any]:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("task title is required")

        clean_assignees = [item.strip().lower() for item in assignees if item.strip()]
        if not clean_assignees:
            raise ValueError("at least one assignee is required")

        clean_status = status.strip().lower()
        if clean_status not in TASK_STATUSES:
            raise ValueError(f"invalid task status: {status}")

        clean_priority = priority.strip().lower()
        if clean_priority not in PRIORITY_LEVELS:
            raise ValueError(f"invalid task priority: {priority}")
        clean_side_effects = self._normalize_side_effects(side_effects)

        workspace = self.load_workspace_data()
        projects = workspace["projects"]
        project_lookup = {str(row.get("id")): row for row in projects}

        selected_project_id: str | None = None
        if project_id and project_id.strip():
            selected_project_id = project_id.strip()
            if selected_project_id not in project_lookup:
                raise ValueError(f"project not found: {selected_project_id}")
        elif assign_default_project:
            active = [row for row in projects if str(row.get("status")) in {"active", "planned"}]
            if active:
                selected_project_id = str(active[0].get("id"))

        now = iso_now_utc()
        task = self._normalize_task(
            {
                "id": f"task-{slugify(clean_title)}-{uuid.uuid4().hex[:6]}",
                "title": clean_title,
                "status": clean_status,
                "project_id": selected_project_id,
                "assignees": clean_assignees,
                "priority": clean_priority,
                "due_at": due_at.strip() if due_at and due_at.strip() else None,
                "notes": (notes or "").strip(),
                "source": source.strip() or "dashboard",
                "progress_pct": progress_pct,
                "requires_approval": bool(requires_approval or clean_side_effects),
                "side_effects": clean_side_effects,
                "created_at": now,
                "updated_at": now,
            }
        )

        workspace["tasks"].append(task)
        self.save_workspace_data(workspace)
        return task

    def update_task(
        self,
        *,
        task_id: str,
        title: str | None = None,
        status: str | None = None,
        project_id: str | None = None,
        assignees: list[str] | None = None,
        priority: str | None = None,
        due_at: str | None = None,
        notes: str | None = None,
        progress_pct: int | None = None,
        side_effects: list[str] | None = None,
        requires_approval: bool | None = None,
    ) -> dict[str, Any]:
        clean_id = task_id.strip()
        if not clean_id:
            raise ValueError("task_id is required")

        workspace = self.load_workspace_data()
        tasks = workspace["tasks"]
        projects = {str(row.get("id")): row for row in workspace["projects"]}

        target: dict[str, Any] | None = None
        for row in tasks:
            if row.get("id") == clean_id:
                target = row
                break

        if target is None:
            raise ValueError(f"task not found: {clean_id}")

        if title is not None:
            clean_title = title.strip()
            if not clean_title:
                raise ValueError("task title cannot be empty")
            target["title"] = clean_title

        if status is not None:
            clean_status = status.strip().lower()
            if clean_status not in TASK_STATUSES:
                raise ValueError(f"invalid task status: {status}")
            target["status"] = clean_status

        if project_id is not None:
            clean_project_id = project_id.strip()
            if clean_project_id and clean_project_id not in projects:
                raise ValueError(f"project not found: {clean_project_id}")
            target["project_id"] = clean_project_id or None

        if assignees is not None:
            clean_assignees = [item.strip().lower() for item in assignees if item.strip()]
            if not clean_assignees:
                raise ValueError("at least one assignee is required")
            target["assignees"] = clean_assignees

        if priority is not None:
            clean_priority = priority.strip().lower()
            if clean_priority not in PRIORITY_LEVELS:
                raise ValueError(f"invalid task priority: {priority}")
            target["priority"] = clean_priority

        if due_at is not None:
            target["due_at"] = due_at.strip() or None

        if notes is not None:
            target["notes"] = notes.strip()

        if progress_pct is not None:
            if progress_pct < 0 or progress_pct > 100:
                raise ValueError("progress_pct must be between 0 and 100")
            target["progress_pct"] = int(progress_pct)

        if side_effects is not None:
            clean_side_effects = self._normalize_side_effects(side_effects)
            target["side_effects"] = clean_side_effects
            if clean_side_effects and requires_approval is None:
                target["requires_approval"] = True

        if requires_approval is not None:
            target["requires_approval"] = requires_approval

        if target.get("status") == "done" and progress_pct is None:
            target["progress_pct"] = 100

        target["updated_at"] = iso_now_utc()
        normalized = self._normalize_task(target)

        for idx, row in enumerate(tasks):
            if row.get("id") == clean_id:
                tasks[idx] = normalized
                break

        self.save_workspace_data(workspace)
        return normalized

    def delete_task(self, task_id: str) -> dict[str, Any]:
        clean_id = task_id.strip()
        if not clean_id:
            raise ValueError("task_id is required")

        workspace = self.load_workspace_data()
        tasks = workspace["tasks"]
        remaining = [row for row in tasks if row.get("id") != clean_id]
        if len(remaining) == len(tasks):
            raise ValueError(f"task not found: {clean_id}")

        workspace["tasks"] = remaining
        self.save_workspace_data(workspace)
        return {"ok": True, "deleted_task_id": clean_id}

    def create_approval_request(
        self,
        *,
        task_id: str | None = None,
        action_type: str = "external_write",
        target: str | None = None,
        reason: str | None = None,
        requested_by: str = "pavel",
    ) -> dict[str, Any]:
        workspace = self.load_workspace_data()
        tasks = workspace["tasks"]
        approvals = workspace["approvals"]

        clean_task_id = (task_id or "").strip() or None
        task: dict[str, Any] | None = None
        if clean_task_id:
            for row in tasks:
                if row.get("id") == clean_task_id:
                    task = row
                    break
            if task is None:
                raise ValueError(f"task not found: {clean_task_id}")

        action = action_type.strip().lower() or "external_write"
        clean_target = (target or "").strip() or (str(task.get("title", "")).strip() if task else "")
        clean_reason = (reason or "").strip()
        requester = requested_by.strip().lower() or "pavel"

        for row in approvals:
            if (
                str(row.get("status")) == "pending"
                and str(row.get("task_id") or "") == (clean_task_id or "")
                and str(row.get("action_type")) == action
                and str(row.get("target")) == clean_target
            ):
                return self._normalize_approval(row)

        approval = self._normalize_approval(
            {
                "id": f"appr-{uuid.uuid4().hex[:10]}",
                "task_id": clean_task_id,
                "action_type": action,
                "target": clean_target,
                "reason": clean_reason,
                "requested_by": requester,
                "requested_at": iso_now_utc(),
                "status": "pending",
            }
        )
        approvals.append(approval)

        if task is not None and str(task.get("status")) not in {"done", "blocked"}:
            task["status"] = "blocked"
            task["updated_at"] = iso_now_utc()

        self.save_workspace_data(workspace)
        return approval

    def decide_approval(
        self,
        *,
        approval_id: str,
        decision: str,
        decided_by: str = "pavel",
        decision_note: str | None = None,
    ) -> dict[str, Any]:
        clean_id = approval_id.strip()
        if not clean_id:
            raise ValueError("approval_id is required")

        clean_decision = decision.strip().lower()
        if clean_decision not in {"approved", "rejected", "cancelled"}:
            raise ValueError("decision must be approved, rejected, or cancelled")

        workspace = self.load_workspace_data()
        approvals = workspace["approvals"]
        tasks = workspace["tasks"]

        target: dict[str, Any] | None = None
        for row in approvals:
            if row.get("id") == clean_id:
                target = row
                break
        if target is None:
            raise ValueError(f"approval not found: {clean_id}")

        target["status"] = clean_decision
        target["decided_by"] = decided_by.strip().lower() or "pavel"
        target["decided_at"] = iso_now_utc()
        target["decision_note"] = (decision_note or "").strip()
        target["updated_at"] = iso_now_utc()

        task_id = str(target.get("task_id", "")).strip()
        if task_id:
            for task in tasks:
                if task.get("id") != task_id:
                    continue
                if clean_decision == "approved" and str(task.get("status")) == "blocked":
                    task["status"] = "todo"
                elif clean_decision in {"rejected", "cancelled"}:
                    task["status"] = "blocked"
                task["updated_at"] = iso_now_utc()
                break

        self.save_workspace_data(workspace)
        return self._normalize_approval(target)

    def dispatch_task(
        self,
        *,
        task_id: str,
        assignee: str | None = None,
        requested_by: str = "pavel",
    ) -> dict[str, Any]:
        clean_task_id = task_id.strip()
        if not clean_task_id:
            raise ValueError("task_id is required")

        workspace = self.load_workspace_data()
        tasks = workspace["tasks"]
        runs = workspace["runs"]
        approvals = workspace["approvals"]

        task: dict[str, Any] | None = None
        for row in tasks:
            if row.get("id") == clean_task_id:
                task = row
                break
        if task is None:
            raise ValueError(f"task not found: {clean_task_id}")

        if str(task.get("status")) == "done":
            raise ValueError("task is already done")

        selected_assignee = (assignee or "").strip().lower()
        if not selected_assignee:
            existing = ensure_string_list(task.get("assignees", []))
            selected_assignee = existing[0] if existing else "unassigned"

        if self._task_requires_approval(task):
            approved = None
            pending = None
            for row in approvals:
                if str(row.get("task_id", "")).strip() != clean_task_id:
                    continue
                status = str(row.get("status", "")).strip()
                if status == "pending":
                    pending = row
                if status == "approved":
                    approved = row

            if pending is not None:
                return {
                    "queued": False,
                    "requires_approval": True,
                    "approval": self._normalize_approval(pending),
                }

            if approved is None:
                approval = self.create_approval_request(
                    task_id=clean_task_id,
                    action_type="external_write",
                    target=str(task.get("title", "")),
                    reason="Task appears to include an external write action and needs approval before dispatch.",
                    requested_by=requested_by,
                )
                return {
                    "queued": False,
                    "requires_approval": True,
                    "approval": approval,
                }

        run = self._normalize_run(
            {
                "id": f"run-{uuid.uuid4().hex[:10]}",
                "task_id": clean_task_id,
                "assignee": selected_assignee,
                "status": "queued",
                "queued_at": iso_now_utc(),
                "updated_at": iso_now_utc(),
                "logs": [
                    {
                        "ts": iso_now_utc(),
                        "message": f"queued by {requested_by.strip().lower() or 'pavel'}",
                    }
                ],
            }
        )
        runs.append(run)

        task_assignees = ensure_string_list(task.get("assignees", []))
        if selected_assignee not in task_assignees and selected_assignee != "unassigned":
            task_assignees.append(selected_assignee)
            task["assignees"] = task_assignees
        task["status"] = "in_progress"
        task["updated_at"] = iso_now_utc()

        self.save_workspace_data(workspace)
        return {
            "queued": True,
            "requires_approval": False,
            "run": run,
        }

    def assign_calendar_candidate_to_project(
        self,
        *,
        candidate_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        clean_candidate_id = candidate_id.strip()
        clean_project_id = project_id.strip()
        if not clean_candidate_id:
            raise ValueError("candidate_id is required")
        if not clean_project_id:
            raise ValueError("project_id is required")

        raw = read_json(self.calendar_candidates_path)
        if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
            raise ValueError("calendar candidates file not available")

        workspace = self.load_workspace_data()
        workspace = self._ensure_project_spaces_in_workspace(workspace)
        project = next((self._normalize_project(ensure_dict(row)) for row in workspace["projects"] if str(row.get("id")) == clean_project_id), None)
        if project is None:
            raise ValueError(f"project not found: {clean_project_id}")

        space = next((self._normalize_space(ensure_dict(row)) for row in workspace["spaces"] if str(row.get("project_id")) == clean_project_id), None)
        if space is None:
            raise ValueError(f"project space not found: {clean_project_id}")

        target_item: dict[str, Any] | None = None
        items = [ensure_dict(item) for item in raw.get("items", []) if isinstance(item, dict)]
        for item in items:
            if str(item.get("id")) == clean_candidate_id:
                target_item = item
                break
        if target_item is None:
            raise ValueError(f"calendar candidate not found: {clean_candidate_id}")

        now = iso_now_utc()
        target_item["project_id"] = project["id"]
        target_item["project_name"] = project["name"]
        target_item["space_id"] = space["id"]
        target_item["space_key"] = space["key"]
        target_item["assignment_source"] = "dashboard"
        target_item["assignment_updated_at"] = now
        target_item["updated_at"] = now

        raw["items"] = items
        write_json(self.calendar_candidates_path, raw)
        return {
            "item": target_item,
            "project": project,
            "space": space,
        }

    def apply_calendar_candidates_runtime(
        self,
        *,
        apply: bool = True,
        env_file: Path | None = None,
        fixtures_file: Path | None = None,
    ) -> dict[str, Any]:
        env_values: dict[str, str] = {}
        resolved_env = env_file or self._integration_env_file_path()
        if resolved_env is not None and resolved_env.exists():
            env_values = calendar_runtime.load_env_file(resolved_env)

        calendar_runtime.resolve_calendar_integration(self.integrations_path)
        default_timezone = calendar_runtime.resolve_default_timezone(env_values, self.root)
        calendar_id = calendar_runtime.resolve_calendar_id(env_file_values=env_values, override=None)
        client = calendar_runtime.build_client(
            env_file_values=env_values,
            fixtures_file=str(fixtures_file) if fixtures_file else None,
        )
        outcome = calendar_runtime.apply_calendar_candidates(
            client,
            calendar_id=calendar_id,
            candidates_path=self.calendar_candidates_path,
            default_timezone=default_timezone,
            apply=apply,
        )
        upcoming_events = calendar_runtime.list_upcoming(
            client,
            calendar_id=calendar_id,
            default_timezone=default_timezone,
            limit=20,
            window_days=14,
        )
        payload = calendar_runtime.build_status_payload(
            calendar_id=calendar_id,
            action="apply_candidates",
            dry_run=not apply,
            upcoming_events=upcoming_events,
            recent_results=outcome["results"],
            window_days=14,
            pending_candidate_count=int(outcome["pending_candidate_count"]),
            created_count=int(outcome["created_count"]),
            updated_count=int(outcome["updated_count"]),
            skipped_count=int(outcome["skipped_count"]),
            error_count=int(outcome["error_count"]),
        )
        write_json(self.calendar_runtime_status_path, payload)
        return {"status": payload, "outcome": outcome}

    def _personal_task_runtime_common(
        self,
        *,
        env_file: Path | None = None,
        fixtures_file: Path | None = None,
    ) -> tuple[dict[str, str], str, Any]:
        env_values: dict[str, str] = {}
        resolved_env = env_file or self._integration_env_file_path()
        if resolved_env is not None and resolved_env.exists():
            env_values = personal_task_runtime.load_env_file(resolved_env)
        personal_task_runtime.resolve_personal_task_integration(self.integrations_path)
        provider = personal_task_runtime.resolve_provider(
            env_file_values=env_values,
            override=None,
            fixtures_file=str(fixtures_file) if fixtures_file else None,
        )
        client = personal_task_runtime.build_client(
            provider=provider,
            env_file_values=env_values,
            fixtures_file=str(fixtures_file) if fixtures_file else None,
        )
        return env_values, provider, client

    def run_fitness_command(self, *, command_text: str) -> dict[str, Any]:
        clean = command_text.strip()
        if not clean:
            raise ValueError("fitness command text is required")
        runtime = self._fitness_runtime()
        result = ensure_dict(runtime.execute_text(clean))
        status = ensure_dict(result.get("status"))
        if status:
            write_json(self.fitness_runtime_status_path, status)
        return result

    def sync_personal_tasks_runtime(
        self,
        *,
        env_file: Path | None = None,
        fixtures_file: Path | None = None,
    ) -> dict[str, Any]:
        _, provider, client = self._personal_task_runtime_common(env_file=env_file, fixtures_file=fixtures_file)
        tasks = personal_task_runtime.list_personal_tasks(client, limit=50, filter_text=None)
        payload = personal_task_runtime.build_status_payload(
            provider=provider,
            action="snapshot",
            dry_run=False,
            tasks=tasks,
            recent_results=[],
        )
        write_json(self.personal_task_status_path, payload)
        return {"status": payload}

    def create_personal_task_runtime(
        self,
        *,
        title: str,
        description: str | None = None,
        priority: int | None = None,
        due_string: str | None = None,
        due_datetime: str | None = None,
        due_date: str | None = None,
        apply: bool = True,
        env_file: Path | None = None,
        fixtures_file: Path | None = None,
    ) -> dict[str, Any]:
        _, provider, client = self._personal_task_runtime_common(env_file=env_file, fixtures_file=fixtures_file)
        task_payload = personal_task_runtime.build_create_payload(
            title=title,
            description=description,
            priority=priority,
            due_string=due_string,
            due_datetime=due_datetime,
            due_date=due_date,
        )
        if apply:
            created = personal_task_runtime.normalize_task(client.create_task(task_payload))
            recent = {"action": "create_task", "status": "created", "task_id": created["id"], "title": created["title"]}
        else:
            recent = {"action": "create_task", "status": "preview", "payload": task_payload}
        tasks = personal_task_runtime.list_personal_tasks(client, limit=50, filter_text=None)
        payload = personal_task_runtime.build_status_payload(
            provider=provider,
            action="create_task",
            dry_run=not apply,
            tasks=tasks,
            recent_results=[recent],
        )
        write_json(self.personal_task_status_path, payload)
        return {"status": payload}

    def complete_personal_task_runtime(
        self,
        *,
        task_id: str,
        apply: bool = True,
        env_file: Path | None = None,
        fixtures_file: Path | None = None,
    ) -> dict[str, Any]:
        clean_task_id = task_id.strip()
        if not clean_task_id:
            raise ValueError("task_id is required")
        _, provider, client = self._personal_task_runtime_common(env_file=env_file, fixtures_file=fixtures_file)
        if apply:
            result = client.close_task(clean_task_id)
            recent = {"action": "complete_task", "status": "completed", "task_id": str(result.get("id") or clean_task_id)}
        else:
            recent = {"action": "complete_task", "status": "preview", "task_id": clean_task_id}
        tasks = personal_task_runtime.list_personal_tasks(client, limit=50, filter_text=None)
        payload = personal_task_runtime.build_status_payload(
            provider=provider,
            action="complete_task",
            dry_run=not apply,
            tasks=tasks,
            recent_results=[recent],
        )
        write_json(self.personal_task_status_path, payload)
        return {"status": payload}

    def defer_personal_task_runtime(
        self,
        *,
        task_id: str,
        due_string: str | None = None,
        due_datetime: str | None = None,
        due_date: str | None = None,
        apply: bool = True,
        env_file: Path | None = None,
        fixtures_file: Path | None = None,
    ) -> dict[str, Any]:
        clean_task_id = task_id.strip()
        if not clean_task_id:
            raise ValueError("task_id is required")
        _, provider, client = self._personal_task_runtime_common(env_file=env_file, fixtures_file=fixtures_file)
        defer_payload = personal_task_runtime.build_defer_payload(
            due_string=due_string,
            due_datetime=due_datetime,
            due_date=due_date,
        )
        if apply:
            updated = personal_task_runtime.normalize_task(client.update_task(clean_task_id, defer_payload))
            recent = {
                "action": "defer_task",
                "status": "updated",
                "task_id": updated["id"],
                "title": updated["title"],
                "due_value": updated["due_value"],
            }
        else:
            recent = {"action": "defer_task", "status": "preview", "task_id": clean_task_id, "payload": defer_payload}
        tasks = personal_task_runtime.list_personal_tasks(client, limit=50, filter_text=None)
        payload = personal_task_runtime.build_status_payload(
            provider=provider,
            action="defer_task",
            dry_run=not apply,
            tasks=tasks,
            recent_results=[recent],
        )
        write_json(self.personal_task_status_path, payload)
        return {"status": payload}

    def update_calendar_candidate(
        self,
        *,
        candidate_id: str,
        title: str | None = None,
        status: str | None = None,
        description: str | None = None,
        location: str | None = None,
        timezone_name: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        clean_candidate_id = candidate_id.strip()
        if not clean_candidate_id:
            raise ValueError("candidate_id is required")

        raw = read_json(self.calendar_candidates_path)
        if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
            raise ValueError("calendar candidates file not available")

        items = [ensure_dict(item) for item in raw.get("items", []) if isinstance(item, dict)]
        target_item: dict[str, Any] | None = None
        for item in items:
            if str(item.get("id")) == clean_candidate_id:
                target_item = item
                break
        if target_item is None:
            raise ValueError(f"calendar candidate not found: {clean_candidate_id}")

        if title is not None:
            clean_title = title.strip()
            if not clean_title:
                raise ValueError("title cannot be empty")
            target_item["title"] = clean_title

        if status is not None:
            clean_status = status.strip().lower()
            if clean_status not in CALENDAR_CANDIDATE_STATUSES:
                raise ValueError(
                    "invalid calendar candidate status: "
                    + status
                    + ". allowed: "
                    + ", ".join(sorted(CALENDAR_CANDIDATE_STATUSES))
                )
            target_item["status"] = clean_status

        if description is not None:
            clean_description = description.strip()
            if clean_description:
                target_item["description"] = clean_description
            else:
                target_item.pop("description", None)

        if location is not None:
            clean_location = location.strip()
            if clean_location:
                target_item["location"] = clean_location
            else:
                target_item.pop("location", None)

        if timezone_name is not None:
            clean_timezone = timezone_name.strip()
            if clean_timezone:
                target_item["timezone"] = clean_timezone
            else:
                target_item.pop("timezone", None)

        if start_at is not None:
            clean_start_at = start_at.strip()
            if clean_start_at:
                target_item["start_at"] = clean_start_at
            else:
                target_item.pop("start_at", None)

        if end_at is not None:
            clean_end_at = end_at.strip()
            if clean_end_at:
                target_item["end_at"] = clean_end_at
            else:
                target_item.pop("end_at", None)

        if start_date is not None:
            clean_start_date = start_date.strip()
            if clean_start_date:
                target_item["start_date"] = clean_start_date
            else:
                target_item.pop("start_date", None)

        if end_date is not None:
            clean_end_date = end_date.strip()
            if clean_end_date:
                target_item["end_date"] = clean_end_date
            else:
                target_item.pop("end_date", None)

        if attendees is not None:
            clean_attendees = [item.strip() for item in attendees if isinstance(item, str) and item.strip()]
            if clean_attendees:
                target_item["attendees"] = clean_attendees
            else:
                target_item.pop("attendees", None)

        current_status = str(target_item.get("status") or "proposed").strip().lower() or "proposed"
        if current_status in {"ready", "approved"}:
            core_data = self.load_yaml_dict(self.core_path)
            default_timezone = str(ensure_dict(core_data.get("owner")).get("timezone", "UTC")).strip() or "UTC"
            calendar_runtime.build_event_from_candidate(dict(target_item), default_timezone)

        target_item["updated_at"] = iso_now_utc()
        raw["items"] = items
        write_json(self.calendar_candidates_path, raw)
        return {"item": target_item}

    def update_run(
        self,
        *,
        run_id: str,
        status: str | None = None,
        log_message: str | None = None,
        output_summary: str | None = None,
        error: str | None = None,
        actor: str = "pavel",
    ) -> dict[str, Any]:
        clean_run_id = run_id.strip()
        if not clean_run_id:
            raise ValueError("run_id is required")

        workspace = self.load_workspace_data()
        runs = workspace["runs"]
        tasks = workspace["tasks"]

        run: dict[str, Any] | None = None
        for row in runs:
            if row.get("id") == clean_run_id:
                run = row
                break
        if run is None:
            raise ValueError(f"run not found: {clean_run_id}")

        now = iso_now_utc()
        if not isinstance(run.get("logs"), list):
            run["logs"] = []

        new_status = str(run.get("status", "queued")).strip().lower()
        if status is not None:
            candidate = status.strip().lower()
            if candidate not in RUN_STATUSES:
                raise ValueError(f"invalid run status: {status}")
            new_status = candidate

        previous_status = str(run.get("status", "queued")).strip().lower()
        run["status"] = new_status
        run["updated_at"] = now

        if previous_status == "queued" and new_status == "running":
            run["started_at"] = run.get("started_at") or now
        if new_status in {"succeeded", "failed", "cancelled"}:
            run["finished_at"] = now
            if not run.get("started_at"):
                run["started_at"] = now

        if output_summary is not None:
            run["output_summary"] = output_summary.strip()
        if error is not None:
            run["error"] = error.strip()
            if error.strip() and new_status not in {"failed", "cancelled"}:
                run["status"] = "failed"
                run["finished_at"] = now

        clean_log = (log_message or "").strip()
        if clean_log:
            run["logs"].append(
                {
                    "ts": now,
                    "message": f"{actor.strip().lower() or 'pavel'}: {clean_log}",
                }
            )

        task_id = str(run.get("task_id", "")).strip()
        if task_id:
            for task in tasks:
                if task.get("id") != task_id:
                    continue
                run_state = str(run.get("status"))
                if run_state == "succeeded":
                    task["status"] = "done"
                    task["progress_pct"] = 100
                elif run_state in {"failed", "cancelled"}:
                    task["status"] = "blocked"
                elif run_state == "running":
                    task["status"] = "in_progress"
                task["updated_at"] = now
                break

        self.save_workspace_data(workspace)
        return self._normalize_run(run)

    def _project_progress(
        self,
        project: dict[str, Any],
        tasks: list[dict[str, Any]],
    ) -> tuple[int, dict[str, int]]:
        project_id = str(project.get("id", "")).strip()
        project_tasks = [row for row in tasks if str(row.get("project_id", "")).strip() == project_id]

        counters = {"todo": 0, "in_progress": 0, "blocked": 0, "done": 0}
        for task in project_tasks:
            status = str(task.get("status", "todo"))
            if status in counters:
                counters[status] += 1
            else:
                counters["todo"] += 1

        total = len(project_tasks)
        if total > 0:
            progress_pct = int((counters["done"] * 100) / total)
        else:
            progress = project.get("progress_pct")
            progress_pct = int(progress) if isinstance(progress, int) else 0

        return progress_pct, counters

    def _workspace_summary(self) -> dict[str, Any]:
        workspace = self.load_workspace_data()
        projects = [self._normalize_project(ensure_dict(item)) for item in workspace.get("projects", [])]
        spaces = [self._normalize_space(ensure_dict(item)) for item in workspace.get("spaces", [])]
        tasks = [self._normalize_task(ensure_dict(item)) for item in workspace.get("tasks", [])]
        runs = [self._normalize_run(ensure_dict(item)) for item in workspace.get("runs", [])]
        approvals = [self._normalize_approval(ensure_dict(item)) for item in workspace.get("approvals", [])]

        project_lookup = {row["id"]: row for row in projects}
        space_lookup_by_project = {
            str(row.get("project_id")): row for row in spaces if str(row.get("project_id", "")).strip()
        }

        task_rows = []
        task_counts = {"todo": 0, "in_progress": 0, "blocked": 0, "done": 0}
        for task in tasks:
            status = str(task.get("status", "todo"))
            if status in task_counts:
                task_counts[status] += 1
            else:
                task_counts["todo"] += 1

            row = dict(task)
            row["project_name"] = project_lookup.get(str(task.get("project_id")), {}).get("name")
            task_rows.append(row)

        task_rows.sort(
            key=lambda row: (
                1 if row.get("status") == "done" else 0,
                0 if row.get("priority") == "urgent" else 1 if row.get("priority") == "high" else 2,
                row.get("due_at") or "9999",
                row.get("title") or "",
            )
        )

        project_rows = []
        for project in projects:
            progress_pct, counters = self._project_progress(project, tasks)
            space = ensure_dict(space_lookup_by_project.get(project["id"]))
            project_rows.append(
                {
                    **project,
                    "progress_pct": progress_pct,
                    "task_total": sum(counters.values()),
                    "task_todo": counters["todo"],
                    "task_in_progress": counters["in_progress"],
                    "task_blocked": counters["blocked"],
                    "task_done": counters["done"],
                    "space_id": space.get("id"),
                    "space_key": space.get("key"),
                    "space_session_strategy": space.get("session_strategy"),
                    "space_agent_strategy": space.get("agent_strategy"),
                    "space_target_channel": space.get("target_channel"),
                    "space_entry_command_hint": space.get("entry_command_hint"),
                }
            )

        project_rows.sort(
            key=lambda row: (
                0 if row.get("status") in {"active", "planned"} else 1,
                row.get("target_date") or "9999",
                row.get("name") or "",
            )
        )

        markdown_todos: list[dict[str, Any]] = []
        for source in self.todo_sources:
            markdown_todos.extend(parse_markdown_todos(source))

        todo_queue: list[dict[str, Any]] = []
        for task in task_rows:
            if task.get("status") == "done":
                continue
            todo_queue.append(
                {
                    "id": task.get("id"),
                    "title": task.get("title"),
                    "source": "dashboard_task",
                    "status": task.get("status"),
                    "assignees": task.get("assignees", []),
                    "project_name": task.get("project_name"),
                    "priority": task.get("priority"),
                    "due_at": task.get("due_at"),
                    "requires_approval": task.get("requires_approval", False),
                    "side_effects": task.get("side_effects", []),
                }
            )

        for item in markdown_todos:
            if item.get("done") is True:
                continue
            todo_queue.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "source": "markdown",
                    "status": "todo",
                    "assignees": [],
                    "project_name": None,
                    "priority": "low",
                    "due_at": None,
                    "path": item.get("path"),
                    "line": item.get("line"),
                }
            )

        total_tasks = sum(task_counts.values())
        completion_pct = int((task_counts["done"] * 100) / total_tasks) if total_tasks else 0

        progress = {
            "task_completion_pct": completion_pct,
            "task_total": total_tasks,
            "task_done": task_counts["done"],
            "active_projects": len([row for row in project_rows if row.get("status") in {"active", "planned", "blocked"}]),
            "project_spaces": len([row for row in spaces if row.get("kind") == "project"]),
        }
        project_counts = {
            "active": len([row for row in project_rows if row.get("status") == "active"]),
            "planned": len([row for row in project_rows if row.get("status") == "planned"]),
            "paused": len([row for row in project_rows if row.get("status") == "paused"]),
            "blocked": len([row for row in project_rows if row.get("status") == "blocked"]),
            "done": len([row for row in project_rows if row.get("status") == "done"]),
            "archived": len([row for row in project_rows if row.get("status") == "archived"]),
        }

        space_counts: dict[str, int] = defaultdict(int)
        for space in spaces:
            space_counts[str(space.get("kind", "project"))] += 1

        run_counts = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0, "cancelled": 0}
        run_rows: list[dict[str, Any]] = []
        for run in runs:
            status = str(run.get("status", "queued"))
            if status in run_counts:
                run_counts[status] += 1
            else:
                run_counts["queued"] += 1

            task = next((item for item in task_rows if item.get("id") == run.get("task_id")), None)
            run_rows.append(
                {
                    **run,
                    "task_title": str((task or {}).get("title", "")).strip() or None,
                }
            )
        run_rows.sort(key=lambda row: str(row.get("updated_at", "")), reverse=True)

        approval_counts = {"pending": 0, "approved": 0, "rejected": 0, "cancelled": 0}
        approval_rows: list[dict[str, Any]] = []
        for approval in approvals:
            status = str(approval.get("status", "pending"))
            if status in approval_counts:
                approval_counts[status] += 1
            else:
                approval_counts["pending"] += 1

            task = next((item for item in task_rows if item.get("id") == approval.get("task_id")), None)
            approval_rows.append(
                {
                    **approval,
                    "task_title": str((task or {}).get("title", "")).strip() or None,
                }
            )
        approval_rows.sort(
            key=lambda row: (
                0 if row.get("status") == "pending" else 1,
                str(row.get("updated_at", "")),
            ),
            reverse=False,
        )

        return {
            "projects": project_rows,
            "spaces": spaces,
            "space_counts": dict(space_counts),
            "project_counts": project_counts,
            "tasks": task_rows,
            "task_counts": task_counts,
            "progress": progress,
            "runs": run_rows[:80],
            "run_counts": run_counts,
            "approvals": approval_rows[:80],
            "approval_counts": approval_counts,
            "todo_queue": todo_queue[:60],
            "assignable_entities": self._assignable_entities(),
            "side_effect_catalog": self._side_effect_catalog(),
            "task_templates": self._task_templates(),
            "markdown_todos": markdown_todos,
        }

    def build_weekly_markdown_report(self, days: int = 7) -> str:
        lookback_days = max(1, min(30, int(days)))
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=lookback_days)

        workspace = self._workspace_summary()
        reminders = self._pending_reminders()
        local_usage = self._local_usage()

        projects = workspace.get("projects", [])
        tasks = workspace.get("tasks", [])
        progress = ensure_dict(workspace.get("progress"))
        task_counts = ensure_dict(workspace.get("task_counts"))

        recent_tasks = [
            row
            for row in tasks
            if (parse_iso_safe(str(row.get("updated_at", ""))) or datetime(1970, 1, 1, tzinfo=timezone.utc)) >= since
        ]

        open_tasks = [row for row in tasks if str(row.get("status")) != "done"]
        active_projects = [row for row in projects if str(row.get("status")) in {"active", "planned", "blocked"}]

        lines: list[str] = []
        lines.append("# Weekly Progress Report")
        lines.append("")
        lines.append(f"- Generated at: {now.isoformat()}")
        lines.append(f"- Lookback days: {lookback_days}")
        lines.append("")
        lines.append("## Summary")
        lines.append(f"- Task completion: {progress.get('task_completion_pct', 0)}%")
        lines.append(f"- Tasks total: {progress.get('task_total', 0)}")
        lines.append(f"- Tasks done: {progress.get('task_done', 0)}")
        lines.append(f"- Tasks open: {len(open_tasks)}")
        lines.append(f"- Active projects: {len(active_projects)}")
        lines.append(f"- Pending reminders: {len(reminders)}")
        lines.append("")
        lines.append("## Usage Snapshot")
        if local_usage.get("available"):
            overall = ensure_dict(local_usage.get("overall"))
            lines.append(f"- Calls: {overall.get('calls', 0)}")
            lines.append(f"- Tokens: {overall.get('total_tokens', 0)}")
            lines.append(f"- Errors: {overall.get('errors', 0)}")
            lines.append(f"- Fallbacks: {overall.get('fallbacks', 0)}")
            lines.append(f"- Estimated cost (USD): {overall.get('estimated_cost_usd', 0.0)}")
        else:
            lines.append("- Local telemetry not available")
        lines.append("")
        lines.append("## Active Projects")
        if active_projects:
            for project in active_projects:
                lines.append(
                    f"- {project.get('name')} | status={project.get('status')} | progress={project.get('progress_pct')}% | tasks={project.get('task_done')}/{project.get('task_total')}"
                )
        else:
            lines.append("- none")
        lines.append("")
        lines.append("## Open Tasks")
        if open_tasks:
            for task in open_tasks[:30]:
                assignees = ", ".join(ensure_string_list(task.get("assignees", []))) or "unassigned"
                lines.append(
                    f"- {task.get('title')} | status={task.get('status')} | priority={task.get('priority')} | assignees={assignees} | due={task.get('due_at') or '-'} | project={task.get('project_name') or '-'}"
                )
        else:
            lines.append("- none")
        lines.append("")
        lines.append("## Recent Task Activity")
        if recent_tasks:
            for task in sorted(recent_tasks, key=lambda row: str(row.get("updated_at", "")), reverse=True)[:30]:
                lines.append(
                    f"- {task.get('updated_at')} | {task.get('title')} | status={task.get('status')} | progress={task.get('progress_pct')}%"
                )
        else:
            lines.append("- none in lookback window")
        lines.append("")
        lines.append("## Pending Reminders")
        if reminders:
            for reminder in reminders[:30]:
                lines.append(
                    f"- {reminder.get('message')} | status={reminder.get('status')} | remind_at={reminder.get('remind_at')} | next_followup={reminder.get('next_followup_at') or '-'}"
                )
        else:
            lines.append("- none")
        lines.append("")
        lines.append("## Task Breakdown")
        lines.append(f"- todo: {task_counts.get('todo', 0)}")
        lines.append(f"- in_progress: {task_counts.get('in_progress', 0)}")
        lines.append(f"- blocked: {task_counts.get('blocked', 0)}")
        lines.append(f"- done: {task_counts.get('done', 0)}")
        lines.append("")

        return "\n".join(lines) + "\n"

    def build_tasks_csv_report(self) -> str:
        workspace = self._workspace_summary()
        tasks = workspace.get("tasks", [])

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "task_id",
                "title",
                "project_id",
                "project_name",
                "status",
                "priority",
                "assignees",
                "due_at",
                "progress_pct",
                "source",
                "updated_at",
            ]
        )

        for task in tasks:
            writer.writerow(
                [
                    task.get("id", ""),
                    task.get("title", ""),
                    task.get("project_id", ""),
                    task.get("project_name", ""),
                    task.get("status", ""),
                    task.get("priority", ""),
                    ", ".join(ensure_string_list(task.get("assignees", []))),
                    task.get("due_at", ""),
                    task.get("progress_pct", 0),
                    task.get("source", ""),
                    task.get("updated_at", ""),
                ]
            )

        return output.getvalue()

    def build_state(self) -> dict[str, Any]:
        integrations_data = self.load_yaml_dict(self.integrations_path)
        memory_data = self.load_yaml_dict(self.memory_path)
        core_data = self.load_yaml_dict(self.core_path)
        channels_data = self.load_yaml_dict(self.channels_path)
        reminders_data = self.load_yaml_dict(self.reminders_path)
        dashboard_cfg = self.read_dashboard_config()

        integration_profiles = ensure_dict(ensure_dict(integrations_data.get("profiles")).get("definitions"))
        memory_profiles = ensure_dict(ensure_dict(memory_data.get("profiles")).get("definitions"))

        integrations = ensure_dict(integrations_data.get("integrations"))
        memory_modules = ensure_dict(memory_data.get("memory_modules"))

        integrations_rows = []
        for name, row in sorted(integrations.items(), key=lambda kv: kv[0]):
            if not isinstance(row, dict):
                continue
            integrations_rows.append(
                {
                    "name": name,
                    "enabled": bool(row.get("enabled") is True),
                    "execution_mode": str(row.get("execution_mode", "unknown")),
                    "cost_class": str(row.get("cost_class", "unknown")),
                    "required_env_count": len(ensure_string_list(row.get("required_env"))),
                    "optional_env_count": len(ensure_string_list(row.get("optional_env"))),
                    "provider": str(row.get("provider", "multi")),
                }
            )

        memory_rows = []
        for name, row in sorted(memory_modules.items(), key=lambda kv: kv[0]):
            if not isinstance(row, dict):
                continue
            memory_rows.append(
                {
                    "name": name,
                    "enabled": bool(row.get("enabled") is True),
                    "required_env_count": len(ensure_string_list(row.get("required_env"))),
                }
            )

        n8n_row = ensure_dict(integrations.get("n8n"))
        n8n_modules = ensure_dict(n8n_row.get("modules"))
        n8n_rows = [
            {
                "name": name,
                "enabled": bool(value is True),
            }
            for name, value in sorted(n8n_modules.items(), key=lambda kv: kv[0])
        ]

        env = self._profile_env_requirements()
        reminder_counts = self._count_reminders()
        reminder_pending = self._pending_reminders()
        gmail_inbox = self._gmail_inbox_status()
        calendar_runtime = self._calendar_runtime_status()
        calendar_candidates = self._calendar_candidates()
        personal_tasks = self._personal_task_runtime_status()
        fitness_runtime_state = self._fitness_runtime_status()
        drive_workspace = self._drive_workspace_status()
        research_flow = self._research_flow_status()
        braindump = self._braindump_status()
        provider_health = self._provider_health_status()
        telegram_adapter = self._telegram_adapter_status()
        assistant_chat = self._assistant_chat_status()
        agent_chats = self._agent_chats_status()
        agent_runtime = self._agent_runtime_snapshot()
        continuous_improvement_status = self._continuous_improvement_status()
        memory_sync_status = self._memory_sync_status()
        workspace = self._workspace_summary()

        local_telemetry_enabled = bool(
            ensure_dict(ensure_dict(dashboard_cfg.get("dashboard")).get("adapters")).get(
                "local_telemetry_enabled",
                True,
            )
        )
        local_usage = self._local_usage() if local_telemetry_enabled else {"available": False, "disabled": True}
        routing_modes, active_routing_mode = self._routing_modes()

        codexbar = self._codexbar_usage(dashboard_cfg)

        presets = ensure_dict(ensure_dict(dashboard_cfg.get("dashboard")).get("presets"))
        preset_rows = []
        for name, row in sorted(presets.items(), key=lambda kv: kv[0]):
            cfg = ensure_dict(row)
            preset_rows.append(
                {
                    "name": name,
                    "description": str(cfg.get("description", "")).strip(),
                    "integrations_profile": str(cfg.get("integrations_profile", "")).strip() or None,
                    "memory_profile": str(cfg.get("memory_profile", "")).strip() or None,
                }
            )

        return {
            "project": {
                "name": str(ensure_dict(core_data.get("project")).get("name", "openclaw-v2")),
                "environment": str(ensure_dict(core_data.get("project")).get("environment", "unknown")),
            },
            "owner": {
                "timezone": str(ensure_dict(core_data.get("owner")).get("timezone", "unknown")),
            },
            "channels": {
                "primary": str(ensure_dict(channels_data.get("channels")).get("primary_human_channel", "n/a")),
                "enabled": ensure_string_list(ensure_dict(channels_data.get("channels")).get("enabled", [])),
            },
            "profiles": {
                "integrations": {
                    "active": str(ensure_dict(integrations_data.get("profiles")).get("active_profile", "")),
                    "definitions": sorted(integration_profiles.keys()),
                },
                "memory": {
                    "active": str(ensure_dict(memory_data.get("profiles")).get("active_profile", "")),
                    "definitions": sorted(memory_profiles.keys()),
                },
            },
            "routing": {
                "active_mode": active_routing_mode,
                "modes": routing_modes,
            },
            "presets": preset_rows,
            "modules": {
                "integrations": integrations_rows,
                "memory": memory_rows,
                "n8n": n8n_rows,
            },
            "limits": {
                "daily_usd_cap": ensure_dict(core_data.get("budgets")).get("daily_usd_cap"),
                "monthly_usd_cap": ensure_dict(core_data.get("budgets")).get("monthly_usd_cap"),
            },
            "reminders": {
                "auto_followup_mode": str(ensure_dict(reminders_data.get("reminders")).get("auto_followup_mode", "n/a")),
                "followup_interval_minutes": ensure_dict(reminders_data.get("reminders")).get(
                    "followup_interval_minutes"
                ),
                "max_auto_followups": ensure_dict(reminders_data.get("reminders")).get("max_auto_followups"),
                "counts": reminder_counts,
                "pending_items": reminder_pending,
            },
            "gmail_inbox": gmail_inbox,
            "calendar_runtime": calendar_runtime,
            "calendar_candidates": calendar_candidates,
            "personal_tasks": personal_tasks,
            "fitness_runtime": fitness_runtime_state,
            "drive_workspace": drive_workspace,
            "research_flow": research_flow,
            "braindump": braindump,
            "provider_health": provider_health,
            "telegram_adapter": telegram_adapter,
            "assistant_chat": assistant_chat,
            "agent_chats": agent_chats,
            "agent_runtime": agent_runtime,
            "continuous_improvement_status": continuous_improvement_status,
            "memory_sync_status": memory_sync_status,
            "workspace": workspace,
            "env": env,
            "telemetry": {
                "local": local_usage,
                "codexbar": codexbar,
                "report_markdown_present": self.model_usage_report_path.exists(),
                "ops_snapshot_present": self.ops_snapshot_path.exists(),
                "report_markdown_path": str(self.model_usage_report_path),
                "ops_snapshot_path": str(self.ops_snapshot_path),
            },
            "dashboard": dashboard_cfg,
        }
