#!/usr/bin/env python3
"""Search memory with semantic embeddings (OpenAI) or keyword fallback."""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "memory.yaml"


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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def call_openai_embedding(api_key: str, model: str, text: str) -> list[float]:
    payload = json.dumps({"model": model, "input": text}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        method="POST",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI embeddings HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI embeddings request failed: {exc.reason}") from exc

    data = json.loads(body)
    items = data.get("data")
    if not isinstance(items, list) or not items:
        raise RuntimeError("OpenAI embeddings response missing data")
    first = ensure_dict(items[0])
    vector = first.get("embedding")
    if not isinstance(vector, list) or not vector:
        raise RuntimeError("OpenAI embeddings response missing embedding vector")
    return [float(x) for x in vector]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if len(vec_a) != len(vec_b) or not vec_a:
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def resolve_active_modules(memory_cfg: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any], list[str]]:
    profiles = ensure_dict(memory_cfg.get("profiles"))
    definitions = ensure_dict(profiles.get("definitions"))
    active_profile = profiles.get("active_profile")
    if not isinstance(active_profile, str) or not active_profile.strip():
        raise RuntimeError("memory.profiles.active_profile is required")

    active_name = active_profile.strip()
    profile = ensure_dict(definitions.get(active_name))
    if not profile:
        raise RuntimeError(f"memory profile not found: {active_name}")

    modules = ensure_dict(memory_cfg.get("memory_modules"))
    enabled_modules = ensure_string_list(profile.get("enabled_modules"))
    return active_name, profile, modules, enabled_modules


def resolve_db_path(workspace: Path, modules: dict[str, Any], sqlite_state_enabled: bool) -> Path:
    env_db = os.environ.get("MEMORY_SQLITE_DB_PATH", "").strip()
    if env_db:
        return Path(env_db).expanduser().resolve()

    sqlite_cfg = ensure_dict(modules.get("sqlite_state"))
    semantic_cfg = ensure_dict(modules.get("semantic_embeddings"))
    semantic_storage = ensure_dict(semantic_cfg.get("storage"))

    db_rel = ""
    if sqlite_state_enabled:
        db_rel = str(sqlite_cfg.get("db_path") or "").strip()
    if not db_rel:
        db_rel = str(semantic_storage.get("sqlite_db_path") or "").strip()
    if not db_rel:
        db_rel = ".memory/memory.db"

    path = Path(db_rel)
    if path.is_absolute():
        return path
    return (workspace / path).resolve()


def write_recall_event(conn: sqlite3.Connection, query: str, mode: str, top_k: int, results_count: int, latency_ms: int) -> None:
    try:
        conn.execute(
            (
                "INSERT INTO recall_events(query_text, mode, top_k, results_count, latency_ms, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?)"
            ),
            (query, mode, top_k, results_count, latency_ms, now_iso()),
        )
        conn.commit()
    except sqlite3.DatabaseError:
        return


