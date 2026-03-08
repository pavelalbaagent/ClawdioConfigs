#!/usr/bin/env python3
"""Shared helpers for Google Workspace runtime scripts."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


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
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def resolve_repo_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def get_integration_config(config_path: Path, integration_name: str) -> dict[str, Any]:
    data = ensure_dict(load_yaml(config_path))
    integrations = ensure_dict(data.get("integrations"))
    integration = ensure_dict(integrations.get(integration_name))
    if not integration:
        raise RuntimeError(f"integration not found in config: {integration_name}")
    return integration


class GoogleOAuthClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token

    def fetch_access_token(self) -> str:
        payload = urllib.parse.urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            method="POST",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = _request_json(req)
        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            raise RuntimeError("token response missing access_token")
        return access_token


class GoogleApiClient:
    def __init__(self, access_token: str):
        self.access_token = access_token

    def request_json(
        self,
        method: str,
        url: str,
        *,
        query: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if query:
            encoded = urllib.parse.urlencode(
                {key: value for key, value in query.items() if value is not None}, doseq=True
            )
            if encoded:
                joiner = "&" if "?" in url else "?"
                url = f"{url}{joiner}{encoded}"
        data = None
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, method=method.upper(), data=data, headers=headers)
        return _request_json(req)


def _request_json(req: urllib.request.Request) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"google api http {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"google api request failed: {exc.reason}") from exc

    data = json.loads(body or "{}")
    return ensure_dict(data)
