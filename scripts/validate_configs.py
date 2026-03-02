#!/usr/bin/env python3
"""Validate config YAML files with schema and cross-file checks.

No third-party Python dependency is required. YAML parsing tries PyYAML first,
then falls back to Ruby's YAML parser when available.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"

EXPECTED_CONFIGS = {
    "core": CONFIG_DIR / "core.yaml",
    "channels": CONFIG_DIR / "channels.yaml",
    "models": CONFIG_DIR / "models.yaml",
    "integrations": CONFIG_DIR / "integrations.yaml",
    "agents": CONFIG_DIR / "agents.yaml",
    "tasks": CONFIG_DIR / "tasks.yaml",
    "security": CONFIG_DIR / "security.yaml",
    "reminders": CONFIG_DIR / "reminders.yaml",
    "session_policy": CONFIG_DIR / "session_policy.yaml",
}


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


def is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def add_error(errors: list[str], code: str, message: str) -> None:
    errors.append(f"[{code}] {message}")


def add_warning(warnings: list[str], code: str, message: str) -> None:
    warnings.append(f"[{code}] {message}")


def require_dict(data: Any, errors: list[str], name: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        add_error(errors, "TYPE", f"{name} must be a mapping")
        return {}
    return data


def validate_string_list(value: Any, field_name: str, errors: list[str], *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list):
        add_error(errors, "TYPE", f"{field_name} must be a list")
        return []
    if not allow_empty and not value:
        add_error(errors, "REQ", f"{field_name} must be a non-empty list")
        return []
    clean: list[str] = []
    for item in value:
        if not is_non_empty_str(item):
            add_error(errors, "TYPE", f"{field_name} entries must be non-empty strings")
            continue
        clean.append(item)
    return clean


def validate_core(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    project = require_dict(data.get("project"), errors, "core.project")
    owner = require_dict(data.get("owner"), errors, "core.owner")
    limits = require_dict(data.get("limits"), errors, "core.limits")
    budgets = require_dict(data.get("budgets"), errors, "core.budgets")

    if not is_non_empty_str(project.get("name")):
        add_error(errors, "REQ", "core.project.name is required")
    if not is_non_empty_str(owner.get("timezone")):
        add_error(errors, "REQ", "core.owner.timezone is required")

    max_parallel = limits.get("max_parallel_tasks")
    if not isinstance(max_parallel, int) or max_parallel < 1:
        add_error(errors, "RANGE", "core.limits.max_parallel_tasks must be integer >= 1")

    for key in ("daily_usd_cap", "monthly_usd_cap"):
        value = budgets.get(key)
        if not isinstance(value, (int, float)) or value <= 0:
            add_error(errors, "RANGE", f"core.budgets.{key} must be > 0")

    daily = budgets.get("daily_usd_cap")
    monthly = budgets.get("monthly_usd_cap")
    if isinstance(daily, (int, float)) and isinstance(monthly, (int, float)) and daily > monthly:
        add_warning(warnings, "BUDGET", "core daily budget exceeds monthly budget")


def validate_channels(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    channels = require_dict(data.get("channels"), errors, "channels.channels")
    enabled = channels.get("enabled")
    disabled = channels.get("disabled")

    if not isinstance(enabled, list) or not enabled:
        add_error(errors, "REQ", "channels.channels.enabled must be a non-empty list")
        enabled = []
    if not isinstance(disabled, list):
        add_error(errors, "TYPE", "channels.channels.disabled must be a list")
        disabled = []

    primary = channels.get("primary_human_channel")
    if not is_non_empty_str(primary):
        add_error(errors, "REQ", "channels.channels.primary_human_channel is required")
    elif primary not in enabled:
        add_warning(warnings, "CHAN", "primary_human_channel is not in enabled list")

    overlap = set(enabled).intersection(set(disabled))
    if overlap:
        add_error(errors, "CHAN", f"enabled/disabled overlap: {sorted(overlap)}")


def validate_models(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    routing = require_dict(data.get("routing"), errors, "models.routing")
    lanes = require_dict(routing.get("lanes"), errors, "models.routing.lanes")
    fallback = routing.get("fallback_order")

    if not lanes:
        add_error(errors, "REQ", "models.routing.lanes must not be empty")

    if not isinstance(fallback, list) or not fallback:
        add_error(errors, "REQ", "models.routing.fallback_order must be a non-empty list")
    else:
        for lane_name in fallback:
            if lane_name not in lanes:
                add_error(errors, "LANE", f"fallback lane not defined: {lane_name}")

    for lane_name, lane_data in lanes.items():
        if not isinstance(lane_data, dict):
            add_error(errors, "TYPE", f"lane {lane_name} must be a mapping")
            continue
        if lane_name != "L0_no_model":
            for token_key in ("max_input_tokens", "max_output_tokens"):
                value = lane_data.get(token_key)
                if not isinstance(value, int) or value <= 0:
                    add_error(errors, "RANGE", f"{lane_name}.{token_key} must be integer > 0")

    distribution = require_dict(data.get("budget_distribution_target"), errors, "models.budget_distribution_target")
    keys = ["L1_low_cost_pct", "L2_balanced_pct", "L3_heavy_pct"]
    if all(isinstance(distribution.get(k), int) for k in keys):
        total = sum(distribution[k] for k in keys)
        if total != 100:
            add_error(errors, "BUDGET", f"model budget distribution must sum to 100 (got {total})")
    else:
        add_error(errors, "REQ", "models.budget_distribution_target must include integer lane percentages")


def validate_integrations(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    profiles = require_dict(data.get("profiles"), errors, "integrations.profiles")
    active_profile = profiles.get("active_profile")
    if not is_non_empty_str(active_profile):
        add_error(errors, "REQ", "integrations.profiles.active_profile is required")
        active_profile = ""
    definitions = require_dict(profiles.get("definitions"), errors, "integrations.profiles.definitions")

    integrations = require_dict(data.get("integrations"), errors, "integrations.integrations")
    integration_names = set(integrations.keys())

    if active_profile and active_profile not in definitions:
        add_error(
            errors,
            "PROFILE",
            f"active integration profile not found: {active_profile}",
        )

    for profile_name, profile in definitions.items():
        if not isinstance(profile, dict):
            add_error(errors, "TYPE", f"profile {profile_name} must be a mapping")
            continue
        enabled_integrations = validate_string_list(
            profile.get("enabled_integrations"),
            f"integrations.profiles.definitions.{profile_name}.enabled_integrations",
            errors,
            allow_empty=False,
        )
        for name in enabled_integrations:
            if name not in integration_names:
                add_error(errors, "PROFILE", f"profile {profile_name} references unknown integration: {name}")

    tool_clis = require_dict(data.get("tool_clis"), errors, "integrations.tool_clis")
    tool_cli_names = set(tool_clis.keys())

    for profile_name, profile in definitions.items():
        if not isinstance(profile, dict):
            continue
        enabled_tool_clis = validate_string_list(
            profile.get("enabled_tool_clis"),
            f"integrations.profiles.definitions.{profile_name}.enabled_tool_clis",
            errors,
            allow_empty=False,
        )
        for cli_name in enabled_tool_clis:
            if cli_name not in tool_cli_names:
                add_error(errors, "PROFILE", f"profile {profile_name} references unknown tool cli: {cli_name}")

    for integration_name, integration in integrations.items():
        section_name = f"integrations.integrations.{integration_name}"
        row = require_dict(integration, errors, section_name)
        enabled = row.get("enabled")
        if not isinstance(enabled, bool):
            add_error(errors, "TYPE", f"{section_name}.enabled must be boolean")

        validate_string_list(row.get("required_env", []), f"{section_name}.required_env", errors, allow_empty=True)
        validate_string_list(row.get("optional_env", []), f"{section_name}.optional_env", errors, allow_empty=True)

        if row.get("provider_env_requirements") is not None:
            provider_requirements = require_dict(
                row.get("provider_env_requirements"),
                errors,
                f"{section_name}.provider_env_requirements",
            )
            provider_priority = validate_string_list(
                row.get("provider_priority", []),
                f"{section_name}.provider_priority",
                errors,
                allow_empty=True,
            )
            for provider_name, env_list in provider_requirements.items():
                validate_string_list(
                    env_list,
                    f"{section_name}.provider_env_requirements.{provider_name}",
                    errors,
                    allow_empty=False,
                )
            if provider_priority:
                missing_mappings = sorted(set(provider_priority) - set(provider_requirements.keys()))
                if missing_mappings:
                    add_warning(
                        warnings,
                        "PROVIDER",
                        f"{section_name} provider mappings missing for: {missing_mappings}",
                    )

        if enabled is True:
            if not is_non_empty_str(row.get("execution_mode")):
                add_error(errors, "REQ", f"{section_name}.execution_mode is required when enabled=true")

            auth_type = row.get("auth_type")
            if auth_type == "oauth":
                validate_string_list(row.get("scopes"), f"{section_name}.scopes", errors, allow_empty=False)

            validate_string_list(row.get("read_actions", []), f"{section_name}.read_actions", errors, allow_empty=True)
            validate_string_list(row.get("write_actions", []), f"{section_name}.write_actions", errors, allow_empty=True)

        if integration_name == "linkedin" and row.get("enabled") is True:
            if row.get("execution_mode") != "manual_review_only":
                add_warning(
                    warnings,
                    "LINKEDIN",
                    "linkedin is enabled without manual_review_only mode; verify compliance constraints",
                )

        if integration_name == "n8n":
            contracts_file = row.get("workflow_contracts_file")
            if is_non_empty_str(contracts_file):
                contracts_path = ROOT / str(contracts_file)
                if not contracts_path.exists():
                    add_warning(
                        warnings,
                        "N8N",
                        f"n8n workflow contracts file not found: {contracts_file}",
                    )
            elif row.get("enabled") is True:
                add_warning(
                    warnings,
                    "N8N",
                    "n8n is enabled without workflow_contracts_file",
                )

            modules = require_dict(row.get("modules", {}), errors, f"{section_name}.modules")
            for module_name, module_enabled in modules.items():
                if not isinstance(module_enabled, bool):
                    add_error(errors, "TYPE", f"{section_name}.modules.{module_name} must be boolean")

    for cli_name, cli_data in tool_clis.items():
        cli = require_dict(cli_data, errors, f"integrations.tool_clis.{cli_name}")
        timeout = cli.get("timeout_seconds")
        if not isinstance(timeout, int) or timeout <= 0:
            add_error(errors, "RANGE", f"{cli_name}.timeout_seconds must be integer > 0")
        max_output = cli.get("max_output_chars")
        if not isinstance(max_output, int) or max_output <= 0:
            add_error(errors, "RANGE", f"{cli_name}.max_output_chars must be integer > 0")
        if not is_non_empty_str(cli.get("command")):
            add_error(errors, "REQ", f"{cli_name}.command is required")
        validate_string_list(cli.get("required_env", []), f"integrations.tool_clis.{cli_name}.required_env", errors)
        validate_string_list(cli.get("optional_env", []), f"integrations.tool_clis.{cli_name}.optional_env", errors)
        validate_string_list(
            cli.get("approval_required_for", []),
            f"integrations.tool_clis.{cli_name}.approval_required_for",
            errors,
            allow_empty=False,
        )

    secrets = require_dict(data.get("secrets"), errors, "integrations.secrets")
    if not is_non_empty_str(secrets.get("source")):
        add_error(errors, "REQ", "integrations.secrets.source is required")
    rotate_days = secrets.get("rotate_days")
    if not isinstance(rotate_days, int) or rotate_days <= 0:
        add_error(errors, "RANGE", "integrations.secrets.rotate_days must be integer > 0")


def validate_agents(data: dict[str, Any], model_lanes: set[str], errors: list[str], warnings: list[str]) -> None:
    agents = require_dict(data.get("agents"), errors, "agents.agents")
    if not agents:
        add_error(errors, "REQ", "agents.agents must not be empty")
    for agent_name, agent_data in agents.items():
        if not isinstance(agent_data, dict):
            add_error(errors, "TYPE", f"agent {agent_name} must be a mapping")
            continue
        lane = agent_data.get("default_lane")
        if not is_non_empty_str(lane):
            add_error(errors, "REQ", f"agent {agent_name}.default_lane is required")
        elif lane not in model_lanes:
            add_error(errors, "LANE", f"agent {agent_name} references unknown lane {lane}")

    spawn_policy = require_dict(data.get("spawn_policy"), errors, "agents.spawn_policy")
    max_active = spawn_policy.get("max_active_subagents")
    if not isinstance(max_active, int) or max_active < 1:
        add_error(errors, "RANGE", "agents.spawn_policy.max_active_subagents must be integer >= 1")


def validate_tasks(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    personal_tasks = require_dict(data.get("personal_tasks"), errors, "tasks.personal_tasks")
    if personal_tasks.get("enabled") is True:
        if personal_tasks.get("system") == "provider_from_env":
            if not is_non_empty_str(personal_tasks.get("provider_env_key")):
                add_error(errors, "REQ", "tasks.personal_tasks.provider_env_key is required")
            validate_string_list(
                personal_tasks.get("supported_providers"),
                "tasks.personal_tasks.supported_providers",
                errors,
                allow_empty=False,
            )

    agent_tasks = require_dict(data.get("agent_tasks"), errors, "tasks.agent_tasks")
    if agent_tasks.get("enabled") is True and agent_tasks.get("system") == "provider_from_env":
        if not is_non_empty_str(agent_tasks.get("provider_env_key")):
            add_error(errors, "REQ", "tasks.agent_tasks.provider_env_key is required")
        validate_string_list(
            agent_tasks.get("supported_providers"),
            "tasks.agent_tasks.supported_providers",
            errors,
            allow_empty=False,
        )

    statuses = agent_tasks.get("statuses")
    if not isinstance(statuses, list) or not statuses:
        add_error(errors, "REQ", "tasks.agent_tasks.statuses must be a non-empty list")
    else:
        required = {"new", "running", "done"}
        missing = sorted(required - set(statuses))
        if missing:
            add_warning(warnings, "TASK", f"agent statuses missing common states: {missing}")


def validate_security(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    audit = require_dict(data.get("audit"), errors, "security.audit")
    log_file = audit.get("log_file")
    if not is_non_empty_str(log_file):
        add_error(errors, "REQ", "security.audit.log_file is required")
    elif not str(log_file).startswith("/"):
        add_warning(warnings, "PATH", "security.audit.log_file is not absolute")


def validate_reminders(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    reminders = require_dict(data.get("reminders"), errors, "reminders.reminders")
    followup = reminders.get("followup_interval_minutes")
    if not isinstance(followup, int) or followup <= 0:
        add_error(errors, "RANGE", "reminders.followup_interval_minutes must be integer > 0")

    max_auto = reminders.get("max_auto_followups")
    if not isinstance(max_auto, int) or max_auto < 0:
        add_error(errors, "RANGE", "reminders.max_auto_followups must be integer >= 0")

    repeat = reminders.get("repeat_followups_until_response")
    if repeat is False and isinstance(max_auto, int) and max_auto > 1:
        add_warning(
            warnings,
            "REM",
            "max_auto_followups > 1 while repeat_followups_until_response=false",
        )

    states = data.get("states")
    if not isinstance(states, list) or not states:
        add_error(errors, "REQ", "reminders.states must be a non-empty list")
    else:
        for required in ("pending", "awaiting_reply", "done"):
            if required not in states:
                add_error(errors, "STATE", f"missing reminder state: {required}")


def validate_session_policy(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    lifecycle = require_dict(data.get("session_lifecycle"), errors, "session_policy.session_lifecycle")
    for field in (
        "default_context_window_tokens",
        "summarize_when_context_tokens_over",
        "checkpoint_every_turns",
        "checkpoint_every_minutes",
        "idle_reset_minutes",
    ):
        value = lifecycle.get(field)
        if not isinstance(value, int) or value <= 0:
            add_error(errors, "RANGE", f"session_policy.session_lifecycle.{field} must be integer > 0")

    validate_string_list(
        lifecycle.get("summarize_when"),
        "session_policy.session_lifecycle.summarize_when",
        errors,
        allow_empty=False,
    )
    validate_string_list(
        lifecycle.get("restart_when"),
        "session_policy.session_lifecycle.restart_when",
        errors,
        allow_empty=False,
    )
    validate_string_list(
        lifecycle.get("preserve_on_restart"),
        "session_policy.session_lifecycle.preserve_on_restart",
        errors,
        allow_empty=False,
    )

    spawn = require_dict(data.get("spawn_controls"), errors, "session_policy.spawn_controls")
    max_parallel = spawn.get("max_parallel_subagents")
    if not isinstance(max_parallel, int) or max_parallel < 1:
        add_error(errors, "RANGE", "session_policy.spawn_controls.max_parallel_subagents must be integer >= 1")

    ttl_default = spawn.get("ttl_minutes_default")
    ttl_max = spawn.get("ttl_minutes_max")
    if not isinstance(ttl_default, int) or ttl_default <= 0:
        add_error(errors, "RANGE", "session_policy.spawn_controls.ttl_minutes_default must be integer > 0")
    if not isinstance(ttl_max, int) or ttl_max <= 0:
        add_error(errors, "RANGE", "session_policy.spawn_controls.ttl_minutes_max must be integer > 0")
    if isinstance(ttl_default, int) and isinstance(ttl_max, int) and ttl_default > ttl_max:
        add_error(errors, "RANGE", "session_policy ttl_minutes_default cannot exceed ttl_minutes_max")

    validate_string_list(
        spawn.get("spawn_requires"),
        "session_policy.spawn_controls.spawn_requires",
        errors,
        allow_empty=False,
    )

    handoff = require_dict(data.get("handoff"), errors, "session_policy.handoff")
    if not is_non_empty_str(handoff.get("write_checkpoints_to")):
        add_error(errors, "REQ", "session_policy.handoff.write_checkpoints_to is required")
    validate_string_list(
        handoff.get("summary_template"),
        "session_policy.handoff.summary_template",
        errors,
        allow_empty=False,
    )


def validate_spawn_alignment(
    agents_data: dict[str, Any],
    session_policy_data: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    agents_spawn = require_dict(agents_data.get("spawn_policy"), errors, "agents.spawn_policy")
    session_spawn = require_dict(session_policy_data.get("spawn_controls"), errors, "session_policy.spawn_controls")

    agents_max = agents_spawn.get("max_active_subagents")
    session_max = session_spawn.get("max_parallel_subagents")
    if isinstance(agents_max, int) and isinstance(session_max, int) and session_max > agents_max:
        add_warning(
            warnings,
            "SPAWN",
            "session_policy allows more parallel subagents than agents.spawn_policy",
        )


def validate_watchlist(path: Path, errors: list[str], warnings: list[str]) -> None:
    if not path.exists():
        return
    data = require_dict(load_yaml(path), errors, "watchlist")
    youtube = data.get("youtube")
    if youtube is None:
        add_warning(warnings, "WATCH", "watchlist has no youtube section")
        return
    if not isinstance(youtube, list):
        add_error(errors, "WATCH", "watchlist.youtube must be a list")
        return
    if not youtube:
        add_warning(warnings, "WATCH", "watchlist.youtube list is empty")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Clawdio config files")
    parser.add_argument("--config-dir", default=str(CONFIG_DIR))
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = parser.parse_args()

    config_dir = Path(args.config_dir)
    errors: list[str] = []
    warnings: list[str] = []
    loaded: dict[str, Any] = {}

    for name, default_path in EXPECTED_CONFIGS.items():
        path = config_dir / default_path.name
        if not path.exists():
            add_error(errors, "MISSING", f"missing config file: {path}")
            continue
        try:
            loaded[name] = load_yaml(path)
        except Exception as exc:
            add_error(errors, "PARSE", f"failed to parse {path}: {exc}")

    if "core" in loaded:
        validate_core(require_dict(loaded["core"], errors, "core"), errors, warnings)
    if "channels" in loaded:
        validate_channels(require_dict(loaded["channels"], errors, "channels"), errors, warnings)
    if "models" in loaded:
        validate_models(require_dict(loaded["models"], errors, "models"), errors, warnings)
    if "integrations" in loaded:
        validate_integrations(require_dict(loaded["integrations"], errors, "integrations"), errors, warnings)

    model_lanes = set()
    if "models" in loaded and isinstance(loaded["models"], dict):
        model_lanes = set(((loaded["models"].get("routing") or {}).get("lanes") or {}).keys())

    if "agents" in loaded:
        validate_agents(require_dict(loaded["agents"], errors, "agents"), model_lanes, errors, warnings)
    if "tasks" in loaded:
        validate_tasks(require_dict(loaded["tasks"], errors, "tasks"), errors, warnings)
    if "security" in loaded:
        validate_security(require_dict(loaded["security"], errors, "security"), errors, warnings)
    if "reminders" in loaded:
        validate_reminders(require_dict(loaded["reminders"], errors, "reminders"), errors, warnings)
    if "session_policy" in loaded:
        validate_session_policy(require_dict(loaded["session_policy"], errors, "session_policy"), errors, warnings)

    if "agents" in loaded and "session_policy" in loaded:
        validate_spawn_alignment(
            require_dict(loaded["agents"], errors, "agents"),
            require_dict(loaded["session_policy"], errors, "session_policy"),
            errors,
            warnings,
        )

    validate_watchlist(config_dir / "watchlist.yaml", errors, warnings)

    if errors:
        print("Config validation errors:")
        for err in errors:
            print(f"- {err}")
    if warnings:
        print("Config validation warnings:")
        for warn in warnings:
            print(f"- {warn}")

    if errors:
        return 1
    if args.strict and warnings:
        return 2

    print("Config validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
