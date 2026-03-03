#!/usr/bin/env python3
"""Generate a markdown usage report from model call NDJSON logs."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Totals:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    errors: int = 0
    fallbacks: int = 0
    estimated_cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def read_ndjson(path: Path) -> list[dict]:
    entries: list[dict] = []
    if not path.exists():
        return entries
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def accumulate(totals: Totals, entry: dict) -> None:
    totals.calls += 1
    totals.prompt_tokens += int(entry.get("prompt_tokens", 0) or 0)
    totals.completion_tokens += int(entry.get("completion_tokens", 0) or 0)
    totals.latency_ms += int(entry.get("latency_ms", 0) or 0)
    totals.estimated_cost_usd += float(entry.get("estimated_cost_usd", 0.0) or 0.0)
    status = str(entry.get("status", "")).lower()
    if status == "error":
        totals.errors += 1
    if status == "fallback":
        totals.fallbacks += 1


def render(entries: list[dict]) -> str:
    overall = Totals()
    by_lane: dict[str, Totals] = defaultdict(Totals)
    by_model: dict[str, Totals] = defaultdict(Totals)
    fallback_reasons: dict[str, int] = defaultdict(int)

    for entry in entries:
        lane = str(entry.get("lane", "unknown"))
        model = str(entry.get("model", "unknown"))
        accumulate(overall, entry)
        accumulate(by_lane[lane], entry)
        accumulate(by_model[model], entry)
        reason = entry.get("fallback_reason")
        if reason:
            fallback_reasons[str(reason)] += 1

    lines: list[str] = []
    lines.append("# Model Usage Report")
    lines.append("")
    lines.append(f"- Calls: {overall.calls}")
    lines.append(f"- Prompt tokens: {overall.prompt_tokens}")
    lines.append(f"- Completion tokens: {overall.completion_tokens}")
    lines.append(f"- Total tokens: {overall.total_tokens}")
    lines.append(f"- Errors: {overall.errors}")
    lines.append(f"- Fallbacks: {overall.fallbacks}")
    lines.append(f"- Estimated cost (USD): {overall.estimated_cost_usd:.4f}")
    lines.append("")

    lines.append("## By Lane")
    lines.append("| Lane | Calls | Tokens | Errors | Fallbacks | Avg Latency (ms) |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for lane, totals in sorted(by_lane.items(), key=lambda kv: kv[0]):
        avg_latency = int(totals.latency_ms / totals.calls) if totals.calls else 0
        lines.append(
            f"| {lane} | {totals.calls} | {totals.total_tokens} | {totals.errors} | {totals.fallbacks} | {avg_latency} |"
        )
    lines.append("")

    lines.append("## By Model")
    lines.append("| Model | Calls | Tokens | Errors | Fallbacks |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for model, totals in sorted(by_model.items(), key=lambda kv: kv[0]):
        lines.append(
            f"| {model} | {totals.calls} | {totals.total_tokens} | {totals.errors} | {totals.fallbacks} |"
        )
    lines.append("")

    lines.append("## Fallback Reasons")
    if fallback_reasons:
        for reason, count in sorted(fallback_reasons.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate model usage report from NDJSON logs")
    parser.add_argument("--input", required=True, help="path to model call NDJSON")
    parser.add_argument("--output", help="optional output markdown file")
    args = parser.parse_args()

    entries = read_ndjson(Path(args.input))
    report = render(entries)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
    else:
        print(report, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
