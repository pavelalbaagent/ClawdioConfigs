#!/usr/bin/env python3
"""Manual-review-first job search assistant for saved postings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from env_file_utils import load_env_file
from google_workspace_common import ensure_dict, load_yaml, resolve_repo_path  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "job_search.yaml"
ALLOWED_POSTING_SUFFIXES = {".txt", ".md", ".html", ".htm"}
RECOMMENDATION_VALUES = {"apply", "manual_review", "stretch_apply", "pass"}


class HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def get_text(self) -> str:
        return " ".join(self.parts)


@dataclass
class TriageResult:
    title: str
    recommendation: str
    eligibility: str
    fit_score: int
    source_label: str
    reasons: list[str]
    allow_hits: list[str]
    possible_hits: list[str]
    deny_hits: list[str]
    strong_positive_hits: list[str]
    positive_hits: list[str]
    stretch_hits: list[str]
    negative_hits: list[str]
    seniority_penalties: list[str]
    notes: list[str]
    next_step: str
    extracted_preview: str
    analyzed_at: str


class TelegramReportClient:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"

    def send_message(self, *, chat_id: str, text: str) -> dict[str, Any]:
        payload = urllib.parse.urlencode(
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/sendMessage", data=payload, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=40) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"telegram api http {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"telegram api request failed: {exc.reason}") from exc
        if not isinstance(data, dict) or data.get("ok") is not True:
            raise RuntimeError(f"telegram api error: {data}")
        return ensure_dict(data.get("result"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_config(path: Path) -> dict[str, Any]:
    raw = ensure_dict(load_yaml(path))
    config = ensure_dict(raw.get("job_search"))
    if not config:
        raise RuntimeError(f"job_search config missing in {path}")
    return config


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "job_posting"


def env_get(name: str, env_file_values: dict[str, str]) -> str:
    return env_file_values.get(name, os.environ.get(name, "")).strip()


def normalize_text(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_title(text: str) -> str:
    for line in text.splitlines():
        clean = line.strip()
        if clean:
            return clean[:180]
    return (normalize_text(text)[:180] or "Untitled job posting").strip()


def fetch_url_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read()
    parser = HTMLTextExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return parser.get_text()


def read_posting_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".html", ".htm"}:
        parser = HTMLTextExtractor()
        parser.feed(text)
        return parser.get_text()
    return text


def find_hits(text: str, patterns: list[str]) -> list[str]:
    lowered = text.lower()
    return [pattern for pattern in patterns if pattern.lower() in lowered]


def compute_eligibility(
    text: str,
    eligibility_rules: dict[str, Any],
) -> tuple[str, list[str], list[str], list[str], list[str]]:
    allow_hits = find_hits(text, list(eligibility_rules.get("allow_patterns") or []))
    possible_hits = find_hits(text, list(eligibility_rules.get("possible_patterns") or []))
    deny_hits = find_hits(text, list(eligibility_rules.get("deny_patterns") or []))
    notes: list[str] = []

    if deny_hits:
        notes.append("Posting contains explicit location or authorization restrictions.")
        return "likely_no", allow_hits, possible_hits, deny_hits, notes
    if allow_hits:
        notes.append("Posting contains explicit signals that remote work may be possible from Ecuador or LATAM.")
        return "direct_yes", allow_hits, possible_hits, deny_hits, notes
    if possible_hits:
        notes.append("Posting is remote, but Ecuador/LATAM eligibility is not explicit.")
        return "possible_manual_check", allow_hits, possible_hits, deny_hits, notes

    notes.append("No clear remote-location signal found. Treat as manual review.")
    return "unclear", allow_hits, possible_hits, deny_hits, notes


def compute_fit(
    text: str,
    title: str,
    fit_rules: dict[str, Any],
) -> tuple[int, list[str], list[str], list[str], list[str], list[str], list[str]]:
    lowered = text.lower()
    title_lower = title.lower()

    strong_positive_hits = find_hits(lowered, list(fit_rules.get("strong_positive_keywords") or []))
    positive_hits = find_hits(lowered, list(fit_rules.get("positive_keywords") or []))
    stretch_hits = find_hits(lowered, list(fit_rules.get("stretch_keywords") or []))
    negative_hits = find_hits(lowered, list(fit_rules.get("negative_keywords") or []))

    score = 50
    score += len(strong_positive_hits) * 8
    score += len(positive_hits) * 4
    score += len(stretch_hits) * 2
    score -= len(negative_hits) * 8

    seniority_penalties: list[str] = []
    for seniority, penalty in ensure_dict(fit_rules.get("seniority_penalties")).items():
        if seniority in title_lower:
            penalty_value = int(penalty)
            score -= penalty_value
            seniority_penalties.append(f"{seniority} (-{penalty_value})")

    return (
        max(0, min(100, score)),
        strong_positive_hits,
        positive_hits,
        stretch_hits,
        negative_hits,
        seniority_penalties,
        [],
    )


def recommend(
    fit_score: int,
    eligibility: str,
    negative_hits: list[str],
    seniority_penalties: list[str],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if negative_hits:
        reasons.append("Role contains target-lane mismatch signals.")
    if seniority_penalties:
        reasons.append("Title suggests a seniority stretch.")

    if eligibility == "likely_no":
        reasons.append("Location/work authorization language likely blocks remote work from Ecuador.")
        return "pass", reasons

    if fit_score >= 70 and eligibility == "direct_yes":
        reasons.append("Strong role fit and explicit remote-eligibility signals.")
        return "apply", reasons

    if fit_score >= 70 and eligibility in {"possible_manual_check", "unclear"}:
        reasons.append("Strong role fit, but remote eligibility needs manual confirmation.")
        return "manual_review", reasons

    if fit_score >= 55 and eligibility == "direct_yes":
        reasons.append("Decent fit with explicit remote-eligibility signals.")
        return "manual_review", reasons

    if fit_score >= 55:
        reasons.append("Potential fit, but both role and eligibility need closer review.")
        return "manual_review", reasons

    if fit_score >= 40:
        reasons.append("Stretch role. Apply only if strategically valuable.")
        return "stretch_apply", reasons

    reasons.append("Fit is too weak relative to target lanes.")
    return "pass", reasons


def next_step_for(recommendation: str, eligibility: str) -> str:
    if recommendation == "apply":
        return "Apply now. Use the default AI enablement framing unless the posting clearly pulls elsewhere."
    if recommendation == "manual_review":
        if eligibility != "direct_yes":
            return "Confirm Ecuador/LATAM eligibility before applying."
        return "Quick manual review, then apply if the responsibilities still match."
    if recommendation == "stretch_apply":
        return "Apply only if the role is strategically valuable enough to justify the stretch."
    return "Pass unless new evidence changes the location or fit assessment."


def triage_posting(text: str, source_label: str, config: dict[str, Any]) -> TriageResult:
    title = extract_title(text)
    cleaned = normalize_text(text)
    eligibility, allow_hits, possible_hits, deny_hits, eligibility_notes = compute_eligibility(
        cleaned,
        ensure_dict(config.get("eligibility_rules")),
    )
    (
        fit_score,
        strong_positive_hits,
        positive_hits,
        stretch_hits,
        negative_hits,
        seniority_penalties,
        fit_notes,
    ) = compute_fit(cleaned, title, ensure_dict(config.get("fit_rules")))
    recommendation, reasons = recommend(fit_score, eligibility, negative_hits, seniority_penalties)
    notes = eligibility_notes + fit_notes

    return TriageResult(
        title=title,
        recommendation=recommendation,
        eligibility=eligibility,
        fit_score=fit_score,
        source_label=source_label,
        reasons=reasons,
        allow_hits=allow_hits,
        possible_hits=possible_hits,
        deny_hits=deny_hits,
        strong_positive_hits=strong_positive_hits,
        positive_hits=positive_hits,
        stretch_hits=stretch_hits,
        negative_hits=negative_hits,
        seniority_penalties=seniority_penalties,
        notes=notes,
        next_step=next_step_for(recommendation, eligibility),
        extracted_preview=cleaned[:600],
        analyzed_at=now_iso(),
    )


def result_output_stem(result: TriageResult) -> str:
    source = result.source_label
    if source != "stdin":
        source = Path(source).stem if "/" in source or "\\" in source else source
    digest = hashlib.sha1(f"{result.title}\n{result.source_label}".encode("utf-8")).hexdigest()[:8]
    return f"{slugify(f'{result.title}_{source}')}_{digest}"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def display_source_label(source_label: str) -> str:
    if source_label in {"stdin", "inline-text"}:
        return source_label
    path = Path(source_label)
    return path.name if path.name else source_label


def write_triage_output(output_dir: Path, result: TriageResult) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = result_output_stem(result)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"

    write_json(json_path, asdict(result))

    markdown = textwrap.dedent(
        f"""\
        # {result.title}

        - Recommendation: `{result.recommendation}`
        - Remote-from-Ecuador eligibility: `{result.eligibility}`
        - Fit score: `{result.fit_score}/100`
        - Source: `{result.source_label}`
        - Analyzed at: `{result.analyzed_at}`
        - Next step: {result.next_step}

        ## Why
        {chr(10).join(f"- {reason}" for reason in result.reasons) if result.reasons else "- No explicit reasons recorded."}

        ## Eligibility Signals
        - Allow hits: {", ".join(result.allow_hits) if result.allow_hits else "none"}
        - Possible hits: {", ".join(result.possible_hits) if result.possible_hits else "none"}
        - Deny hits: {", ".join(result.deny_hits) if result.deny_hits else "none"}

        ## Fit Signals
        - Strong positive hits: {", ".join(result.strong_positive_hits) if result.strong_positive_hits else "none"}
        - Positive hits: {", ".join(result.positive_hits) if result.positive_hits else "none"}
        - Stretch hits: {", ".join(result.stretch_hits) if result.stretch_hits else "none"}
        - Negative hits: {", ".join(result.negative_hits) if result.negative_hits else "none"}
        - Seniority penalties: {", ".join(result.seniority_penalties) if result.seniority_penalties else "none"}

        ## Notes
        {chr(10).join(f"- {note}" for note in result.notes) if result.notes else "- none"}

        ## Preview
        {result.extracted_preview}
        """
    )
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


def build_search_pack(config: dict[str, Any]) -> str:
    profile = ensure_dict(config.get("candidate_profile"))
    strategy = ensure_dict(config.get("search_strategy"))
    lines = [
        "# Job Search Pack",
        "",
        f"- Base location: `{profile.get('base_location', '')}`",
        f"- Primary market: `{profile.get('primary_market', '')}`",
        f"- Preferred employment types: {', '.join(profile.get('preferred_employment_types') or [])}",
        "",
        "## Core Search Queries",
    ]
    lines.extend(f"- `{query}`" for query in strategy.get("core_boolean_queries") or [])
    lines.extend(
        [
            "",
            "## Filter Guidance",
        ]
    )
    lines.extend(f"- {note}" for note in strategy.get("filter_notes") or [])
    lines.extend(
        [
            "",
            "## Manual Checks",
            "- Look for explicit location restrictions in the description.",
            "- Treat `Remote + United States` as inconclusive unless the posting also allows LATAM or international candidates.",
            "- Prioritize jobs that mention LATAM, global remote, contractor, or U.S. time-zone overlap without work-authorization restrictions.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_priority_map(values: list[str]) -> dict[str, int]:
    return {value: index for index, value in enumerate(values)}


def collect_posting_files(input_dir: Path, *, allow_empty: bool = False) -> list[Path]:
    if not input_dir.exists():
        raise RuntimeError(f"input directory not found: {input_dir}")
    if not input_dir.is_dir():
        raise RuntimeError(f"input path is not a directory: {input_dir}")
    files = [
        path
        for path in sorted(input_dir.iterdir())
        if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in ALLOWED_POSTING_SUFFIXES
    ]
    if not files and not allow_empty:
        raise RuntimeError(f"no posting files found in {input_dir}")
    return files


def triage_saved_postings(
    input_dir: Path,
    triage_output_dir: Path,
    config: dict[str, Any],
    *,
    allow_empty: bool = False,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for posting_path in collect_posting_files(input_dir, allow_empty=allow_empty):
        result = triage_posting(read_posting_file(posting_path), str(posting_path), config)
        json_path, md_path = write_triage_output(triage_output_dir, result)
        artifacts.append({"result": result, "json_path": json_path, "markdown_path": md_path})
    return artifacts


def build_summary_row(artifact: dict[str, Any]) -> dict[str, Any]:
    result: TriageResult = artifact["result"]
    return {
        "title": result.title,
        "recommendation": result.recommendation,
        "eligibility": result.eligibility,
        "fit_score": result.fit_score,
        "next_step": result.next_step,
        "reasons": list(result.reasons),
        "source_label": result.source_label,
        "source_name": display_source_label(result.source_label),
        "triage_json": str(artifact["json_path"]),
        "triage_markdown": str(artifact["markdown_path"]),
        "analyzed_at": result.analyzed_at,
    }


def rank_artifacts(artifacts: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    summary_cfg = ensure_dict(config.get("daily_summary"))
    recommendation_rank = build_priority_map(list(summary_cfg.get("recommendation_priority") or []))
    eligibility_rank = build_priority_map(list(summary_cfg.get("eligibility_priority") or []))

    def sort_key(artifact: dict[str, Any]) -> tuple[int, int, int, str]:
        result: TriageResult = artifact["result"]
        return (
            recommendation_rank.get(result.recommendation, len(recommendation_rank)),
            eligibility_rank.get(result.eligibility, len(eligibility_rank)),
            -result.fit_score,
            result.title.lower(),
        )

    return sorted(artifacts, key=sort_key)


def summary_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {name: 0 for name in RECOMMENDATION_VALUES}
    for row in rows:
        recommendation = str(row.get("recommendation") or "")
        if recommendation in counts:
            counts[recommendation] += 1
    return counts


def write_daily_summary(
    *,
    rows: list[dict[str, Any]],
    input_dir: Path,
    output_dir: Path,
    latest_status_file: Path,
    day_label: str,
    config: dict[str, Any],
) -> tuple[Path, Path, dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_cfg = ensure_dict(config.get("daily_summary"))
    section_order = [name for name in list(summary_cfg.get("include_sections") or []) if name in RECOMMENDATION_VALUES]
    max_roles = int(summary_cfg.get("max_roles_per_section") or 10)

    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in section_order}
    for row in rows:
        recommendation = str(row.get("recommendation") or "")
        if recommendation in grouped:
            grouped[recommendation].append(row)

    grouped = {name: values[:max_roles] for name, values in grouped.items()}
    counts = summary_counts(rows)
    recommended_rows = [row for row in rows if row["recommendation"] != "pass"]

    payload = {
        "generated_at": now_iso(),
        "day_label": day_label,
        "input_dir": str(input_dir),
        "summary": {
            "processed_count": len(rows),
            "apply_count": counts["apply"],
            "manual_review_count": counts["manual_review"],
            "stretch_apply_count": counts["stretch_apply"],
            "pass_count": counts["pass"],
            "recommended_count": len(recommended_rows),
        },
        "recommendations": recommended_rows,
        "sections": grouped,
    }

    markdown_lines = [
        f"# Daily Job Search Summary - {day_label}",
        "",
        "- LinkedIn remains manual-review only. This summary assumes saved or pasted posting text, not browser automation.",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Input directory: `{input_dir}`",
        f"- Processed postings: `{payload['summary']['processed_count']}`",
        f"- Apply: `{payload['summary']['apply_count']}`",
        f"- Manual review: `{payload['summary']['manual_review_count']}`",
        f"- Stretch apply: `{payload['summary']['stretch_apply_count']}`",
        f"- Pass: `{payload['summary']['pass_count']}`",
    ]

    for section_name in section_order:
        section_rows = grouped.get(section_name) or []
        markdown_lines.extend(["", f"## {section_name.replace('_', ' ').title()}"])
        if not section_rows:
            markdown_lines.append("- none")
            continue
        for index, row in enumerate(section_rows, start=1):
            markdown_lines.append(
                f"{index}. {row['title']} | fit `{row['fit_score']}/100` | eligibility `{row['eligibility']}` | source `{row['source_name']}`"
            )
            markdown_lines.append(f"   - Next step: {row['next_step']}")
            markdown_lines.append(
                "   - Why: " + ("; ".join(row["reasons"]) if row["reasons"] else "No explicit reason captured.")
            )
            markdown_lines.append(f"   - Triage report: `{row['triage_markdown']}`")

    json_path = output_dir / f"{day_label}.json"
    md_path = output_dir / f"{day_label}.md"
    write_json(json_path, payload)
    md_path.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")
    write_json(latest_status_file, payload)
    return json_path, md_path, payload


def format_report_message(
    payload: dict[str, Any],
    *,
    summary_json_path: Path,
    summary_md_path: Path,
    config: dict[str, Any],
) -> str:
    delivery_cfg = ensure_dict(config.get("delivery"))
    telegram_cfg = ensure_dict(delivery_cfg.get("telegram"))
    max_entries = int(telegram_cfg.get("max_entries_per_section") or 3)
    include_pass_section = bool(delivery_cfg.get("include_pass_section"))
    sections = ensure_dict(payload.get("sections"))
    summary = ensure_dict(payload.get("summary"))

    lines = [
        f"Job search digest | {payload.get('day_label')}",
        f"Processed: {summary.get('processed_count', 0)} | Apply: {summary.get('apply_count', 0)} | Review: {summary.get('manual_review_count', 0)} | Stretch: {summary.get('stretch_apply_count', 0)} | Pass: {summary.get('pass_count', 0)}",
        "",
    ]

    section_specs = [
        ("apply", "Apply Today"),
        ("manual_review", "Manual Checks Before Applying"),
        ("stretch_apply", "Stretch Roles"),
    ]
    if include_pass_section:
        section_specs.append(("pass", "Pass"))

    for section_key, heading in section_specs:
        rows = list(sections.get(section_key) or [])[:max_entries]
        if not rows:
            continue
        lines.append(heading)
        for index, row in enumerate(rows, start=1):
            lines.append(
                f"{index}. {row['title']} | fit {row['fit_score']}/100 | {row['eligibility']}"
            )
            lines.append(f"   {row['next_step']}")
        lines.append("")

    if telegram_cfg.get("include_output_paths") is True:
        lines.append(f"Full report: {summary_md_path}")
        lines.append(f"JSON: {summary_json_path}")

    message = "\n".join(line for line in lines if line is not None).strip()
    max_chars = int(telegram_cfg.get("max_message_chars") or 3200)
    if len(message) <= max_chars:
        return message
    trimmed = message[: max_chars - 24].rstrip()
    return f"{trimmed}\n\n[truncated for Telegram]"


def resolve_output_dir(config: dict[str, Any], *, override: Path | None, key: str) -> Path:
    if override is not None:
        return override.expanduser().resolve()
    outputs = ensure_dict(config.get("outputs"))
    value = outputs.get(key)
    if not value:
        raise RuntimeError(f"missing outputs.{key} in config")
    return resolve_repo_path(str(value))


def resolve_input_dir(config: dict[str, Any], *, override: Path | None) -> Path:
    if override is not None:
        return override.expanduser().resolve()
    inputs = ensure_dict(config.get("inputs"))
    value = inputs.get("saved_postings_dir")
    if not value:
        raise RuntimeError("missing inputs.saved_postings_dir in config")
    return resolve_repo_path(str(value))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("generate-search-pack", help="Generate reusable job-search guidance.")
    search_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    search_parser.add_argument("--output", required=True, type=Path)

    triage_parser = subparsers.add_parser("triage", help="Triage a single job posting.")
    triage_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    triage_parser.add_argument("--input-file", type=Path)
    triage_parser.add_argument("--url")
    triage_parser.add_argument("--stdin", action="store_true")
    triage_parser.add_argument("--text")
    triage_parser.add_argument("--output-dir", type=Path)

    summary_parser = subparsers.add_parser(
        "daily-summary",
        help="Triage a directory of saved postings and write a ranked daily summary.",
    )
    summary_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    summary_parser.add_argument("--input-dir", type=Path)
    summary_parser.add_argument("--triage-output-dir", type=Path)
    summary_parser.add_argument("--summary-output-dir", type=Path)
    summary_parser.add_argument("--day-label")
    summary_parser.add_argument("--allow-empty", action="store_true")

    publish_parser = subparsers.add_parser(
        "publish-report",
        help="Generate the daily summary and optionally send the digest to Telegram.",
    )
    publish_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    publish_parser.add_argument("--input-dir", type=Path)
    publish_parser.add_argument("--triage-output-dir", type=Path)
    publish_parser.add_argument("--summary-output-dir", type=Path)
    publish_parser.add_argument("--day-label")
    publish_parser.add_argument("--env-file", type=Path)
    publish_parser.add_argument("--allow-empty", action="store_true")
    publish_parser.add_argument("--apply", action="store_true", help="send the report to the configured Telegram chat")

    return parser.parse_args()


def read_input_text(args: argparse.Namespace) -> tuple[str, str]:
    provided = sum(
        1
        for candidate in [args.input_file is not None, args.url is not None, args.stdin, args.text is not None]
        if candidate
    )
    if provided != 1:
        raise RuntimeError("Provide exactly one of --input-file, --url, --stdin, or --text.")

    if args.input_file is not None:
        return read_posting_file(args.input_file), str(args.input_file)
    if args.url is not None:
        try:
            return fetch_url_text(args.url), args.url
        except urllib.error.URLError as exc:
            raise RuntimeError(f"failed to fetch URL: {exc}") from exc
    if args.stdin:
        return sys.stdin.read(), "stdin"
    return str(args.text or ""), "inline-text"


def generate_daily_report(
    *,
    config: dict[str, Any],
    input_dir: Path,
    triage_output_dir: Path,
    summary_output_dir: Path,
    latest_status_file: Path,
    day_label: str,
    allow_empty: bool,
) -> tuple[Path, Path, dict[str, Any]]:
    artifacts = triage_saved_postings(input_dir, triage_output_dir, config, allow_empty=allow_empty)
    ranked_rows = [build_summary_row(artifact) for artifact in rank_artifacts(artifacts, config)]
    return write_daily_summary(
        rows=ranked_rows,
        input_dir=input_dir,
        output_dir=summary_output_dir,
        latest_status_file=latest_status_file,
        day_label=day_label,
        config=config,
    )


def main() -> int:
    args = parse_args()
    config = load_config(args.config)

    if args.command == "generate-search-pack":
        output = build_search_pack(config)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        print(args.output)
        return 0

    if args.command == "triage":
        text, source_label = read_input_text(args)
        output_dir = resolve_output_dir(config, override=args.output_dir, key="triage_dir")
        result = triage_posting(text, source_label, config)
        json_path, md_path = write_triage_output(output_dir, result)
        print(
            json.dumps(
                {
                    "title": result.title,
                    "recommendation": result.recommendation,
                    "eligibility": result.eligibility,
                    "fit_score": result.fit_score,
                    "next_step": result.next_step,
                    "json": str(json_path),
                    "markdown": str(md_path),
                }
            )
        )
        return 0

    if args.command == "daily-summary":
        input_dir = resolve_input_dir(config, override=args.input_dir)
        triage_output_dir = resolve_output_dir(config, override=args.triage_output_dir, key="triage_dir")
        summary_output_dir = resolve_output_dir(config, override=args.summary_output_dir, key="daily_summary_dir")
        latest_status_file = resolve_output_dir(config, override=None, key="latest_status_file")
        day_label = str(args.day_label or datetime.now().date().isoformat())
        summary_json, summary_md, payload = generate_daily_report(
            config=config,
            input_dir=input_dir,
            triage_output_dir=triage_output_dir,
            summary_output_dir=summary_output_dir,
            latest_status_file=latest_status_file,
            day_label=day_label,
            allow_empty=bool(args.allow_empty),
        )
        print(
            json.dumps(
                {
                    "day_label": day_label,
                    "processed_count": payload["summary"]["processed_count"],
                    "summary_json": str(summary_json),
                    "summary_markdown": str(summary_md),
                    "latest_status": str(latest_status_file),
                    "top_recommendations": payload["recommendations"][:5],
                }
            )
        )
        return 0

    input_dir = resolve_input_dir(config, override=args.input_dir)
    triage_output_dir = resolve_output_dir(config, override=args.triage_output_dir, key="triage_dir")
    summary_output_dir = resolve_output_dir(config, override=args.summary_output_dir, key="daily_summary_dir")
    latest_status_file = resolve_output_dir(config, override=None, key="latest_status_file")
    day_label = str(args.day_label or datetime.now().date().isoformat())
    schedule_cfg = ensure_dict(config.get("schedule"))
    delivery_cfg = ensure_dict(config.get("delivery"))
    allow_empty = bool(args.allow_empty or schedule_cfg.get("allow_empty_report") or delivery_cfg.get("send_when_empty"))
    summary_json, summary_md, payload = generate_daily_report(
        config=config,
        input_dir=input_dir,
        triage_output_dir=triage_output_dir,
        summary_output_dir=summary_output_dir,
        latest_status_file=latest_status_file,
        day_label=day_label,
        allow_empty=allow_empty,
    )
    message = format_report_message(payload, summary_json_path=summary_json, summary_md_path=summary_md, config=config)

    sent = False
    delivery_meta: dict[str, Any] = {"channel": delivery_cfg.get("channel") or "telegram"}
    if args.apply:
        env_values = load_env_file(args.env_file.expanduser().resolve()) if args.env_file else {}
        token = env_get("TELEGRAM_BOT_TOKEN", env_values)
        chat_id = env_get("TELEGRAM_ALLOWED_CHAT_ID", env_values)
        if not token:
            raise RuntimeError("missing TELEGRAM_BOT_TOKEN")
        if not chat_id:
            raise RuntimeError("missing TELEGRAM_ALLOWED_CHAT_ID")
        client = TelegramReportClient(token)
        response = client.send_message(chat_id=chat_id, text=message)
        sent = True
        delivery_meta["telegram_message_id"] = response.get("message_id")

    print(
        json.dumps(
            {
                "day_label": day_label,
                "processed_count": payload["summary"]["processed_count"],
                "summary_json": str(summary_json),
                "summary_markdown": str(summary_md),
                "latest_status": str(latest_status_file),
                "delivery": {
                    **delivery_meta,
                    "sent": sent,
                    "preview": message,
                },
                "top_recommendations": payload["recommendations"][:5],
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        raise SystemExit(str(exc))
