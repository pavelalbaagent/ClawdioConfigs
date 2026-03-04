#!/usr/bin/env python3
"""Sync markdown memory into SQLite and optional OpenAI embeddings."""

from __future__ import annotations

import argparse
import hashlib
import json
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
DEFAULT_SCHEMA = ROOT / "contracts" / "memory" / "sqlite_schema.sql"


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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def chunk_text(content: str, max_chars: int, overlap_chars: int) -> list[str]:
    text = content.strip()
    if not text:
        return []

    chunks: list[str] = []
    cursor = 0
    text_len = len(text)

    while cursor < text_len:
        end = min(cursor + max_chars, text_len)
        if end < text_len:
            split_at = text.rfind("\n", cursor, end)
            if split_at > cursor + (max_chars // 3):
                end = split_at

        piece = text[cursor:end].strip()
        if piece:
            chunks.append(piece)

        if end >= text_len:
            break

        if overlap_chars > 0:
            next_cursor = max(end - overlap_chars, cursor + 1)
        else:
            next_cursor = end

        if next_cursor <= cursor:
            next_cursor = end

        cursor = next_cursor

    return chunks


def markdown_chunks(text: str, max_chars: int, overlap_chars: int) -> list[tuple[str | None, str]]:
    sections: list[tuple[str | None, str]] = []
    heading: str | None = None
    lines: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        if line.startswith("## "):
            if lines:
                sections.append((heading, "\n".join(lines).strip()))
            heading = line[3:].strip() or None
            lines = []
            continue
        lines.append(line)

    if lines:
        sections.append((heading, "\n".join(lines).strip()))

    if not sections:
        return []

    output: list[tuple[str | None, str]] = []
    for sec_heading, sec_content in sections:
        for piece in chunk_text(sec_content, max_chars=max_chars, overlap_chars=overlap_chars):
            output.append((sec_heading, piece))
    return output


def token_estimate(text: str) -> int:
    return max(1, len(text) // 4)


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


def resolve_schema_path(modules: dict[str, Any]) -> Path:
    sqlite_cfg = ensure_dict(modules.get("sqlite_state"))
    schema_value = str(sqlite_cfg.get("schema_file") or "").strip()
    if not schema_value:
        return DEFAULT_SCHEMA
    schema_path = Path(schema_value)
    if schema_path.is_absolute():
        return schema_path
    return (ROOT / schema_path).resolve()


def collect_source_files(workspace: Path, globs: list[str], max_files: int | None) -> list[Path]:
    files: dict[str, Path] = {}
    for pattern in globs:
        for match in workspace.glob(pattern):
            if match.is_file() and match.suffix.lower() == ".md":
                files[str(match.resolve())] = match.resolve()

    ordered = [files[key] for key in sorted(files)]
    if max_files is not None and max_files >= 0:
        return ordered[:max_files]
    return ordered


def apply_pragmas(conn: sqlite3.Connection, sqlite_cfg: dict[str, Any]) -> None:
    pragmas = ensure_dict(sqlite_cfg.get("pragmas"))
    for key, value in pragmas.items():
        if not isinstance(key, str):
            continue
        if not isinstance(value, (str, int, float)):
            continue
        conn.execute(f"PRAGMA {key}={value}")


def get_state_int(conn: sqlite3.Connection, key: str) -> int:
    row = conn.execute("SELECT value FROM memory_state WHERE key = ?", (key,)).fetchone()
    if not row:
        return 0
    try:
        return int(str(row[0]))
    except ValueError:
        return 0


def set_state_int(conn: sqlite3.Connection, key: str, value: int) -> None:
    conn.execute(
        (
            "INSERT INTO memory_state(key, value, updated_at) VALUES(?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at"
        ),
        (key, str(value), now_iso()),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync markdown memory into SQLite and optional embeddings")
    parser.add_argument("--workspace", default=".", help="workspace containing MEMORY.md and memory/*.md")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="path to memory config yaml")
    parser.add_argument("--force", action="store_true", help="re-index all files even if checksum unchanged")
    parser.add_argument("--dry-run", action="store_true", help="print plan only; do not write DB or call APIs")
    parser.add_argument("--max-files", type=int, help="max markdown files to process")
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
        active_profile, profile, modules, enabled_module_names = resolve_active_modules(cfg)
    except RuntimeError as exc:
        print(f"Config error: {exc}")
        return 1

    structured_cfg = ensure_dict(modules.get("structured_markdown"))
    semantic_cfg = ensure_dict(modules.get("semantic_embeddings"))
    sqlite_cfg = ensure_dict(modules.get("sqlite_state"))

    structured_enabled = (
        "structured_markdown" in enabled_module_names and structured_cfg.get("enabled") is True
    )
    semantic_enabled = (
        "semantic_embeddings" in enabled_module_names and semantic_cfg.get("enabled") is True
    )
    sqlite_enabled = (
        "sqlite_state" in enabled_module_names and sqlite_cfg.get("enabled") is True
    ) or semantic_enabled

    print(f"Profile: {active_profile}")
    print(f"Enabled modules: {', '.join(enabled_module_names) if enabled_module_names else 'none'}")

    if not structured_enabled:
        print("structured_markdown is disabled; nothing to sync")
        return 0

    source_globs = ensure_string_list(structured_cfg.get("source_globs"))
    if not source_globs:
        print("No source_globs configured for structured_markdown")
        return 1

    max_chars = 1200
    overlap_chars = 120
    chunking_cfg = ensure_dict(semantic_cfg.get("chunking"))
    if isinstance(chunking_cfg.get("max_chars_per_chunk"), int):
        max_chars = int(chunking_cfg["max_chars_per_chunk"])
    if isinstance(chunking_cfg.get("overlap_chars"), int):
        overlap_chars = int(chunking_cfg["overlap_chars"])

    files = collect_source_files(workspace, source_globs, args.max_files)
    if not files:
        print("No markdown files matched source_globs")
        return 0

    db_path = resolve_db_path(workspace, modules, sqlite_enabled)
    schema_path = resolve_schema_path(modules)
    if sqlite_enabled and not schema_path.exists():
        print(f"SQLite schema not found: {schema_path}")
        return 1

    print(f"Workspace: {workspace}")
    print(f"Matched files: {len(files)}")
    print(f"SQLite path: {db_path}")

    if args.dry_run:
        for path in files:
            rel = path.relative_to(workspace)
            print(f"- {rel}")
        print("Dry run complete")
        return 0

    if not sqlite_enabled:
        print("SQLite-backed modules are disabled; nothing to persist")
        return 0

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    apply_pragmas(conn, sqlite_cfg)

    conn.executescript(schema_path.read_text(encoding="utf-8"))

    files_changed = 0
    files_skipped = 0
    chunks_created = 0

    pending_embeddings: list[tuple[int, str]] = []

    for path in files:
        rel_path = str(path.relative_to(workspace))
        checksum = file_sha256(path)
        text = path.read_text(encoding="utf-8")

        existing = conn.execute(
            "SELECT id, checksum FROM source_documents WHERE path = ?",
            (rel_path,),
        ).fetchone()

        source_id: int | None = None
        if existing:
            source_id = int(existing[0])
            existing_checksum = str(existing[1])
            if existing_checksum == checksum and not args.force:
                files_skipped += 1
                continue

        ts = now_iso()
        conn.execute(
            (
                "INSERT INTO source_documents(path, checksum, source_type, updated_at) "
                "VALUES(?, ?, 'markdown', ?) "
                "ON CONFLICT(path) DO UPDATE SET checksum=excluded.checksum, updated_at=excluded.updated_at"
            ),
            (rel_path, checksum, ts),
        )
        row = conn.execute("SELECT id FROM source_documents WHERE path = ?", (rel_path,)).fetchone()
        if not row:
            raise RuntimeError(f"failed to upsert source document: {rel_path}")

        source_id = int(row[0])
        conn.execute("DELETE FROM memory_chunks WHERE source_id = ?", (source_id,))

        file_chunks = markdown_chunks(text, max_chars=max_chars, overlap_chars=overlap_chars)
        for order_idx, (heading, content) in enumerate(file_chunks):
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            cur = conn.execute(
                (
                    "INSERT INTO memory_chunks(source_id, chunk_order, heading, content, token_estimate, content_hash, created_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    source_id,
                    order_idx,
                    heading,
                    content,
                    token_estimate(content),
                    content_hash,
                    ts,
                ),
            )
            chunk_id = int(cur.lastrowid)
            if semantic_enabled:
                pending_embeddings.append((chunk_id, content))

        files_changed += 1
        chunks_created += len(file_chunks)

    embeddings_created = 0
    embeddings_skipped_missing_key = 0
    embeddings_skipped_budget = 0

    if semantic_enabled and pending_embeddings:
        provider = str(semantic_cfg.get("provider") or "").strip().lower()
        if provider != "openai":
            print(f"Semantic provider not implemented: {provider}")
        else:
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not api_key:
                embeddings_skipped_missing_key = len(pending_embeddings)
                print("OPENAI_API_KEY is missing; semantic embeddings were skipped")
            else:
                model = os.environ.get("OPENAI_EMBEDDING_MODEL", "").strip() or str(
                    semantic_cfg.get("model") or "text-embedding-3-small"
                )
                budget_cfg = ensure_dict(semantic_cfg.get("budget_controls"))
                max_per_run = budget_cfg.get("max_new_embeddings_per_run")
                max_chars_per_day = budget_cfg.get("max_embedding_chars_per_day")
                skip_if_above_daily_cap = budget_cfg.get("skip_if_above_daily_cap") is True

                if not isinstance(max_per_run, int) or max_per_run <= 0:
                    max_per_run = len(pending_embeddings)
                if not isinstance(max_chars_per_day, int) or max_chars_per_day <= 0:
                    max_chars_per_day = 10**9

                day_key = datetime.now(timezone.utc).strftime("embedding_chars_%Y%m%d")
                used_chars_today = get_state_int(conn, day_key)

                to_process = pending_embeddings[:max_per_run]
                for chunk_id, content in to_process:
                    next_used = used_chars_today + len(content)
                    if skip_if_above_daily_cap and next_used > max_chars_per_day:
                        embeddings_skipped_budget += 1
                        continue

                    try:
                        start = time.time()
                        vector = call_openai_embedding(api_key=api_key, model=model, text=content)
                        elapsed = int((time.time() - start) * 1000)
                    except Exception as exc:  # noqa: BLE001
                        print(f"embedding failed for chunk_id={chunk_id}: {exc}")
                        embeddings_skipped_budget += 1
                        continue

                    conn.execute(
                        (
                            "INSERT INTO embeddings(chunk_id, provider, model, vector_json, embedding_dim, created_at) "
                            "VALUES(?, ?, ?, ?, ?, ?) "
                            "ON CONFLICT(chunk_id) DO UPDATE SET "
                            "provider=excluded.provider, model=excluded.model, "
                            "vector_json=excluded.vector_json, embedding_dim=excluded.embedding_dim, created_at=excluded.created_at"
                        ),
                        (
                            chunk_id,
                            "openai",
                            model,
                            json.dumps(vector),
                            len(vector),
                            now_iso(),
                        ),
                    )

                    conn.execute(
                        (
                            "INSERT INTO recall_events(query_text, mode, top_k, results_count, latency_ms, created_at) "
                            "VALUES(?, ?, ?, ?, ?, ?)"
                        ),
                        (
                            "[index_sync]",
                            "embedding_write",
                            1,
                            1,
                            elapsed,
                            now_iso(),
                        ),
                    )

                    used_chars_today = next_used
                    embeddings_created += 1

                set_state_int(conn, day_key, used_chars_today)
                if len(pending_embeddings) > max_per_run:
                    embeddings_skipped_budget += len(pending_embeddings) - max_per_run

    conn.commit()
    conn.close()

    print("Sync summary:")
    print(f"- files_changed: {files_changed}")
    print(f"- files_skipped_unchanged: {files_skipped}")
    print(f"- chunks_created: {chunks_created}")
    print(f"- embeddings_created: {embeddings_created}")
    print(f"- embeddings_skipped_missing_key: {embeddings_skipped_missing_key}")
    print(f"- embeddings_skipped_budget_or_error: {embeddings_skipped_budget}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
