#!/usr/bin/env python3
"""Route inbound text into canonical spaces and project spaces."""

from __future__ import annotations

import re
from typing import Any


SPACE_HINT_RE = re.compile(r"^\[(?P<hint>[^\]]+)\]\s*(?P<body>.*)$")


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned.strip("-")


def parse_space_hint(text: str) -> dict[str, Any]:
    clean_text = text.strip()
    match = SPACE_HINT_RE.match(clean_text)
    if not match:
        return {
            "matched": False,
            "raw_hint": None,
            "space_key": "main",
            "kind": "main",
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

    return {
        "matched": True,
        "raw_hint": raw_hint,
        "space_key": hint,
        "kind": hint,
        "project_slug": None,
        "stripped_text": body,
    }


def route_text(text: str, project_spaces: list[dict[str, Any]]) -> dict[str, Any]:
    parsed = parse_space_hint(text)
    if parsed["kind"] != "project":
        return {
            **parsed,
            "resolved": True,
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
