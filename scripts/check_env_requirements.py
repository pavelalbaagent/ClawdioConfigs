#!/usr/bin/env python3
"""Report required environment variables for enabled integrations and tool CLIs."""

from __future__ import annotations

import argparse
import json
import os
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
    return [item for item in value if isinstance(item, str) and item.strip()]


def env_state(var_name: str) -> str:
    return "SET" if os.environ.get(var_name, "").strip() else "MISSING"


def resolve_provider_requirements(integration: dict[str, Any], base_required: list[str]) -> tuple[str | None, str | None, list[str]]:
    provider_priority = ensure_string_list(integration.get("provider_priority"))
    provider_requirements = ensure_dict(integration.get("provider_env_requirements"))

    selected_provider: str | None = None
    selected_from: str | None = None
    for var in base_required:
        if not var.endswith("_PROVIDER"):
            continue
        value = os.environ.get(var, "").strip()
        if value:
            selected_provider = value
            selected_from = var
            break

    if not selected_provider and provider_priority:
        selected_provider = provider_priority[0]
        selected_from = "default_priority"

    if not selected_provider:
        return None, None, []

    provider_required = ensure_string_list(provider_requirements.get(selected_provider))
    return selected_provider, selected_from, provider_required


def append_missing(vars_list: list[str], missing: list[str]) -> None:
    for var in vars_list:
        if env_state(var) == "MISSING":
            missing.append(var)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check required env vars for integration profile")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="path to integrations.yaml")
    parser.add_argument("--profile", help="override active profile")
    parser.add_argument("--strict", action="store_true", help="exit non-zero if required env vars are missing")
    args = parser.parse_args()

    config_path = Path(args.config)
    data = ensure_dict(load_yaml(config_path))

    profiles = ensure_dict(data.get("profiles"))
    definitions = ensure_dict(profiles.get("definitions"))
    profile_name = args.profile or profiles.get("active_profile")
    if not isinstance(profile_name, str) or profile_name.strip() == "":
        print("No active profile found")
        return 1
    profile_name = profile_name.strip()

    profile = ensure_dict(definitions.get(profile_name))
    if not profile:
        print(f"Profile not found: {profile_name}")
        return 1

    integrations = ensure_dict(data.get("integrations"))
    tool_clis = ensure_dict(data.get("tool_clis"))
    integration_names = ensure_string_list(profile.get("enabled_integrations"))
    tool_names = ensure_string_list(profile.get("enabled_tool_clis"))

    missing_required: list[str] = []
    print(f"Profile: {profile_name}")
    print("")
    print("Integrations:")
    for name in integration_names:
        integration = ensure_dict(integrations.get(name))
        enabled = integration.get("enabled") is True
        required = ensure_string_list(integration.get("required_env"))
        if not integration:
            print(f"- {name}: NOT_DEFINED")
            continue
        if not enabled:
            print(f"- {name}: DISABLED")
            continue
        selected_provider, selected_from, provider_required = resolve_provider_requirements(integration, required)
        all_required = list(dict.fromkeys(required + provider_required))

        if not all_required:
            print(f"- {name}: no required env vars")
            continue
        statuses = [f"{var}={env_state(var)}" for var in all_required]
        provider_label = ""
        if selected_provider:
            from_label = f" via {selected_from}" if selected_from else ""
            provider_label = f" [provider={selected_provider}{from_label}]"
            if provider_required and selected_from == "default_priority":
                print(f"- {name}: using default provider `{selected_provider}` because *_PROVIDER env is not set")

        print(f"- {name}: " + ", ".join(statuses) + provider_label)
        append_missing(all_required, missing_required)
        if selected_provider and not provider_required and ensure_dict(integration.get("provider_env_requirements")):
            print(f"- {name}: provider `{selected_provider}` has no mapped env requirements in config")

    print("")
    print("Tool CLIs:")
    for name in tool_names:
        cli = ensure_dict(tool_clis.get(name))
        enabled = cli.get("enabled") is True
        required = ensure_string_list(cli.get("required_env"))
        if not cli:
            print(f"- {name}: NOT_DEFINED")
            continue
        if not enabled:
            print(f"- {name}: DISABLED")
            continue
        if not required:
            print(f"- {name}: no required env vars")
            continue
        statuses = [f"{var}={env_state(var)}" for var in required]
        print(f"- {name}: " + ", ".join(statuses))
        append_missing(required, missing_required)

    unique_missing = sorted(set(missing_required))
    print("")
    if unique_missing:
        print("Missing required vars:")
        for var in unique_missing:
            print(f"- {var}")
        return 1 if args.strict else 0

    print("All required vars for enabled modules are set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
