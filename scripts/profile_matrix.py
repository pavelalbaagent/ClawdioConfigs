#!/usr/bin/env python3
"""Print integration profile module and env-key matrix."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "integrations.yaml"


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


def resolve_profile_required_env(
    profile: dict[str, Any],
    integrations: dict[str, Any],
) -> tuple[list[str], list[str], dict[str, list[str]]]:
    modules = ensure_string_list(profile.get("enabled_integrations"))
    required: list[str] = []
    optional: list[str] = []
    module_required: dict[str, list[str]] = {}

    for module_name in modules:
        integration = ensure_dict(integrations.get(module_name))
        if not integration:
            module_required[module_name] = []
            continue

        req = ensure_string_list(integration.get("required_env"))

        provider_priority = ensure_string_list(integration.get("provider_priority"))
        provider_requirements = ensure_dict(integration.get("provider_env_requirements"))
        if provider_priority:
            default_provider = provider_priority[0]
            req.extend(ensure_string_list(provider_requirements.get(default_provider)))

        req = list(dict.fromkeys(req))
        module_required[module_name] = req
        required.extend(req)
        optional.extend(ensure_string_list(integration.get("optional_env")))

    return (
        modules,
        sorted(set(required)),
        {k: v for k, v in module_required.items()},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Print profile module matrix and required env keys")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="path to integrations.yaml")
    parser.add_argument("--profile", help="show details for one profile")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        return 1

    data = ensure_dict(load_yaml(config_path))
    profiles = ensure_dict(ensure_dict(data.get("profiles")).get("definitions"))
    active = ensure_dict(data.get("profiles")).get("active_profile")
    integrations = ensure_dict(data.get("integrations"))

    if not profiles:
        print("No profiles found")
        return 1

    profile_names = [args.profile] if args.profile else sorted(profiles.keys())

    for name in profile_names:
        if not isinstance(name, str) or name not in profiles:
            print(f"Profile not found: {name}")
            return 1
        profile = ensure_dict(profiles[name])
        modules, required_env, module_required = resolve_profile_required_env(profile, integrations)
        marker = " (active)" if name == active else ""

        print(f"Profile: {name}{marker}")
        description = profile.get("description")
        if isinstance(description, str) and description.strip():
            print(f"- Description: {description.strip()}")
        print(f"- Integrations ({len(modules)}): {', '.join(modules) if modules else 'none'}")
        print(f"- Required env count (default provider assumptions): {len(required_env)}")
        if required_env:
            print("- Required env keys:")
            for key in required_env:
                print(f"  - {key}")

        if args.profile:
            print("- Module -> required env:")
            for module_name in modules:
                keys = module_required.get(module_name, [])
                if keys:
                    print(f"  - {module_name}: {', '.join(keys)}")
                else:
                    print(f"  - {module_name}: none")

        print("")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
