#!/usr/bin/env python3
"""Role-aware bounded chat runtime for Telegram and dashboard-driven interactions."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import model_route_decider
from env_file_utils import load_env_file
import fitness_runtime
import openai_session_transport


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "dashboard") not in sys.path:
    sys.path.insert(0, str(ROOT / "dashboard"))

from backend import DashboardBackend, ensure_dict, ensure_string_list, read_json  # type: ignore  # noqa: E402

DEFAULT_TELEMETRY_PATH = ROOT / "telemetry" / "model-calls.ndjson"
DEFAULT_CHECKPOINT_PATH = ROOT / "telemetry" / "session-checkpoints.ndjson"
DEFAULT_AGENT_STATE_FILES = {
    "assistant": "assistant-chat-state.json",
    "researcher": "researcher-chat-state.json",
    "builder": "builder-chat-state.json",
    "fitness_coach": "fitness-coach-chat-state.json",
}

SUPPORTED_CHAT_TRANSPORTS = {
    "google_generative_language",
    "openrouter_chat_completions",
    "anthropic_messages",
    "codex_exec_session",
}

SPACE_CONTEXT_ITEM_LIMITS = {
    "general": 4,
    "calendar": 6,
    "tasks": 8,
    "reminders": 8,
    "braindump": 8,
    "research": 6,
    "job-search": 6,
    "fitness": 8,
    "coding": 6,
    "ops": 6,
    "project": 8,
}

ROLE_PROMPTS = {
    "assistant": {
        "headline": "You are Assistant Agent for Pavel.",
        "guidance": [
            "You are the default front door for reminders, tasks, calendar, braindump, inbox questions, and project coordination.",
            "Prefer concise, operational answers that clarify current state and the next concrete action.",
            "If the user asks to schedule, defer, or rearrange things, reason from the provided state and avoid inventing side effects.",
        ],
    },
    "researcher": {
        "headline": "You are Researcher Agent for Pavel.",
        "guidance": [
            "You handle tech research, tool evaluation, recommendation synthesis, and job-search analysis.",
            "Structure conclusions around tradeoffs, evidence, uncertainty, and the next decision Pavel should make.",
            "Prefer comparisons and short recommendation frames over long generic prose.",
        ],
    },
    "builder": {
        "headline": "You are Builder Agent for Pavel.",
        "guidance": [
            "You handle coding, implementation planning, debugging, refactors, and repo-scoped execution guidance.",
            "Think like a pragmatic software engineer: prioritize concrete file-level actions, risks, tests, and rollback safety.",
            "Do not claim code or infra changed unless the deterministic tool path already executed it.",
        ],
    },
    "fitness_coach": {
        "headline": "You are Fitness Coach for Pavel.",
        "guidance": [
            "You coach Pavel through his home-training program, workout execution, substitutions, progression, and recovery decisions.",
            "Treat the deterministic fitness runtime and workout logs as the source of truth for completed sessions and logged sets.",
            "When advising, tie recommendations to the actual plan, recent logs, equipment limits, and recovery context instead of generic fitness advice.",
        ],
    },
    "ops_guard": {
        "headline": "You are Ops Guard for Pavel.",
        "guidance": [
            "You focus on service health, failures, regressions, capacity issues, and runtime governance.",
            "Keep outputs compact and evidence-driven.",
        ],
    },
}

MEMORY_ENABLED_AGENTS = {"assistant", "researcher", "builder", "fitness_coach"}
MEMORY_HINT_KEYWORDS = {
    "remember",
    "previous",
    "before",
    "decided",
    "history",
    "context",
    "similar",
    "earlier",
    "already",
    "what did we",
    "last time",
}


def iso_now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def append_ndjson(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def env_get(name: str, env_values: dict[str, str]) -> str:
    return str(env_values.get(name, os.environ.get(name, ""))).strip()


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def truncate(text: str, *, limit: int = 220) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def choose_situation(*, agent_id: str, text: str, space_key: str) -> str:
    lowered = text.strip().lower()
    heavy_keywords = (
        "architecture",
        "tradeoff",
        "roadmap",
        "redesign",
        "system design",
        "rebuild plan",
        "major refactor",
        "long-term strategy",
    )
    synthesis_keywords = (
        "compare",
        "recommend",
        "explain",
        "why",
        "how should",
        "help me plan",
        "help me organize",
        "summarize",
        "think through",
        "evaluate",
        "pros and cons",
        "what should",
        "what do you think",
        "move things around",
        "reschedule",
        "prioritize",
    )
    fitness_reflection_keywords = (
        "progress",
        "plateau",
        "stalled",
        "swap",
        "replace",
        "substitute",
        "program",
        "cycle",
        "deload",
        "volume",
        "recover",
        "recovery",
        "sore",
        "superset",
        "myorep",
    )
    if any(keyword in lowered for keyword in heavy_keywords):
        return "architecture_or_high_ambiguity"
    if agent_id == "builder":
        return "coding_and_integration"
    if agent_id == "researcher":
        return "research_synthesis"
    if agent_id == "fitness_coach":
        if any(keyword in lowered for keyword in fitness_reflection_keywords) or len(lowered) >= 80:
            return "research_synthesis"
        return "quick_read_write"
    if space_key.startswith("projects/"):
        return "research_synthesis"
    if space_key in {"calendar", "tasks", "reminders", "braindump"} and len(lowered) <= 120:
        return "quick_read_write"
    if len(lowered) > 180 or any(keyword in lowered for keyword in synthesis_keywords):
        return "research_synthesis"
    return "quick_read_write"


def resolve_agent_chat_policy(
    *,
    agents_data: dict[str, Any],
    agent_id: str,
    situation: str,
) -> dict[str, Any]:
    agents_cfg = ensure_dict(agents_data.get("agents"))
    internal_cfg = ensure_dict(agents_data.get("internal_roles"))
    agent_row = ensure_dict(agents_cfg.get(agent_id))
    if not agent_row:
        agent_row = ensure_dict(internal_cfg.get(agent_id))
    return ensure_dict(ensure_dict(agent_row.get("chat_routing")).get(situation))


def local_provider_ready(
    *,
    provider_name: str,
    provider_cfg: dict[str, Any],
    env_values: dict[str, str],
) -> bool:
    transport = str(provider_cfg.get("transport", "")).strip()
    if transport not in SUPPORTED_CHAT_TRANSPORTS:
        return False
    required_env = ensure_string_list(provider_cfg.get("required_env"))
    if any(not env_get(var, env_values) for var in required_env):
        return False
    required_command = str(provider_cfg.get("required_command", "")).strip()
    if required_command and not shutil.which(required_command):
        return False
    return True


def resolve_chat_route(
    *,
    agent_id: str,
    situation: str,
    models_path: Path,
    agents_path: Path,
    env_values: dict[str, str],
) -> dict[str, Any]:
    models_data = ensure_dict(model_route_decider.load_yaml(models_path))
    routing = ensure_dict(models_data.get("routing"))
    lanes = ensure_dict(routing.get("lanes"))
    usage_modes = ensure_dict(routing.get("usage_modes"))
    decision_matrix = ensure_dict(routing.get("decision_matrix"))
    fallback_order = ensure_string_list(routing.get("fallback_order"))
    provider_inventory = ensure_dict(models_data.get("provider_inventory"))

    agents_data = ensure_dict(model_route_decider.load_yaml(agents_path))
    mode_name = str(ensure_dict(agents_data.get("routing_overrides")).get("active_mode", "")).strip() or "balanced_default"
    mode_cfg = ensure_dict(usage_modes.get(mode_name))
    situation_cfg = ensure_dict(decision_matrix.get(situation))
    agent_policy = resolve_agent_chat_policy(agents_data=agents_data, agent_id=agent_id, situation=situation)
    agent_provider_models = ensure_string_dict(agent_policy.get("provider_models"))
    preferred_lane = (
        str(agent_policy.get("preferred_lane", "")).strip()
        or str(situation_cfg.get("preferred_lane", "")).strip()
        or str(mode_cfg.get("default_lane", "")).strip()
    )
    if not preferred_lane:
        preferred_lane = fallback_order[0]

    requested_lane = preferred_lane
    requested_lane_cfg = ensure_dict(lanes.get(requested_lane))
    requested_approval = bool(requested_lane_cfg.get("approval_required") is True or situation_cfg.get("approval_required") is True)

    fallback_lanes = ensure_string_list(agent_policy.get("fallback_lanes"))
    if not fallback_lanes:
        fallback_lanes = ensure_string_list(situation_cfg.get("fallback_lanes"))
    if not fallback_lanes:
        fallback_lanes = [lane for lane in fallback_order if lane != requested_lane]

    lane_sequence = [requested_lane, *fallback_lanes]
    downgraded_from: str | None = None
    if requested_approval:
        lane_sequence = fallback_lanes or [requested_lane]
        downgraded_from = requested_lane

    route_attempts: list[dict[str, Any]] = []
    for lane_name in lane_sequence:
        lane_cfg = ensure_dict(lanes.get(lane_name))
        if not lane_cfg:
            continue
        provider_preference = ensure_string_list(agent_policy.get("provider_preference"))
        if not provider_preference:
            provider_preference = ensure_string_list(situation_cfg.get("provider_preference"))
        if lane_name != requested_lane or not provider_preference:
            provider_preference = ensure_string_list(lane_cfg.get("provider_priority"))
        candidates = model_route_decider.resolve_provider_candidates(
            provider_preference=provider_preference,
            lane_cfg=lane_cfg,
            provider_inventory=provider_inventory,
        )
        for candidate in candidates:
            provider_name = str(candidate.get("provider") or "").strip()
            provider_cfg = ensure_dict(provider_inventory.get(provider_name))
            model = str(candidate.get("model") or "").strip() or None
            if agent_provider_models.get(provider_name):
                model = agent_provider_models[provider_name]
            if local_provider_ready(provider_name=provider_name, provider_cfg=provider_cfg, env_values=env_values):
                return {
                    "situation": situation,
                    "mode": mode_name,
                    "lane": lane_name,
                    "requested_lane": requested_lane,
                    "downgraded_from_lane": downgraded_from,
                    "provider": provider_name,
                    "provider_cfg": provider_cfg,
                    "model": model or str(provider_cfg.get("default_model", "")).strip() or None,
                    "max_output_tokens": int(lane_cfg.get("max_output_tokens", 900) or 900),
                    "approval_required": requested_approval,
                    "route_attempts": route_attempts,
                }
            route_attempts.append(
                {
                    "lane": lane_name,
                    "provider": provider_name,
                    "model": model or str(provider_cfg.get("default_model", "")).strip() or None,
                    "transport": str(provider_cfg.get("transport", "")).strip() or None,
                    "missing_env": [var for var in ensure_string_list(provider_cfg.get("required_env")) if not env_get(var, env_values)],
                    "required_command": str(provider_cfg.get("required_command", "")).strip() or None,
                }
            )
    raise RuntimeError(f"no supported chat provider is ready for situation={situation}")


def request_json(
    url: str,
    *,
    method: str = "POST",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    req_headers = dict(headers or {})
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, method=method.upper(), data=body, headers=req_headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"http {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc.reason}") from exc
    data = json.loads(raw or "{}")
    return ensure_dict(data)


def call_google(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    messages: list[dict[str, str]],
    max_output_tokens: int,
) -> dict[str, Any]:
    contents = []
    for row in messages:
        role = "model" if row["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": row["content"]}]})
    started = time.perf_counter()
    data = request_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        payload={
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.35, "maxOutputTokens": int(max_output_tokens)},
        },
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("google response missing candidates")
    content = ensure_dict(ensure_dict(candidates[0]).get("content"))
    parts = content.get("parts")
    if not isinstance(parts, list):
        raise RuntimeError("google response missing content parts")
    reply = "\n".join(str(ensure_dict(part).get("text") or "").strip() for part in parts).strip()
    if not reply:
        raise RuntimeError("google response missing text")
    usage = ensure_dict(data.get("usageMetadata"))
    return {
        "text": reply,
        "latency_ms": latency_ms,
        "prompt_tokens": int(usage.get("promptTokenCount", 0) or 0),
        "completion_tokens": int(usage.get("candidatesTokenCount", 0) or 0),
    }


def call_openrouter(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    messages: list[dict[str, str]],
    max_output_tokens: int,
) -> dict[str, Any]:
    chat_messages = [{"role": "system", "content": system_prompt}, *messages]
    started = time.perf_counter()
    data = request_json(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        payload={
            "model": model,
            "messages": chat_messages,
            "temperature": 0.35,
            "max_tokens": int(max_output_tokens),
        },
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("openrouter response missing choices")
    message = ensure_dict(ensure_dict(choices[0]).get("message"))
    reply = str(message.get("content") or "").strip()
    if not reply:
        raise RuntimeError("openrouter response missing content")
    usage = ensure_dict(data.get("usage"))
    return {
        "text": reply,
        "latency_ms": latency_ms,
        "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
    }


def call_anthropic(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    messages: list[dict[str, str]],
    max_output_tokens: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    data = request_json(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": f"{api_key}",
            "anthropic-version": "2023-06-01",
        },
        payload={
            "model": model,
            "system": system_prompt,
            "messages": messages,
            "temperature": 0.35,
            "max_tokens": int(max_output_tokens),
        },
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    content = data.get("content")
    if not isinstance(content, list) or not content:
        raise RuntimeError("anthropic response missing content")
    reply = "\n".join(str(ensure_dict(part).get("text") or "").strip() for part in content).strip()
    if not reply:
        raise RuntimeError("anthropic response missing text")
    usage = ensure_dict(data.get("usage"))
    return {
        "text": reply,
        "latency_ms": latency_ms,
        "prompt_tokens": int(usage.get("input_tokens", 0) or 0),
        "completion_tokens": int(usage.get("output_tokens", 0) or 0),
    }


def invoke_chat_provider(
    *,
    provider_name: str,
    provider_cfg: dict[str, Any],
    model: str,
    env_values: dict[str, str],
    system_prompt: str,
    messages: list[dict[str, str]],
    max_output_tokens: int,
    workdir: Path | None = None,
) -> dict[str, Any]:
    transport = str(provider_cfg.get("transport", "")).strip()
    if transport == "google_generative_language":
        return call_google(
            api_key=env_get("GEMINI_API_KEY", env_values),
            model=model,
            system_prompt=system_prompt,
            messages=messages,
            max_output_tokens=max_output_tokens,
        )
    if transport == "openrouter_chat_completions":
        return call_openrouter(
            api_key=env_get("OPENROUTER_API_KEY", env_values),
            model=model,
            system_prompt=system_prompt,
            messages=messages,
            max_output_tokens=max_output_tokens,
        )
    if transport == "anthropic_messages":
        return call_anthropic(
            api_key=env_get("ANTHROPIC_API_KEY", env_values),
            model=model,
            system_prompt=system_prompt,
            messages=messages,
            max_output_tokens=max_output_tokens,
        )
    if transport == "codex_exec_session":
        timeout_seconds = 240 if max_output_tokens <= 2500 else 360
        return openai_session_transport.invoke_codex_session(
            root=(workdir or ROOT),
            model=model,
            system_prompt=system_prompt,
            messages=messages,
            timeout_seconds=timeout_seconds,
        )
    raise RuntimeError(f"unsupported chat transport: {transport or provider_name}")


def deterministic_checkpoint(summary: str, turns: list[dict[str, str]]) -> str:
    items = []
    for row in turns[:6]:
        role = row.get("role", "user")
        content = truncate(str(row.get("content") or ""), limit=120)
        if content:
            items.append(f"- {role}: {content}")
    parts = [part.strip() for part in [summary.strip(), *items] if part and part.strip()]
    if not parts:
        return ""
    joined = "\n".join(parts)
    return joined[-1400:]


def normalize_turns(turns: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not isinstance(turns, list):
        return []
    out: list[dict[str, str]] = []
    for row in turns:
        role = str(row.get("role") or "").strip().lower()
        content = str(row.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        out.append({"role": role, "content": content})
    return out[-12:]


def load_memory_profile(memory_path: Path) -> tuple[dict[str, Any], str, dict[str, Any], list[str]]:
    memory_cfg = ensure_dict(model_route_decider.load_yaml(memory_path))
    profiles = ensure_dict(memory_cfg.get("profiles"))
    definitions = ensure_dict(profiles.get("definitions"))
    active_profile = str(profiles.get("active_profile") or "").strip() or "md_only"
    profile = ensure_dict(definitions.get(active_profile))
    modules = ensure_dict(memory_cfg.get("memory_modules"))
    enabled_module_names = ensure_string_list(profile.get("enabled_modules"))
    return memory_cfg, active_profile, modules, enabled_module_names


def should_query_memory(*, agent_id: str, text: str, space_key: str, route: dict[str, Any]) -> bool:
    if agent_id not in MEMORY_ENABLED_AGENTS:
        return False
    lowered = text.strip().lower()
    if not lowered:
        return False
    if space_key.startswith("projects/") or str(route.get("project_name") or "").strip():
        return True
    if agent_id in {"researcher", "builder"}:
        return len(lowered) >= 20
    if agent_id == "fitness_coach":
        return len(lowered) >= 40 or any(
            keyword in lowered
            for keyword in (
                "last",
                "previous",
                "progress",
                "plateau",
                "stalled",
                "cycle",
                "program",
                "swap",
                "replace",
                "volume",
            )
        )
    if any(keyword in lowered for keyword in MEMORY_HINT_KEYWORDS):
        return True
    return len(lowered) >= 100


def format_memory_context(results: list[dict[str, Any]], *, mode: str) -> str:
    if not results:
        return ""
    lines = [f"Relevant memory recall ({mode}):"]
    for item in results[:4]:
        row = ensure_dict(item)
        source_path = Path(str(row.get("source_path") or "memory")).name or "memory"
        heading = str(row.get("heading") or "").strip()
        label = f"{source_path}"
        if heading:
            label += f" :: {heading}"
        lines.append(f"- {label}: {truncate(str(row.get('content') or ''), limit=190)}")
    return "\n".join(lines)


def build_space_snapshot(
    snapshot: dict[str, Any],
    *,
    root: Path,
    agent_id: str,
    space_key: str,
    route: dict[str, Any],
) -> str:
    reminders = ensure_dict(snapshot.get("reminders"))
    calendar = ensure_dict(snapshot.get("calendar_runtime"))
    personal_tasks = ensure_dict(snapshot.get("personal_tasks"))
    braindump = ensure_dict(snapshot.get("braindump"))
    fitness_state = ensure_dict(snapshot.get("fitness_runtime"))
    workspace = ensure_dict(snapshot.get("workspace"))
    provider_health = ensure_dict(snapshot.get("provider_health"))
    pending_reminders = reminders.get("pending_items", [])
    reminder_lines = [
        f"- {truncate(str(item.get('message') or ''), limit=80)} @ {str(item.get('remind_at') or '-')}"
        for item in pending_reminders[: SPACE_CONTEXT_ITEM_LIMITS.get("reminders", 4)]
        if isinstance(item, dict)
    ]
    event_lines = [
        f"- {str(row.get('start_value') or '-')} | {truncate(str(row.get('summary') or '(untitled)'), limit=80)}"
        for row in calendar.get("upcoming_events", [])[: SPACE_CONTEXT_ITEM_LIMITS.get("calendar", 4)]
        if isinstance(row, dict)
    ]
    task_lines = [
        f"- {truncate(str(row.get('title') or ''), limit=90)} | due={str(row.get('due_at') or row.get('due_value') or '-')}"
        for row in workspace.get("todo_queue", [])[: SPACE_CONTEXT_ITEM_LIMITS.get("tasks", 6)]
        if isinstance(row, dict)
    ]
    due_braindump = [
        f"- [{str(row.get('category') or '-')}] {truncate(str(row.get('short_text') or ''), limit=90)}"
        for row in braindump.get("due_items", [])[: SPACE_CONTEXT_ITEM_LIMITS.get("braindump", 6)]
        if isinstance(row, dict)
    ]
    fitness_today = ensure_dict(fitness_state.get("today_plan"))
    fitness_active = ensure_dict(fitness_state.get("active_session"))
    fitness_progress_flags = [
        ensure_dict(item)
        for item in fitness_state.get("progression_flags", [])[: SPACE_CONTEXT_ITEM_LIMITS.get("fitness", 6)]
        if isinstance(item, dict)
    ]
    weekly_volume = ensure_dict(fitness_state.get("weekly_volume"))

    sections = [
        f"Space: {space_key}",
        "System state:",
        f"- reminders_pending={ensure_dict(reminders.get('counts')).get('pending', 0)}",
        f"- reminders_awaiting_reply={ensure_dict(reminders.get('counts')).get('awaiting_reply', 0)}",
        f"- calendar_upcoming={ensure_dict(calendar.get('summary')).get('upcoming_count', 0)}",
        f"- personal_tasks_open={ensure_dict(personal_tasks.get('summary')).get('open_count', 0)}",
        f"- braindump_due={braindump.get('due_count', 0)}",
        f"- active_projects={ensure_dict(workspace.get('project_counts')).get('active', 0)}",
    ]

    if space_key in {"general", "reminders"} and reminder_lines:
        sections.extend(["Open reminders:", *reminder_lines])
    if space_key in {"general", "calendar"} and event_lines:
        sections.extend(["Upcoming calendar:", *event_lines])
    if space_key in {"general", "tasks"} and task_lines:
        sections.extend(["Open tasks:", *task_lines])
    if space_key in {"general", "braindump"} and due_braindump:
        sections.extend(["Braindump due for review:", *due_braindump])

    if agent_id == "researcher" or space_key in {"research", "job-search"}:
        summary_path = root / "data" / "job-search-daily-summary.json"
        raw_summary = read_json(summary_path)
        summary = ensure_dict(raw_summary.get("summary")) if isinstance(raw_summary, dict) else {}
        if isinstance(raw_summary, dict) and raw_summary:
            sections.extend(
                [
                    "Research/job-search state:",
                    f"- generated_at={str(raw_summary.get('generated_at') or '-')}",
                    f"- reviewed_items={summary.get('reviewed_items', 0)}",
                    f"- shortlisted={summary.get('shortlisted_items', 0)}",
                ]
            )

    if agent_id == "builder" or space_key == "coding":
        builder_tasks = [
            ensure_dict(row)
            for row in workspace.get("tasks", [])
            if isinstance(row, dict) and "builder" in [str(item) for item in row.get("assignees", [])]
        ]
        if builder_tasks:
            sections.extend(
                [
                    "Builder queue:",
                    *[
                        f"- {truncate(str(row.get('title') or ''), limit=90)} | status={row.get('status') or '-'}"
                        for row in builder_tasks[: SPACE_CONTEXT_ITEM_LIMITS.get('coding', 6)]
                    ],
                ]
            )

    if agent_id == "fitness_coach" or space_key == "fitness":
        sections.append("Fitness state:")
        if fitness_today:
            plan = ensure_dict(fitness_today.get("plan"))
            sections.append(
                f"- next_plan={plan.get('code') or '-'} | {plan.get('title') or '-'} | mode={fitness_today.get('mode') or '-'}"
            )
        if fitness_active:
            sections.append(
                f"- active_session={fitness_active.get('training_day_code') or '-'} | started={fitness_active.get('created_at') or '-'}"
            )
        if weekly_volume:
            top_volume = sorted(weekly_volume.items(), key=lambda item: (-float(item[1] or 0), str(item[0])))[:4]
            sections.extend(["Weekly volume:", *[f"- {name}={value}" for name, value in top_volume]])
        if fitness_progress_flags:
            sections.extend(
                [
                    "Progression flags:",
                    *[
                        f"- {truncate(str(row.get('message') or row.get('flag') or row.get('exercise_name') or ''), limit=100)}"
                        for row in fitness_progress_flags
                    ],
                ]
            )

    if space_key.startswith("projects/"):
        projects = [ensure_dict(row) for row in workspace.get("projects", []) if isinstance(row, dict)]
        project = next((row for row in projects if str(row.get("space_key") or "") == space_key), None)
        if project:
            sections.extend(
                [
                    "Active project:",
                    f"- name={project.get('name') or '-'}",
                    f"- status={project.get('status') or '-'}",
                    f"- progress={project.get('progress_pct') or 0}%",
                ]
            )
            related_tasks = [
                ensure_dict(row)
                for row in workspace.get("tasks", [])
                if isinstance(row, dict) and str(row.get("project_id") or "") == str(project.get("id") or "")
            ]
            if related_tasks:
                sections.extend(
                    [
                        "Project tasks:",
                        *[
                            f"- {truncate(str(row.get('title') or ''), limit=90)} | status={row.get('status') or '-'} | assignees={','.join(str(item) for item in row.get('assignees', [])) or '-'}"
                            for row in related_tasks[: SPACE_CONTEXT_ITEM_LIMITS.get('project', 8)]
                        ],
                    ]
                )

    if agent_id == "ops_guard" or space_key == "ops":
        provider_summary = ensure_dict(provider_health.get("summary"))
        sections.extend(
            [
                "Ops signals:",
                f"- providers_local_ready={provider_summary.get('local_ready_count', 0)}",
                f"- providers_live_ok={provider_summary.get('live_ok_count', 0)}",
                f"- reminder_errors={ensure_dict(reminders.get('counts')).get('error', 0)}",
                f"- blocked_tasks={ensure_dict(workspace.get('task_counts')).get('blocked', 0)}",
            ]
        )

    return "\n".join(sections)


def extract_markdown_section_bullets(path: Path, heading: str, *, limit: int = 6) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$" + r"(?P<body>.*?)(?=^##\s+|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        return []
    body = str(match.group("body") or "")
    rows: list[str] = []
    for raw in body.splitlines():
        line = raw.strip().replace("`", "")
        if not line:
            continue
        line = re.sub(r"^\d+\.\s+", "", line)
        line = re.sub(r"^-\s+", "", line)
        line = " ".join(line.split())
        if not line:
            continue
        rows.append(line)
    return rows[:limit]


def extract_session_queue_pointer(path: Path) -> str | None:
    rows = extract_markdown_section_bullets(path, "Current Pointer", limit=2)
    if not rows:
        return None
    return rows[0]


def build_fitness_program_brief(root: Path) -> str:
    profile_path = root / "fitness" / "ATHLETE_PROFILE.md"
    queue_path = root / "fitness" / "SESSION_QUEUE.md"
    config = fitness_runtime.load_fitness_config(root)
    program = ensure_dict(config.get("_program"))
    days = ensure_dict(program.get("days"))

    lines = ["Canonical fitness program context:"]
    goals = extract_markdown_section_bullets(profile_path, "Goals", limit=3)
    if goals:
        lines.extend(["Goals:", *[f"- {item}" for item in goals]])
    schedule = extract_markdown_section_bullets(profile_path, "Schedule Preferences", limit=4)
    if schedule:
        lines.extend(["Schedule preferences:", *[f"- {item}" for item in schedule]])
    emphasis = extract_markdown_section_bullets(profile_path, "Muscle Emphasis Preferences", limit=4)
    if emphasis:
        lines.extend(["Emphasis:", *[f"- {item}" for item in emphasis]])
    equipment = extract_markdown_section_bullets(profile_path, "Equipment and Constraints", limit=4)
    if equipment:
        lines.extend(["Equipment and constraints:", *[f"- {item}" for item in equipment]])
    logging = extract_markdown_section_bullets(profile_path, "Logging Preferences", limit=4)
    if logging:
        lines.extend(["Logging preferences:", *[f"- {item}" for item in logging]])

    current_pointer = extract_session_queue_pointer(queue_path)
    if current_pointer:
        lines.append(f"Session queue pointer: {current_pointer}")

    lines.append("Canonical session templates:")
    for code in ("M1", "M2", "M3", "M4", "O5"):
        plan = days.get(code)
        if not hasattr(plan, "title") or not hasattr(plan, "exercises"):
            continue
        equipment_text = ", ".join(getattr(plan, "equipment", []) or []) or "-"
        lines.append(f"- {getattr(plan, 'code', code)}: {getattr(plan, 'title', code)} | equipment={equipment_text}")
        for item in getattr(plan, "exercises", [])[:5]:
            slot_label = getattr(item, "slot_label", "?")
            display_name = getattr(item, "display_name", getattr(item, "exercise_code", "exercise"))
            prescription = getattr(item, "prescription_text", "-")
            lines.append(f"  - {slot_label} {display_name}: {prescription}")
    return "\n".join(lines)


def build_system_prompt(
    *,
    agent_id: str,
    space_key: str,
    route: dict[str, Any],
    backend: DashboardBackend,
    session_summary: str,
    memory_context: str,
) -> str:
    route_mode = str(route.get("route_mode") or "default_front_door")
    now_local = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    dashboard_snapshot = backend.build_state()
    agent_runtime = ensure_dict(dashboard_snapshot.get("agent_runtime"))
    roles = agent_runtime.get("visible_agents", []) + agent_runtime.get("internal_roles", [])
    role = next((ensure_dict(row) for row in roles if str(ensure_dict(row).get("id")) == agent_id), {})
    prompt_cfg = ROLE_PROMPTS.get(agent_id, ROLE_PROMPTS["assistant"])
    instructions = [
        prompt_cfg["headline"],
        *prompt_cfg["guidance"],
        "Use the provided system state as ground truth where possible.",
        "Do not claim an action was executed unless the deterministic tool path already executed it.",
        "If the user is asking for an action you cannot execute from chat, say what is missing and propose the next concrete step.",
        "Prefer short answers with bullet points when that improves clarity.",
        f"Current route mode: {route_mode}.",
        f"Current local time: {now_local}.",
    ]
    responsibilities = ensure_string_list(role.get("responsibilities"))
    if responsibilities:
        instructions.extend(["Primary responsibilities:", *[f"- {item}" for item in responsibilities[:6]]])
    tools = ensure_string_list(role.get("allowed_tools"))
    if tools:
        instructions.extend(["Available tool surface (read/plan against these, do not pretend writes happened):", *[f"- {item}" for item in tools[:8]]])
    instructions.append(build_space_snapshot(dashboard_snapshot, root=backend.root, agent_id=agent_id, space_key=space_key, route=route))
    if agent_id == "fitness_coach" or space_key == "fitness":
        instructions.append(build_fitness_program_brief(backend.root))
    if memory_context.strip():
        instructions.extend([memory_context.strip()])
    if session_summary.strip():
        instructions.extend(["Session summary:", session_summary.strip()])
    return "\n\n".join(part for part in instructions if part and part.strip())


class AgentChatRuntime:
    def __init__(
        self,
        *,
        root: Path,
        backend: DashboardBackend,
        env_values: dict[str, str],
        agent_id: str = "assistant",
        state_path: Path | None = None,
        telemetry_path: Path | None = None,
        checkpoint_path: Path | None = None,
    ) -> None:
        clean_agent = agent_id.strip().lower() or "assistant"
        self.root = root
        self.backend = backend
        self.env_values = env_values
        self.agent_id = clean_agent
        self.models_path = self.root / "config" / "models.yaml"
        self.agents_path = self.root / "config" / "agents.yaml"
        self.memory_path = self.root / "config" / "memory.yaml"
        self.session_policy_path = self.root / "config" / "session_policy.yaml"
        default_state_name = DEFAULT_AGENT_STATE_FILES.get(clean_agent, f"{clean_agent}-chat-state.json")
        self.state_path = state_path or (self.root / "data" / default_state_name)
        self.telemetry_path = telemetry_path or DEFAULT_TELEMETRY_PATH
        self.checkpoint_path = checkpoint_path or DEFAULT_CHECKPOINT_PATH
        self.session_lifecycle = ensure_dict(ensure_dict(model_route_decider.load_yaml(self.session_policy_path)).get("session_lifecycle"))
        self.context_token_limit = int(self.session_lifecycle.get("summarize_when_context_tokens_over", 8500) or 8500)
        self.checkpoint_every_turns = int(self.session_lifecycle.get("checkpoint_every_turns", 20) or 20)
        self.idle_reset_minutes = int(self.session_lifecycle.get("idle_reset_minutes", 120) or 120)

    def _load_state(self) -> dict[str, Any]:
        raw = read_json(self.state_path)
        if not isinstance(raw, dict):
            raw = {}
        spaces = ensure_dict(raw.get("spaces"))
        normalized_spaces: dict[str, dict[str, Any]] = {}
        for key, row in spaces.items():
            clean_key = str(key).strip() or "general"
            item = ensure_dict(row)
            normalized_spaces[clean_key] = {
                "summary": str(item.get("summary") or "").strip(),
                "turns": normalize_turns(item.get("turns", [])),
                "updated_at": str(item.get("updated_at") or "").strip() or None,
                "last_lane": str(item.get("last_lane") or "").strip() or None,
                "last_provider": str(item.get("last_provider") or "").strip() or None,
                "last_model": str(item.get("last_model") or "").strip() or None,
                "exchange_count": int(item.get("exchange_count", 0) or 0),
                "last_checkpoint_at": str(item.get("last_checkpoint_at") or "").strip() or None,
            }
        return {"agent_id": self.agent_id, "spaces": normalized_spaces}

    def _save_state(self, state: dict[str, Any]) -> None:
        payload = {
            "agent_id": self.agent_id,
            "updated_at": iso_now_utc(),
            "spaces": ensure_dict(state.get("spaces")),
        }
        write_json(self.state_path, payload)

    def _space_state(self, state: dict[str, Any], space_key: str) -> dict[str, Any]:
        spaces = ensure_dict(state.setdefault("spaces", {}))
        return ensure_dict(
            spaces.setdefault(
                space_key,
                {
                    "summary": "",
                    "turns": [],
                    "updated_at": None,
                    "last_lane": None,
                    "last_provider": None,
                    "last_model": None,
                    "exchange_count": 0,
                    "last_checkpoint_at": None,
                },
            )
        )

    def _log_checkpoint(self, *, space_key: str, summary: str, turns: list[dict[str, str]], trigger: str) -> None:
        append_ndjson(
            self.checkpoint_path,
            {
                "ts": iso_now_utc(),
                "agent_id": self.agent_id,
                "space_key": space_key,
                "trigger": trigger,
                "summary": truncate(summary, limit=1200),
                "turn_count": len(turns),
            },
        )

    def _maybe_idle_reset(self, *, space_key: str, space_state: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
        summary = str(space_state.get("summary") or "").strip()
        turns = normalize_turns(space_state.get("turns", []))
        updated_at = _parse_iso(str(space_state.get("updated_at") or ""))
        if not turns or updated_at is None:
            return summary, turns
        threshold = datetime.now(timezone.utc) - timedelta(minutes=max(self.idle_reset_minutes, 1))
        if updated_at.astimezone(timezone.utc) >= threshold:
            return summary, turns
        refreshed = deterministic_checkpoint(summary, turns)
        if refreshed:
            self._log_checkpoint(space_key=space_key, summary=refreshed, turns=turns, trigger="idle_reset")
        return refreshed, []

    def _prepare_history(self, *, space_key: str, space_state: dict[str, Any], user_text: str) -> tuple[str, list[dict[str, str]]]:
        summary, turns = self._maybe_idle_reset(space_key=space_key, space_state=space_state)
        turns.append({"role": "user", "content": user_text.strip()})
        total_tokens = estimate_tokens(summary + "\n" + "\n".join(row["content"] for row in turns))
        if total_tokens > self.context_token_limit or len(turns) > 8:
            refreshed = deterministic_checkpoint(summary, turns[:-6] if len(turns) > 6 else turns[:-2])
            if refreshed and refreshed != summary:
                self._log_checkpoint(space_key=space_key, summary=refreshed, turns=turns, trigger="context_compaction")
                summary = refreshed
            turns = turns[-6:]
        return summary, turns[-8:]

    def _persist_turns(
        self,
        *,
        state: dict[str, Any],
        space_key: str,
        summary: str,
        turns: list[dict[str, str]],
        lane: str,
        provider: str,
        model: str,
        exchange_count: int,
    ) -> None:
        chat_space = self._space_state(state, space_key)
        chat_space["summary"] = summary[-1400:] if summary else ""
        chat_space["turns"] = turns[-10:]
        chat_space["updated_at"] = iso_now_utc()
        chat_space["last_lane"] = lane
        chat_space["last_provider"] = provider
        chat_space["last_model"] = model
        chat_space["exchange_count"] = exchange_count
        if exchange_count and exchange_count % max(self.checkpoint_every_turns, 1) == 0:
            chat_space["last_checkpoint_at"] = iso_now_utc()
            self._log_checkpoint(space_key=space_key, summary=summary, turns=turns, trigger="turn_cadence")
        self._save_state(state)

    def _log_call(
        self,
        *,
        lane: str,
        provider: str,
        model: str,
        space_key: str,
        situation: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        status: str,
    ) -> None:
        append_ndjson(
            self.telemetry_path,
            {
                "ts": iso_now_utc(),
                "task_id": f"{self.agent_id}-chat-{space_key}",
                "agent_id": self.agent_id,
                "lane": lane,
                "provider": provider,
                "model": model,
                "status": status,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "latency_ms": latency_ms,
                "estimated_cost_usd": 0.0,
                "situation": situation,
                "space_key": space_key,
            },
        )

    def _memory_context(self, *, text: str, route: dict[str, Any], space_key: str) -> str:
        _, active_profile, modules, enabled_module_names = load_memory_profile(self.memory_path)
        if "semantic_embeddings" not in enabled_module_names and "sqlite_state" not in enabled_module_names:
            return ""
        if not should_query_memory(agent_id=self.agent_id, text=text, space_key=space_key, route=route):
            return ""
        query_parts = []
        project_name = str(route.get("project_name") or "").strip()
        if project_name:
            query_parts.append(project_name)
        if space_key and space_key != "general":
            query_parts.append(space_key.replace("projects/", "project ").replace("-", " "))
        query_parts.append(text.strip())
        query = " | ".join(part for part in query_parts if part)
        env = os.environ.copy()
        env.update({key: value for key, value in self.env_values.items() if isinstance(value, str)})
        cmd = [
            "python3",
            str(self.root / "scripts" / "memory_search.py"),
            "--workspace",
            str(self.root),
            "--config",
            str(self.memory_path),
            "--query",
            query,
            "--top-k",
            "4",
            "--mode",
            "auto",
            "--json",
        ]
        proc = subprocess.run(cmd, cwd=str(self.root), capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            return ""
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return ""
        results = [ensure_dict(item) for item in payload.get("results", []) if isinstance(item, dict)]
        if not results:
            return ""
        mode = str(payload.get("mode") or active_profile).strip() or active_profile
        return format_memory_context(results, mode=mode)

    def reply(self, *, text: str, route: dict[str, Any]) -> dict[str, Any]:
        route_agent = str(route.get("agent_id") or self.agent_id).strip().lower() or self.agent_id
        if route_agent != self.agent_id:
            raise RuntimeError(f"runtime agent mismatch: expected {self.agent_id}, got {route_agent}")
        space_key = str(route.get("space_key") or "general").strip() or "general"
        situation = choose_situation(agent_id=self.agent_id, text=text, space_key=space_key)
        plan = resolve_chat_route(
            agent_id=self.agent_id,
            situation=situation,
            models_path=self.models_path,
            agents_path=self.agents_path,
            env_values=self.env_values,
        )

        state = self._load_state()
        space_state = self._space_state(state, space_key)
        session_summary, turns = self._prepare_history(space_key=space_key, space_state=space_state, user_text=text)
        memory_context = self._memory_context(text=text, route=route, space_key=space_key)
        system_prompt = build_system_prompt(
            agent_id=self.agent_id,
            space_key=space_key,
            route=route,
            backend=self.backend,
            session_summary=session_summary,
            memory_context=memory_context,
        )
        messages = [{"role": row["role"], "content": row["content"]} for row in turns]
        try:
            result = invoke_chat_provider(
                provider_name=str(plan["provider"]),
                provider_cfg=ensure_dict(plan["provider_cfg"]),
                model=str(plan["model"]),
                env_values=self.env_values,
                system_prompt=system_prompt,
                messages=messages,
                max_output_tokens=int(plan.get("max_output_tokens", 900) or 900),
                workdir=self.root,
            )
        except Exception:
            self._log_call(
                lane=str(plan["lane"]),
                provider=str(plan["provider"]),
                model=str(plan["model"]),
                space_key=space_key,
                situation=situation,
                prompt_tokens=estimate_tokens(system_prompt + "\n" + "\n".join(row["content"] for row in messages)),
                completion_tokens=0,
                latency_ms=0,
                status="error",
            )
            raise
        reply_text = str(result.get("text") or "").strip()
        if not reply_text:
            raise RuntimeError("chat provider returned an empty response")

        prompt_tokens = int(result.get("prompt_tokens", 0) or 0) or estimate_tokens(system_prompt + "\n" + "\n".join(row["content"] for row in messages))
        completion_tokens = int(result.get("completion_tokens", 0) or 0) or estimate_tokens(reply_text)
        latency_ms = int(result.get("latency_ms", 0) or 0)

        turns.append({"role": "assistant", "content": reply_text})
        turns = turns[-10:]
        refreshed_summary = session_summary
        if len(turns) > 8:
            refreshed_summary = deterministic_checkpoint(session_summary, turns[:-6])
            turns = turns[-6:]
        exchange_count = int(space_state.get("exchange_count", 0) or 0) + 1
        self._persist_turns(
            state=state,
            space_key=space_key,
            summary=refreshed_summary,
            turns=turns,
            lane=str(plan["lane"]),
            provider=str(plan["provider"]),
            model=str(plan["model"]),
            exchange_count=exchange_count,
        )
        self._log_call(
            lane=str(plan["lane"]),
            provider=str(plan["provider"]),
            model=str(plan["model"]),
            space_key=space_key,
            situation=situation,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            status="success",
        )
        return {
            "reply_text": reply_text,
            "agent_id": self.agent_id,
            "space_key": space_key,
            "situation": situation,
            "lane": str(plan["lane"]),
            "requested_lane": str(plan["requested_lane"]),
            "downgraded_from_lane": plan.get("downgraded_from_lane"),
            "provider": str(plan["provider"]),
            "model": str(plan["model"]),
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "memory_context_used": bool(memory_context.strip()),
        }


AssistantChatRuntime = AgentChatRuntime


def build_runtime(
    *,
    root: Path = ROOT,
    env_file: Path | None = None,
    agent_id: str = "assistant",
) -> AgentChatRuntime:
    env_values = load_env_file(env_file, strict=True) if env_file else {}
    backend = DashboardBackend(root=root)
    return AgentChatRuntime(root=root, backend=backend, env_values=env_values, agent_id=agent_id)
