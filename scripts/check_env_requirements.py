#!/usr/bin/env python3
"""Report required environment variables for enabled integrations and tool CLIs."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "integrations.yaml"
DEFAULT_MEMORY_CONFIG = ROOT / "config" / "memory.yaml"


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


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f"env file not found: {path}")

    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            raise ValueError(f"invalid env line {line_no}: missing '='")

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"invalid env key on line {line_no}: {key}")

        if (
            len(value) >= 2
            and ((value[0] == value[-1] == "\"") or (value[0] == value[-1] == "'"))
        ):
            value = value[1:-1]

        values[key] = value

    return values


def env_get(var_name: str, env_overrides: dict[str, str]) -> str:
    if var_name in env_overrides:
        return env_overrides[var_name]
    return os.environ.get(var_name, "")


def env_state(var_name: str, env_overrides: dict[str, str]) -> str:
    return "SET" if env_get(var_name, env_overrides).strip() else "MISSING"


def resolve_provider_requirements(
    integration: dict[str, Any],
    base_required: list[str],
    env_overrides: dict[str, str],
) -> tuple[str | None, str | None, list[str]]:
    provider_priority = ensure_string_list(integration.get("provider_priority"))
    provider_requirements = ensure_dict(integration.get("provider_env_requirements"))

    selected_provider: str | None = None
    selected_from: str | None = None
    for var in base_required:
        if not var.endswith("_PROVIDER"):
            continue
        value = env_get(var, env_overrides).strip()
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


def append_missing(vars_list: list[str], missing: list[str], env_overrides: dict[str, str]) -> None:
    for var in vars_list:
        if env_state(var, env_overrides) == "MISSING":
            missing.append(var)


def resolve_memory_profile(memory_data: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    profiles = ensure_dict(memory_data.get("profiles"))
    definitions = ensure_dict(profiles.get("definitions"))
    profile_name = profiles.get("active_profile")
    if not isinstance(profile_name, str) or not profile_name.strip():
        return "", {}, {}
    profile_name = profile_name.strip()
    profile = ensure_dict(definitions.get(profile_name))
    modules = ensure_dict(memory_data.get("memory_modules"))
    return profile_name, profile, modules


def main() -> int:
    parser = argparse.ArgumentParser(description="Check required env vars for integration profile")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="path to integrations.yaml")
    parser.add_argument("--memory-config", default=str(DEFAULT_MEMORY_CONFIG), help="path to memory.yaml")
    parser.add_argument("--env-file", help="dotenv-like file to use for checks without exporting vars")
    parser.add_argument("--include-optional", action="store_true", help="also report optional env vars")
    parser.add_argument("--profile", help="override active profile")
    parser.add_argument("--strict", action="store_true", help="exit non-zero if required env vars are missing")
    args = parser.parse_args()

    env_overrides: dict[str, str] = {}
    if args.env_file:
        env_path = Path(args.env_file).expanduser().resolve()
        try:
            env_overrides = load_env_file(env_path)
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to read --env-file: {exc}")
            return 1
        print(f"Using env file: {env_path}")
        print("")

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
        selected_provider, selected_from, provider_required = resolve_provider_requirements(
            integration,
            required,
            env_overrides,
        )
        all_required = list(dict.fromkeys(required + provider_required))

        if args.include_optional:
            optional = ensure_string_list(integration.get("optional_env", []))
            if optional:
                optional_status = [f"{var}={env_state(var, env_overrides)}" for var in optional]
                print(f"- {name} (optional): " + ", ".join(optional_status))

        if not all_required:
            print(f"- {name}: no required env vars")
            continue
        statuses = [f"{var}={env_state(var, env_overrides)}" for var in all_required]
        provider_label = ""
        if selected_provider:
            from_label = f" via {selected_from}" if selected_from else ""
            provider_label = f" [provider={selected_provider}{from_label}]"
            if provider_required and selected_from == "default_priority":
                print(f"- {name}: using default provider `{selected_provider}` because *_PROVIDER env is not set")

        print(f"- {name}: " + ", ".join(statuses) + provider_label)
        append_missing(all_required, missing_required, env_overrides)
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
        statuses = [f"{var}={env_state(var, env_overrides)}" for var in required]
        print(f"- {name}: " + ", ".join(statuses))
        append_missing(required, missing_required, env_overrides)
        if args.include_optional:
            optional = ensure_string_list(cli.get("optional_env", []))
            if optional:
                optional_status = [f"{var}={env_state(var, env_overrides)}" for var in optional]
                print(f"- {name} (optional): " + ", ".join(optional_status))

    print("")
    print("Memory modules:")
    memory_config_path = Path(args.memory_config)
    if not memory_config_path.exists():
        print(f"- memory config not found: {memory_config_path}")
    else:
        memory_data = ensure_dict(load_yaml(memory_config_path))
        memory_profile_name, memory_profile, memory_modules = resolve_memory_profile(memory_data)
        if not memory_profile_name:
            print("- no active memory profile found")
        elif not memory_profile:
            print(f"- profile not found: {memory_profile_name}")
        else:
            print(f"- profile: {memory_profile_name}")
            enabled_modules = ensure_string_list(memory_profile.get("enabled_modules"))
            if not enabled_modules:
                print("- enabled_modules: empty")
            for module_name in enabled_modules:
                module = ensure_dict(memory_modules.get(module_name))
                if not module:
                    print(f"- {module_name}: NOT_DEFINED")
                    continue
                if module.get("enabled") is not True:
                    print(f"- {module_name}: DISABLED")
                    continue
                required = ensure_string_list(module.get("required_env", []))
                if not required:
                    print(f"- {module_name}: no required env vars")
                else:
                    statuses = [f"{var}={env_state(var, env_overrides)}" for var in required]
                    print(f"- {module_name}: " + ", ".join(statuses))
                    append_missing(required, missing_required, env_overrides)
                if args.include_optional:
                    optional = ensure_string_list(module.get("optional_env", []))
                    if optional:
                        optional_status = [f"{var}={env_state(var, env_overrides)}" for var in optional]
                        print(f"- {module_name} (optional): " + ", ".join(optional_status))

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
