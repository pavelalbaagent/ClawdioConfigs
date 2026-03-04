#!/usr/bin/env python3
"""Switch active integration and/or memory profile in config files."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INTEGRATIONS_CONFIG = ROOT / "config" / "integrations.yaml"
MEMORY_CONFIG = ROOT / "config" / "memory.yaml"
ADDONS_CONFIG = ROOT / "config" / "addons.yaml"
ACTIVE_RE = re.compile(r"^(\s*active_profile:\s*)([^\s#]+)(.*)$")


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


def get_profile_definitions(path: Path) -> tuple[str, set[str]]:
    data = ensure_dict(load_yaml(path))
    profiles = ensure_dict(data.get("profiles"))
    active = profiles.get("active_profile")
    if not isinstance(active, str):
        active = ""
    definitions = ensure_dict(profiles.get("definitions"))
    return active, set(definitions.keys())


def replace_active_profile(text: str, new_profile: str) -> tuple[str, str]:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = ACTIVE_RE.match(line)
        if not match:
            continue
        previous = match.group(2)
        lines[i] = f"{match.group(1)}{new_profile}{match.group(3)}"
        return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), previous
    raise RuntimeError("active_profile key not found")


def update_config(path: Path, new_profile: str, dry_run: bool) -> tuple[str, str]:
    content = path.read_text(encoding="utf-8")
    updated, previous = replace_active_profile(content, new_profile)
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return previous, new_profile


def main() -> int:
    parser = argparse.ArgumentParser(description="Switch active profile in integrations/memory/add-ons configs")
    parser.add_argument("--integrations-profile", help="new active profile for config/integrations.yaml")
    parser.add_argument("--memory-profile", help="new active profile for config/memory.yaml")
    parser.add_argument("--addons-profile", help="new active profile for config/addons.yaml")
    parser.add_argument("--dry-run", action="store_true", help="validate and preview without writing files")
    args = parser.parse_args()

    if not args.integrations_profile and not args.memory_profile and not args.addons_profile:
        print("Nothing to change. Provide --integrations-profile, --memory-profile, and/or --addons-profile")
        return 2

    if args.integrations_profile:
        current, definitions = get_profile_definitions(INTEGRATIONS_CONFIG)
        if args.integrations_profile not in definitions:
            print(f"Unknown integrations profile: {args.integrations_profile}")
            print(f"Available: {', '.join(sorted(definitions))}")
            return 2
        prev, new = update_config(INTEGRATIONS_CONFIG, args.integrations_profile, args.dry_run)
        mode = "would switch" if args.dry_run else "switched"
        print(f"integrations: {mode} {prev} -> {new}")

    if args.memory_profile:
        current, definitions = get_profile_definitions(MEMORY_CONFIG)
        if args.memory_profile not in definitions:
            print(f"Unknown memory profile: {args.memory_profile}")
            print(f"Available: {', '.join(sorted(definitions))}")
            return 2
        prev, new = update_config(MEMORY_CONFIG, args.memory_profile, args.dry_run)
        mode = "would switch" if args.dry_run else "switched"
        print(f"memory: {mode} {prev} -> {new}")

    if args.addons_profile:
        current, definitions = get_profile_definitions(ADDONS_CONFIG)
        if args.addons_profile not in definitions:
            print(f"Unknown add-ons profile: {args.addons_profile}")
            print(f"Available: {', '.join(sorted(definitions))}")
            return 2
        prev, new = update_config(ADDONS_CONFIG, args.addons_profile, args.dry_run)
        mode = "would switch" if args.dry_run else "switched"
        print(f"addons: {mode} {prev} -> {new}")

    if args.dry_run:
        print("dry run complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
