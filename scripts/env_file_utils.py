#!/usr/bin/env python3
"""Shared dotenv-style env file parsing and normalization helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path


SAFE_UNQUOTED_RE = re.compile(r"^[A-Za-z0-9_./:@%+=,-]+$")
VALID_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def strip_matching_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'")):
        return text[1:-1]
    return text


def parse_env_text(text: str, *, strict: bool = True) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            if strict:
                raise ValueError(f"invalid env line {line_no}: missing '='")
            continue

        key, value = line.split("=", 1)
        clean_key = key.strip()
        if not VALID_ENV_KEY_RE.fullmatch(clean_key):
            if strict:
                raise ValueError(f"invalid env key on line {line_no}: {clean_key}")
            continue

        clean_value = strip_matching_quotes(value)
        if "\n" in clean_value or "\r" in clean_value:
            if strict:
                raise ValueError(f"invalid env value on line {line_no}: multiline values are not supported")
            clean_value = clean_value.replace("\n", "").replace("\r", "")
        values[clean_key] = clean_value
    return values


def load_env_file(path: Path, *, strict: bool = True) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"env file not found: {path}")
    return parse_env_text(path.read_text(encoding="utf-8"), strict=strict)


def quote_env_value(value: str) -> str:
    if SAFE_UNQUOTED_RE.fullmatch(value):
        return value
    return json.dumps(value)


def dump_env_text(
    values: dict[str, str],
    *,
    sort_keys: bool = True,
    header_comment: str | None = None,
) -> str:
    keys = sorted(values) if sort_keys else list(values.keys())
    lines: list[str] = []
    if header_comment:
        lines.append(f"# {header_comment}")
    for key in keys:
        clean_key = key.strip()
        if not VALID_ENV_KEY_RE.fullmatch(clean_key):
            raise ValueError(f"invalid env key for output: {clean_key}")
        raw_value = str(values[key])
        if "\n" in raw_value or "\r" in raw_value:
            raise ValueError(f"multiline env values are not supported: {clean_key}")
        lines.append(f"{clean_key}={quote_env_value(raw_value)}")
    return "\n".join(lines) + "\n"


def normalize_env_file(
    source: Path,
    *,
    target: Path | None = None,
    sort_keys: bool = True,
    header_comment: str | None = None,
) -> Path:
    values = load_env_file(source, strict=True)
    output_path = target or source
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        dump_env_text(values, sort_keys=sort_keys, header_comment=header_comment),
        encoding="utf-8",
    )
    return output_path
