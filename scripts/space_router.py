#!/usr/bin/env python3
"""Route inbound text into canonical spaces and project spaces."""

from __future__ import annotations

import re
from typing import Any


SPACE_HINT_RE = re.compile(r"^\[(?P<hint>[^\]]+)\]\s*(?P<body>.*)$")
PREFIX_RE = re.compile(r"^(?P<prefix>[a-z][a-z0-9_-]*)\s*:\s*(?P<body>.+)$", re.IGNORECASE)

PREFIX_ROUTES: dict[str, dict[str, str]] = {
    "assistant": {"agent_id": "assistant", "space_key": "general"},
    "general": {"agent_id": "assistant", "space_key": "general"},
    "reminder": {"agent_id": "assistant", "space_key": "reminders"},
    "reminders": {"agent_id": "assistant", "space_key": "reminders"},
    "calendar": {"agent_id": "assistant", "space_key": "calendar"},
    "task": {"agent_id": "assistant", "space_key": "tasks"},
    "tasks": {"agent_id": "assistant", "space_key": "tasks"},
    "todo": {"agent_id": "assistant", "space_key": "tasks"},
    "braindump": {"agent_id": "assistant", "space_key": "braindump"},
    "notes": {"agent_id": "assistant", "space_key": "braindump"},
    "research": {"agent_id": "researcher", "space_key": "research"},
    "job": {"agent_id": "researcher", "space_key": "job-search"},
    "job-search": {"agent_id": "researcher", "space_key": "job-search"},
    "fitness": {"agent_id": "fitness_coach", "space_key": "fitness"},
    "coding": {"agent_id": "builder", "space_key": "coding"},
    "build": {"agent_id": "builder", "space_key": "coding"},
    "ops": {"agent_id": "ops_guard", "space_key": "ops"},
}

SPACE_DEFAULT_AGENTS: dict[str, str] = {
    row["space_key"]: row["agent_id"] for row in PREFIX_ROUTES.values()
}
SPACE_DEFAULT_AGENTS.setdefault("general", "assistant")


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned.strip("-")


def _parse_prefix(text: str) -> tuple[dict[str, Any] | None, str]:
    clean_text = text.strip()
    match = PREFIX_RE.match(clean_text)
    if not match:
        return None, clean_text

    prefix = match.group("prefix").strip().lower()
    route = PREFIX_ROUTES.get(prefix)
    if route is None:
        return None, clean_text

    return (
        {
            "prefix": prefix,
            "agent_id": route["agent_id"],
            "space_key": route["space_key"],
        },
        match.group("body").strip(),
    )


def _parse_bracket_hint(text: str) -> dict[str, Any]:
    clean_text = text.strip()
    match = SPACE_HINT_RE.match(clean_text)
    if not match:
        return {
            "matched": False,
            "raw_hint": None,
            "space_key": None,
            "kind": None,
            "project_slug": None,
            "stripped_text": clean_text,
        }

    raw_hint = match.group("hint").strip()
    hint = raw_hint.lower().strip()
    body = match.group("body").strip()

    if hint.startswith("project:"):
        project_slug = slugify(hint.split(":", 1)[1])
        return {
            "matched": True,
            "raw_hint": raw_hint,
            "space_key": f"projects/{project_slug}",
            "kind": "project",
            "project_slug": project_slug,
            "stripped_text": body,
        }

    if hint.startswith("project/") or hint.startswith("projects/"):
        project_slug = slugify(hint.split("/", 1)[1])
        return {
            "matched": True,
            "raw_hint": raw_hint,
            "space_key": f"projects/{project_slug}",
            "kind": "project",
            "project_slug": project_slug,
            "stripped_text": body,
        }

    mapped = PREFIX_ROUTES.get(hint)
    if mapped is not None:
        return {
            "matched": True,
            "raw_hint": raw_hint,
            "space_key": mapped["space_key"],
            "kind": "core",
            "project_slug": None,
            "stripped_text": body,
            "hint_agent_id": mapped["agent_id"],
        }

    return {
        "matched": True,
        "raw_hint": raw_hint,
        "space_key": hint,
        "kind": "core",
        "project_slug": None,
        "stripped_text": body,
    }


def parse_space_hint(text: str, *, default_agent: str = "assistant") -> dict[str, Any]:
    prefix_route, remainder = _parse_prefix(text)
    bracket = _parse_bracket_hint(remainder)

    if bracket["matched"]:
        kind = str(bracket.get("kind") or "core")
        space_key = str(bracket.get("space_key") or "") or "general"
        stripped_text = str(bracket.get("stripped_text") or "").strip()
        project_slug = bracket.get("project_slug")
        raw_hint = bracket.get("raw_hint")
    else:
        kind = "core"
        space_key = prefix_route["space_key"] if prefix_route is not None else "general"
        stripped_text = remainder.strip()
        project_slug = None
        raw_hint = prefix_route["prefix"] if prefix_route is not None else None

    if prefix_route is not None:
        agent_id = prefix_route["agent_id"]
        agent_source = "prefix"
    elif bracket.get("hint_agent_id"):
        agent_id = str(bracket.get("hint_agent_id"))
        agent_source = "space_alias"
    else:
        agent_id = default_agent
        agent_source = "default"

    return {
        "matched": bool(prefix_route is not None or bracket["matched"]),
        "raw_hint": raw_hint,
        "prefix": prefix_route["prefix"] if prefix_route is not None else None,
        "explicit_agent": prefix_route is not None,
        "explicit_space": bool(prefix_route is not None or bracket["matched"]),
        "agent_id": agent_id,
        "agent_source": agent_source,
        "space_key": space_key,
        "kind": kind,
        "project_slug": project_slug,
        "stripped_text": stripped_text,
    }


def route_text(
    text: str,
    project_spaces: list[dict[str, Any]],
    *,
    default_agent: str = "assistant",
) -> dict[str, Any]:
    parsed = parse_space_hint(text, default_agent=default_agent)
    if parsed["kind"] != "project":
        return {
            **parsed,
            "resolved": True,
            "space_id": None,
            "project_id": None,
            "project_name": None,
        }

    for row in project_spaces:
        space_key = str(row.get("key", "")).strip()
        if space_key == parsed["space_key"]:
            return {
                **parsed,
                "resolved": True,
                "space_id": row.get("id"),
                "project_id": row.get("project_id"),
                "project_name": row.get("name"),
            }

    return {
        **parsed,
        "resolved": False,
        "space_id": None,
        "project_id": None,
        "project_name": None,
    }


if __name__ == "__main__":
    raise SystemExit("Use as a library module.")
