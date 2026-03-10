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
import difflib
import json
import re
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
import fitness_runtime as fitness_runtime  # type: ignore  # noqa: E402
import google_calendar_runtime as calendar_runtime  # type: ignore  # noqa: E402
from normalize_event import normalize_telegram  # type: ignore  # noqa: E402
import personal_task_runtime  # type: ignore  # noqa: E402
import reminder_state_machine as reminder_sm  # type: ignore  # noqa: E402
from validate_configs import load_yaml  # type: ignore  # noqa: E402


DEFAULT_ENV = Path("/etc/openclaw/openclaw.env")
DEFAULT_STATE = ROOT / "data" / "telegram-adapter-state.json"
TELEGRAM_MESSAGE_CHUNK_LIMIT = 3500
HELP_TEXT = "\n".join(
    [
        "Examples:",
        "- research flow status",
        "- run job search digest",
        "- run tech digest",
        "- remind me to review grades in 1 hour",
        "- what reminders do i have?",
        "- add review syllabus to my tasks for tomorrow 10am",
        "- what's on my calendar tomorrow?",
        "- give me my morning briefing",
        "- note this: test AgentMail later",
        "- what's my workout today?",
        "- I'm starting my workout",
        "- I did hammer curls 12 reps with 10kg each",
        "- if this chat is a specialist surface, just speak normally there",
        "- research: <text> / coding: <text> / fitness: <text> / [project:slug] <text> still work if you want explicit routing",
    ]
)

CONVERSATIONAL_SPECIALISTS = {"assistant", "researcher", "builder", "fitness_coach"}
DEFAULT_ASSISTANT_BINDING_ID = "assistant_main"
FOCUSABLE_AGENTS = {
    "assistant": {"space_key": "general", "label": "Assistant"},
    "researcher": {"space_key": "research", "label": "Researcher"},
    "fitness_coach": {"space_key": "fitness", "label": "Fitness Coach"},
    "builder": {"space_key": "coding", "label": "Builder"},
    "ops_guard": {"space_key": "ops", "label": "Ops Guard"},
}
AGENT_FOCUS_ALIASES = {
    "assistant": ["assistant", "general", "normal", "default", "front door"],
    "researcher": ["research", "researcher", "job search", "analysis"],
    "fitness_coach": ["fitness", "fitness coach", "workout", "training", "coach"],
    "builder": ["builder", "coding", "coding agent", "developer", "code"],
    "ops_guard": ["ops", "ops guard", "operations", "system health"],
}

REMINDER_LIST_PHRASES = {
    "what reminders do i have",
    "show reminders",
    "show my reminders",
    "list reminders",
    "what should you remind me about",
    "what am i waiting on",
}
TASK_LIST_PHRASES = {
    "what tasks do i have",
    "show my tasks",
    "list my tasks",
    "show tasks",
    "what is on my todo list",
    "what's on my todo list",
    "what is on my task list",
    "personal tasks",
    "todoist tasks",
    "do i have any tasks pending",
    "do i have any pending tasks",
    "what tasks are pending",
    "what tasks are open",
    "show pending tasks",
    "list pending tasks",
    "due tasks",
    "tasks due today",
}

DAY_BRIEFING_PHRASES = {
    "morning briefing",
    "daily briefing",
    "day briefing",
    "brief me on my day",
    "brief me on today",
    "give me my morning briefing",
    "give me today's briefing",
    "give me todays briefing",
    "give me my daily briefing",
    "how does my day look",
    "how does my day look today",
    "how is my day looking",
    "how is my day looking today",
    "what should i schedule today",
    "what still needs to be scheduled today",
}

MORNING_BRIEFING_DEFAULT_TIME = "07:00"
OPEN_CALENDAR_CANDIDATE_STATUSES = {"proposed", "needs_details", "ready", "approved"}

BRAINDUMP_NATURAL_PATTERNS = [
    (re.compile(r"^(?:note this|save this|save this idea|remember this for later)\s*[:,-]?\s*(?P<body>.+)$", re.IGNORECASE), "personal_note"),
    (re.compile(r"^gift idea(?:\s+for\s+(?:my\s+)?wife)?\s*[:,-]?\s*(?P<body>.+)$", re.IGNORECASE), "gift_idea_wife"),
    (re.compile(r"^tool to test\s*[:,-]?\s*(?P<body>.+)$", re.IGNORECASE), "tool_to_test"),
    (re.compile(r"^kid idea\s*[:,-]?\s*(?P<body>.+)$", re.IGNORECASE), "kid_idea"),
    (re.compile(r"^project idea\s*[:,-]?\s*(?P<body>.+)$", re.IGNORECASE), "project_idea"),
    (re.compile(r"^research topic\s*[:,-]?\s*(?P<body>.+)$", re.IGNORECASE), "research_topic"),
]

FITNESS_NATURAL_PATTERNS = [
    (re.compile(r"^(?:what(?: am i| are we)?(?: training)? today|what(?:'s| is) my workout today|what exercises today)\??$", re.IGNORECASE), "workout today"),
    (re.compile(r"^(?:i'?m\s+)?starting\s+(?:my\s+)?workout$", re.IGNORECASE), "start workout"),
    (re.compile(r"^(?:i'?m\s+)?done\s+with\s+(?:my\s+)?workout$", re.IGNORECASE), "finish workout"),
    (re.compile(r"^(?:i\s+did|did)\s+(?P<exercise>.+?)\s+(?P<reps>\d+)\s+reps?(?:\s+(?:with|at))?\s+(?P<weight>\d+(?:\.\d+)?)\s*kg(?:\s+(?P<mode>each|bb total|bb side|total))?$", re.IGNORECASE), None),
]

NATURAL_AGENT_RULES = [
    {
        "agent_id": "researcher",
        "space_key": "job-search",
        "keywords": ["job search", "resume", "cv", "interview", "apply", "application", "salary"],
    },
    {
        "agent_id": "researcher",
        "space_key": "research",
        "keywords": ["research", "compare", "evaluate", "pros and cons", "which tool", "should i use", "recommend", "tradeoff"],
    },
    {
        "agent_id": "builder",
        "space_key": "coding",
        "keywords": ["code", "coding", "debug", "fix", "implement", "refactor", "repo", "repository", "test", "bug", "pr", "pull request"],
    },
    {
        "agent_id": "ops_guard",
        "space_key": "ops",
        "keywords": ["service", "logs", "down", "incident", "outage", "health", "quota", "provider issue", "restart", "failing"],
    },
]

WEEKDAY_TO_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(frozen=True)
class TelegramChatBinding:
    binding_id: str
    label: str
    chat_id: str
    default_agent: str
    default_space: str
    natural_language_services: dict[str, bool]

    def allows(self, capability: str, *, default: bool = False) -> bool:
        return bool(self.natural_language_services.get(capability, default))


@dataclass(frozen=True)
class MorningBriefingConfig:
    enabled: bool
    binding_id: str
    delivery_time_local: str
    timezone_name: str
    max_schedule_suggestions: int


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


def normalize_binding_services(row: dict[str, Any]) -> dict[str, bool]:
    services = ensure_dict(row.get("natural_language_services"))
    return {
        "reminders": bool(services.get("reminders") is True),
        "tasks": bool(services.get("tasks") is True),
        "calendar": bool(services.get("calendar") is True),
        "braindump": bool(services.get("braindump") is True),
        "fitness": bool(services.get("fitness") is True),
        "cross_agent_routing": bool(services.get("cross_agent_routing") is True),
    }


def resolve_chat_bindings(root: Path, env_values: dict[str, str]) -> tuple[dict[str, TelegramChatBinding], str]:
    channels_cfg = ensure_dict(load_yaml_dict(root / "config" / "channels.yaml").get("channels"))
    telegram_cfg = ensure_dict(channels_cfg.get("telegram"))
    configured_bindings = ensure_dict(telegram_cfg.get("chat_bindings"))
    default_binding_id = str(telegram_cfg.get("default_binding") or DEFAULT_ASSISTANT_BINDING_ID).strip() or DEFAULT_ASSISTANT_BINDING_ID
    bindings: dict[str, TelegramChatBinding] = {}

    for binding_id, raw in configured_bindings.items():
        row = ensure_dict(raw)
        env_key = str(row.get("chat_id_env") or "").strip()
        chat_id = env_get(env_key, env_values) if env_key else str(row.get("chat_id") or "").strip()
        if not chat_id and binding_id == DEFAULT_ASSISTANT_BINDING_ID:
            chat_id = env_get("TELEGRAM_ALLOWED_CHAT_ID", env_values)
        if not chat_id:
            continue
        bindings[chat_id] = TelegramChatBinding(
            binding_id=str(binding_id).strip() or DEFAULT_ASSISTANT_BINDING_ID,
            label=str(row.get("label") or binding_id).strip() or str(binding_id),
            chat_id=str(chat_id).strip(),
            default_agent=str(row.get("default_agent") or "assistant").strip() or "assistant",
            default_space=str(row.get("default_space") or "general").strip() or "general",
            natural_language_services=normalize_binding_services(row),
        )

    if not bindings:
        allowed_chat_id = env_get("TELEGRAM_ALLOWED_CHAT_ID", env_values)
        if allowed_chat_id:
            bindings[allowed_chat_id] = TelegramChatBinding(
                binding_id=DEFAULT_ASSISTANT_BINDING_ID,
                label="Assistant Main",
                chat_id=allowed_chat_id,
                default_agent="assistant",
                default_space="general",
                natural_language_services={
                    "reminders": True,
                    "tasks": True,
                    "calendar": True,
                    "braindump": True,
                    "fitness": True,
                    "cross_agent_routing": True,
                },
            )
    return bindings, default_binding_id


def resolve_morning_briefing_config(
    root: Path,
    *,
    default_binding_id: str,
    default_timezone: str,
) -> MorningBriefingConfig:
    channels_cfg = ensure_dict(load_yaml_dict(root / "config" / "channels.yaml").get("channels"))
    telegram_cfg = ensure_dict(channels_cfg.get("telegram"))
    briefing_cfg = ensure_dict(telegram_cfg.get("assistant_morning_briefing"))

    delivery_time = str(briefing_cfg.get("delivery_time_local") or MORNING_BRIEFING_DEFAULT_TIME).strip()
    if parse_hhmm(delivery_time) is None:
        delivery_time = MORNING_BRIEFING_DEFAULT_TIME

    max_suggestions_raw = briefing_cfg.get("max_schedule_suggestions")
    if isinstance(max_suggestions_raw, int):
        max_suggestions = max(1, min(6, max_suggestions_raw))
    else:
        max_suggestions = 3

    return MorningBriefingConfig(
        enabled=bool(briefing_cfg.get("enabled") is True),
        binding_id=str(briefing_cfg.get("binding_id") or default_binding_id).strip() or default_binding_id,
        delivery_time_local=delivery_time,
        timezone_name=str(briefing_cfg.get("timezone") or default_timezone).strip() or default_timezone,
        max_schedule_suggestions=max_suggestions,
    )


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


def normalize_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower().rstrip("?.!"))


def resolve_agent_alias(text: str) -> str | None:
    lowered = normalize_phrase(text)
    for agent_id, aliases in AGENT_FOCUS_ALIASES.items():
        for alias in aliases:
            if re.search(rf"(^|\b){re.escape(alias)}(\b|$)", lowered):
                return agent_id
    return None


