#!/usr/bin/env python3
"""Evaluate provider wiring and run optional smoke probes."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from env_file_utils import load_env_file
import openai_session_transport


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODELS = ROOT / "config" / "models.yaml"
DEFAULT_MEMORY = ROOT / "config" / "memory.yaml"
DEFAULT_INTEGRATIONS = ROOT / "config" / "integrations.yaml"
DEFAULT_AGENTS = ROOT / "config" / "agents.yaml"
DEFAULT_OUTPUT = ROOT / "data" / "provider-smoke-status.json"


def _parse_with_python_yaml(path: Path) -> Any:
    import yaml  # type: ignore

    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


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
    return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]


def ensure_string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, str) and key.strip() and item.strip():
            out[key.strip()] = item.strip()
    return out


def iso_now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_env_file(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    return load_env_file(path, strict=True)


def env_get(name: str, env_file_values: dict[str, str]) -> str:
    value = env_file_values.get(name)
    if value is None:
        value = os.environ.get(name, "")
    return value.strip()


def command_path(name: str) -> str | None:
    resolved = shutil.which(name)
    return resolved or None


def resolve_lane_candidates(
    lane_name: str,
    lane_cfg: dict[str, Any],
    provider_inventory: dict[str, Any],
) -> list[dict[str, Any]]:
    provider_models = ensure_string_dict(lane_cfg.get("provider_models"))
    candidates: list[dict[str, Any]] = []
    for provider_name in ensure_string_list(lane_cfg.get("provider_priority")):
        provider_cfg = ensure_dict(provider_inventory.get(provider_name))
        model = provider_models.get(provider_name)
        if not model:
            model = str(provider_cfg.get("default_model", "")).strip()
        if not model:
            override_env = str(provider_cfg.get("model_env_override", "")).strip()
            if override_env:
                model = f"env:{override_env}"
        candidates.append(
            {
                "provider": provider_name,
                "model": model or None,
                "budget_type": str(provider_cfg.get("budget_type", "")).strip() or None,
            }
        )
    return candidates


def _request_json(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    req_headers = headers or {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers = {**req_headers, "Content-Type": "application/json"}
    req = urllib.request.Request(url, method=method.upper(), data=data, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"http {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc.reason}") from exc
    return ensure_dict(json.loads(body or "{}"))


def _probe_google(api_key: str, model: str) -> dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    started = time.perf_counter()
    data = _request_json(
        url,
        method="POST",
        payload={
            "contents": [{"parts": [{"text": "Reply with OK only."}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 8},
        },
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("google response missing candidates")
    return {"ok": True, "latency_ms": latency_ms}


def _probe_openrouter(api_key: str, model: str) -> dict[str, Any]:
    started = time.perf_counter()
    data = _request_json(
        "https://openrouter.ai/api/v1/chat/completions",
        method="POST",
        headers={"Authorization": f"Bearer {api_key}"},
        payload={
            "model": model,
            "messages": [{"role": "user", "content": "Reply with OK only."}],
            "max_tokens": 8,
        },
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("openrouter response missing choices")
    return {"ok": True, "latency_ms": latency_ms}


def _probe_anthropic(api_key: str, model: str) -> dict[str, Any]:
    started = time.perf_counter()
    data = _request_json(
        "https://api.anthropic.com/v1/messages",
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        payload={
            "model": model,
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "Reply with OK only."}],
        },
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    content = data.get("content")
    if not isinstance(content, list) or not content:
        raise RuntimeError("anthropic response missing content")
    return {"ok": True, "latency_ms": latency_ms}


def _probe_openai_embeddings(api_key: str, model: str) -> dict[str, Any]:
    started = time.perf_counter()
    data = _request_json(
        "https://api.openai.com/v1/embeddings",
        method="POST",
        headers={"Authorization": f"Bearer {api_key}"},
        payload={"model": model, "input": "provider smoke check"},
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    rows = data.get("data")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("openai embeddings response missing data")
    return {"ok": True, "latency_ms": latency_ms}


def _probe_cli(command: str) -> dict[str, Any]:
    started = time.perf_counter()
    proc = subprocess.run([command, "--version"], capture_output=True, text=True, timeout=20)
    latency_ms = int((time.perf_counter() - started) * 1000)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"{command} --version failed")
    first_line = (proc.stdout.strip() or proc.stderr.strip()).splitlines()[0] if (proc.stdout or proc.stderr) else ""
    return {"ok": True, "latency_ms": latency_ms, "version": first_line}


def _probe_provider(provider_name: str, provider_cfg: dict[str, Any], resolved_model: str | None, env_file_values: dict[str, str]) -> dict[str, Any]:
    if provider_name == "google_ai_studio_free":
        api_key = env_get("GEMINI_API_KEY", env_file_values)
        if not api_key:
            raise RuntimeError("missing GEMINI_API_KEY")
        return _probe_google(api_key, resolved_model or str(provider_cfg.get("healthcheck_model", "")).strip())
    if provider_name == "openrouter_free_overflow":
        api_key = env_get("OPENROUTER_API_KEY", env_file_values)
        if not api_key:
            raise RuntimeError("missing OPENROUTER_API_KEY")
        return _probe_openrouter(api_key, resolved_model or str(provider_cfg.get("healthcheck_model", "")).strip())
    if provider_name == "anthropic_credit_pool":
        api_key = env_get("ANTHROPIC_API_KEY", env_file_values)
        if not api_key:
            raise RuntimeError("missing ANTHROPIC_API_KEY")
        return _probe_anthropic(api_key, resolved_model or str(provider_cfg.get("healthcheck_model", "")).strip())
    if provider_name == "openai_embeddings":
        api_key = env_get("OPENAI_API_KEY", env_file_values)
        if not api_key:
            raise RuntimeError("missing OPENAI_API_KEY")
        return _probe_openai_embeddings(api_key, resolved_model or str(provider_cfg.get("healthcheck_model", "")).strip())
    if provider_name == "openai_subscription_session":
        return openai_session_transport.probe_codex_session(
            root=ROOT,
            model=resolved_model or str(provider_cfg.get("healthcheck_model", "")).strip() or "gpt-5-mini",
        )
    if provider_name in {"codex_subscription_cli", "openai_subscription_session", "gemini_cli_local"}:
        command = str(provider_cfg.get("required_command", "")).strip()
        if not command:
            raise RuntimeError("missing required_command")
        return _probe_cli(command)
    raise RuntimeError(f"no probe implementation for provider {provider_name}")


def collect_status(
    *,
    models_path: Path = DEFAULT_MODELS,
    memory_path: Path = DEFAULT_MEMORY,
    integrations_path: Path = DEFAULT_INTEGRATIONS,
    agents_path: Path = DEFAULT_AGENTS,
    env_file: Path | None = None,
    live: bool = False,
) -> dict[str, Any]:
    env_file_values = parse_env_file(env_file)
    models_data = ensure_dict(load_yaml(models_path))
    memory_data = ensure_dict(load_yaml(memory_path))
    integrations_data = ensure_dict(load_yaml(integrations_path))
    agents_data = ensure_dict(load_yaml(agents_path))

    routing = ensure_dict(models_data.get("routing"))
    lanes = ensure_dict(routing.get("lanes"))
    decision_matrix = ensure_dict(routing.get("decision_matrix"))
    provider_inventory = ensure_dict(models_data.get("provider_inventory"))

    memory_profiles = ensure_dict(memory_data.get("profiles"))
    memory_active_name = str(memory_profiles.get("active_profile", "")).strip()
    memory_profile = ensure_dict(ensure_dict(memory_profiles.get("definitions")).get(memory_active_name))
    memory_modules = ensure_dict(memory_data.get("memory_modules"))

    integrations_profiles = ensure_dict(integrations_data.get("profiles"))
    integrations_active_name = str(integrations_profiles.get("active_profile", "")).strip()
    integrations_profile = ensure_dict(ensure_dict(integrations_profiles.get("definitions")).get(integrations_active_name))

    routing_active_mode = str(ensure_dict(agents_data.get("routing_overrides")).get("active_mode", "")).strip() or "balanced_default"

    if "openai_embeddings" not in provider_inventory and "semantic_embeddings" in memory_modules:
        semantic = ensure_dict(memory_modules.get("semantic_embeddings"))
        provider_inventory["openai_embeddings"] = {
            "required_env": ensure_string_list(semantic.get("required_env")),
            "budget_type": "embedding_index",
            "default_model": str(semantic.get("model", "")).strip() or None,
            "healthcheck_model": str(semantic.get("model", "")).strip() or None,
            "transport": "openai_embeddings",
        }

    referenced_by_provider: dict[str, list[str]] = {}
    lane_rows: list[dict[str, Any]] = []
    for lane_name, lane_raw in lanes.items():
        lane_cfg = ensure_dict(lane_raw)
        candidates = resolve_lane_candidates(lane_name, lane_cfg, provider_inventory)
        for candidate in candidates:
            referenced_by_provider.setdefault(str(candidate["provider"]), []).append(lane_name)
        lane_rows.append(
            {
                "lane": lane_name,
                "model": str(lane_cfg.get("model", "")).strip() or None,
                "provider_candidates": candidates,
                "manual_tool_fallbacks": ensure_string_list(lane_cfg.get("manual_tool_fallbacks")),
                "approval_required": lane_cfg.get("approval_required") is True,
                "max_input_tokens": lane_cfg.get("max_input_tokens"),
                "max_output_tokens": lane_cfg.get("max_output_tokens"),
            }
        )

    situation_rows: list[dict[str, Any]] = []
    for situation_name, situation_raw in sorted(decision_matrix.items(), key=lambda kv: kv[0]):
        situation_cfg = ensure_dict(situation_raw)
        preferred_lane = str(situation_cfg.get("preferred_lane", "")).strip()
        lane_cfg = ensure_dict(lanes.get(preferred_lane))
        candidates = resolve_lane_candidates(preferred_lane, lane_cfg, provider_inventory) if preferred_lane else []
        situation_rows.append(
            {
                "name": situation_name,
                "preferred_lane": preferred_lane or None,
                "provider_candidates": candidates,
                "approval_required": situation_cfg.get("approval_required") is True or lane_cfg.get("approval_required") is True,
            }
        )

    provider_rows: list[dict[str, Any]] = []
    for provider_name, provider_raw in sorted(provider_inventory.items(), key=lambda kv: kv[0]):
        provider_cfg = ensure_dict(provider_raw)
        required_env = ensure_string_list(provider_cfg.get("required_env"))
        missing_env = [name for name in required_env if not env_get(name, env_file_values)]
        required_command = str(provider_cfg.get("required_command", "")).strip() or None
        resolved_command = command_path(required_command) if required_command else None
        command_missing = bool(required_command and not resolved_command)
        default_model = str(provider_cfg.get("default_model", "")).strip() or None
        override_env = str(provider_cfg.get("model_env_override", "")).strip()
        resolved_default_model = env_get(override_env, env_file_values) if override_env else ""
        if not resolved_default_model:
            resolved_default_model = default_model or ""
        configured = not missing_env and not command_missing
        locally_usable = configured
        local_status = "ready" if locally_usable else ("missing_env" if missing_env else "missing_command")
        live_probe = {"attempted": False, "ok": False, "error": None, "latency_ms": None, "version": None}
        if live and locally_usable:
            try:
                probe = _probe_provider(provider_name, provider_cfg, resolved_default_model or default_model, env_file_values)
                live_probe.update({"attempted": True, "ok": True, **probe})
            except Exception as exc:
                live_probe.update({"attempted": True, "ok": False, "error": str(exc)})
        provider_rows.append(
            {
                "provider": provider_name,
                "transport": str(provider_cfg.get("transport", "")).strip() or None,
                "budget_type": str(provider_cfg.get("budget_type", "")).strip() or None,
                "required_env": required_env,
                "missing_env": missing_env,
                "required_command": required_command,
                "command_path": resolved_command,
                "default_model": default_model,
                "resolved_default_model": resolved_default_model or default_model,
                "healthcheck_model": str(provider_cfg.get("healthcheck_model", "")).strip() or None,
                "supported_models": ensure_string_list(provider_cfg.get("supported_models")),
                "referenced_by_lanes": sorted(set(referenced_by_provider.get(provider_name, []))),
                "enabled_in_active_routing": bool(referenced_by_provider.get(provider_name)),
                "enabled_in_active_memory": provider_name == "openai_embeddings"
                and "semantic_embeddings" in ensure_string_list(memory_profile.get("enabled_modules")),
                "local_status": local_status,
                "configured": configured,
                "locally_usable": locally_usable,
                "live_probe": live_probe,
            }
        )

    manual_tools = []
    tool_clis = ensure_dict(integrations_data.get("tool_clis"))
    for tool_name, tool_raw in sorted(tool_clis.items(), key=lambda kv: kv[0]):
        tool_cfg = ensure_dict(tool_raw)
        command = str(tool_cfg.get("command", "")).strip()
        if not command:
            continue
        manual_tools.append(
            {
                "name": tool_name,
                "command": command,
                "command_path": command_path(command),
                "required_env": ensure_string_list(tool_cfg.get("required_env")),
                "optional_env": ensure_string_list(tool_cfg.get("optional_env")),
            }
        )

    summary = {
        "total_providers": len(provider_rows),
        "configured_count": sum(1 for row in provider_rows if row["configured"]),
        "locally_usable_count": sum(1 for row in provider_rows if row["locally_usable"]),
        "live_ok_count": sum(1 for row in provider_rows if ensure_dict(row.get("live_probe")).get("ok") is True),
        "missing_env_count": sum(1 for row in provider_rows if row["local_status"] == "missing_env"),
        "missing_command_count": sum(1 for row in provider_rows if row["local_status"] == "missing_command"),
    }

    return {
        "generated_at": iso_now_utc(),
        "live_probe": live,
        "env_file": str(env_file) if env_file else None,
        "active_profiles": {
            "integrations": integrations_active_name or None,
            "memory": memory_active_name or None,
            "routing_mode": routing_active_mode or None,
        },
        "summary": summary,
        "providers": provider_rows,
        "manual_tools": manual_tools,
        "lanes": lane_rows,
        "situations": situation_rows,
    }


def write_snapshot(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check configured providers and optionally run live smoke probes")
    parser.add_argument("--models-config", default=str(DEFAULT_MODELS))
    parser.add_argument("--memory-config", default=str(DEFAULT_MEMORY))
    parser.add_argument("--integrations-config", default=str(DEFAULT_INTEGRATIONS))
    parser.add_argument("--agents-config", default=str(DEFAULT_AGENTS))
    parser.add_argument("--env-file", help="dotenv-style env file to use without exporting vars")
    parser.add_argument("--live", action="store_true", help="run live provider probes where credentials are present")
    parser.add_argument("--write-snapshot", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = collect_status(
        models_path=Path(args.models_config).expanduser().resolve(),
        memory_path=Path(args.memory_config).expanduser().resolve(),
        integrations_path=Path(args.integrations_config).expanduser().resolve(),
        agents_path=Path(args.agents_config).expanduser().resolve(),
        env_file=Path(args.env_file).expanduser().resolve() if args.env_file else None,
        live=args.live,
    )
    snapshot_path = Path(args.write_snapshot).expanduser().resolve()
    write_snapshot(snapshot_path, payload)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Provider snapshot written to {snapshot_path}")
        print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