def semantic_search(
    conn: sqlite3.Connection,
    query: str,
    top_k: int,
    min_similarity: float,
    api_key: str,
    model: str,
) -> list[dict[str, Any]]:
    start = time.time()
    query_vector = call_openai_embedding(api_key=api_key, model=model, text=query)
    rows = conn.execute(
        (
            "SELECT c.id, s.path, c.heading, c.content, e.vector_json "
            "FROM memory_chunks c "
            "JOIN source_documents s ON s.id = c.source_id "
            "JOIN embeddings e ON e.chunk_id = c.id"
        )
    ).fetchall()

    scored: list[dict[str, Any]] = []
    for row in rows:
        chunk_id = int(row[0])
        source_path = str(row[1])
        heading = str(row[2]) if row[2] is not None else ""
        content = str(row[3])
        try:
            candidate_vector = [float(x) for x in json.loads(str(row[4]))]
        except Exception:
            continue
        score = cosine_similarity(query_vector, candidate_vector)
        if score < min_similarity:
            continue
        scored.append(
            {
                "chunk_id": chunk_id,
                "source_path": source_path,
                "heading": heading,
                "content": content,
                "score": score,
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    elapsed = int((time.time() - start) * 1000)
    write_recall_event(conn, query=query, mode="semantic", top_k=top_k, results_count=min(top_k, len(scored)), latency_ms=elapsed)
    return scored[:top_k]


def keyword_search(conn: sqlite3.Connection, query: str, top_k: int) -> list[dict[str, Any]]:
    start = time.time()
    terms = [term.strip().lower() for term in query.split() if term.strip()]
    if not terms:
        return []

    where_parts: list[str] = []
    params: list[str] = []
    for term in terms:
        like_term = f"%{term}%"
        where_parts.append("(LOWER(c.content) LIKE ? OR LOWER(COALESCE(c.heading, '')) LIKE ?)")
        params.extend([like_term, like_term])

    where_sql = " OR ".join(where_parts)
    sql = (
        "SELECT c.id, s.path, c.heading, c.content "
        "FROM memory_chunks c "
        "JOIN source_documents s ON s.id = c.source_id "
        f"WHERE {where_sql} "
        "ORDER BY c.id DESC LIMIT ?"
    )
    params.append(top_k)
    rows = conn.execute(sql, tuple(params)).fetchall()

    results = [
        {
            "chunk_id": int(row[0]),
            "source_path": str(row[1]),
            "heading": str(row[2]) if row[2] is not None else "",
            "content": str(row[3]),
            "score": None,
        }
        for row in rows
    ]
    elapsed = int((time.time() - start) * 1000)
    write_recall_event(conn, query=query, mode="keyword", top_k=top_k, results_count=len(results), latency_ms=elapsed)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Search memory with semantic embeddings and keyword fallback")
    parser.add_argument("--workspace", default=".", help="workspace containing .memory/memory.db")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="path to memory config yaml")
    parser.add_argument("--query", required=True, help="search query")
    parser.add_argument("--top-k", type=int, help="result count")
    parser.add_argument(
        "--mode",
        choices=["auto", "semantic", "keyword"],
        default="auto",
        help="search mode",
    )
    parser.add_argument("--json", action="store_true", help="print JSON output")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    config_path = Path(args.config).resolve()

    if not workspace.exists():
        print(f"Workspace not found: {workspace}")
        return 1
    if not config_path.exists():
        print(f"Memory config not found: {config_path}")
        return 1

    cfg = ensure_dict(load_yaml(config_path))
    try:
        _, profile, modules, enabled_module_names = resolve_active_modules(cfg)
    except RuntimeError as exc:
        print(f"Config error: {exc}")
        return 1

    semantic_cfg = ensure_dict(modules.get("semantic_embeddings"))
    sqlite_cfg = ensure_dict(modules.get("sqlite_state"))

    semantic_enabled = (
        "semantic_embeddings" in enabled_module_names and semantic_cfg.get("enabled") is True
    )
    sqlite_enabled = (
        "sqlite_state" in enabled_module_names and sqlite_cfg.get("enabled") is True
    ) or semantic_enabled

    if not sqlite_enabled:
        print("SQLite-backed memory is disabled in current profile")
        return 1

    db_path = resolve_db_path(workspace, modules, sqlite_enabled)
    if not db_path.exists():
        print(f"Memory DB not found: {db_path}")
        print("Run scripts/memory_index_sync.py first")
        return 1

    retrieval_cfg = ensure_dict(semantic_cfg.get("retrieval"))
    top_k = args.top_k if isinstance(args.top_k, int) and args.top_k > 0 else retrieval_cfg.get("top_k_default", 8)
    if not isinstance(top_k, int) or top_k <= 0:
        top_k = 8

    min_similarity = retrieval_cfg.get("min_similarity", 0.32)
    if not isinstance(min_similarity, (int, float)):
        min_similarity = 0.32
    min_similarity = float(min_similarity)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")

    mode_used = args.mode
    results: list[dict[str, Any]] = []

    if args.mode in {"auto", "semantic"} and semantic_enabled:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        model = os.environ.get("OPENAI_EMBEDDING_MODEL", "").strip() or str(
            semantic_cfg.get("model") or "text-embedding-3-small"
        )
        if api_key:
            try:
                results = semantic_search(
                    conn=conn,
                    query=args.query,
                    top_k=top_k,
                    min_similarity=min_similarity,
                    api_key=api_key,
                    model=model,
                )
                mode_used = "semantic"
            except Exception as exc:  # noqa: BLE001
                if args.mode == "semantic":
                    print(f"Semantic search failed: {exc}")
                    conn.close()
                    return 1
                print(f"Semantic search failed, falling back to keyword: {exc}")

    if not results and args.mode in {"auto", "keyword"}:
        results = keyword_search(conn=conn, query=args.query, top_k=top_k)
        mode_used = "keyword"

    conn.close()

    if args.json:
        print(
            json.dumps(
                {
                    "query": args.query,
                    "mode": mode_used,
                    "count": len(results),
                    "results": results,
                },
                indent=2,
            )
        )
        return 0

    print(f"Query: {args.query}")
    print(f"Mode: {mode_used}")
    print(f"Results: {len(results)}")

    for idx, item in enumerate(results, start=1):
        score = item.get("score")
        score_str = f" score={score:.4f}" if isinstance(score, float) else ""
        heading = str(item.get("heading") or "")
        heading_part = f" | {heading}" if heading else ""
        excerpt = str(item.get("content") or "").strip().replace("\n", " ")
        if len(excerpt) > 220:
            excerpt = excerpt[:220].rstrip() + "..."

        print(f"{idx}. {item['source_path']}{heading_part}{score_str}")
        print(f"   {excerpt}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
