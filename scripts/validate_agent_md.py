#!/usr/bin/env python3
"""Validate agent markdown baseline files in a workspace."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "agent_md_baseline.yaml"
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")


def _parse_with_python_yaml(path: Path) -> Any:
    import yaml  # type: ignore

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_with_ruby_yaml(path: Path) -> Any:
    ruby_cmd = [
        "ruby",
        "-ryaml",
        "-rjson",
        "-e",
        (
            "obj = YAML.safe_load(File.read(ARGV[0]), permitted_classes: [], aliases: true); "
            "puts JSON.generate(obj)"
        ),
        str(path),
    ]
    proc = subprocess.run(ruby_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ruby YAML parser failed")
    return json.loads(proc.stdout)


def load_yaml(path: Path) -> Any:
    try:
        return _parse_with_python_yaml(path)
    except Exception:
        return _parse_with_ruby_yaml(path)


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def ensure_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def extract_h2_headings(text: str) -> set[str]:
    headings: set[str] = set()
    for line in text.splitlines():
        match = HEADING_RE.match(line.strip())
        if match:
            headings.add(match.group(1))
    return headings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate agent markdown baseline files")
    parser.add_argument("--target", default=str(ROOT / "baselines" / "agent_md"), help="target workspace path")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="baseline config file")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    config_path = Path(args.config).resolve()

    if not config_path.exists():
        print(f"Config not found: {config_path}")
        return 1
    if not target.exists():
        print(f"Target not found: {target}")
        return 1

    cfg = ensure_dict(load_yaml(config_path))
    baseline = ensure_dict(cfg.get("baseline"))
    required_files = ensure_string_list(baseline.get("required_files"))
    required_headings_cfg = ensure_dict(baseline.get("required_headings"))
    max_lines_cfg = ensure_dict(baseline.get("max_lines"))

    errors: list[str] = []
    warnings: list[str] = []

    for rel_path in required_files:
        path = target / rel_path
        if not path.exists():
            errors.append(f"missing required file: {rel_path}")
            continue

        if path.suffix.lower() != ".md":
            continue

        text = path.read_text(encoding="utf-8")
        headings = extract_h2_headings(text)

        required_h2 = ensure_string_list(required_headings_cfg.get(rel_path))
        for heading in required_h2:
            if heading not in headings:
                errors.append(f"{rel_path}: missing required heading '## {heading}'")

        max_lines = max_lines_cfg.get(rel_path)
        if isinstance(max_lines, int) and max_lines > 0:
            line_count = len(text.splitlines())
            if line_count > max_lines:
                warnings.append(f"{rel_path}: exceeds max_lines ({line_count} > {max_lines})")

    if errors:
        print("Agent markdown validation errors:")
        for item in errors:
            print(f"- {item}")
    if warnings:
        print("Agent markdown validation warnings:")
        for item in warnings:
            print(f"- {item}")

    if errors:
        return 1
    if args.strict and warnings:
        return 2

    print("Agent markdown validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