def detect_focus_instruction(text: str) -> dict[str, str] | None:
    lowered = normalize_phrase(text)
    if lowered in {
        "who am i talking to",
        "which agent am i talking to",
        "what mode are we in",
        "what focus are we in",
        "what are you focused on",
    }:
        return {"action": "status"}

    if any(
        phrase in lowered
        for phrase in {
            "back to assistant",
            "back to general",
            "switch back",
            "general mode",
            "normal mode",
            "clear mode",
            "clear focus",
            "exit current mode",
        }
    ):
        return {"action": "clear"}

    alias = resolve_agent_alias(lowered)
    if not alias:
        return None
    if any(
        trigger in lowered
        for trigger in {
            "switch to",
            "use the",
            "use ",
            "talk to",
            "work with",
            "be my",
            "act as",
            "stay in",
            "go into",
            "enter ",
            "focus on",
        }
    ) or " mode" in lowered or " agent" in lowered or " chat" in lowered:
        return {"action": "set", "agent_id": alias}
    return None


def classify_research_flow_workflow(text: str) -> str | None:
    lowered = normalize_phrase(text)
    if any(phrase in lowered for phrase in {"both digests", "all digests", "run both", "run all"}):
        return "all"
    if any(
        phrase in lowered
        for phrase in {
            "job search digest",
            "job-search digest",
            "job digest",
            "job search report",
            "job report",
        }
    ):
        return "job_search_digest"
    if any(
        phrase in lowered
        for phrase in {
            "tech digest",
            "ai tools digest",
            "ai-tools digest",
            "ai digest",
            "tools digest",
        }
    ):
        return "ai_tools_watch"
    return None


def is_bare_research_flow_phrase(text: str) -> bool:
    lowered = normalize_phrase(text)
    return lowered in {
        "tech digest",
        "ai tools digest",
        "ai-tools digest",
        "ai digest",
        "tools digest",
        "job search digest",
        "job-search digest",
        "job digest",
        "job search report",
        "job report",
        "both digests",
        "all digests",
    }


def parse_research_flow_request(text: str, *, command_name: str = "", body: str = "") -> dict[str, Any] | None:
    clean = normalize_phrase(text)
    if command_name in {"researchflow", "research-flow", "rf"}:
        lowered_body = normalize_phrase(body)
        workflow = classify_research_flow_workflow(lowered_body)
        if not lowered_body or any(word in lowered_body for word in {"status", "state", "health"}):
            return {"action": "status"}
        if workflow is not None:
            return {
                "action": "run",
                "workflow": workflow,
                "apply": bool(re.search(r"\b(send|publish|deliver)\b", lowered_body)),
            }
        if any(word in lowered_body for word in {"run", "refresh", "generate"}):
            return {"action": "run", "workflow": "all", "apply": False}
        return {"action": "status"}

    if clean in {
        "research flow",
        "researchflow",
        "digests",
        "digest status",
        "research digest status",
        "research flow status",
        "research status",
    }:
        return {"action": "status"}
    if any(phrase in clean for phrase in {"research flow status", "digest status", "digests status"}):
        return {"action": "status"}

    workflow = classify_research_flow_workflow(clean)
    if workflow is None:
        return None
    if is_bare_research_flow_phrase(clean):
        return {"action": "run", "workflow": workflow, "apply": False}
    if not re.search(r"\b(run|refresh|generate|create|send|publish|deliver|do)\b", clean):
        return None
    return {
        "action": "run",
        "workflow": workflow,
        "apply": bool(re.search(r"\b(send|publish|deliver)\b", clean)),
    }


def is_reminder_list_request(text: str) -> bool:
    lowered = normalize_phrase(text)
    return lowered in REMINDER_LIST_PHRASES


def parse_hhmm(text: str | None) -> tuple[int, int] | None:
    clean = str(text or "").strip()
    match = re.fullmatch(r"(\d{2}):(\d{2})", clean)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def is_day_briefing_request(text: str) -> bool:
    clean = normalize_phrase(text)
    if clean in DAY_BRIEFING_PHRASES:
        return True
    return bool(
        re.fullmatch(
            r"(?:show|give|send)(?: me)? (?:my |a )?(?:morning |daily |today'?s )?(?:brief|briefing|day plan)",
            clean,
        )
        or re.fullmatch(r"(?:what|how)(?:'s| is| does)? my day (?:look|looking)(?: like)?(?: today)?", clean)
        or re.fullmatch(r"what should i (?:put on my calendar|schedule)(?: today)?", clean)
    )


def infer_natural_agent(text: str) -> tuple[str, str] | None:
    lowered = normalize_phrase(text)
    for rule in NATURAL_AGENT_RULES:
        for keyword in rule["keywords"]:
            if re.search(rf"(^|\b){re.escape(keyword)}(\b|$)", lowered):
                return str(rule["agent_id"]), str(rule["space_key"])
    return None


def parse_natural_braindump_text(text: str) -> tuple[str, str] | None:
    clean = text.strip()
    for pattern, category in BRAINDUMP_NATURAL_PATTERNS:
        match = pattern.match(clean)
        if match:
            body = str(match.group("body") or "").strip()
            if body:
                return category, body
    return None


def translate_natural_fitness_text(text: str) -> str | None:
    clean = text.strip()
    for pattern, replacement in FITNESS_NATURAL_PATTERNS:
        match = pattern.match(clean)
        if not match:
            continue
        if replacement is not None:
            return replacement
        exercise = str(match.group("exercise") or "").strip()
        reps = str(match.group("reps") or "").strip()
        weight = str(match.group("weight") or "").strip()
        mode = str(match.group("mode") or "each").strip().lower()
        if mode == "total":
            mode = "bb total"
        return f"log {exercise} {reps} reps {weight}kg {mode}"
    return None


def is_calendar_today_request(text: str) -> bool:
    clean = normalize_phrase(text)
    return clean in {
        "calendar today",
        "today calendar",
        "calendar",
        "today",
        "what is on my calendar today",
        "what's on my calendar today",
        "what do i have today",
        "what is on today",
        "what's on today",
    } or clean.startswith("/calendar") or bool(
        re.fullmatch(
            r"(?:do i have(?: anything)?|what do i have|show(?: me)?|anything(?: on)?)(?: scheduled)?(?: on| for)? today",
            clean,
        )
    )


def is_calendar_next_request(text: str) -> bool:
    clean = normalize_phrase(text)
    return clean in {
        "calendar next",
        "calendar upcoming",
        "upcoming calendar",
        "next calendar",
        "what is coming up",
        "what's coming up",
        "what is on my calendar next",
        "what's on my calendar next",
        "how is my calendar looking",
        "show my calendar",
        "calendar overview",
    } or bool(
        re.fullmatch(
            r"(?:how is|how's|show(?: me)?|what(?: is| what's|s)?|give me)(?: my)? calendar(?: looking)?(?: (?:this week|upcoming|overview))?",
            clean,
        )
    ) or bool(
        re.fullmatch(
            r"(?:what do i have|do i have anything)(?: scheduled)?(?: on)? (?:this week|coming up|upcoming)",
            clean,
        )
    )


def is_calendar_tomorrow_request(text: str) -> bool:
    clean = normalize_phrase(text)
    return clean in {
        "calendar tomorrow",
        "what do i have tomorrow",
        "what is on my calendar tomorrow",
        "what's on my calendar tomorrow",
        "what is tomorrow on my calendar",
    } or bool(
        re.fullmatch(
            r"(?:do i have(?: anything)?|what do i have|show(?: me)?|anything(?: on)?)(?: scheduled)?(?: on| for)? tomorrow",
            clean,
        )
    )


def parse_task_create_text(text: str) -> tuple[str, str | None] | None:
    clean = text.strip()
    lowered = normalize_phrase(clean)
    prefixes = ("add-task ", "task ", "todo ")
    body = None
    for prefix in prefixes:
        if lowered.startswith(prefix):
            body = clean[len(prefix) :].strip()
            break
    if body is not None:
        if not body:
            return None
        if "::" in body:
            title, due = body.split("::", 1)
            return title.strip(), due.strip() or None
        return body, None
    natural_patterns = [
        re.compile(
            r"^(?:(?:can|could|would)\s+you\s+|please\s+)?(?:add|put)\s+(?P<title>.+?)\s+to\s+(?:my\s+)?(?:tasks|task list|todo(?: list)?|todoist)"
            r"(?:\s+(?:for|by|due)\s+(?P<due>.+))?$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:(?:can|could|would)\s+you\s+|please\s+)?create\s+(?:a\s+)?(?:task|todo)(?:\s+for\s+me)?\s+(?:to\s+)?(?P<title>.+?)"
            r"(?:\s+(?:for|by|due)\s+(?P<due>.+?))?(?:\s+in\s+(?:todoist|my\s+tasks|my\s+todo(?: list)?))?$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:(?:can|could|would)\s+you\s+|please\s+)?(?:set|make)\s+(?:a\s+)?(?:task|todo)(?:\s+(?:called|named))?\s+(?P<title>.+?)"
            r"(?:\s+(?:for|by|due)\s+(?P<due>.+?))?(?:\s+in\s+(?:todoist|my\s+tasks|my\s+todo(?: list)?))?$",
            re.IGNORECASE,
        ),
    ]
    for pattern in natural_patterns:
        match = pattern.match(clean)
        if not match:
            continue
        title = str(match.group("title") or "").strip(" .")
        due = str(match.group("due") or "").strip(" .") or None
        if title:
            return title, due
    return None


def parse_duration_text(text: str | None) -> timedelta | None:
    clean = str(text or "").strip().lower()
    if not clean:
        return None
    match = re.fullmatch(r"(\d+)\s*(m|mins?|minutes?|h|hrs?|hours?)", clean)
    if not match:
        return None
    qty = int(match.group(1))
    unit = match.group(2)
    if unit.startswith("h"):
        return timedelta(hours=qty)
    return timedelta(minutes=qty)


def normalize_task_due_text(text: str | None) -> str | None:
    clean = str(text or "").strip()
    if not clean:
        return None
    lowered = normalize_phrase(clean)
    match = re.fullmatch(r"tonight(?: at)?\s+(.+)", lowered)
    if match:
        return f"today {str(match.group(1) or '').strip()}".strip()
    return clean


def parse_time_component(text: str) -> tuple[int, int] | None:
    clean = str(text or "").strip().lower()
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", clean)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    marker = match.group(3)
    if marker:
        if hour < 1 or hour > 12:
            return None
        if marker == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
    elif hour > 23 or minute > 59:
        return None
    if minute > 59:
        return None
    return hour, minute


