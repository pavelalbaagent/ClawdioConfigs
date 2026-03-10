#!/usr/bin/env python3
"""Validate config YAML files with schema and cross-file checks.

No third-party Python dependency is required. YAML parsing tries PyYAML first,
then falls back to Ruby's YAML parser when available.
"""

from __future__ import annotations

import argparse
import json
import re
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
    "addons": CONFIG_DIR / "addons.yaml",
    "memory": CONFIG_DIR / "memory.yaml",
    "agents": CONFIG_DIR / "agents.yaml",
    "tasks": CONFIG_DIR / "tasks.yaml",
    "security": CONFIG_DIR / "security.yaml",
    "reminders": CONFIG_DIR / "reminders.yaml",
    "session_policy": CONFIG_DIR / "session_policy.yaml",
    "dashboard": CONFIG_DIR / "dashboard.yaml",
    "job_search": CONFIG_DIR / "job_search.yaml",
    "knowledge_sources": CONFIG_DIR / "knowledge_sources.yaml",
    "research_flow": CONFIG_DIR / "research_flow.yaml",
}

TASK_STATUSES = {"todo", "in_progress", "blocked", "done"}
PRIORITY_LEVELS = {"low", "medium", "high", "urgent"}
JOB_RECOMMENDATIONS = {"apply", "manual_review", "stretch_apply", "pass"}
JOB_ELIGIBILITY = {"direct_yes", "possible_manual_check", "unclear", "likely_no"}


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


def resolve_repo_path(path_value: str) -> Path:
    path = Path(str(path_value))
    if not path.is_absolute():
        path = ROOT / path
    return path


