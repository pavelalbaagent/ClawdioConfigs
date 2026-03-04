#!/usr/bin/env python3
"""Resolve model lane/provider fallbacks from config/models.yaml."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "models.yaml"


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
    return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]


def lane_level(lane: str) -> int:
    match = re.match(r"^L(\d+)_", lane)
    if not match:
        return 999
    return int(match.group(1))


def find_situation_by_intent_tag(decision_matrix: dict[str, Any], intent_tag: str) -> str | None:
    for situation, row in decision_matrix.items():
        if not isinstance(situation, str):
            continue
        tags = ensure_string_list(ensure_dict(row).get("intent_tags"))
        if intent_tag in tags:
            return situation
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve model lane/provider policy for a task situation")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="path to config/models.yaml")
    parser.add_argument("--mode", help="routing mode name from routing.usage_modes")
    parser.add_argument("--situation", help="routing situation from routing.decision_matrix")
    parser.add_argument("--intent-tag", help="intent tag to match a situation (for example: code_generation)")
    parser.add_argument("--list-situations", action="store_true", help="list known situations and exit")
    parser.add_argument("--list-modes", action="store_true", help="list known routing modes and exit")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        return 1

    data = ensure_dict(load_yaml(config_path))
    routing = ensure_dict(data.get("routing"))
    lanes = ensure_dict(routing.get("lanes"))
    fallback_order = ensure_string_list(routing.get("fallback_order"))
    usage_modes = ensure_dict(routing.get("usage_modes"))
    decision_matrix = ensure_dict(routing.get("decision_matrix"))

    if args.list_modes:
        for mode in usage_modes.keys():
            print(mode)
        return 0

    if args.list_situations:
        for situation in decision_matrix.keys():
            print(situation)
        return 0

    if args.mode:
        mode_name = args.mode
    elif "balanced_default" in usage_modes:
        mode_name = "balanced_default"
    else:
        mode_name = next(iter(usage_modes.keys()), "")

    mode_cfg = ensure_dict(usage_modes.get(mode_name))
    if mode_name and not mode_cfg:
        print(f"Unknown mode: {mode_name}")
        return 1

    situation_name = args.situation
    if not situation_name and args.intent_tag:
        matched = find_situation_by_intent_tag(decision_matrix, args.intent_tag.strip())
        if matched:
            situation_name = matched

    situation_cfg = ensure_dict(decision_matrix.get(situation_name)) if situation_name else {}
    if situation_name and not situation_cfg:
        print(f"Unknown situation: {situation_name}")
        return 1

    preferred_lane = str(situation_cfg.get("preferred_lane", "")).strip()
    if not preferred_lane:
        preferred_lane = str(mode_cfg.get("default_lane", "")).strip()
    if not preferred_lane and fallback_order:
        preferred_lane = fallback_order[0]
    if not preferred_lane:
        print("Could not resolve preferred lane")
        return 1
    if preferred_lane not in lanes:
        print(f"Resolved lane is not defined in config: {preferred_lane}")
        return 1

    lane_cfg = ensure_dict(lanes.get(preferred_lane))
    provider_preference = ensure_string_list(situation_cfg.get("provider_preference"))
    if not provider_preference:
        provider_preference = ensure_string_list(lane_cfg.get("provider_priority"))
    if not provider_preference:
        provider = str(lane_cfg.get("provider", "")).strip()
        provider_preference = [provider] if provider else []

    fallback_lanes = ensure_string_list(situation_cfg.get("fallback_lanes"))
    if not fallback_lanes:
        fallback_lanes = [lane for lane in fallback_order if lane != preferred_lane]

    max_auto_lane = str(mode_cfg.get("allow_auto_escalation_up_to", "")).strip()
    if max_auto_lane and max_auto_lane in lanes:
        max_level = lane_level(max_auto_lane)
        fallback_lanes = [
            lane
            for lane in fallback_lanes
            if lane not in lanes or lane_level(lane) <= max_level
        ]

    lane_approval = lane_cfg.get("approval_required") is True
    decision_approval = situation_cfg.get("approval_required") is True
    approval_required = lane_approval or decision_approval

    resolved = {
        "config": str(config_path),
        "mode": mode_name or None,
        "situation": situation_name or None,
        "intent_tag": args.intent_tag or None,
        "preferred_lane": preferred_lane,
        "provider_preference": provider_preference,
        "fallback_lanes": fallback_lanes,
        "approval_required": approval_required,
        "lane_limits": {
            "max_input_tokens": lane_cfg.get("max_input_tokens"),
            "max_output_tokens": lane_cfg.get("max_output_tokens"),
        },
    }

    if args.json:
        print(json.dumps(resolved, indent=2))
        return 0

    print(f"Config: {resolved['config']}")
    print(f"Mode: {resolved['mode'] or '-'}")
    print(f"Situation: {resolved['situation'] or '-'}")
    print(f"Intent tag: {resolved['intent_tag'] or '-'}")
    print(f"Preferred lane: {resolved['preferred_lane']}")
    print(
        "Provider preference: "
        + (", ".join(resolved["provider_preference"]) if resolved["provider_preference"] else "-")
    )
    print("Fallback lanes: " + (", ".join(resolved["fallback_lanes"]) if resolved["fallback_lanes"] else "-"))
    print(f"Approval required: {'yes' if resolved['approval_required'] else 'no'}")
    print(
        "Lane limits: "
        f"input={resolved['lane_limits']['max_input_tokens']} output={resolved['lane_limits']['max_output_tokens']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
