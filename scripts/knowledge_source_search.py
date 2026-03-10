#!/usr/bin/env python3
"""Search configured local markdown knowledge sources such as AIToolsDB."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from google_workspace_common import ensure_dict, load_yaml  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "knowledge_sources.yaml"
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "your",
    "about",
    "what",
    "when",
    "where",
    "which",
    "have",
    "does",
    "would",
    "there",
    "their",
    "than",
    "them",
    "then",
    "just",
    "over",
    "also",
}


def load_config(path: Path) -> dict[str, Any]:
    raw = ensure_dict(load_yaml(path))
    return ensure_dict(raw.get("knowledge_sources"))


def ensure_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9+._-]{1,}", str(text or "").lower())
    return [token for token in tokens if token not in STOPWORDS]


def resolve_enabled_sources(config: dict[str, Any]) -> list[str]:
    profiles = ensure_dict(config.get("profiles"))
    active_profile = str(config.get("active_profile") or "default").strip() or "default"
    profile = ensure_dict(profiles.get(active_profile))
    return ensure_string_list(profile.get("enabled_sources"))


def resolve_source_config(config: dict[str, Any], source_id: str) -> dict[str, Any]:
    sources = ensure_dict(config.get("sources"))
    return ensure_dict(sources.get(source_id))


def resolve_source_root(source_cfg: dict[str, Any], *, base_dir: Path | None = None) -> Path | None:
    for candidate in ensure_string_list(source_cfg.get("root_candidates")):
        path = Path(candidate).expanduser()
        if not path.is_absolute() and base_dir is not None:
            path = (base_dir / path).resolve()
        if path.exists() and path.is_dir():
            return path.resolve()
    return None


def should_query_source(*, source_cfg: dict[str, Any], agent_id: str, space_key: str, query: str) -> bool:
    if source_cfg.get("enabled") is not True:
        return False
    allowed_agents = ensure_string_list(source_cfg.get("allowed_agents"))
    if allowed_agents and agent_id not in allowed_agents:
        return False
    allowed_spaces = ensure_string_list(source_cfg.get("allowed_spaces"))
    if allowed_spaces and space_key not in allowed_spaces and not (space_key.startswith("projects/") and "coding" in allowed_spaces):
        return False
    auto_cfg = ensure_dict(source_cfg.get("auto_query"))
    if agent_id in ensure_string_list(auto_cfg.get("always_for_agents")):
        return True
    lowered = str(query or "").lower()
    return any(hint.lower() in lowered for hint in ensure_string_list(auto_cfg.get("keyword_hints")))


def iter_markdown_files(root: Path, *, limit: int) -> list[Path]:
    files = [path for path in root.rglob("*.md") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files[:limit]


def read_file_excerpt(path: Path, *, limit_chars: int = 7000) -> str:
    return path.read_text(encoding="utf-8", errors="replace")[:limit_chars]


def extract_title(path: Path, text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip().lstrip("#").strip()
        if line:
            return line[:160]
    return path.stem.replace("_", " ")


def score_document(*, query_terms: list[str], raw_query: str, path: Path, text: str) -> float:
    lowered = text.lower()
    name = path.name.lower()
    stem = path.stem.lower().replace("_", " ")
    score = 0.0
    for term in query_terms:
        if term in name:
            score += 5.0
        if term in stem:
            score += 4.0
        if term in lowered:
            score += 1.5
    phrase = " ".join(query_terms)
    if phrase and phrase in lowered:
        score += 8.0
    if raw_query.lower() in lowered:
        score += 10.0
    if query_terms and all(term in lowered or term in name for term in query_terms[: min(3, len(query_terms))]):
        score += 4.0
    return score


def best_excerpt(*, text: str, query_terms: list[str], limit_chars: int) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return ""
    if not query_terms:
        return clean[:limit_chars]
    lowered = clean.lower()
    positions = [lowered.find(term) for term in query_terms if lowered.find(term) >= 0]
    if not positions:
        return clean[:limit_chars]
    start = max(0, min(positions) - (limit_chars // 3))
    end = min(len(clean), start + limit_chars)
    excerpt = clean[start:end].strip()
    if start > 0:
        excerpt = "…" + excerpt
    if end < len(clean):
        excerpt = excerpt + "…"
    return excerpt


def search_source(
    *,
    source_cfg: dict[str, Any],
    query: str,
    base_dir: Path | None = None,
    top_k: int | None = None,
) -> dict[str, Any]:
    source_root = resolve_source_root(source_cfg, base_dir=base_dir)
    if source_root is None:
        return {"available": False, "root": None, "results": []}

    query_terms = tokenize(query)
    excerpt_chars = int(source_cfg.get("excerpt_chars", 280) or 280)
    max_files_scan = int(source_cfg.get("max_files_scan", 600) or 600)
    effective_top_k = int(top_k or source_cfg.get("top_k", 4) or 4)

    scored: list[dict[str, Any]] = []
    for path in iter_markdown_files(source_root, limit=max_files_scan):
        text = read_file_excerpt(path)
        score = score_document(query_terms=query_terms, raw_query=query, path=path, text=text)
        if score <= 0:
            continue
        excerpt = best_excerpt(text=text, query_terms=query_terms, limit_chars=excerpt_chars)
        scored.append(
            {
                "path": str(path),
                "title": extract_title(path, text),
                "score": round(score, 2),
                "excerpt": excerpt,
            }
        )
    scored.sort(key=lambda row: (-float(row.get("score", 0.0)), str(row.get("title") or "")))
    return {"available": True, "root": str(source_root), "results": scored[:effective_top_k]}


def search_enabled_sources(
    *,
    config_path: Path,
    query: str,
    agent_id: str,
    space_key: str,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    config = load_config(config_path)
    results: list[dict[str, Any]] = []
    for source_id in resolve_enabled_sources(config):
        source_cfg = resolve_source_config(config, source_id)
        if not should_query_source(source_cfg=source_cfg, agent_id=agent_id, space_key=space_key, query=query):
            continue
        payload = search_source(source_cfg=source_cfg, query=query, base_dir=config_path.parent, top_k=top_k)
        if not payload.get("available") or not payload.get("results"):
            continue
        results.append(
            {
                "source_id": source_id,
                "root": payload.get("root"),
                "results": payload.get("results"),
            }
        )
    return results


def format_context_block(groups: list[dict[str, Any]], *, max_sources: int = 1, max_results_per_source: int = 3) -> str:
    if not groups:
        return ""
    lines = ["Relevant local knowledge sources:"]
    for group in groups[:max_sources]:
        source_id = str(group.get("source_id") or "knowledge_source")
        lines.append(f"- Source: {source_id}")
        for row in group.get("results", [])[:max_results_per_source]:
            item = ensure_dict(row)
            lines.append(
                f"  - {item.get('title') or Path(str(item.get('path') or '')).name}: {str(item.get('excerpt') or '').strip()}"
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Search configured local knowledge sources.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="knowledge source config path")
    parser.add_argument("--query", required=True, help="query text")
    parser.add_argument("--agent-id", default="researcher", help="agent requesting the lookup")
    parser.add_argument("--space-key", default="research", help="space key for policy filtering")
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    groups = search_enabled_sources(
        config_path=Path(args.config).expanduser().resolve(),
        query=args.query,
        agent_id=args.agent_id.strip().lower() or "researcher",
        space_key=args.space_key.strip() or "research",
        top_k=args.top_k,
    )
    payload = {"groups": groups}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(format_context_block(groups))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