def extract_calendar_time_range(when_text: str) -> tuple[str, timedelta | None]:
    clean = str(when_text or "").strip()
    if not clean:
        return "", None
    time_pattern = r"\d{1,2}(?::\d{2})?\s*(?:am|pm)?"
    day_pattern = r"(?:today|tomorrow|(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|\d{4}-\d{2}-\d{2})"
    patterns = [
        re.compile(rf"^(?P<day>{day_pattern})\s+(?P<start>{time_pattern})\s*(?:to|-)\s*(?P<end>{time_pattern})$", re.IGNORECASE),
        re.compile(rf"^(?P<start>{time_pattern})\s*(?:to|-)\s*(?P<end>{time_pattern})\s+(?P<day>{day_pattern})$", re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.match(clean)
        if not match:
            continue
        day_text = str(match.group("day") or "").strip()
        start_text = str(match.group("start") or "").strip()
        end_text = str(match.group("end") or "").strip()
        start_clock = parse_time_component(start_text)
        end_clock = parse_time_component(end_text)
        if start_clock is None or end_clock is None:
            continue
        start_minutes = start_clock[0] * 60 + start_clock[1]
        end_minutes = end_clock[0] * 60 + end_clock[1]
        if end_minutes <= start_minutes:
            continue
        return f"{day_text} {start_text}".strip(), timedelta(minutes=end_minutes - start_minutes)
    return clean, None


def parse_human_calendar_when(
    text: str,
    *,
    timezone_name: str,
    reference_utc: datetime,
) -> dict[str, str]:
    clean = str(text or "").strip()
    if not clean:
        raise ValueError("calendar time is required")

    zone = ZoneInfo(timezone_name)
    reference_local = reference_utc.astimezone(zone)
    lowered = normalize_phrase(clean)

    if lowered.startswith("in "):
        start_utc = reminder_sm.parse_when(clean, timezone_name, reference_utc)
        return {"kind": "timed", "start_at": start_utc.isoformat(timespec="seconds")}

    trailing_day_match = re.fullmatch(r"(.+?)\s+(today|tomorrow)", lowered)
    if trailing_day_match:
        time_text = str(trailing_day_match.group(1) or "").strip()
        day_keyword = str(trailing_day_match.group(2) or "").strip()
        target_day = reference_local.date() + timedelta(days=1 if day_keyword == "tomorrow" else 0)
        clock = parse_time_component(time_text)
        if clock is not None:
            start_local = datetime.combine(target_day, datetime.min.time(), tzinfo=zone).replace(
                hour=clock[0], minute=clock[1]
            )
            return {"kind": "timed", "start_at": start_local.astimezone(timezone.utc).isoformat(timespec="seconds")}

    day_match = re.fullmatch(r"(today|tomorrow)(?:\s+at\s+|\s+)?(.+)?", lowered)
    if day_match:
        day_keyword = day_match.group(1)
        time_text = str(day_match.group(2) or "").strip()
        target_day = reference_local.date() + timedelta(days=1 if day_keyword == "tomorrow" else 0)
        if not time_text:
            return {"kind": "all_day", "start_date": target_day.isoformat()}
        clock = parse_time_component(time_text)
        if clock is None:
            raise ValueError(f"unsupported calendar time: {clean}")
        start_local = datetime.combine(target_day, datetime.min.time(), tzinfo=zone).replace(
            hour=clock[0], minute=clock[1]
        )
        return {"kind": "timed", "start_at": start_local.astimezone(timezone.utc).isoformat(timespec="seconds")}

    weekday_match = re.fullmatch(r"(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:\s+at\s+|\s+)?(.+)?", lowered)
    if weekday_match:
        force_next = bool(weekday_match.group(1))
        weekday = WEEKDAY_TO_INDEX[str(weekday_match.group(2))]
        time_text = str(weekday_match.group(3) or "").strip()
        days_ahead = (weekday - reference_local.weekday()) % 7
        if days_ahead == 0 or force_next:
            days_ahead = days_ahead or 7
        target_day = reference_local.date() + timedelta(days=days_ahead)
        if not time_text:
            return {"kind": "all_day", "start_date": target_day.isoformat()}
        clock = parse_time_component(time_text)
        if clock is None:
            raise ValueError(f"unsupported calendar time: {clean}")
        start_local = datetime.combine(target_day, datetime.min.time(), tzinfo=zone).replace(
            hour=clock[0], minute=clock[1]
        )
        return {"kind": "timed", "start_at": start_local.astimezone(timezone.utc).isoformat(timespec="seconds")}

    iso_day_match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:\s+at\s+|\s+)?(.+)?", clean, flags=re.IGNORECASE)
    if iso_day_match:
        target_day = date.fromisoformat(iso_day_match.group(1))
        time_text = str(iso_day_match.group(2) or "").strip()
        if not time_text:
            return {"kind": "all_day", "start_date": target_day.isoformat()}
        clock = parse_time_component(time_text)
        if clock is None:
            raise ValueError(f"unsupported calendar time: {clean}")
        start_local = datetime.combine(target_day, datetime.min.time(), tzinfo=zone).replace(
            hour=clock[0], minute=clock[1]
        )
        return {"kind": "timed", "start_at": start_local.astimezone(timezone.utc).isoformat(timespec="seconds")}

    clock = parse_time_component(clean)
    if clock is not None:
        start_local = datetime.combine(reference_local.date(), datetime.min.time(), tzinfo=zone).replace(
            hour=clock[0], minute=clock[1]
        )
        if start_local <= reference_local:
            start_local = start_local + timedelta(days=1)
        return {"kind": "timed", "start_at": start_local.astimezone(timezone.utc).isoformat(timespec="seconds")}

    try:
        start_utc = reminder_sm.parse_when(clean, timezone_name, reference_utc)
        return {"kind": "timed", "start_at": start_utc.isoformat(timespec="seconds")}
    except Exception as exc:
        raise ValueError(f"unsupported calendar time: {clean}") from exc


def looks_like_calendar_when_text(text: str) -> bool:
    clean = normalize_phrase(text)
    if not clean:
        return False
    if clean.startswith("in "):
        return True
    if re.fullmatch(r"(today|tomorrow)(?:\s+at\s+|\s+)?(.+)?", clean):
        return True
    if re.fullmatch(r"(.+?)\s+(today|tomorrow)", clean):
        return True
    if re.fullmatch(r"(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:\s+at\s+|\s+)?(.+)?", clean):
        return True
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:\s+at\s+|\s+)?(.+)?", clean):
        return True
    return bool(re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b", clean))


def split_calendar_title_when(body: str) -> tuple[str, str] | None:
    clean = str(body or "").strip(" .")
    if not clean:
        return None
    separators = (" at ", " on ", " for ")
    for separator in separators:
        positions = [match.start() for match in re.finditer(re.escape(separator), clean, flags=re.IGNORECASE)]
        for start in reversed(positions):
            title = clean[:start].strip(" .,:-")
            when_text = clean[start + len(separator) :].strip(" .,:-")
            if title and when_text and looks_like_calendar_when_text(when_text):
                return title, when_text
    return None


def normalize_created_title(title: str) -> str:
    clean = str(title or "").strip(" .")
    if not clean:
        return ""
    return re.sub(r"^(?:a|an)\s+", "", clean, count=1, flags=re.IGNORECASE).strip(" .")


def parse_calendar_create_text(text: str) -> dict[str, Any] | None:
    clean = str(text or "").strip()
    heuristic_patterns = [
        re.compile(
            r"^(?:(?:can|could|would)\s+you\s+|please\s+)?schedule\s+(?P<body>.+?)(?:\s+in\s+(?:my\s+)?calendar)?$",
            re.IGNORECASE,
        ),
    ]
    for pattern in heuristic_patterns:
        match = pattern.match(clean)
        if not match:
            continue
        split = split_calendar_title_when(str(match.group("body") or ""))
        if split is None:
            continue
        title, when_text = split
        when_text, inferred_duration = extract_calendar_time_range(when_text)
        return {
            "title": normalize_created_title(title),
            "when_text": when_text,
            "duration": inferred_duration,
        }

    patterns = [
        re.compile(
            r"^(?:(?:can|could|would)\s+you\s+|please\s+)?schedule\s+(?P<title>.+?)\s+(?:for|at|on)\s+(?P<when>.+?)(?:\s+in\s+(?:my\s+)?calendar)?(?:\s+for\s+(?P<duration>\d+\s*(?:m|mins?|minutes?|h|hrs?|hours?)))?$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:(?:can|could|would)\s+you\s+|please\s+)?(?:add|put|create|set)\s+(?P<title>.+?)\s+(?:to|on|in)\s+(?:my\s+)?calendar\s+(?:for|at|on)\s+(?P<when>.+?)(?:\s+for\s+(?P<duration>\d+\s*(?:m|mins?|minutes?|h|hrs?|hours?)))?$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:(?:can|could|would)\s+you\s+|please\s+)?(?:add|put|create|set)\s+(?P<title>.+?)\s+(?:for|at|on)\s+(?P<when>.+?)\s+(?:to|on|in)\s+(?:my\s+)?calendar(?:\s+for\s+(?P<duration>\d+\s*(?:m|mins?|minutes?|h|hrs?|hours?)))?$",
            re.IGNORECASE,
        ),
    ]
    for pattern in patterns:
        match = pattern.match(clean)
        if not match:
            continue
        title = str(match.group("title") or "").strip(" .")
        when_text = str(match.group("when") or "").strip(" .")
        duration_text = str(match.group("duration") or "").strip()
        when_text, inferred_duration = extract_calendar_time_range(when_text)
        if title and when_text:
            return {
                "title": normalize_created_title(title),
                "when_text": when_text,
                "duration": parse_duration_text(duration_text) or inferred_duration,
            }
    return None


def parse_calendar_move_text(text: str) -> dict[str, Any] | None:
    clean = str(text or "").strip()
    patterns = [
        re.compile(
            r"^(?:please\s+)?(?:move|reschedule)\s+(?P<title>.+?)\s+on\s+(?:my\s+)?calendar\s+to\s+(?P<when>.+?)(?:\s+for\s+(?P<duration>\d+\s*(?:m|mins?|minutes?|h|hrs?|hours?)))?$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:please\s+)?calendar\s+(?:move|reschedule)\s+(?P<title>.+?)\s+to\s+(?P<when>.+?)(?:\s+for\s+(?P<duration>\d+\s*(?:m|mins?|minutes?|h|hrs?|hours?)))?$",
            re.IGNORECASE,
        ),
    ]
    for pattern in patterns:
        match = pattern.match(clean)
        if not match:
            continue
        title = str(match.group("title") or "").strip(" .")
        when_text = str(match.group("when") or "").strip(" .")
        duration_text = str(match.group("duration") or "").strip()
        when_text, inferred_duration = extract_calendar_time_range(when_text)
        if title and when_text:
            return {
                "title": title,
                "when_text": when_text,
                "duration": parse_duration_text(duration_text) or inferred_duration,
            }
    return None


def classify_task_list_request(text: str) -> str | None:
    clean = normalize_phrase(text)
    if clean in {"tasks", "task list", "todo list", "/tasks"} | TASK_LIST_PHRASES:
        if "today" in clean:
            return "today"
        if "overdue" in clean:
            return "overdue"
        if "due" in clean:
            return "due"
        return "open"
    if re.fullmatch(
        r"(?:do i have|what do i have|show(?: me)?|list)(?: any)? (?:(?:pending|open|due|overdue|personal)\s+)?(?:tasks|task list|todo list|todos)",
        clean,
    ):
        if "overdue" in clean:
            return "overdue"
        if "due" in clean:
            return "due"
        return "open"
    if re.fullmatch(r"(?:tasks|todos) due today", clean):
        return "today"
    if re.fullmatch(r"(?:tasks|todos) due tomorrow", clean):
        return "tomorrow"
    return None


def task_due_local_date(task: dict[str, Any], timezone_name: str) -> date | None:
    due_value = str(task.get("due_value") or "").strip()
    due_mode = str(task.get("due_mode") or "").strip()
    if not due_value:
        return None
    if due_mode == "date":
        try:
            return date.fromisoformat(due_value)
        except ValueError:
            return None
    if due_mode == "datetime":
        try:
            dt = datetime.fromisoformat(due_value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(ZoneInfo(timezone_name)).date()
        except ValueError:
            return None
    return None


def reminder_local_date(reminder: dict[str, Any], timezone_name: str) -> date | None:
    remind_at = str(reminder.get("remind_at") or "").strip()
    if not remind_at:
        return None
    try:
        dt = datetime.fromisoformat(remind_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(timezone_name)).date()


def task_due_bucket(task: dict[str, Any], *, timezone_name: str, today_local: date) -> str | None:
    due_date = task_due_local_date(task, timezone_name)
    if due_date is not None:
        if due_date < today_local:
            return "overdue"
        if due_date == today_local:
            return "today"
        return None
    due_string = normalize_phrase(str(task.get("due_string") or ""))
    if due_string.startswith("today") or due_string.startswith("tonight"):
        return "today"
    return None


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


def format_calendar_event_brief(event: dict[str, Any], timezone_name: str) -> str:
    summary = str(event.get("summary") or "(untitled event)")
    if event.get("all_day"):
        when = str(event.get("start_value") or "")
    else:
        when = format_dt(str(event.get("start_value") or ""), timezone_name)
    return f"{when} | {summary}"


def calendar_event_match_score(query: str, summary: str) -> float:
    clean_query = normalize_phrase(query)
    clean_summary = normalize_phrase(summary)
    if not clean_query or not clean_summary:
        return 0.0
    if clean_query == clean_summary:
        return 1.0
    if clean_query in clean_summary:
        return 0.95
    if clean_summary in clean_query:
        return 0.9
    return difflib.SequenceMatcher(a=clean_query, b=clean_summary).ratio()


def title_has_calendar_match(title: str, events: list[dict[str, Any]]) -> bool:
    clean_title = str(title or "").strip()
    if not clean_title:
        return False
    return any(
        calendar_event_match_score(clean_title, str(ensure_dict(event).get("summary") or "")) >= 0.7
        for event in events
        if isinstance(event, dict)
    )


def split_telegram_text(text: str, *, limit: int = TELEGRAM_MESSAGE_CHUNK_LIMIT) -> list[str]:
    clean = str(text or "").strip()
    if not clean:
        return [""]
    if len(clean) <= limit:
        return [clean]

    parts: list[str] = []
    remaining = clean
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = max(
            window.rfind("\n\n"),
            window.rfind("\n"),
            window.rfind(" "),
        )
        if cut < max(200, limit // 4):
            cut = limit
        chunk = remaining[:cut].strip()
        if not chunk:
            chunk = remaining[:limit].strip()
            cut = len(chunk)
        parts.append(chunk)
        remaining = remaining[cut:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


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
        allowed_chat_id: str | None = None,
        chat_bindings: dict[str, TelegramChatBinding] | None = None,
        default_binding_id: str | None = None,
        reminder_binding_id: str | None = None,
        env_values: dict[str, str],
        state_path: Path,
        reminder_state_path: Path,
        default_timezone: str,
    ) -> None:
        self.root = root
        self.backend = backend
        self.client = client
        normalized_bindings = dict(chat_bindings or {})
        if not normalized_bindings and allowed_chat_id:
            normalized_bindings = {
                allowed_chat_id.strip(): TelegramChatBinding(
                    binding_id=DEFAULT_ASSISTANT_BINDING_ID,
                    label="Assistant Main",
                    chat_id=allowed_chat_id.strip(),
                    default_agent="assistant",
                    default_space="general",
                    natural_language_services={
                        "reminders": True,
                        "tasks": True,
                        "calendar": True,
                        "braindump": True,
                        "fitness": True,
                        "cross_agent_routing": True,
                    },
                )
            }
        self.chat_bindings = normalized_bindings
        self.default_binding_id = (default_binding_id or DEFAULT_ASSISTANT_BINDING_ID).strip() or DEFAULT_ASSISTANT_BINDING_ID
        self.reminder_binding_id = (reminder_binding_id or DEFAULT_ASSISTANT_BINDING_ID).strip() or DEFAULT_ASSISTANT_BINDING_ID
        self.env_values = env_values
        self.state_path = state_path
        self.reminder_state_path = reminder_state_path
        self.default_timezone = default_timezone
        self.morning_briefing_cfg = resolve_morning_briefing_config(
            root,
            default_binding_id=self.default_binding_id,
            default_timezone=default_timezone,
        )
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
        self.fitness_runtime = fitness_runtime.FitnessRuntime(root=root)

    def _runtime_env_values(self) -> dict[str, str]:
        merged = dict(self.env_values)
        env_path = self.backend._integration_env_file_path()
        if env_path is not None and env_path.exists():
            try:
                loaded = load_env_file(env_path)
            except Exception:
                loaded = {}
            for key, value in loaded.items():
                if key not in merged or not str(merged.get(key) or "").strip():
                    merged[key] = value
        return merged

    def _send_text(
        self,
        *,
        chat_id: str,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> list[dict[str, Any]]:
        responses: list[dict[str, Any]] = []
        chunks = split_telegram_text(text)
        for index, chunk in enumerate(chunks):
            response = self.client.send_message(
                chat_id=chat_id,
                text=chunk,
                reply_to_message_id=reply_to_message_id if index == 0 else None,
            )
            responses.append(ensure_dict(response))
        return responses

    def _binding_for_chat(self, chat_id: str) -> TelegramChatBinding | None:
        return self.chat_bindings.get(chat_id.strip())

    def _binding_by_id(self, binding_id: str) -> TelegramChatBinding | None:
        clean = binding_id.strip()
        for binding in self.chat_bindings.values():
            if binding.binding_id == clean:
                return binding
        return None

    def _assistant_binding(self) -> TelegramChatBinding | None:
        return self._binding_by_id(self.default_binding_id) or next(iter(self.chat_bindings.values()), None)

    def _reminder_chat_id(self) -> str | None:
        binding = self._binding_by_id(self.reminder_binding_id)
        if binding is not None:
            return binding.chat_id
        assistant_binding = self._assistant_binding()
        return assistant_binding.chat_id if assistant_binding is not None else None

    def load_adapter_state(self) -> dict[str, Any]:
        data = read_json(self.state_path)
        links = ensure_dict(data.get("reminder_message_links"))
        data["reminder_message_links"] = {
            str(chat_id): ensure_dict(value) for chat_id, value in links.items()
        }
        focus = ensure_dict(data.get("conversation_focus"))
        data["conversation_focus"] = {
            "agent_id": str(focus.get("agent_id") or "assistant").strip() or "assistant",
            "space_key": str(focus.get("space_key") or "general").strip() or "general",
            "set_at": str(focus.get("set_at") or "").strip() or None,
        }
        briefing = ensure_dict(data.get("morning_briefing"))
        data["morning_briefing"] = {
            "enabled": self.morning_briefing_cfg.enabled,
            "binding_id": self.morning_briefing_cfg.binding_id,
            "delivery_time_local": self.morning_briefing_cfg.delivery_time_local,
            "timezone": self.morning_briefing_cfg.timezone_name,
            "max_schedule_suggestions": self.morning_briefing_cfg.max_schedule_suggestions,
            "last_sent_at": str(briefing.get("last_sent_at") or "").strip() or None,
            "last_sent_local_date": str(briefing.get("last_sent_local_date") or "").strip() or None,
            "last_delivery_kind": str(briefing.get("last_delivery_kind") or "").strip() or None,
            "last_status": str(briefing.get("last_status") or "").strip() or None,
            "last_message_preview": str(briefing.get("last_message_preview") or "").strip() or None,
            "last_summary": ensure_dict(briefing.get("last_summary")),
        }
        if "last_update_id" not in data:
            data["last_update_id"] = 0
        return data

    def save_adapter_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = short_now_iso()
        write_json(self.state_path, state)

    def _set_conversation_focus(self, state: dict[str, Any], *, agent_id: str) -> dict[str, Any]:
        focus_cfg = ensure_dict(FOCUSABLE_AGENTS.get(agent_id))
        focus = {
            "agent_id": agent_id,
            "space_key": str(focus_cfg.get("space_key") or "general"),
            "set_at": short_now_iso(),
        }
        state["conversation_focus"] = focus
        return focus

    def _clear_conversation_focus(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._set_conversation_focus(state, agent_id="assistant")

    def _conversation_focus(self, state: dict[str, Any]) -> dict[str, Any]:
        focus = ensure_dict(state.get("conversation_focus"))
        if not focus:
            return self._clear_conversation_focus(state)
        agent_id = str(focus.get("agent_id") or "assistant").strip() or "assistant"
        if agent_id not in FOCUSABLE_AGENTS:
            return self._clear_conversation_focus(state)
        return {
            "agent_id": agent_id,
            "space_key": str(focus.get("space_key") or FOCUSABLE_AGENTS[agent_id]["space_key"]).strip()
            or str(FOCUSABLE_AGENTS[agent_id]["space_key"]),
            "set_at": str(focus.get("set_at") or "").strip() or None,
        }

    def _focus_label(self, focus: dict[str, Any]) -> str:
        agent_id = str(focus.get("agent_id") or "assistant").strip() or "assistant"
        cfg = ensure_dict(FOCUSABLE_AGENTS.get(agent_id))
        label = str(cfg.get("label") or agent_id).strip() or agent_id
        space_key = str(focus.get("space_key") or cfg.get("space_key") or "general").strip() or "general"
        return f"{label} ({space_key})"

    def _handle_focus_instruction(self, state: dict[str, Any], instruction: dict[str, str]) -> str:
        action = str(instruction.get("action") or "").strip()
        if action == "status":
            focus = self._conversation_focus(state)
            return f"Current conversation focus: {self._focus_label(focus)}"
        if action == "clear":
            focus = self._clear_conversation_focus(state)
            return f"Switched back to {self._focus_label(focus)}"
        if action == "set":
            agent_id = str(instruction.get("agent_id") or "assistant").strip() or "assistant"
            if agent_id not in FOCUSABLE_AGENTS:
                return "I do not recognize that agent."
            focus = self._set_conversation_focus(state, agent_id=agent_id)
            return f"Conversation focus set to {self._focus_label(focus)}"
        return "Could not update conversation focus."

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
            responses = self._send_text(chat_id=chat_id, text=item.outbound_text)
            response = responses[0] if responses else {}
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
        env_values = self._runtime_env_values()
        default_timezone = calendar_runtime.resolve_default_timezone(env_values, self.root)
        calendar_runtime.resolve_calendar_id(env_file_values=env_values, override=None)
        client = calendar_runtime.build_client(env_file_values=env_values, fixtures_file=None)
        return client, default_timezone

    def _personal_task_client(self) -> tuple[str, Any]:
        personal_task_runtime.resolve_personal_task_integration(self.root / "config" / "integrations.yaml")
        env_values = self._runtime_env_values()
        provider = personal_task_runtime.resolve_provider(
            env_file_values=env_values,
            override=None,
            fixtures_file=None,
        )
        client = personal_task_runtime.build_client(
            provider=provider,
            env_file_values=env_values,
            fixtures_file=None,
        )
        return provider, client

    def _handle_calendar_today(self) -> str:
        return self._handle_calendar_day(day_offset=0, heading="Calendar today")

    def _handle_calendar_tomorrow(self) -> str:
        return self._handle_calendar_day(day_offset=1, heading="Calendar tomorrow")

    def _handle_calendar_day(self, *, day_offset: int, heading: str) -> str:
        try:
            client, timezone_name = self._calendar_client()
            env_values = self._runtime_env_values()
            calendar_id = calendar_runtime.resolve_calendar_id(env_file_values=env_values, override=None)
            events = calendar_runtime.list_upcoming(
                client,
                calendar_id=calendar_id,
                default_timezone=timezone_name,
                limit=12,
                window_days=7,
            )
            target_day = datetime.now(ZoneInfo(timezone_name)).date() + timedelta(days=day_offset)
            day_events = [row for row in events if event_local_date(row, timezone_name) == target_day]
            return format_calendar_lines(day_events, timezone_name, heading=heading)
        except Exception:
            return "Calendar is not configured yet."

    def _handle_calendar_next(self) -> str:
        try:
            client, timezone_name = self._calendar_client()
            env_values = self._runtime_env_values()
            calendar_id = calendar_runtime.resolve_calendar_id(env_file_values=env_values, override=None)
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

    def _refresh_calendar_runtime_status(
        self,
        *,
        client: Any,
        calendar_id: str,
        timezone_name: str,
        action: str,
        recent_results: list[dict[str, Any]],
        created_count: int = 0,
        updated_count: int = 0,
    ) -> None:
        upcoming_events = calendar_runtime.list_upcoming(
            client,
            calendar_id=calendar_id,
            default_timezone=timezone_name,
            limit=20,
            window_days=14,
        )
        payload = calendar_runtime.build_status_payload(
            calendar_id=calendar_id,
            action=action,
            dry_run=False,
            upcoming_events=upcoming_events,
            recent_results=recent_results,
            window_days=14,
            created_count=created_count,
            updated_count=updated_count,
        )
        calendar_runtime.write_json(self.root / "data" / "calendar-runtime-status.json", payload)

    def _timed_event_end(
        self,
        *,
        start_at: str,
        duration: timedelta | None,
        default_timezone: str,
    ) -> str:
        start_dt = calendar_runtime.parse_datetime_text(start_at, default_timezone)
        end_dt = start_dt + (duration or timedelta(hours=1))
        return end_dt.isoformat(timespec="seconds")

    def _match_calendar_event(
        self,
        *,
        title: str,
        events: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        scored: list[tuple[float, dict[str, Any]]] = []
        for event in events:
            score = calendar_event_match_score(title, str(event.get("summary") or ""))
            if score >= 0.62:
                scored.append((score, event))
        if not scored:
            return None, []
        scored.sort(key=lambda item: item[0], reverse=True)
        top_score = scored[0][0]
        top = [row for score, row in scored if score >= max(0.9, top_score - 0.03)]
        if len(top) == 1:
            return top[0], top
        exact = [row for row in top if normalize_phrase(str(row.get("summary") or "")) == normalize_phrase(title)]
        if len(exact) == 1:
            return exact[0], exact
        return None, top[:3]

    def _handle_calendar_create_from_text(self, text: str) -> str:
        parsed = parse_calendar_create_text(text)
        if not parsed:
            raise ValueError("invalid calendar create request")
        client, timezone_name = self._calendar_client()
        env_values = self._runtime_env_values()
        calendar_id = calendar_runtime.resolve_calendar_id(env_file_values=env_values, override=None)
        when_spec = parse_human_calendar_when(
            str(parsed.get("when_text") or ""),
            timezone_name=timezone_name,
            reference_utc=datetime.now(timezone.utc),
        )
        if when_spec["kind"] == "all_day":
            event_spec = calendar_runtime.build_event_payload(
                title=str(parsed["title"]),
                description=None,
                location=None,
                attendees=None,
                start_at=None,
                end_at=None,
                start_date=when_spec["start_date"],
                end_date=None,
                timezone_name=timezone_name,
            )
        else:
            start_at = when_spec["start_at"]
            end_at = self._timed_event_end(
                start_at=start_at,
                duration=parsed.get("duration"),
                default_timezone=timezone_name,
            )
            event_spec = calendar_runtime.build_event_payload(
                title=str(parsed["title"]),
                description=None,
                location=None,
                attendees=None,
                start_at=start_at,
                end_at=end_at,
                start_date=None,
                end_date=None,
                timezone_name=timezone_name,
            )
        event = calendar_runtime.normalize_event(client.create_event(calendar_id, event_spec.payload))
        result = {
            "action": "create_event",
            "status": "scheduled",
            "event_id": event.get("id"),
            "event_html_link": event.get("html_link"),
            "title": event.get("summary"),
        }
        self._refresh_calendar_runtime_status(
            client=client,
            calendar_id=calendar_id,
            timezone_name=timezone_name,
            action="create_event",
            recent_results=[result],
            created_count=1,
        )
        link = str(event.get("html_link") or "").strip()
        suffix = f"\n{link}" if link else ""
        return f"Calendar event created: {format_calendar_event_brief(event, timezone_name)}{suffix}"

    def _handle_calendar_move_from_text(self, text: str) -> str:
        parsed = parse_calendar_move_text(text)
        if not parsed:
            raise ValueError("invalid calendar move request")
        client, timezone_name = self._calendar_client()
        env_values = self._runtime_env_values()
        calendar_id = calendar_runtime.resolve_calendar_id(env_file_values=env_values, override=None)
        events = calendar_runtime.list_upcoming(
            client,
            calendar_id=calendar_id,
            default_timezone=timezone_name,
            limit=30,
            window_days=45,
        )
        matched, candidates = self._match_calendar_event(title=str(parsed["title"]), events=events)
        if matched is None:
            if candidates:
                options = " | ".join(format_calendar_event_brief(item, timezone_name) for item in candidates)
                return f"Multiple calendar matches found. Be more specific: {options}"
            return f"Could not find a future calendar event matching: {parsed['title']}"

        when_spec = parse_human_calendar_when(
            str(parsed.get("when_text") or ""),
            timezone_name=timezone_name,
            reference_utc=datetime.now(timezone.utc),
        )
        payload: dict[str, Any] = {"summary": str(matched.get("summary") or "").strip()}
        if when_spec["kind"] == "all_day":
            payload.update(
                calendar_runtime.build_event_times(
                    start_at=None,
                    end_at=None,
                    start_date=when_spec["start_date"],
                    end_date=None,
                    timezone_name=timezone_name,
                ).payload
            )
        else:
            start_at = when_spec["start_at"]
            duration = parsed.get("duration")
            if duration is None and not matched.get("all_day"):
                start_value = str(matched.get("start_value") or "").strip()
                end_value = str(matched.get("end_value") or "").strip()
                if start_value and end_value:
                    try:
                        duration = calendar_runtime.parse_datetime_text(end_value, timezone_name) - calendar_runtime.parse_datetime_text(
                            start_value, timezone_name
                        )
                    except Exception:
                        duration = None
            end_at = self._timed_event_end(
                start_at=start_at,
                duration=duration,
                default_timezone=timezone_name,
            )
            payload.update(
                calendar_runtime.build_event_times(
                    start_at=start_at,
                    end_at=end_at,
                    start_date=None,
                    end_date=None,
                    timezone_name=timezone_name,
                ).payload
            )

        event = calendar_runtime.normalize_event(
            client.update_event(calendar_id, str(matched.get("id") or ""), payload)
        )
        result = {
            "action": "update_event",
            "status": "scheduled",
            "event_id": event.get("id"),
            "event_html_link": event.get("html_link"),
            "title": event.get("summary"),
        }
        self._refresh_calendar_runtime_status(
            client=client,
            calendar_id=calendar_id,
            timezone_name=timezone_name,
            action="update_event",
            recent_results=[result],
            updated_count=1,
        )
        link = str(event.get("html_link") or "").strip()
        suffix = f"\n{link}" if link else ""
        return f"Calendar event moved: {format_calendar_event_brief(event, timezone_name)}{suffix}"

    def _handle_tasks_list(self, *, filter_kind: str | None = None) -> str:
        try:
            _, client = self._personal_task_client()
            tasks = personal_task_runtime.list_personal_tasks(client, limit=50, filter_text=None)
            today_local = datetime.now(ZoneInfo(self.default_timezone)).date()
            heading = "Open tasks"
            filtered = tasks
            if filter_kind == "due":
                heading = "Tasks with due dates"
                filtered = [task for task in tasks if str(task.get("due_value") or "").strip()]
            elif filter_kind == "today":
                heading = "Tasks due today"
                filtered = [
                    task
                    for task in tasks
                    if task_due_local_date(task, self.default_timezone) == today_local
                ]
            elif filter_kind == "tomorrow":
                heading = "Tasks due tomorrow"
                filtered = [
                    task
                    for task in tasks
                    if task_due_local_date(task, self.default_timezone) == (today_local + timedelta(days=1))
                ]
            elif filter_kind == "overdue":
                heading = "Overdue tasks"
                filtered = [
                    task
                    for task in tasks
                    if (due_date := task_due_local_date(task, self.default_timezone)) is not None and due_date < today_local
                ]
            if not filtered:
                return f"{heading}\n- none"
            lines = [heading]
            for task in filtered[:8]:
                due = str(task.get("due_value") or "").strip() or "-"
                lines.append(f"- {task.get('title')} | due={due}")
            return "\n".join(lines)
        except Exception:
            return "Personal task provider is not configured yet."

    def _handle_reminders_list(self) -> str:
        rows = self.backend._pending_reminders()
        if not rows:
            return "Pending reminders\n- none"
        lines = ["Pending reminders"]
        for row in rows[:8]:
            due = format_dt(str(row.get("remind_at") or ""), self.default_timezone)
            lines.append(f"- {row.get('message')} | {row.get('status')} | {due}")
        return "\n".join(lines)

    def _handle_task_create(self, text: str) -> str:
        parsed = parse_task_create_text(text)
        if not parsed:
            raise ValueError("invalid task create text")
        title, due_string = parsed
        normalized_due = normalize_task_due_text(due_string)
        try:
            result = self.backend.create_personal_task_runtime(
                title=title,
                due_string=normalized_due,
                apply=True,
            )
            recent = ensure_dict(ensure_dict(result.get("status")).get("recent_results", [{}])[0])
            due_note = f" | due={normalized_due}" if normalized_due else ""
            return f"Created personal task: {recent.get('title') or title}{due_note}"
        except RuntimeError as exc:
            text = str(exc)
            lowered = text.lower()
            if "missing required personal task env" in lowered or "missing task provider" in lowered:
                return "Personal task provider is not configured yet."
            return f"Task request failed: {text}"
        except Exception as exc:  # noqa: BLE001
            return f"Task request failed: {exc}"

    def _handle_status(self, *, binding: TelegramChatBinding | None = None) -> str:
        snapshot = self.backend.build_state()
        agent_runtime = ensure_dict(snapshot.get("agent_runtime"))
        activity = ensure_dict(agent_runtime.get("activity"))
        last_route = ensure_dict(activity.get("last_route"))
        recent_routes = [ensure_dict(item) for item in activity.get("recent_routes", []) if isinstance(item, dict)]
        reminders = ensure_dict(snapshot.get("reminders"))
        calendar_runtime_state = ensure_dict(snapshot.get("calendar_runtime"))
        personal_tasks = ensure_dict(snapshot.get("personal_tasks"))
        braindump = ensure_dict(snapshot.get("braindump"))
        workspace = ensure_dict(snapshot.get("workspace"))
        active_binding = binding or self._assistant_binding()
        display_route = last_route
        if str(last_route.get("action") or "").strip() == "status":
            for candidate in reversed(recent_routes[:-1] if recent_routes else []):
                if str(candidate.get("action") or "").strip() != "status":
                    display_route = candidate
                    break
        lines = [
            "OpenClaw status",
            f"- Reminders pending: {ensure_dict(reminders.get('counts')).get('pending', 0)}",
            f"- Reminders awaiting reply: {ensure_dict(reminders.get('counts')).get('awaiting_reply', 0)}",
            f"- Calendar upcoming: {ensure_dict(calendar_runtime_state.get('summary')).get('upcoming_count', 0)}",
            f"- Personal tasks open: {ensure_dict(personal_tasks.get('summary')).get('open_count', 0)}",
            f"- Braindump due: {ensure_dict(braindump.get('counts')).get('due_for_review', 0)}",
            f"- Active projects: {ensure_dict(workspace.get('project_counts')).get('active', 0)}",
            f"- Front door agent: {agent_runtime.get('default_user_facing_agent') or 'assistant'}",
            f"- Current surface: {(active_binding.label + ' -> ' + active_binding.default_agent + '/' + active_binding.default_space) if active_binding else '-'}",
        ]
        if display_route:
            lines.append(
                f"- Last routed work: {display_route.get('agent_id')} -> {display_route.get('space_key')} ({display_route.get('route_mode')})"
            )
            if display_route.get("lane") or display_route.get("provider") or display_route.get("model"):
                lines.append(
                    f"- Last provider route: lane={display_route.get('lane') or '-'} | provider={display_route.get('provider') or '-'} | model={display_route.get('model') or '-'}"
                )
        if active_binding and active_binding.default_agent == "builder":
            builder_status = assistant_chat_runtime.builder_runtime_capability_snapshot(
                root=self.root,
                env_values=self.env_values,
            )
            tools = ensure_dict(builder_status.get("tools"))
            github = ensure_dict(builder_status.get("github"))
            github_auth = ensure_dict(github.get("auth"))
            lines.extend(
                [
                    f"- Builder workbench mode: {ensure_dict(builder_status.get('policy')).get('workbench_mode') or 'repo_task_oriented'}",
                    f"- Builder local tools: codex={'ready' if ensure_dict(tools.get('codex_cli')).get('ready') else 'missing'}, gemini={'ready' if ensure_dict(tools.get('gemini_cli')).get('ready') else 'missing'}, git={'ready' if ensure_dict(tools.get('git')).get('ready') else 'missing'}, gh={'ready' if ensure_dict(tools.get('gh')).get('ready') else 'missing'}",
                    f"- Builder GitHub: source={github.get('credential_source') or 'unconfigured'} | owner={github.get('owner') or '-'} | repo={github.get('repo') or '-'} | token={'set' if github.get('token_configured') else 'missing'} | gh_auth={github_auth.get('status') or '-'} | account={github_auth.get('account') or '-'}",
                ]
            )
        return "\n".join(lines)

    def _format_research_flow_status(self, status: dict[str, Any]) -> str:
        if status.get("available") is not True:
            return "ResearchFlow is not configured."
        lines = [
            "ResearchFlow status",
            f"- Owner: {status.get('owner_agent') or 'researcher'} / {status.get('default_space') or 'research'}",
        ]
        last_run = ensure_dict(status.get("last_run"))
        if last_run:
            lines.append(
                f"- Last run: {last_run.get('workflow') or '-'} @ {last_run.get('executed_at') or '-'}"
            )
        workflows = [ensure_dict(item) for item in status.get("workflows", []) if isinstance(item, dict)]
        for row in workflows:
            name = str(row.get("name") or "-")
            label = str(row.get("output_label") or name).strip() or name
            last_status = ensure_dict(row.get("last_status"))
            artifacts = row.get("artifact_paths") if isinstance(row.get("artifact_paths"), list) else []
            if name == "job_search_digest":
                summary = ensure_dict(last_status.get("summary"))
                lines.append(
                    f"- {label}: processed={summary.get('processed_count', 0)} | recommended={summary.get('recommended_count', 0)} | artifacts={len(artifacts)}"
                )
            elif name == "ai_tools_watch":
                lines.append(
                    f"- {label}: items={last_status.get('item_count', 0)} | delivered={last_status.get('delivered', False)} | artifacts={len(artifacts)}"
                )
            else:
                lines.append(f"- {label}: artifacts={len(artifacts)}")
        return "\n".join(lines)

    def _format_research_flow_run_result(self, status: dict[str, Any]) -> str:
        last_run = ensure_dict(status.get("last_run"))
        workflows = {
            str(row.get("name") or ""): ensure_dict(row)
            for row in status.get("workflows", [])
            if isinstance(row, dict)
        }
        results = [ensure_dict(item) for item in last_run.get("results", []) if isinstance(item, dict)]
        if not results:
            return "ResearchFlow ran, but no workflow results were returned."
        lines = [f"ResearchFlow run complete: {last_run.get('workflow') or '-'}"]
        for row in results:
            workflow_name = str(row.get("workflow") or "-")
            workflow_status = ensure_dict(workflows.get(workflow_name))
            label = str(workflow_status.get("output_label") or workflow_name).strip() or workflow_name
            if row.get("ok") is not True:
                error = str(row.get("stderr") or row.get("stdout") or "workflow failed").strip()
                lines.append(f"- {label}: failed | {error}")
                continue
            payload = ensure_dict(row.get("payload"))
            artifacts = row.get("artifact_paths") if isinstance(row.get("artifact_paths"), list) else []
            preview = str(
                ensure_dict(payload.get("delivery")).get("preview")
                or payload.get("preview")
                or ""
            ).strip()
            if workflow_name == "job_search_digest":
                lines.append(
                    f"- {label}: processed={payload.get('processed_count', 0)} | artifacts={len(artifacts)}"
                )
            elif workflow_name == "ai_tools_watch":
                lines.append(
                    f"- {label}: items={payload.get('item_count', 0)} | artifacts={len(artifacts)}"
                )
            else:
                lines.append(f"- {label}: ok | artifacts={len(artifacts)}")
            if preview:
                lines.append(preview[:800].rstrip())
            if artifacts:
                lines.append("Artifacts:")
                lines.extend(f"- {path}" for path in artifacts[:4])
        return "\n".join(lines)

    def _handle_research_flow_request(self, request: dict[str, Any]) -> str:
        if request.get("action") == "status":
            return self._format_research_flow_status(self.backend._research_flow_status())
        workflow = str(request.get("workflow") or "all").strip() or "all"
        apply = bool(request.get("apply") is True)
        try:
            result = self.backend.run_research_flow_runtime(workflow=workflow, apply=apply)
        except Exception as exc:  # noqa: BLE001
            return f"ResearchFlow failed: {exc}"
        status = ensure_dict(result.get("status"))
        return self._format_research_flow_run_result(status)

    def _morning_briefing_binding(self) -> TelegramChatBinding | None:
        return self._binding_by_id(self.morning_briefing_cfg.binding_id) or self._assistant_binding()

    def _store_morning_briefing_result(
        self,
        state: dict[str, Any],
        *,
        payload: dict[str, Any],
        delivery_kind: str,
        status: str,
    ) -> None:
        briefing = ensure_dict(state.setdefault("morning_briefing", {}))
        briefing.update(
            {
                "enabled": self.morning_briefing_cfg.enabled,
                "binding_id": self.morning_briefing_cfg.binding_id,
                "delivery_time_local": self.morning_briefing_cfg.delivery_time_local,
                "timezone": self.morning_briefing_cfg.timezone_name,
                "max_schedule_suggestions": self.morning_briefing_cfg.max_schedule_suggestions,
                "last_delivery_kind": delivery_kind,
                "last_status": status,
                "last_message_preview": " ".join(str(payload.get("text") or "").split())[:220] or None,
                "last_summary": ensure_dict(payload.get("summary")),
            }
        )
        if status == "sent":
            briefing["last_sent_at"] = str(payload.get("generated_at") or "").strip() or short_now_iso()
            briefing["last_sent_local_date"] = str(payload.get("local_date") or "").strip() or None

    def _briefing_calendar_state(self, *, current: datetime) -> dict[str, Any]:
        timezone_name = self.default_timezone
        calendar_status = self.backend._calendar_runtime_status()
        upcoming_events = [ensure_dict(item) for item in calendar_status.get("upcoming_events", []) if isinstance(item, dict)]
        try:
            client, timezone_name = self._calendar_client()
            env_values = self._runtime_env_values()
            calendar_id = calendar_runtime.resolve_calendar_id(env_file_values=env_values, override=None)
            upcoming_events = calendar_runtime.list_upcoming(
                client,
                calendar_id=calendar_id,
                default_timezone=timezone_name,
                limit=20,
                window_days=7,
            )
            self._refresh_calendar_runtime_status(
                client=client,
                calendar_id=calendar_id,
                timezone_name=timezone_name,
                action="snapshot",
                recent_results=[],
            )
            calendar_status = self.backend._calendar_runtime_status()
        except Exception:
            pass

        today_local = current.astimezone(ZoneInfo(timezone_name)).date()
        today_events = [row for row in upcoming_events if event_local_date(row, timezone_name) == today_local]
        return {
            "available": bool(calendar_status.get("available")) or bool(upcoming_events),
            "timezone": timezone_name,
            "today_events": today_events,
            "upcoming_events": upcoming_events,
            "summary": ensure_dict(calendar_status.get("summary")),
        }

    def _briefing_personal_tasks_status(self) -> dict[str, Any]:
        status = self.backend._personal_task_runtime_status()
        try:
            self.backend.sync_personal_tasks_runtime()
            status = self.backend._personal_task_runtime_status()
        except Exception:
            pass
        return status

    def _build_morning_briefing_payload(self, *, current: datetime | None = None) -> dict[str, Any]:
        now_utc = current or datetime.now(timezone.utc)
        timezone_name = self.morning_briefing_cfg.timezone_name or self.default_timezone
        local_now = now_utc.astimezone(ZoneInfo(timezone_name))
        today_local = local_now.date()

        reminders = self.backend._pending_reminders()
        reminders_today = [row for row in reminders if reminder_local_date(row, timezone_name) == today_local]
        reminders_overdue = [
            row
            for row in reminders
            if (due_date := reminder_local_date(row, timezone_name)) is not None and due_date < today_local
        ]

        calendar_state = self._briefing_calendar_state(current=now_utc)
        calendar_timezone = str(calendar_state.get("timezone") or timezone_name).strip() or timezone_name
        today_events = [ensure_dict(item) for item in calendar_state.get("today_events", []) if isinstance(item, dict)]

        personal_status = self._briefing_personal_tasks_status()
        personal_tasks = [ensure_dict(item) for item in personal_status.get("tasks", []) if isinstance(item, dict)]
        tasks_due_today = [
            row for row in personal_tasks if task_due_bucket(row, timezone_name=timezone_name, today_local=today_local) == "today"
        ]
        tasks_overdue = [
            row for row in personal_tasks if task_due_bucket(row, timezone_name=timezone_name, today_local=today_local) == "overdue"
        ]

        gmail_status = self.backend._gmail_inbox_status()
        manual_review_open = int(gmail_status.get("manual_review_open", 0) or 0)
        calendar_candidates = self.backend._calendar_candidates()
        open_candidates = [
            ensure_dict(item)
            for item in calendar_candidates.get("items", [])
            if isinstance(item, dict) and str(ensure_dict(item).get("status") or "proposed") in OPEN_CALENDAR_CANDIDATE_STATUSES
        ]

        suggestions: list[str] = []
        schedule_note = (
            "I do not see a matching calendar block yet."
            if calendar_state.get("available")
            else "Consider blocking time for it today."
        )
        for task in tasks_overdue + tasks_due_today:
            if title_has_calendar_match(str(task.get("title") or ""), today_events):
                continue
            due_date = task_due_local_date(task, timezone_name)
            if due_date is not None and due_date < today_local:
                due_label = f"overdue from {due_date.isoformat()}"
            else:
                due_label = "due today"
            suggestions.append(f"{task.get('title')}: {due_label}. {schedule_note}")
            if len(suggestions) >= self.morning_briefing_cfg.max_schedule_suggestions:
                break

        if len(suggestions) < self.morning_briefing_cfg.max_schedule_suggestions:
            for candidate in open_candidates:
                title = str(candidate.get("title") or candidate.get("summary") or "").strip() or "(untitled candidate)"
                status = str(candidate.get("status") or "proposed").strip() or "proposed"
                if status == "needs_details":
                    suggestions.append(f"{title}: it is in calendar candidates and still needs timing details.")
                else:
                    suggestions.append(f"{title}: it is in calendar candidates and still needs a real calendar slot.")
                if len(suggestions) >= self.morning_briefing_cfg.max_schedule_suggestions:
                    break

        calendar_count = len(today_events)
        task_pressure = len(tasks_due_today) + len(tasks_overdue)
        reminder_pressure = len(reminders_today) + len(reminders_overdue)
        headline = (
            f"Today looks like {calendar_count} calendar item{'s' if calendar_count != 1 else ''}, "
            f"{task_pressure} due or overdue task{'s' if task_pressure != 1 else ''}, "
            f"{reminder_pressure} active reminder{'s' if reminder_pressure != 1 else ''}"
        )
        if gmail_status.get("available"):
            headline += f", and {manual_review_open} Gmail review item{'s' if manual_review_open != 1 else ''}"
        headline += "."

        greeting = "Good morning." if local_now.hour < 12 else "Here is today's briefing."
        lines = [
            f"{greeting} {local_now.strftime('%A %Y-%m-%d')}.",
            headline,
            "",
            "Calendar:",
        ]
        if today_events:
            lines.extend(f"- {format_calendar_event_brief(event, calendar_timezone)}" for event in today_events[:6])
        elif calendar_state.get("available"):
            lines.append("- Your calendar is still open today.")
        else:
            lines.append("- Calendar is not configured yet.")

        lines.extend(["", "Tasks:"])
        if not personal_status.get("available"):
            lines.append("- Personal tasks are not configured yet.")
        elif not tasks_due_today and not tasks_overdue:
            lines.append("- No personal tasks are due today.")
        else:
            for task in tasks_overdue[:3]:
                due = str(task.get("due_value") or task.get("due_string") or "-")
                lines.append(f"- Overdue: {task.get('title')} | due={due}")
            for task in tasks_due_today[:3]:
                due = str(task.get("due_value") or task.get("due_string") or "-")
                lines.append(f"- Due today: {task.get('title')} | due={due}")

        lines.extend(["", "Reminders:"])
        if not reminders_today and not reminders_overdue:
            lines.append("- No active reminders are due today.")
        else:
            for reminder in reminders_overdue[:3]:
                lines.append(f"- Overdue: {reminder.get('message')} | {format_dt(str(reminder.get('remind_at') or ''), timezone_name)}")
            for reminder in reminders_today[:3]:
                lines.append(f"- Today: {reminder.get('message')} | {format_dt(str(reminder.get('remind_at') or ''), timezone_name)}")

        lines.extend(["", "Inbox:"])
        if gmail_status.get("available"):
            if manual_review_open:
                lines.append(f"- {manual_review_open} Gmail item(s) still need assistant review.")
            else:
                lines.append("- Gmail manual-review queue is clear.")
        else:
            lines.append("- Gmail inbox triage snapshot is not available yet.")
        if open_candidates:
            for candidate in open_candidates[:2]:
                lines.append(
                    f"- Calendar candidate: {candidate.get('title') or candidate.get('summary') or '(untitled)'} | status={candidate.get('status') or 'proposed'}"
                )
        elif calendar_candidates.get("available"):
            lines.append("- No open calendar candidates are waiting on the assistant.")

        lines.extend(["", "Things you should probably schedule:"])
        if suggestions:
            lines.extend(f"- {item}" for item in suggestions[: self.morning_briefing_cfg.max_schedule_suggestions])
        else:
            lines.append("- Nothing obvious still needs a calendar slot right now.")

        summary = {
            "calendar_events_today": calendar_count,
            "tasks_due_today": len(tasks_due_today),
            "tasks_overdue": len(tasks_overdue),
            "reminders_today": len(reminders_today),
            "reminders_overdue": len(reminders_overdue),
            "gmail_manual_review_open": manual_review_open,
            "calendar_candidates_open": len(open_candidates),
            "schedule_suggestions": min(len(suggestions), self.morning_briefing_cfg.max_schedule_suggestions),
        }
        return {
            "text": "\n".join(lines).strip(),
            "summary": summary,
            "generated_at": now_utc.isoformat(timespec="seconds"),
            "local_date": today_local.isoformat(),
            "timezone": timezone_name,
        }

    def _handle_morning_briefing_request(self, *, state: dict[str, Any]) -> str:
        payload = self._build_morning_briefing_payload()
        self._store_morning_briefing_result(state, payload=payload, delivery_kind="manual", status="sent")
        return str(payload.get("text") or "").strip()

    def maybe_send_morning_briefing(self, *, state: dict[str, Any], current: datetime | None = None) -> int:
        if not self.morning_briefing_cfg.enabled:
            return 0
        binding = self._morning_briefing_binding()
        schedule_clock = parse_hhmm(self.morning_briefing_cfg.delivery_time_local)
        if binding is None or schedule_clock is None:
            return 0

        now_utc = current or datetime.now(timezone.utc)
        zone = ZoneInfo(self.morning_briefing_cfg.timezone_name)
        now_local = now_utc.astimezone(zone)
        already_sent = str(ensure_dict(state.get("morning_briefing")).get("last_sent_local_date") or "").strip()
        if already_sent == now_local.date().isoformat():
            return 0

        due_local = datetime.combine(now_local.date(), datetime.min.time(), tzinfo=zone).replace(
            hour=schedule_clock[0],
            minute=schedule_clock[1],
        )
        if now_local < due_local:
            return 0

        payload = self._build_morning_briefing_payload(current=now_utc)
        try:
            self._send_text(chat_id=binding.chat_id, text=str(payload.get("text") or ""))
        except Exception:
            self._store_morning_briefing_result(state, payload=payload, delivery_kind="scheduled", status="error")
            return 0

        self._store_morning_briefing_result(state, payload=payload, delivery_kind="scheduled", status="sent")
        self._record_agent_activity(
            agent_id="assistant",
            space_key="general",
            action="morning_briefing_auto",
            route_mode="scheduled_delivery",
            lane="L0_no_model",
        )
        return 1

    def _route_for_conversation(self, *, text: str, state: dict[str, Any], binding: TelegramChatBinding) -> dict[str, Any]:
        route = self.backend.route_text_to_space(text=text)
        if route.get("explicit_agent") or route.get("explicit_space"):
            return route
        registry = self.backend._agent_runtime_snapshot()
        catalog = {
            str(item.get("key")): ensure_dict(item)
            for item in ensure_dict(registry.get("space_registry")).get("catalog", [])
            if isinstance(item, dict)
        }
        role_lookup = {
            str(item.get("id")): ensure_dict(item)
            for item in registry.get("visible_agents", []) + registry.get("internal_roles", [])
            if isinstance(item, dict)
        }

        def apply_agent_space(agent_id: str, space_key: str, route_mode: str) -> dict[str, Any]:
            updated = dict(route)
            updated["agent_id"] = agent_id
            updated["agent"] = ensure_dict(role_lookup.get(agent_id)) or None
            updated["space_key"] = space_key
            updated["route_mode"] = route_mode
            if updated.get("kind") != "project":
                catalog_row = ensure_dict(catalog.get(space_key))
                updated["space"] = {
                    "id": None,
                    "key": space_key,
                    "kind": "core",
                    "project_id": None,
                    "name": catalog_row.get("name") or self.backend._display_label(space_key),
                    "session_strategy": catalog_row.get("session_strategy") or "shared_session",
                    "agent_strategy": catalog_row.get("agent_strategy") or "coordinator_only",
                    "entry_command_hint": catalog_row.get("entry_command_hint")
                    or self.backend._space_entry_command_hint(space_key),
                }
            return updated

        if route.get("kind") == "project" and route.get("resolved"):
            agent_id = binding.default_agent
            if agent_id == "assistant":
                focus = self._conversation_focus(state)
                focused_agent = str(focus.get("agent_id") or "assistant").strip() or "assistant"
                if focused_agent != "assistant":
                    agent_id = focused_agent
            if agent_id != "assistant":
                route_mode = "focus_project" if binding.default_agent == "assistant" else "bound_project"
                return apply_agent_space(agent_id, str(route.get("space_key") or "general"), route_mode)
            inferred = infer_natural_agent(text) if binding.allows("cross_agent_routing") else None
            if inferred is not None:
                return apply_agent_space(inferred[0], str(route.get("space_key") or "general"), "natural_project")
            return route

        inferred = infer_natural_agent(text) if binding.allows("cross_agent_routing") else None
        if inferred is not None:
            return apply_agent_space(inferred[0], inferred[1], "natural_intent")

        if binding.default_agent == "assistant":
            focus = self._conversation_focus(state)
            focused_agent = str(focus.get("agent_id") or "assistant").strip() or "assistant"
            if focused_agent != "assistant":
                return apply_agent_space(focused_agent, str(focus.get("space_key") or "general"), "focus_mode")

        if binding.default_agent != "assistant":
            return apply_agent_space(binding.default_agent, binding.default_space, "bound_chat")
        return route

    def _handle_fitness_command(self, text: str, *, explicit_context: bool, route_mode: str | None = None) -> str:
        translated = translate_natural_fitness_text(text)
        command_text = translated or text
        if not fitness_runtime.supports_command_text(command_text, explicit_context=explicit_context):
            return (
                "Fitness Coach supports `workout today`, `start workout`, `log ...`, `finish workout`, "
                "and `set barbell empty <kg>kg`."
            )
        try:
            result = self.fitness_runtime.execute_text(command_text)
        except Exception as exc:  # noqa: BLE001
            return f"Fitness Coach failed: {exc}"

        reply_text = str(result.get("reply_text") or "").strip() or "Fitness command applied."
        self._record_agent_activity(
            agent_id="fitness_coach",
            space_key="fitness",
            action="fitness_command",
            text=text,
            route_mode=route_mode or ("explicit_specialist" if explicit_context else "command_match"),
            lane="L0_no_model",
        )
        return reply_text

    def _handle_project_capture(self, text: str, route: dict[str, Any]) -> str:
        task = self._create_task_from_route(text=text, route=route)
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

    def _create_task_from_route(self, *, text: str, route: dict[str, Any]) -> dict[str, Any]:
        stripped = str(route.get("stripped_text") or text).strip()
        if not stripped:
            raise ValueError("routed task text is required")
        agent_id = str(route.get("agent_id") or "assistant").strip().lower() or "assistant"
        notes_parts = [
            "Captured from telegram",
            f"agent={agent_id}",
            f"space={route.get('space_key')}",
        ]
        if route.get("project_name"):
            notes_parts.append(f"project={route.get('project_name')}")
        task = self.backend.create_task(
            title=stripped,
            assignees=[agent_id],
            project_id=str(route.get("project_id") or "").strip() or None,
            notes=" | ".join(notes_parts),
            source="telegram",
            assign_default_project=False,
        )
        self._record_agent_activity(
            agent_id=agent_id,
            space_key=str(route.get("space_key") or "general"),
            action="captured_request",
            text=stripped,
            route_mode=str(route.get("route_mode") or "default_front_door"),
            lane=str(ensure_dict(route.get("agent")).get("default_lane") or "").strip() or None,
        )
        return task

    def _handle_specialist_capture(self, text: str, route: dict[str, Any]) -> str:
        try:
            task = self._create_task_from_route(text=text, route=route)
        except ValueError as exc:
            if route.get("kind") == "project" and route.get("matched") and not route.get("resolved"):
                return self._format_unknown_project_route(route)
            raise exc
        agent = ensure_dict(route.get("agent"))
        label = str(agent.get("label", route.get("agent_id", "assistant"))).strip() or "assistant"
        space_key = str(route.get("space_key") or "general").strip()
        project_note = (
            f" in project {route.get('project_name')}"
            if str(route.get("project_name") or "").strip()
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
        binding = self._binding_for_chat(chat_id)
        if not chat_id or binding is None:
            return []

        text = str(event.get("text") or "").strip()
        if not text:
            return []

        focus_instruction = detect_focus_instruction(text) if binding.default_agent == "assistant" else None
        if focus_instruction is not None:
            return [self._handle_focus_instruction(state, focus_instruction)]

        route = self._route_for_conversation(text=text, state=state, binding=binding)
        routed_text = str(route.get("stripped_text") or "").strip() or text.strip()
        explicit_specialist = bool(route.get("explicit_agent")) and str(route.get("agent_id")) != "assistant"
        explicit_assistant_space = bool(route.get("explicit_space")) and str(route.get("agent_id")) == "assistant"
        agent_id = str(route.get("agent_id") or "assistant").strip() or "assistant"
        route_space = str(route.get("space_key") or "general").strip() or "general"
        reminders_allowed = binding.allows("reminders") or (explicit_assistant_space and route_space == "reminders")
        tasks_allowed = binding.allows("tasks") or (explicit_assistant_space and route_space == "tasks")
        calendar_allowed = binding.allows("calendar") or (explicit_assistant_space and route_space == "calendar")
        braindump_allowed = binding.allows("braindump") or (explicit_assistant_space and route_space == "braindump")
        fitness_allowed = binding.allows("fitness") or agent_id == "fitness_coach"

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
            return [self._handle_status(binding=binding)]

        if (binding.default_agent == "assistant" or str(route.get("agent_id") or "assistant") == "assistant") and is_day_briefing_request(routed_text):
            self._record_agent_activity(
                agent_id="assistant",
                space_key="general",
                action="morning_briefing",
                text=routed_text,
                route_mode=str(route.get("route_mode") or "default_front_door"),
                lane="L0_no_model",
            )
            return [self._handle_morning_briefing_request(state=state)]

        research_flow_request = parse_research_flow_request(routed_text, command_name=command_name, body=body)
        if research_flow_request is not None and (
            agent_id == "researcher"
            or route_space in {"research", "job-search"}
            or binding.default_agent == "researcher"
        ):
            self._record_agent_activity(
                agent_id="researcher",
                space_key=route_space if route_space in {"research", "job-search"} else "research",
                action="research_flow_status" if research_flow_request.get("action") == "status" else "research_flow_run",
                text=routed_text,
                route_mode=str(route.get("route_mode") or "default_front_door"),
                lane="L0_no_model",
            )
            return [self._handle_research_flow_request(research_flow_request)]

        translated_fitness = translate_natural_fitness_text(routed_text) if fitness_allowed else None
        if fitness_allowed and (translated_fitness or fitness_runtime.supports_command_text(routed_text, explicit_context=False)):
            return [
                self._handle_fitness_command(
                    translated_fitness or routed_text,
                    explicit_context=False,
                    route_mode=(
                        "natural_fitness" if translated_fitness else str(route.get("route_mode") or "command_match")
                    ),
                )
            ]

        if explicit_specialist:
            if route.get("kind") == "project" and not route.get("resolved"):
                return [self._format_unknown_project_route(route)]
            if agent_id == "fitness_coach":
                if fitness_runtime.supports_command_text(routed_text, explicit_context=True):
                    return [
                        self._handle_fitness_command(
                            routed_text,
                            explicit_context=True,
                            route_mode=str(route.get("route_mode") or "explicit_specialist"),
                        )
                    ]
                return [self._handle_agent_chat(agent_id=agent_id, text=routed_text, route=route)]
            if agent_id in CONVERSATIONAL_SPECIALISTS:
                return [self._handle_agent_chat(agent_id=agent_id, text=routed_text, route=route)]
            return [self._handle_specialist_capture(text, route)]

        if calendar_allowed and parse_calendar_move_text(routed_text):
            self._record_agent_activity(
                agent_id="assistant",
                space_key="calendar",
                action="calendar_move",
                text=routed_text,
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_calendar_move_from_text(routed_text)]

        if calendar_allowed and parse_calendar_create_text(routed_text):
            self._record_agent_activity(
                agent_id="assistant",
                space_key="calendar",
                action="calendar_create",
                text=routed_text,
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_calendar_create_from_text(routed_text)]

        if calendar_allowed and command_name == "calendar":
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

        if calendar_allowed and is_calendar_today_request(routed_text):
            self._record_agent_activity(
                agent_id="assistant",
                space_key="calendar",
                action="calendar_today",
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_calendar_today()]
        if calendar_allowed and is_calendar_tomorrow_request(routed_text):
            self._record_agent_activity(
                agent_id="assistant",
                space_key="calendar",
                action="calendar_tomorrow",
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_calendar_tomorrow()]
        if calendar_allowed and is_calendar_next_request(routed_text):
            self._record_agent_activity(
                agent_id="assistant",
                space_key="calendar",
                action="calendar_next",
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_calendar_next()]

        task_list_kind = classify_task_list_request(routed_text) if tasks_allowed else None
        if tasks_allowed and (command_name == "tasks" or task_list_kind is not None):
            self._record_agent_activity(
                agent_id="assistant",
                space_key="tasks",
                action="tasks_list",
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_tasks_list(filter_kind=task_list_kind)]

        if reminders_allowed and is_reminder_list_request(routed_text):
            self._record_agent_activity(
                agent_id="assistant",
                space_key="reminders",
                action="reminders_list",
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_reminders_list()]

        if tasks_allowed and command_name in {"task", "add-task"}:
            self._record_agent_activity(
                agent_id="assistant",
                space_key="tasks",
                action="task_create",
                text=body,
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_task_create(f"task {body}")]

        if tasks_allowed and parse_task_create_text(routed_text):
            self._record_agent_activity(
                agent_id="assistant",
                space_key="tasks",
                action="task_create",
                text=routed_text,
                route_mode=str(route.get("route_mode") or "default_front_door"),
            )
            return [self._handle_task_create(routed_text)]

        natural_braindump = parse_natural_braindump_text(routed_text) if braindump_allowed else None
        if natural_braindump is not None:
            category, body = natural_braindump
            result = self.backend.create_braindump_item(
                category=category,
                text=body,
                source="telegram",
            )
            item = ensure_dict(result.get("item"))
            self._record_agent_activity(
                agent_id="assistant",
                space_key="braindump",
                action="braindump_capture",
                text=body,
                route_mode="natural_braindump",
            )
            return [f"Braindump captured: [{item.get('category')}] {item.get('short_text')}"]

        try:
            if not braindump_allowed:
                raise ValueError("braindump disabled for this chat surface")
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
        if reminders_allowed and reply_candidate[0] != "ignore":
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

        if reminders_allowed and reminder_sm.parse_create_text(routed_text):
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
            return [self._handle_project_capture(text, route)]

        if agent_id != "assistant":
            if agent_id in CONVERSATIONAL_SPECIALISTS:
                return [self._handle_agent_chat(agent_id=agent_id, text=routed_text, route=route)]
            return [self._handle_specialist_capture(text, route)]

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
            if self._binding_for_chat(chat_id) is None:
                state["last_update_id"] = max(int(state.get("last_update_id") or 0), update_id)
                continue
            try:
                responses = self.handle_message(message, state=state)
            except Exception as exc:  # noqa: BLE001
                responses = [f"Request failed: {exc}"]
            for response in responses:
                self._send_text(chat_id=chat_id, text=response)
            state["last_update_id"] = max(int(state.get("last_update_id") or 0), update_id)
            handled += 1
        self.save_adapter_state(state)
        return handled

    def poll_once(self, *, timeout: int) -> dict[str, Any]:
        state = self.load_adapter_state()
        offset = int(state.get("last_update_id") or 0) + 1
        updates = self.client.get_updates(offset=offset, timeout=timeout)
        processed = self.process_updates(updates, state=state)
        reminder_chat_id = self._reminder_chat_id()
        due_sent = self.scan_and_dispatch_due_reminders(state=state, chat_id=reminder_chat_id) if reminder_chat_id else 0
        briefing_sent = self.maybe_send_morning_briefing(state=state)
        self.save_adapter_state(state)
        return {
            "ok": True,
            "processed_updates": processed,
            "due_messages_sent": due_sent,
            "morning_briefings_sent": briefing_sent,
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
    if not token:
        raise RuntimeError("missing TELEGRAM_BOT_TOKEN")
    chat_bindings, default_binding_id = resolve_chat_bindings(root, env_values)
    if not chat_bindings:
        raise RuntimeError("missing Telegram chat binding configuration")
    telegram_cfg = ensure_dict(ensure_dict(load_yaml_dict(root / "config" / "channels.yaml").get("channels")).get("telegram"))
    reminder_binding_id = str(telegram_cfg.get("reminder_binding") or default_binding_id).strip() or default_binding_id
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
        chat_bindings=chat_bindings,
        default_binding_id=default_binding_id,
        reminder_binding_id=reminder_binding_id,
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