def require_dict(data: Any, errors: list[str], name: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        add_error(errors, "TYPE", f"{name} must be a mapping")
        return {}
    return data


def ensure_dict(data: Any) -> dict[str, Any]:
    return data if isinstance(data, dict) else {}


def validate_existing_repo_file(path_value: Any, field_name: str, errors: list[str], *, required: bool) -> None:
    if path_value is None:
        if required:
            add_error(errors, "REQ", f"{field_name} is required")
        return
    if not is_non_empty_str(path_value):
        add_error(errors, "TYPE", f"{field_name} must be a non-empty string")
        return
    path = resolve_repo_path(str(path_value))
    if not path.exists():
        add_error(errors, "PATH", f"{field_name} file not found: {path_value}")


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
    provider_inventory = require_dict(data.get("provider_inventory"), errors, "models.provider_inventory")

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

        provider_priority = validate_string_list(
            lane_data.get("provider_priority", []),
            f"{lane_name}.provider_priority",
            errors,
            allow_empty=True,
        )
        provider_models = ensure_dict(lane_data.get("provider_models"))

        for provider_name in provider_priority:
            if provider_name not in provider_inventory:
                add_error(errors, "PROVIDER", f"{lane_name}.provider_priority references unknown provider: {provider_name}")

        for provider_name, model_name in provider_models.items():
            if provider_name not in provider_inventory:
                add_error(errors, "PROVIDER", f"{lane_name}.provider_models references unknown provider: {provider_name}")
                continue
            if not is_non_empty_str(model_name):
                add_error(errors, "MODEL", f"{lane_name}.provider_models.{provider_name} must be a non-empty string")

        for provider_name in provider_priority:
            if provider_name not in provider_models:
                provider_cfg = ensure_dict(provider_inventory.get(provider_name))
                if not is_non_empty_str(provider_cfg.get("default_model")) and not is_non_empty_str(
                    provider_cfg.get("model_env_override")
                ):
                    add_error(
                        errors,
                        "MODEL",
                        f"{lane_name} has no model mapping for provider {provider_name} and provider_inventory lacks defaults",
                    )

    for provider_name, provider_data in provider_inventory.items():
        provider_cfg = require_dict(provider_data, errors, f"models.provider_inventory.{provider_name}")
        required_env = validate_string_list(
            provider_cfg.get("required_env", []),
            f"models.provider_inventory.{provider_name}.required_env",
            errors,
            allow_empty=True,
        )
        required_command = provider_cfg.get("required_command")
        if required_command is not None and not is_non_empty_str(required_command):
            add_error(
                errors,
                "TYPE",
                f"models.provider_inventory.{provider_name}.required_command must be a non-empty string when present",
            )
        if not required_env and required_command is None:
            add_warning(
                warnings,
                "PROVIDER",
                f"models.provider_inventory.{provider_name} has no required_env or required_command gating",
            )
        if provider_cfg.get("default_model") is not None and not is_non_empty_str(provider_cfg.get("default_model")):
            add_error(
                errors,
                "MODEL",
                f"models.provider_inventory.{provider_name}.default_model must be a non-empty string when present",
            )
        if provider_cfg.get("healthcheck_model") is not None and not is_non_empty_str(
            provider_cfg.get("healthcheck_model")
        ):
            add_error(
                errors,
                "MODEL",
                f"models.provider_inventory.{provider_name}.healthcheck_model must be a non-empty string when present",
            )
        if provider_cfg.get("model_env_override") is not None and not is_non_empty_str(
            provider_cfg.get("model_env_override")
        ):
            add_error(
                errors,
                "MODEL",
                f"models.provider_inventory.{provider_name}.model_env_override must be a non-empty string when present",
            )

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

        if integration_name == "gmail":
            inbox_processing = require_dict(row.get("inbox_processing", {}), errors, f"{section_name}.inbox_processing")
            if inbox_processing.get("enabled") is True:
                poll_every = inbox_processing.get("poll_every_minutes")
                if not isinstance(poll_every, int) or poll_every <= 0:
                    add_error(errors, "RANGE", f"{section_name}.inbox_processing.poll_every_minutes must be integer > 0")
                validate_existing_repo_file(
                    inbox_processing.get("contract_file"),
                    f"{section_name}.inbox_processing.contract_file",
                    errors,
                    required=True,
                )
                if not is_non_empty_str(inbox_processing.get("state_store")):
                    add_error(errors, "REQ", f"{section_name}.inbox_processing.state_store is required")
                if not is_non_empty_str(inbox_processing.get("state_db_path")):
                    add_error(errors, "REQ", f"{section_name}.inbox_processing.state_db_path is required")
                validate_string_list(
                    inbox_processing.get("default_actions", []),
                    f"{section_name}.inbox_processing.default_actions",
                    errors,
                    allow_empty=False,
                )

        if integration_name == "drive":
            workspace_policy = require_dict(row.get("workspace_policy", {}), errors, f"{section_name}.workspace_policy")
            if row.get("enabled") is True:
                if not is_non_empty_str(workspace_policy.get("mode")):
                    add_error(errors, "REQ", f"{section_name}.workspace_policy.mode is required")
                if not is_non_empty_str(workspace_policy.get("root_folder_env")):
                    add_error(errors, "REQ", f"{section_name}.workspace_policy.root_folder_env is required")
                validate_existing_repo_file(
                    workspace_policy.get("contract_file"),
                    f"{section_name}.workspace_policy.contract_file",
                    errors,
                    required=True,
                )

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
                contracts_path = resolve_repo_path(str(contracts_file))
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


def validate_addons(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    profiles = require_dict(data.get("profiles"), errors, "addons.profiles")
    active_profile = profiles.get("active_profile")
    if not is_non_empty_str(active_profile):
        add_error(errors, "REQ", "addons.profiles.active_profile is required")
        active_profile = ""
    definitions = require_dict(profiles.get("definitions"), errors, "addons.profiles.definitions")

    addons = require_dict(data.get("addons"), errors, "addons.addons")
    addon_names = set(addons.keys())

    if active_profile and active_profile not in definitions:
        add_error(errors, "PROFILE", f"active add-ons profile not found: {active_profile}")

    active_enabled: set[str] = set()
    for profile_name, profile_data in definitions.items():
        section = f"addons.profiles.definitions.{profile_name}"
        profile = require_dict(profile_data, errors, section)
        enabled_addons = validate_string_list(
            profile.get("enabled_addons", []),
            f"{section}.enabled_addons",
            errors,
            allow_empty=True,
        )
        if profile_name == active_profile:
            active_enabled = set(enabled_addons)
        for addon_name in enabled_addons:
            if addon_name not in addon_names:
                add_error(errors, "PROFILE", f"{section} references unknown add-on: {addon_name}")

    allowed_tiers = {"recommended_now", "optional", "skip_for_now"}
    for addon_name, addon_data in addons.items():
        section = f"addons.addons.{addon_name}"
        addon = require_dict(addon_data, errors, section)
        enabled = addon.get("enabled")
        if not isinstance(enabled, bool):
            add_error(errors, "TYPE", f"{section}.enabled must be boolean")

        validate_string_list(addon.get("required_env", []), f"{section}.required_env", errors, allow_empty=True)
        validate_string_list(addon.get("optional_env", []), f"{section}.optional_env", errors, allow_empty=True)

        tier = addon.get("tier")
        if is_non_empty_str(tier) and tier not in allowed_tiers:
            add_warning(warnings, "ADDON", f"{section}.tier is not in allowed set: {sorted(allowed_tiers)}")
        elif tier is not None and not is_non_empty_str(tier):
            add_error(errors, "TYPE", f"{section}.tier must be a non-empty string when set")

        conflicts = validate_string_list(addon.get("conflicts_with", []), f"{section}.conflicts_with", errors, allow_empty=True)
        unknown_conflicts = sorted(set(conflicts) - addon_names)
        if unknown_conflicts:
            add_warning(warnings, "ADDON", f"{section}.conflicts_with references unknown add-ons: {unknown_conflicts}")

        if addon_name in active_enabled and enabled is False:
            add_warning(warnings, "ADDON", f"active add-ons profile enables {addon_name} but addon is disabled")


def build_known_side_effects(integrations_data: dict[str, Any]) -> set[str]:
    effects = {"custom:external_write"}
    integrations = ensure_dict(integrations_data.get("integrations"))
    tool_clis = ensure_dict(integrations_data.get("tool_clis"))

    for integration_name, integration_data in integrations.items():
        row = ensure_dict(integration_data)
        for action in validate_string_list(
            row.get("write_actions", []),
            f"integrations.integrations.{integration_name}.write_actions",
            [],
            allow_empty=True,
        ):
            effects.add(f"{integration_name}:{action}")

    for cli_name, cli_data in tool_clis.items():
        row = ensure_dict(cli_data)
        for action in validate_string_list(
            row.get("approval_required_for", []),
            f"integrations.tool_clis.{cli_name}.approval_required_for",
            [],
            allow_empty=True,
        ):
            effects.add(f"tool_cli:{cli_name}:{action}")

    return effects


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
    spawn_enabled = spawn_policy.get("enabled", True)
    if not isinstance(spawn_enabled, bool):
        add_error(errors, "TYPE", "agents.spawn_policy.enabled must be boolean")
        spawn_enabled = True
    max_active = spawn_policy.get("max_active_subagents")
    if spawn_enabled:
        if not isinstance(max_active, int) or max_active < 1:
            add_error(errors, "RANGE", "agents.spawn_policy.max_active_subagents must be integer >= 1 when enabled")
    else:
        if not isinstance(max_active, int) or max_active != 0:
            add_error(errors, "RANGE", "agents.spawn_policy.max_active_subagents must be 0 when disabled")
        for agent_name, agent_data in agents.items():
            row = require_dict(agent_data, errors, f"agents.agents.{agent_name}")
            if row.get("can_spawn_subagents") is True:
                add_error(errors, "SPAWN", f"agent {agent_name} cannot allow subagents when agents.spawn_policy.enabled is false")


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


def validate_job_search(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    job_search = require_dict(data.get("job_search"), errors, "job_search.job_search")

    enabled = job_search.get("enabled")
    if not isinstance(enabled, bool):
        add_error(errors, "TYPE", "job_search.job_search.enabled must be boolean")

    mode = job_search.get("mode")
    if not is_non_empty_str(mode):
        add_error(errors, "REQ", "job_search.job_search.mode is required")
    elif mode != "manual_review_only":
        add_warning(warnings, "JOBS", "job_search mode is not manual_review_only")

    blocked_actions = validate_string_list(
        job_search.get("blocked_actions"),
        "job_search.job_search.blocked_actions",
        errors,
        allow_empty=False,
    )
    if "auto_apply" not in blocked_actions:
        add_warning(warnings, "JOBS", "job_search blocked_actions should include auto_apply")

    validate_string_list(
        job_search.get("allowed_sources"),
        "job_search.job_search.allowed_sources",
        errors,
        allow_empty=False,
    )

    outputs = require_dict(job_search.get("outputs"), errors, "job_search.job_search.outputs")
    for field_name in ("triage_dir", "daily_summary_dir", "latest_status_file"):
        if not is_non_empty_str(outputs.get(field_name)):
            add_error(errors, "REQ", f"job_search.job_search.outputs.{field_name} is required")

    inputs = require_dict(job_search.get("inputs"), errors, "job_search.job_search.inputs")
    if not is_non_empty_str(inputs.get("saved_postings_dir")):
        add_error(errors, "REQ", "job_search.job_search.inputs.saved_postings_dir is required")

    schedule = require_dict(job_search.get("schedule"), errors, "job_search.job_search.schedule")
    if not isinstance(schedule.get("enabled"), bool):
        add_error(errors, "TYPE", "job_search.job_search.schedule.enabled must be boolean")
    if not is_non_empty_str(schedule.get("timezone")):
        add_error(errors, "REQ", "job_search.job_search.schedule.timezone is required")
    delivery_time = schedule.get("delivery_time_local")
    if not is_non_empty_str(delivery_time):
        add_error(errors, "REQ", "job_search.job_search.schedule.delivery_time_local is required")
    elif not re.match(r"^\d{2}:\d{2}$", str(delivery_time)):
        add_error(errors, "TYPE", "job_search.job_search.schedule.delivery_time_local must be HH:MM")
    if not isinstance(schedule.get("allow_empty_report"), bool):
        add_error(errors, "TYPE", "job_search.job_search.schedule.allow_empty_report must be boolean")

    delivery = require_dict(job_search.get("delivery"), errors, "job_search.job_search.delivery")
    channel = delivery.get("channel")
    if not is_non_empty_str(channel):
        add_error(errors, "REQ", "job_search.job_search.delivery.channel is required")
    elif channel != "telegram":
        add_warning(warnings, "JOBS", "job_search delivery.channel is not telegram")
    for field_name in ("send_when_empty", "include_pass_section"):
        if not isinstance(delivery.get(field_name), bool):
            add_error(errors, "TYPE", f"job_search.job_search.delivery.{field_name} must be boolean")
    telegram = require_dict(delivery.get("telegram"), errors, "job_search.job_search.delivery.telegram")
    if not isinstance(telegram.get("enabled"), bool):
        add_error(errors, "TYPE", "job_search.job_search.delivery.telegram.enabled must be boolean")
    max_entries = telegram.get("max_entries_per_section")
    if not isinstance(max_entries, int) or max_entries <= 0:
        add_error(errors, "RANGE", "job_search.job_search.delivery.telegram.max_entries_per_section must be integer > 0")
    if not isinstance(telegram.get("include_output_paths"), bool):
        add_error(errors, "TYPE", "job_search.job_search.delivery.telegram.include_output_paths must be boolean")
    max_message_chars = telegram.get("max_message_chars")
    if not isinstance(max_message_chars, int) or max_message_chars < 200:
        add_error(errors, "RANGE", "job_search.job_search.delivery.telegram.max_message_chars must be integer >= 200")

    candidate_profile = require_dict(job_search.get("candidate_profile"), errors, "job_search.job_search.candidate_profile")
    for field_name in ("name", "base_location", "primary_market"):
        if not is_non_empty_str(candidate_profile.get(field_name)):
            add_error(errors, "REQ", f"job_search.job_search.candidate_profile.{field_name} is required")
    validate_string_list(
        candidate_profile.get("preferred_employment_types"),
        "job_search.job_search.candidate_profile.preferred_employment_types",
        errors,
        allow_empty=False,
    )
    validate_string_list(
        candidate_profile.get("required_overlap_notes"),
        "job_search.job_search.candidate_profile.required_overlap_notes",
        errors,
        allow_empty=False,
    )

    search_strategy = require_dict(job_search.get("search_strategy"), errors, "job_search.job_search.search_strategy")
    validate_string_list(
        search_strategy.get("core_boolean_queries"),
        "job_search.job_search.search_strategy.core_boolean_queries",
        errors,
        allow_empty=False,
    )
    validate_string_list(
        search_strategy.get("filter_notes"),
        "job_search.job_search.search_strategy.filter_notes",
        errors,
        allow_empty=False,
    )

    eligibility_rules = require_dict(job_search.get("eligibility_rules"), errors, "job_search.job_search.eligibility_rules")
    for field_name in ("allow_patterns", "possible_patterns", "deny_patterns"):
        validate_string_list(
            eligibility_rules.get(field_name),
            f"job_search.job_search.eligibility_rules.{field_name}",
            errors,
            allow_empty=False,
        )

    fit_rules = require_dict(job_search.get("fit_rules"), errors, "job_search.job_search.fit_rules")
    for field_name in ("strong_positive_keywords", "positive_keywords", "stretch_keywords", "negative_keywords"):
        validate_string_list(
            fit_rules.get(field_name),
            f"job_search.job_search.fit_rules.{field_name}",
            errors,
            allow_empty=False,
        )
    seniority_penalties = require_dict(
        fit_rules.get("seniority_penalties"),
        errors,
        "job_search.job_search.fit_rules.seniority_penalties",
    )
    if not seniority_penalties:
        add_error(errors, "REQ", "job_search.job_search.fit_rules.seniority_penalties must not be empty")
    for key, value in seniority_penalties.items():
        if not is_non_empty_str(key):
            add_error(errors, "TYPE", "job_search.job_search.fit_rules.seniority_penalties keys must be non-empty strings")
        if not isinstance(value, int) or value < 0:
            add_error(errors, "RANGE", f"job_search.job_search.fit_rules.seniority_penalties.{key} must be integer >= 0")

    summary = require_dict(job_search.get("daily_summary"), errors, "job_search.job_search.daily_summary")
    recommendation_priority = validate_string_list(
        summary.get("recommendation_priority"),
        "job_search.job_search.daily_summary.recommendation_priority",
        errors,
        allow_empty=False,
    )
    unknown_recommendations = sorted(set(recommendation_priority) - JOB_RECOMMENDATIONS)
    if unknown_recommendations:
        add_error(
            errors,
            "TYPE",
            f"job_search.job_search.daily_summary.recommendation_priority references unknown values: {unknown_recommendations}",
        )

    eligibility_priority = validate_string_list(
        summary.get("eligibility_priority"),
        "job_search.job_search.daily_summary.eligibility_priority",
        errors,
        allow_empty=False,
    )
    unknown_eligibility = sorted(set(eligibility_priority) - JOB_ELIGIBILITY)
    if unknown_eligibility:
        add_error(
            errors,
            "TYPE",
            f"job_search.job_search.daily_summary.eligibility_priority references unknown values: {unknown_eligibility}",
        )

    include_sections = validate_string_list(
        summary.get("include_sections"),
        "job_search.job_search.daily_summary.include_sections",
        errors,
        allow_empty=False,
    )
    unknown_sections = sorted(set(include_sections) - JOB_RECOMMENDATIONS)
    if unknown_sections:
        add_error(
            errors,
            "TYPE",
            f"job_search.job_search.daily_summary.include_sections references unknown values: {unknown_sections}",
        )

    max_roles = summary.get("max_roles_per_section")
    if not isinstance(max_roles, int) or max_roles <= 0:
        add_error(errors, "RANGE", "job_search.job_search.daily_summary.max_roles_per_section must be integer > 0")


def validate_knowledge_sources(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    registry = require_dict(data.get("knowledge_sources"), errors, "knowledge_sources.knowledge_sources")
    active_profile = str(registry.get("active_profile") or "").strip()
    profiles = require_dict(registry.get("profiles"), errors, "knowledge_sources.knowledge_sources.profiles")
    sources = require_dict(registry.get("sources"), errors, "knowledge_sources.knowledge_sources.sources")
    if not active_profile:
        add_error(errors, "REQ", "knowledge_sources.knowledge_sources.active_profile is required")
    elif active_profile not in profiles:
        add_error(errors, "REF", "knowledge_sources active_profile not found in profiles")

    for profile_name, profile_row in profiles.items():
        row = require_dict(profile_row, errors, f"knowledge_sources.knowledge_sources.profiles.{profile_name}")
        enabled = validate_string_list(
            row.get("enabled_sources"),
            f"knowledge_sources.knowledge_sources.profiles.{profile_name}.enabled_sources",
            errors,
            allow_empty=False,
        )
        unknown = sorted(set(enabled) - set(sources.keys()))
        if unknown:
            add_error(
                errors,
                "REF",
                f"knowledge_sources profile {profile_name} references unknown sources: {', '.join(unknown)}",
            )

    for source_name, source_row in sources.items():
        row = require_dict(source_row, errors, f"knowledge_sources.knowledge_sources.sources.{source_name}")
        if row.get("enabled") is not True and row.get("enabled") is not False:
            add_error(errors, "TYPE", f"knowledge_sources.knowledge_sources.sources.{source_name}.enabled must be boolean")
        roots = validate_string_list(
            row.get("root_candidates"),
            f"knowledge_sources.knowledge_sources.sources.{source_name}.root_candidates",
            errors,
            allow_empty=False,
        )
        if not roots:
            add_error(errors, "REQ", f"knowledge_sources source {source_name} must define root_candidates")
        top_k = row.get("top_k")
        if top_k is not None and (not isinstance(top_k, int) or top_k <= 0):
            add_error(errors, "RANGE", f"knowledge_sources.knowledge_sources.sources.{source_name}.top_k must be integer > 0")
        max_files = row.get("max_files_scan")
        if max_files is not None and (not isinstance(max_files, int) or max_files <= 0):
            add_error(errors, "RANGE", f"knowledge_sources.knowledge_sources.sources.{source_name}.max_files_scan must be integer > 0")
        digest = ensure_dict(row.get("digest"))
        if digest:
            if digest.get("enabled") is not True and digest.get("enabled") is not False:
                add_error(errors, "TYPE", f"knowledge_sources.knowledge_sources.sources.{source_name}.digest.enabled must be boolean")
            chat_env = digest.get("chat_id_env")
            if chat_env is not None and not is_non_empty_str(chat_env):
                add_error(errors, "TYPE", f"knowledge_sources.knowledge_sources.sources.{source_name}.digest.chat_id_env must be a non-empty string")


def validate_research_flow(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    flow = require_dict(data.get("research_flow"), errors, "research_flow.research_flow")
    if flow.get("enabled") is not True and flow.get("enabled") is not False:
        add_error(errors, "TYPE", "research_flow.research_flow.enabled must be boolean")
    if not is_non_empty_str(flow.get("owner_agent")):
        add_error(errors, "REQ", "research_flow.research_flow.owner_agent is required")
    if not is_non_empty_str(flow.get("default_space")):
        add_error(errors, "REQ", "research_flow.research_flow.default_space is required")
    if not is_non_empty_str(flow.get("delivery_chat_env")):
        add_error(errors, "REQ", "research_flow.research_flow.delivery_chat_env is required")
    validate_string_list(
        flow.get("shared_dropzones"),
        "research_flow.research_flow.shared_dropzones",
        errors,
        allow_empty=True,
    )
    workflows = require_dict(flow.get("workflows"), errors, "research_flow.research_flow.workflows")
    if not workflows:
        add_error(errors, "REQ", "research_flow.research_flow.workflows must not be empty")
    for workflow_name, workflow_data in workflows.items():
        row = require_dict(workflow_data, errors, f"research_flow.research_flow.workflows.{workflow_name}")
        if row.get("enabled") is not True and row.get("enabled") is not False:
            add_error(errors, "TYPE", f"research_flow.research_flow.workflows.{workflow_name}.enabled must be boolean")
        if not is_non_empty_str(row.get("kind")):
            add_error(errors, "REQ", f"research_flow.research_flow.workflows.{workflow_name}.kind is required")
        if not is_non_empty_str(row.get("status_file")):
            add_error(errors, "REQ", f"research_flow.research_flow.workflows.{workflow_name}.status_file is required")
        command = require_dict(row.get("command"), errors, f"research_flow.research_flow.workflows.{workflow_name}.command")
        validate_existing_repo_file(
            command.get("script"),
            f"research_flow.research_flow.workflows.{workflow_name}.command.script",
            errors,
            required=True,
        )
        validate_string_list(
            command.get("args"),
            f"research_flow.research_flow.workflows.{workflow_name}.command.args",
            errors,
            allow_empty=True,
        )
        schedule = require_dict(row.get("schedule"), errors, f"research_flow.research_flow.workflows.{workflow_name}.schedule")
        if schedule.get("enabled") is not True and schedule.get("enabled") is not False:
            add_error(errors, "TYPE", f"research_flow.research_flow.workflows.{workflow_name}.schedule.enabled must be boolean")
        if not is_non_empty_str(schedule.get("timezone")):
            add_error(errors, "REQ", f"research_flow.research_flow.workflows.{workflow_name}.schedule.timezone is required")
        delivery_time = schedule.get("delivery_time_local")
        if not is_non_empty_str(delivery_time):
            add_error(errors, "REQ", f"research_flow.research_flow.workflows.{workflow_name}.schedule.delivery_time_local is required")
        elif not re.fullmatch(r"\d{2}:\d{2}", str(delivery_time)):
            add_error(errors, "TYPE", f"research_flow.research_flow.workflows.{workflow_name}.schedule.delivery_time_local must be HH:MM")


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
    spawn_enabled = spawn.get("enabled", True)
    if not isinstance(spawn_enabled, bool):
        add_error(errors, "TYPE", "session_policy.spawn_controls.enabled must be boolean")
        spawn_enabled = True
    max_parallel = spawn.get("max_parallel_subagents")
    ttl_default = spawn.get("ttl_minutes_default")
    ttl_max = spawn.get("ttl_minutes_max")
    if spawn_enabled:
        if not isinstance(max_parallel, int) or max_parallel < 1:
            add_error(errors, "RANGE", "session_policy.spawn_controls.max_parallel_subagents must be integer >= 1 when enabled")
        if not isinstance(ttl_default, int) or ttl_default <= 0:
            add_error(errors, "RANGE", "session_policy.spawn_controls.ttl_minutes_default must be integer > 0 when enabled")
        if not isinstance(ttl_max, int) or ttl_max <= 0:
            add_error(errors, "RANGE", "session_policy.spawn_controls.ttl_minutes_max must be integer > 0 when enabled")
        if isinstance(ttl_default, int) and isinstance(ttl_max, int) and ttl_default > ttl_max:
            add_error(errors, "RANGE", "session_policy ttl_minutes_default cannot exceed ttl_minutes_max")
        validate_string_list(
            spawn.get("spawn_requires"),
            "session_policy.spawn_controls.spawn_requires",
            errors,
            allow_empty=False,
        )
    else:
        if not isinstance(max_parallel, int) or max_parallel != 0:
            add_error(errors, "RANGE", "session_policy.spawn_controls.max_parallel_subagents must be 0 when disabled")
        if not isinstance(ttl_default, int) or ttl_default != 0:
            add_error(errors, "RANGE", "session_policy.spawn_controls.ttl_minutes_default must be 0 when disabled")
        if not isinstance(ttl_max, int) or ttl_max != 0:
            add_error(errors, "RANGE", "session_policy.spawn_controls.ttl_minutes_max must be 0 when disabled")
        validate_string_list(
            spawn.get("spawn_requires"),
            "session_policy.spawn_controls.spawn_requires",
            errors,
            allow_empty=True,
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


def validate_memory(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    profiles = require_dict(data.get("profiles"), errors, "memory.profiles")
    active_profile = profiles.get("active_profile")
    if not is_non_empty_str(active_profile):
        add_error(errors, "REQ", "memory.profiles.active_profile is required")
        active_profile = ""
    definitions = require_dict(profiles.get("definitions"), errors, "memory.profiles.definitions")

    modules = require_dict(data.get("memory_modules"), errors, "memory.memory_modules")

    if active_profile and active_profile not in definitions:
        add_error(errors, "PROFILE", f"active memory profile not found: {active_profile}")

    for profile_name, profile_data in definitions.items():
        section = f"memory.profiles.definitions.{profile_name}"
        profile = require_dict(profile_data, errors, section)
        enabled_modules = validate_string_list(profile.get("enabled_modules"), f"{section}.enabled_modules", errors, allow_empty=False)
        for module_name in enabled_modules:
            if module_name not in modules:
                add_error(errors, "PROFILE", f"{section} references unknown module: {module_name}")
            else:
                module = require_dict(modules.get(module_name), errors, f"memory.memory_modules.{module_name}")
                if not isinstance(module.get("enabled"), bool):
                    add_error(errors, "TYPE", f"memory.memory_modules.{module_name}.enabled must be boolean")
                elif module.get("enabled") is not True:
                    add_warning(warnings, "MEM", f"profile {profile_name} enables {module_name} but module is disabled")

    structured = require_dict(modules.get("structured_markdown"), errors, "memory.memory_modules.structured_markdown")
    if structured.get("enabled") is True:
        validate_string_list(
            structured.get("source_globs"),
            "memory.memory_modules.structured_markdown.source_globs",
            errors,
            allow_empty=False,
        )
        rules = require_dict(structured.get("rules", {}), errors, "memory.memory_modules.structured_markdown.rules")
        retention = rules.get("daily_log_retention_days")
        if retention is not None and (not isinstance(retention, int) or retention <= 0):
            add_error(
                errors,
                "RANGE",
                "memory.memory_modules.structured_markdown.rules.daily_log_retention_days must be integer > 0",
            )

    semantic = require_dict(modules.get("semantic_embeddings"), errors, "memory.memory_modules.semantic_embeddings")
    semantic_enabled = semantic.get("enabled") is True
    if semantic_enabled:
        if not is_non_empty_str(semantic.get("provider")):
            add_error(errors, "REQ", "memory.memory_modules.semantic_embeddings.provider is required")
        if not is_non_empty_str(semantic.get("model")):
            add_error(errors, "REQ", "memory.memory_modules.semantic_embeddings.model is required")
        validate_string_list(
            semantic.get("required_env"),
            "memory.memory_modules.semantic_embeddings.required_env",
            errors,
            allow_empty=False,
        )
        validate_string_list(
            semantic.get("optional_env", []),
            "memory.memory_modules.semantic_embeddings.optional_env",
            errors,
            allow_empty=True,
        )

        chunking = require_dict(semantic.get("chunking"), errors, "memory.memory_modules.semantic_embeddings.chunking")
        max_chars = chunking.get("max_chars_per_chunk")
        overlap = chunking.get("overlap_chars")
        if not isinstance(max_chars, int) or max_chars <= 0:
            add_error(errors, "RANGE", "memory semantic chunking.max_chars_per_chunk must be integer > 0")
        if not isinstance(overlap, int) or overlap < 0:
            add_error(errors, "RANGE", "memory semantic chunking.overlap_chars must be integer >= 0")
        elif isinstance(max_chars, int) and overlap >= max_chars:
            add_warning(warnings, "MEM", "memory overlap_chars >= max_chars_per_chunk can reduce chunk quality")

        retrieval = require_dict(semantic.get("retrieval"), errors, "memory.memory_modules.semantic_embeddings.retrieval")
        top_k = retrieval.get("top_k_default")
        if not isinstance(top_k, int) or top_k <= 0:
            add_error(errors, "RANGE", "memory semantic retrieval.top_k_default must be integer > 0")
        min_similarity = retrieval.get("min_similarity")
        if not isinstance(min_similarity, (int, float)) or not (0 <= float(min_similarity) <= 1):
            add_error(errors, "RANGE", "memory semantic retrieval.min_similarity must be between 0 and 1")

        budget = require_dict(semantic.get("budget_controls"), errors, "memory.memory_modules.semantic_embeddings.budget_controls")
        for field in ("max_new_embeddings_per_run", "max_embedding_chars_per_day"):
            value = budget.get(field)
            if not isinstance(value, int) or value <= 0:
                add_error(errors, "RANGE", f"memory semantic budget {field} must be integer > 0")

        storage = require_dict(semantic.get("storage"), errors, "memory.memory_modules.semantic_embeddings.storage")
        if not is_non_empty_str(storage.get("sqlite_db_path")):
            add_error(errors, "REQ", "memory semantic storage.sqlite_db_path is required")

    sqlite_state = require_dict(modules.get("sqlite_state"), errors, "memory.memory_modules.sqlite_state")
    sqlite_enabled = sqlite_state.get("enabled") is True
    if sqlite_enabled:
        if not is_non_empty_str(sqlite_state.get("db_path")):
            add_error(errors, "REQ", "memory.sqlite_state.db_path is required")
        schema_file = sqlite_state.get("schema_file")
        if not is_non_empty_str(schema_file):
            add_error(errors, "REQ", "memory.sqlite_state.schema_file is required")
        else:
            schema_path = Path(str(schema_file))
            if not schema_path.is_absolute():
                schema_path = ROOT / schema_path
            if not schema_path.exists():
                add_warning(warnings, "MEM", f"memory sqlite schema file not found: {schema_file}")

        validate_string_list(sqlite_state.get("tables"), "memory.sqlite_state.tables", errors, allow_empty=False)

        pragmas = require_dict(sqlite_state.get("pragmas", {}), errors, "memory.sqlite_state.pragmas")
        for key, value in pragmas.items():
            if not is_non_empty_str(key):
                add_error(errors, "TYPE", "memory.sqlite_state.pragmas keys must be non-empty strings")
            if not isinstance(value, (str, int, float)):
                add_error(errors, "TYPE", f"memory.sqlite_state.pragmas.{key} must be string/int/float")

    if semantic_enabled and not sqlite_enabled:
        add_warning(warnings, "MEM", "semantic_embeddings enabled while sqlite_state disabled")

    runtime = require_dict(data.get("runtime"), errors, "memory.runtime")
    for field in ("compact_when_context_tokens_over", "checkpoint_every_minutes"):
        value = runtime.get(field)
        if value is not None and (not isinstance(value, int) or value <= 0):
            add_error(errors, "RANGE", f"memory.runtime.{field} must be integer > 0")


def validate_dashboard(
    data: dict[str, Any],
    integrations_data: dict[str, Any],
    memory_data: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    dashboard = require_dict(data.get("dashboard"), errors, "dashboard.dashboard")

    adapters = require_dict(dashboard.get("adapters"), errors, "dashboard.dashboard.adapters")
    for field in ("local_telemetry_enabled", "codexbar_cost_enabled", "codexbar_usage_enabled"):
        value = adapters.get(field)
        if not isinstance(value, bool):
            add_error(errors, "TYPE", f"dashboard.dashboard.adapters.{field} must be boolean")

    codexbar = require_dict(dashboard.get("codexbar"), errors, "dashboard.dashboard.codexbar")
    provider = codexbar.get("provider")
    if not is_non_empty_str(provider):
        add_error(errors, "REQ", "dashboard.dashboard.codexbar.provider is required")
    elif provider not in {"openai", "anthropic", "google", "all"}:
        add_error(errors, "TYPE", "dashboard.dashboard.codexbar.provider must be one of: openai, anthropic, google, all")
    timeout = codexbar.get("timeout_seconds")
    if not isinstance(timeout, int) or timeout <= 0:
        add_error(errors, "RANGE", "dashboard.dashboard.codexbar.timeout_seconds must be integer > 0")

    ui = require_dict(dashboard.get("ui"), errors, "dashboard.dashboard.ui")
    refresh = ui.get("auto_refresh_seconds")
    if not isinstance(refresh, int) or refresh <= 0:
        add_error(errors, "RANGE", "dashboard.dashboard.ui.auto_refresh_seconds must be integer > 0")

    auth = require_dict(dashboard.get("auth"), errors, "dashboard.dashboard.auth")
    require_token = auth.get("require_token")
    if not isinstance(require_token, bool):
        add_error(errors, "TYPE", "dashboard.dashboard.auth.require_token must be boolean")
    token_env_key = auth.get("token_env_key")
    if not is_non_empty_str(token_env_key):
        add_error(errors, "REQ", "dashboard.dashboard.auth.token_env_key is required")
    ttl = auth.get("session_ttl_minutes")
    if not isinstance(ttl, int) or ttl <= 0:
        add_error(errors, "RANGE", "dashboard.dashboard.auth.session_ttl_minutes must be integer > 0")
    allow_generated = auth.get("allow_generated_token")
    if allow_generated is not None and not isinstance(allow_generated, bool):
        add_error(errors, "TYPE", "dashboard.dashboard.auth.allow_generated_token must be boolean")
    if require_token is True and allow_generated is True:
        add_warning(
            warnings,
            "DASH",
            "dashboard auth allows generated tokens; keep this limited to explicit local dev mode",
        )

    integration_profiles = ensure_dict(ensure_dict(integrations_data.get("profiles")).get("definitions"))
    memory_profiles = ensure_dict(ensure_dict(memory_data.get("profiles")).get("definitions"))
    integration_names = set(ensure_dict(integrations_data.get("integrations")).keys())
    memory_module_names = set(ensure_dict(memory_data.get("memory_modules")).keys())
    n8n_modules = set(ensure_dict(ensure_dict(ensure_dict(integrations_data.get("integrations")).get("n8n")).get("modules")).keys())
    known_side_effects = build_known_side_effects(integrations_data)

    presets = require_dict(dashboard.get("presets"), errors, "dashboard.dashboard.presets")
    for preset_name, preset_data in presets.items():
        section = f"dashboard.dashboard.presets.{preset_name}"
        preset = require_dict(preset_data, errors, section)
        integrations_profile = preset.get("integrations_profile")
        if not is_non_empty_str(integrations_profile):
            add_error(errors, "REQ", f"{section}.integrations_profile is required")
        elif integrations_profile not in integration_profiles:
            add_error(errors, "PROFILE", f"{section}.integrations_profile references unknown profile: {integrations_profile}")

        memory_profile = preset.get("memory_profile")
        if not is_non_empty_str(memory_profile):
            add_error(errors, "REQ", f"{section}.memory_profile is required")
        elif memory_profile not in memory_profiles:
            add_error(errors, "PROFILE", f"{section}.memory_profile references unknown profile: {memory_profile}")

        for toggle_name in ensure_dict(preset.get("integration_toggles")).keys():
            if toggle_name not in integration_names:
                add_error(errors, "PROFILE", f"{section}.integration_toggles references unknown integration: {toggle_name}")
        for toggle_name in ensure_dict(preset.get("memory_module_toggles")).keys():
            if toggle_name not in memory_module_names:
                add_error(errors, "PROFILE", f"{section}.memory_module_toggles references unknown memory module: {toggle_name}")
        for toggle_name in ensure_dict(preset.get("n8n_module_toggles")).keys():
            if toggle_name not in n8n_modules:
                add_error(errors, "PROFILE", f"{section}.n8n_module_toggles references unknown n8n module: {toggle_name}")

    templates = require_dict(dashboard.get("task_templates"), errors, "dashboard.dashboard.task_templates")
    for template_name, template_data in templates.items():
        section = f"dashboard.dashboard.task_templates.{template_name}"
        template = require_dict(template_data, errors, section)
        if not is_non_empty_str(template.get("title")):
            add_error(errors, "REQ", f"{section}.title is required")
        priority = template.get("priority")
        if not is_non_empty_str(priority) or priority not in PRIORITY_LEVELS:
            add_error(errors, "TYPE", f"{section}.priority must be one of: {sorted(PRIORITY_LEVELS)}")
        status = template.get("status")
        if not is_non_empty_str(status) or status not in TASK_STATUSES:
            add_error(errors, "TYPE", f"{section}.status must be one of: {sorted(TASK_STATUSES)}")
        default_assignees = validate_string_list(template.get("default_assignees", []), f"{section}.default_assignees", errors, allow_empty=False)
        if not default_assignees:
            add_warning(warnings, "DASH", f"{section}.default_assignees is empty")
        due_in_hours = template.get("due_in_hours")
        if due_in_hours is not None and (not isinstance(due_in_hours, int) or due_in_hours <= 0):
            add_error(errors, "RANGE", f"{section}.due_in_hours must be integer > 0")
        side_effects = validate_string_list(template.get("side_effects", []), f"{section}.side_effects", errors, allow_empty=True)
        unknown_side_effects = sorted(set(side_effects) - known_side_effects)
        if unknown_side_effects:
            add_error(errors, "TYPE", f"{section}.side_effects references unknown values: {unknown_side_effects}")
        requires_approval = template.get("requires_approval")
        if requires_approval is not None and not isinstance(requires_approval, bool):
            add_error(errors, "TYPE", f"{section}.requires_approval must be boolean")
        if side_effects and requires_approval is False:
            add_warning(warnings, "DASH", f"{section} has side_effects but requires_approval=false")

    approvals = require_dict(dashboard.get("approvals"), errors, "dashboard.dashboard.approvals")
    if not isinstance(approvals.get("require_for_external_writes"), bool):
        add_error(errors, "TYPE", "dashboard.dashboard.approvals.require_for_external_writes must be boolean")
    validate_string_list(
        approvals.get("external_write_keywords"),
        "dashboard.dashboard.approvals.external_write_keywords",
        errors,
        allow_empty=False,
    )
    auto_expire = approvals.get("auto_expire_hours")
    if not isinstance(auto_expire, int) or auto_expire <= 0:
        add_error(errors, "RANGE", "dashboard.dashboard.approvals.auto_expire_hours must be integer > 0")


def validate_spawn_alignment(
    agents_data: dict[str, Any],
    session_policy_data: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    agents_spawn = require_dict(agents_data.get("spawn_policy"), errors, "agents.spawn_policy")
    session_spawn = require_dict(session_policy_data.get("spawn_controls"), errors, "session_policy.spawn_controls")

    if agents_spawn.get("enabled", True) is False or session_spawn.get("enabled", True) is False:
        return

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
    if "addons" in loaded:
        validate_addons(require_dict(loaded["addons"], errors, "addons"), errors, warnings)
    if "memory" in loaded:
        validate_memory(require_dict(loaded["memory"], errors, "memory"), errors, warnings)
    if "dashboard" in loaded and "integrations" in loaded and "memory" in loaded:
        validate_dashboard(
            require_dict(loaded["dashboard"], errors, "dashboard"),
            require_dict(loaded["integrations"], errors, "integrations"),
            require_dict(loaded["memory"], errors, "memory"),
            errors,
            warnings,
        )

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
    if "job_search" in loaded:
        validate_job_search(require_dict(loaded["job_search"], errors, "job_search"), errors, warnings)
    if "knowledge_sources" in loaded:
        validate_knowledge_sources(require_dict(loaded["knowledge_sources"], errors, "knowledge_sources"), errors, warnings)
    if "research_flow" in loaded:
        validate_research_flow(require_dict(loaded["research_flow"], errors, "research_flow"), errors, warnings)

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
