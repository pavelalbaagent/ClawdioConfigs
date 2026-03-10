#!/usr/bin/env python3
"""Discover public job postings and feed the job-search inbox."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from env_file_utils import load_env_file
from google_workspace_common import ensure_dict, load_yaml, resolve_repo_path  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "job_search.yaml"
KNOWN_PROVIDERS = {"brave_search_api", "serpapi"}


class HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def get_text(self) -> str:
        return " ".join(self.parts)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_config(path: Path) -> dict[str, Any]:
    raw = ensure_dict(load_yaml(path))
    config = ensure_dict(raw.get("job_search"))
    if not config:
        raise RuntimeError(f"job_search config missing in {path}")
    return config


def env_get(name: str, env_file_values: dict[str, str]) -> str:
    return env_file_values.get(name, os.environ.get(name, "")).strip()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "job_posting"


def provider_available(provider_name: str, env_values: dict[str, str]) -> bool:
    if provider_name == "brave_search_api":
        return bool(env_get("BRAVE_SEARCH_API_KEY", env_values))
    if provider_name == "serpapi":
        return bool(env_get("SERPAPI_API_KEY", env_values))
    return False


def select_provider(discovery_cfg: dict[str, Any], env_values: dict[str, str]) -> str | None:
    for provider_name in discovery_cfg.get("provider_priority") or []:
        if provider_name in KNOWN_PROVIDERS and provider_available(provider_name, env_values):
            return str(provider_name)
    return None


def suffix_matches(hostname: str, domain: str) -> bool:
    host = hostname.lower().strip(".")
    needle = domain.lower().strip(".")
    return host == needle or host.endswith(f".{needle}")


def canonicalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    cleaned = parsed._replace(query="", fragment="")
    normalized = urllib.parse.urlunparse(cleaned).strip()
    if normalized.endswith("/") and cleaned.path not in {"", "/"}:
        return normalized.rstrip("/")
    return normalized


def url_allowed(url: str, discovery_cfg: dict[str, Any]) -> bool:
    parsed = urllib.parse.urlparse(canonicalize_url(url))
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False

    allowed_domains = [str(item).strip().lower() for item in discovery_cfg.get("allowed_domains") or []]
    if allowed_domains and not any(suffix_matches(hostname, domain) for domain in allowed_domains):
        return False

    required_substrings = [str(item).strip() for item in discovery_cfg.get("required_url_substrings") or [] if str(item).strip()]
    if required_substrings and not any(fragment in url for fragment in required_substrings):
        return False
    return True


def fetch_url_text(url: str, *, timeout_seconds: int) -> str:
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
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read()
    parser = HTMLTextExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return normalize_text(parser.get_text())


def brave_search(*, api_key: str, query: str, count: int) -> list[dict[str, Any]]:
    encoded = urllib.parse.urlencode({"q": query, "count": count, "search_lang": "en"})
    request = urllib.request.Request(
        f"https://api.search.brave.com/res/v1/web/search?{encoded}",
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    web_payload = ensure_dict(payload.get("web"))
    rows = web_payload.get("results", [])
    out: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        item = ensure_dict(row)
        out.append(
            {
                "provider": "brave_search_api",
                "url": str(item.get("url") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "snippet": normalize_text(str(item.get("description") or "").strip()),
            }
        )
    return out


def serpapi_search(*, api_key: str, query: str, count: int) -> list[dict[str, Any]]:
    encoded = urllib.parse.urlencode({"engine": "google", "q": query, "api_key": api_key, "num": count})
    request = urllib.request.Request(
        f"https://serpapi.com/search.json?{encoded}",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows = payload.get("organic_results")
    out: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        item = ensure_dict(row)
        out.append(
            {
                "provider": "serpapi",
                "url": str(item.get("link") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "snippet": normalize_text(str(item.get("snippet") or "").strip()),
            }
        )
    return out


def search_provider(provider_name: str, *, env_values: dict[str, str], query: str, count: int) -> list[dict[str, Any]]:
    if provider_name == "brave_search_api":
        api_key = env_get("BRAVE_SEARCH_API_KEY", env_values)
        if not api_key:
            raise RuntimeError("missing BRAVE_SEARCH_API_KEY")
        return brave_search(api_key=api_key, query=query, count=count)
    if provider_name == "serpapi":
        api_key = env_get("SERPAPI_API_KEY", env_values)
        if not api_key:
            raise RuntimeError("missing SERPAPI_API_KEY")
        return serpapi_search(api_key=api_key, query=query, count=count)
    raise RuntimeError(f"unsupported provider: {provider_name}")


def resolve_path_from_config(config: dict[str, Any], field_name: str) -> Path:
    discovery = ensure_dict(config.get("discovery"))
    value = discovery.get(field_name)
    if not value:
        raise RuntimeError(f"missing discovery.{field_name} in config")
    return resolve_repo_path(str(value))


def resolve_inbox_path(config: dict[str, Any]) -> Path:
    inputs = ensure_dict(config.get("inputs"))
    value = inputs.get("saved_postings_dir")
    if not value:
        raise RuntimeError("missing inputs.saved_postings_dir in config")
    return resolve_repo_path(str(value))


def build_inbox_text(*, title: str, url: str, query: str, snippet: str, body_text: str, discovered_at: str, provider: str) -> str:
    lines = [
        title or "Untitled job posting",
        "",
        f"Source URL: {url}",
        f"Discovered at: {discovered_at}",
        f"Discovery provider: {provider}",
        f"Discovery query: {query}",
    ]
    if snippet:
        lines.append(f"Search snippet: {snippet}")
    lines.extend(["", body_text.strip()])
    return "\n".join(lines).strip() + "\n"


def save_posting(*, inbox_dir: Path, title: str, url: str, query: str, snippet: str, body_text: str, discovered_at: str, provider: str) -> Path:
    inbox_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    filename = f"{slugify(title)}_{digest}.txt"
    path = inbox_dir / filename
    path.write_text(
        build_inbox_text(
            title=title,
            url=url,
            query=query,
            snippet=snippet,
            body_text=body_text,
            discovered_at=discovered_at,
            provider=provider,
        ),
        encoding="utf-8",
    )
    return path


def load_fixture_results(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("queries") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise RuntimeError("fixtures file must contain a list or a {queries:[...]} object")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        item = ensure_dict(row)
        query = str(item.get("query") or "").strip()
        provider = str(item.get("provider") or "fixture").strip() or "fixture"
        results = item.get("results")
        if not isinstance(results, list):
            continue
        for result in results:
            candidate = ensure_dict(result)
            normalized.append(
                {
                    "provider": provider,
                    "query": query,
                    "url": str(candidate.get("url") or "").strip(),
                    "title": str(candidate.get("title") or "").strip(),
                    "snippet": normalize_text(str(candidate.get("snippet") or "").strip()),
                    "fixture_content_text": normalize_text(str(candidate.get("content_text") or "").strip()),
                }
            )
    return normalized


def discover(
    *,
    config_path: Path,
    env_file: Path | None = None,
    fixtures_file: Path | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    discovery_cfg = ensure_dict(config.get("discovery"))
    enabled = discovery_cfg.get("enabled") is True
    status_path = resolve_path_from_config(config, "latest_status_file")
    state_path = resolve_path_from_config(config, "state_file")
    inbox_dir = resolve_inbox_path(config)
    env_values = load_env_file(env_file, strict=True) if env_file and env_file.exists() else {}
    previous_state = read_json(state_path)
    seen_urls = ensure_dict(previous_state.get("seen_urls"))

    if not enabled:
        payload = {
            "ok": True,
            "enabled": False,
            "skipped": True,
            "reason": "disabled",
            "generated_at": now_iso(),
            "status_file": str(status_path),
            "state_file": str(state_path),
        }
        write_json(status_path, payload)
        return payload

    queries = [str(item).strip() for item in discovery_cfg.get("search_queries") or [] if str(item).strip()]
    max_results = int(discovery_cfg.get("max_results_per_query") or 5)
    max_saved = int(discovery_cfg.get("max_saved_postings_per_run") or 10)
    timeout_seconds = int(discovery_cfg.get("fetch_timeout_seconds") or 20)
    allow_snippet = bool(discovery_cfg.get("allow_snippet_only_fallback"))
    discovered_at = now_iso()

    provider_name = "fixture" if fixtures_file else select_provider(discovery_cfg, env_values)
    if not provider_name:
        payload = {
            "ok": True,
            "enabled": True,
            "skipped": True,
            "reason": "no_supported_search_provider_configured",
            "generated_at": discovered_at,
            "summary": {
                "query_count": len(queries),
                "candidate_count": 0,
                "saved_count": 0,
                "duplicate_count": 0,
                "fetch_error_count": 0,
            },
            "status_file": str(status_path),
            "state_file": str(state_path),
            "provider": None,
        }
        write_json(status_path, payload)
        return payload

    candidates: list[dict[str, Any]] = []
    search_errors: list[dict[str, str]] = []
    if fixtures_file:
        candidates = load_fixture_results(fixtures_file)
    else:
        for query in queries:
            try:
                results = search_provider(provider_name, env_values=env_values, query=query, count=max_results)
            except Exception as exc:
                search_errors.append({"query": query, "error": str(exc)})
                continue
            for result in results:
                result["query"] = query
                candidates.append(result)

    candidate_count = 0
    duplicate_count = 0
    fetch_error_count = 0
    saved_rows: list[dict[str, Any]] = []
    recent_errors: list[dict[str, str]] = search_errors[:]

    for candidate in candidates:
        if len(saved_rows) >= max_saved:
            break
        url = str(candidate.get("url") or "").strip()
        url = canonicalize_url(url)
        title = str(candidate.get("title") or "").strip()
        snippet = normalize_text(str(candidate.get("snippet") or "").strip())
        query = str(candidate.get("query") or "").strip()
        provider = str(candidate.get("provider") or provider_name).strip() or provider_name
        if not url or not title or not url_allowed(url, discovery_cfg):
            continue
        candidate_count += 1
        if url in seen_urls:
            duplicate_count += 1
            seen = ensure_dict(seen_urls.get(url))
            seen["last_seen_at"] = discovered_at
            seen["last_query"] = query
            seen["last_provider"] = provider
            seen_urls[url] = seen
            continue

        body_text = str(candidate.get("fixture_content_text") or "").strip()
        if not body_text:
            try:
                body_text = fetch_url_text(url, timeout_seconds=timeout_seconds)
            except Exception as exc:
                fetch_error_count += 1
                recent_errors.append({"url": url, "error": str(exc)})
                if allow_snippet and snippet:
                    body_text = f"Posting body could not be fetched. Use the search snippet for manual follow-up.\n\n{snippet}"
                else:
                    continue

        path = save_posting(
            inbox_dir=inbox_dir,
            title=title,
            url=url,
            query=query,
            snippet=snippet,
            body_text=body_text,
            discovered_at=discovered_at,
            provider=provider,
        )
        seen_urls[url] = {
            "title": title,
            "saved_path": str(path),
            "first_seen_at": discovered_at,
            "last_seen_at": discovered_at,
            "last_query": query,
            "last_provider": provider,
            "content_sha1": hashlib.sha1(body_text.encode("utf-8")).hexdigest(),
        }
        saved_rows.append(
            {
                "title": title,
                "url": url,
                "query": query,
                "provider": provider,
                "saved_path": str(path),
                "snippet_only": body_text.startswith("Posting body could not be fetched."),
            }
        )

    state_payload = {
        "updated_at": discovered_at,
        "provider": provider_name,
        "seen_urls": seen_urls,
    }
    write_json(state_path, state_payload)

    payload = {
        "ok": True,
        "enabled": True,
        "generated_at": discovered_at,
        "provider": provider_name,
        "status_file": str(status_path),
        "state_file": str(state_path),
        "inbox_dir": str(inbox_dir),
        "summary": {
            "query_count": len(queries) if not fixtures_file else len({row["query"] for row in candidates if row.get("query")}),
            "candidate_count": candidate_count,
            "saved_count": len(saved_rows),
            "duplicate_count": duplicate_count,
            "fetch_error_count": fetch_error_count,
            "search_error_count": len(search_errors),
        },
        "saved_postings": saved_rows,
        "recent_errors": recent_errors[:10],
    }
    write_json(status_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--fixtures-file", type=Path, help="offline search+fetch fixture JSON for deterministic tests")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = discover(
        config_path=args.config.expanduser().resolve(),
        env_file=args.env_file.expanduser().resolve() if args.env_file else None,
        fixtures_file=args.fixtures_file.expanduser().resolve() if args.fixtures_file else None,
    )
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
