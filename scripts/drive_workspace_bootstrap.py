#!/usr/bin/env python3
"""Verify or bootstrap the shared Google Drive workspace root."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from env_file_utils import load_env_file
from google_workspace_common import (  # type: ignore
    GoogleApiClient,
    GoogleOAuthClient,
    ensure_dict,
    get_integration_config,
    load_yaml,
    resolve_repo_path,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "integrations.yaml"
DEFAULT_STATUS_PATH = ROOT / "data" / "drive-workspace-status.json"
FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveClient:
    def __init__(self, api: GoogleApiClient):
        self.api = api

    def get_item(self, file_id: str) -> dict[str, Any]:
        return self.api.request_json(
            "GET",
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            query={
                "fields": "id,name,mimeType,owners(displayName,emailAddress),permissions(emailAddress,role)",
                "supportsAllDrives": "true",
            },
        )

    def list_child_folders(self, parent_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        query = f"'{parent_id}' in parents and trashed=false and mimeType='{FOLDER_MIME}'"
        while True:
            payload = self.api.request_json(
                "GET",
                "https://www.googleapis.com/drive/v3/files",
                query={
                    "q": query,
                    "fields": "nextPageToken,files(id,name,mimeType)",
                    "pageSize": 100,
                    "pageToken": page_token,
                    "supportsAllDrives": "true",
                    "includeItemsFromAllDrives": "true",
                },
            )
            items.extend([ensure_dict(item) for item in payload.get("files", []) if isinstance(item, dict)])
            page_token = str(payload.get("nextPageToken") or "").strip() or None
            if not page_token:
                break
        return items

    def create_folder(self, name: str, parent_id: str) -> dict[str, Any]:
        return self.api.request_json(
            "POST",
            "https://www.googleapis.com/drive/v3/files",
            query={"supportsAllDrives": "true"},
            payload={
                "name": name,
                "mimeType": FOLDER_MIME,
                "parents": [parent_id],
            },
        )


class FixtureDriveClient:
    def __init__(self, *, root: dict[str, Any], children: list[dict[str, Any]]):
        self.root = ensure_dict(root)
        self.children_by_parent: dict[str, list[dict[str, Any]]] = {str(self.root.get("id") or ""): []}
        for item in children:
            row = ensure_dict(item)
            parents = row.get("parents")
            if isinstance(parents, list) and parents:
                parent_id = str(parents[0] or "").strip() or str(self.root.get("id") or "")
            else:
                parent_id = str(self.root.get("id") or "")
            self.children_by_parent.setdefault(parent_id, []).append(row)
        self.created: list[dict[str, Any]] = []

    def get_item(self, file_id: str) -> dict[str, Any]:
        if str(self.root.get("id") or "") != file_id:
            raise RuntimeError(f"fixture root not found: {file_id}")
        return self.root

    def list_child_folders(self, parent_id: str) -> list[dict[str, Any]]:
        return list(self.children_by_parent.get(parent_id, []))

    def create_folder(self, name: str, parent_id: str) -> dict[str, Any]:
        item = {"id": f"created-{len(self.created) + 1}", "name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
        self.created.append(item)
        self.children_by_parent.setdefault(parent_id, []).append(item)
        return item


def env_get(name: str, env_file_values: dict[str, str]) -> str:
    return env_file_values.get(name, os.environ.get(name, "")).strip()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_drive_integration(config_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    integration = get_integration_config(config_path, "drive")
    if integration.get("enabled") is not True:
        raise RuntimeError("drive integration is disabled in config")
    workspace_policy = ensure_dict(integration.get("workspace_policy"))
    contract_path = resolve_repo_path(str(workspace_policy.get("contract_file") or "contracts/drive/shared-workspace.yaml"))
    contract = ensure_dict(load_yaml(contract_path))
    return integration, workspace_policy, contract


def resolve_root_folder_id(*, workspace_policy: dict[str, Any], env_file_values: dict[str, str], override: str | None) -> str:
    if override:
        return override.strip()
    env_key = str(workspace_policy.get("root_folder_env") or "GOOGLE_DRIVE_ROOT_FOLDER_ID")
    root_id = env_get(env_key, env_file_values)
    if not root_id:
        raise RuntimeError(f"missing required drive root folder id env: {env_key}")
    return root_id


def resolve_status_path(override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_STATUS_PATH


def expected_folder_names(contract: dict[str, Any]) -> list[str]:
    rows = contract.get("folder_layout")
    if not isinstance(rows, list):
        return []
    names: list[str] = []
    for item in rows:
        row = ensure_dict(item)
        name = str(row.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def expected_folder_tree(contract: dict[str, Any]) -> dict[str, list[str]]:
    rows = contract.get("folder_layout")
    if not isinstance(rows, list):
        return {}
    tree: dict[str, list[str]] = {}
    for item in rows:
        row = ensure_dict(item)
        parent_name = str(row.get("name") or "").strip()
        if not parent_name:
            continue
        children = row.get("children")
        if not isinstance(children, list):
            continue
        child_names: list[str] = []
        for child in children:
            child_row = ensure_dict(child)
            child_name = str(child_row.get("name") or "").strip()
            if child_name:
                child_names.append(child_name)
        if child_names:
            tree[parent_name] = child_names
    return tree


def inspect_workspace(client: Any, *, root_folder_id: str, contract: dict[str, Any], apply: bool) -> dict[str, Any]:
    root = client.get_item(root_folder_id)
    if str(root.get("mimeType") or "") != FOLDER_MIME:
        raise RuntimeError("configured root folder is not a folder")

    expected_names = expected_folder_names(contract)
    expected_tree = expected_folder_tree(contract)
    existing_children = client.list_child_folders(root_folder_id)
    existing_by_name = {str(item.get("name") or "").strip(): ensure_dict(item) for item in existing_children if str(item.get("name") or "").strip()}

    missing = [name for name in expected_names if name not in existing_by_name]
    extra = [name for name in sorted(existing_by_name) if name not in expected_names]
    created: list[dict[str, Any]] = []

    if apply:
        for name in missing:
            created.append(client.create_folder(name, root_folder_id))
        existing_children = client.list_child_folders(root_folder_id)
        existing_by_name = {str(item.get("name") or "").strip(): ensure_dict(item) for item in existing_children if str(item.get("name") or "").strip()}
        missing = [name for name in expected_names if name not in existing_by_name]
        extra = [name for name in sorted(existing_by_name) if name not in expected_names]

    nested: dict[str, Any] = {}
    for parent_name, child_names in expected_tree.items():
        parent = existing_by_name.get(parent_name)
        nested_row: dict[str, Any] = {
            "expected_names": child_names,
            "existing_names": [],
            "missing": list(child_names),
            "extra": [],
            "created": [],
        }
        if parent:
            parent_id = str(parent.get("id") or "").strip()
            child_rows = client.list_child_folders(parent_id)
            child_by_name = {
                str(item.get("name") or "").strip(): ensure_dict(item)
                for item in child_rows
                if str(item.get("name") or "").strip()
            }
            nested_row["existing_names"] = sorted(child_by_name.keys())
            nested_row["missing"] = [name for name in child_names if name not in child_by_name]
            nested_row["extra"] = [name for name in sorted(child_by_name) if name not in child_names]
            if apply and nested_row["missing"]:
                created_children: list[dict[str, Any]] = []
                for name in list(nested_row["missing"]):
                    created_children.append(client.create_folder(name, parent_id))
                child_rows = client.list_child_folders(parent_id)
                child_by_name = {
                    str(item.get("name") or "").strip(): ensure_dict(item)
                    for item in child_rows
                    if str(item.get("name") or "").strip()
                }
                nested_row["existing_names"] = sorted(child_by_name.keys())
                nested_row["missing"] = [name for name in child_names if name not in child_by_name]
                nested_row["extra"] = [name for name in sorted(child_by_name) if name not in child_names]
                nested_row["created"] = [
                    {"id": str(item.get("id") or ""), "name": str(item.get("name") or "")}
                    for item in created_children
                ]
        nested[parent_name] = nested_row

    return {
        "ok": not missing and all(not ensure_dict(row).get("missing") for row in nested.values()),
        "root": {
            "id": str(root.get("id") or ""),
            "name": str(root.get("name") or ""),
            "owners": ensure_dict({"items": root.get("owners")}).get("items", []),
            "permissions": ensure_dict({"items": root.get("permissions")}).get("items", []),
        },
        "expected_names": expected_names,
        "existing_names": sorted(existing_by_name.keys()),
        "missing": missing,
        "extra": extra,
        "created": [{"id": str(item.get("id") or ""), "name": str(item.get("name") or "")} for item in created],
        "nested": nested,
    }


def load_fixture_payload(path: Path) -> FixtureDriveClient:
    data = ensure_dict(json.loads(path.read_text(encoding="utf-8")))
    return FixtureDriveClient(root=ensure_dict(data.get("root")), children=[ensure_dict(item) for item in data.get("children", []) if isinstance(item, dict)])


def human_output(summary: dict[str, Any], apply: bool) -> str:
    root = ensure_dict(summary.get("root"))
    lines = [
        "Drive shared-workspace summary:",
        f"- Root: {root.get('name')} ({root.get('id')})",
        f"- Existing folders: {', '.join(summary.get('existing_names', [])) or '(none)'}",
    ]
    if summary.get("missing"):
        lines.append(f"- Missing folders: {', '.join(summary['missing'])}")
    else:
        lines.append("- Missing folders: none")
    if summary.get("extra"):
        lines.append(f"- Extra folders: {', '.join(summary['extra'])}")
    else:
        lines.append("- Extra folders: none")
    if apply and summary.get("created"):
        lines.append(
            "- Created: " + ", ".join(f"{item['name']} ({item['id']})" for item in summary["created"])
        )
    nested = ensure_dict(summary.get("nested"))
    for parent_name, row in nested.items():
        nested_row = ensure_dict(row)
        lines.append(f"- Nested {parent_name}: existing={', '.join(nested_row.get('existing_names', [])) or '(none)'}")
        if nested_row.get("missing"):
            lines.append(f"  missing={', '.join(nested_row['missing'])}")
    return "\n".join(lines)


def run_workspace(args: argparse.Namespace) -> int:
    env_file_values: dict[str, str] = {}
    if args.env_file:
        env_file_values = load_env_file(Path(args.env_file).expanduser().resolve())

    integration, workspace_policy, contract = resolve_drive_integration(Path(args.config).expanduser().resolve())
    root_folder_id = resolve_root_folder_id(
        workspace_policy=workspace_policy,
        env_file_values=env_file_values,
        override=args.root_folder_id,
    )
    status_path = resolve_status_path(args.status_file)

    if args.fixtures_file:
        client: Any = load_fixture_payload(Path(args.fixtures_file).expanduser().resolve())
    else:
        oauth = GoogleOAuthClient(
            client_id=env_get("GOOGLE_CLIENT_ID", env_file_values),
            client_secret=env_get("GOOGLE_CLIENT_SECRET", env_file_values),
            refresh_token=env_get("GOOGLE_REFRESH_TOKEN", env_file_values),
        )
        missing = [name for name, value in {
            "GOOGLE_CLIENT_ID": oauth.client_id,
            "GOOGLE_CLIENT_SECRET": oauth.client_secret,
            "GOOGLE_REFRESH_TOKEN": oauth.refresh_token,
        }.items() if not value]
        if missing:
            print(f"Missing required env for Drive workspace bootstrap: {', '.join(missing)}")
            return 2
        access_token = oauth.fetch_access_token()
        client = DriveClient(GoogleApiClient(access_token))

    summary = inspect_workspace(client, root_folder_id=root_folder_id, contract=contract, apply=args.apply)
    status_payload = {
        "generated_at": now_iso(),
        "summary": summary,
    }
    write_json(status_path, status_payload)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(human_output(summary, args.apply))

    if args.strict and not summary.get("ok"):
        return 3
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify or bootstrap the shared Google Drive workspace")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--env-file", help="dotenv-style env file to use without exporting vars")
    parser.add_argument("--root-folder-id", help="override GOOGLE_DRIVE_ROOT_FOLDER_ID")
    parser.add_argument("--status-file", help="write latest workspace status JSON to this path")
    parser.add_argument("--apply", action="store_true", help="create missing contract folders under the configured root")
    parser.add_argument("--strict", action="store_true", help="exit non-zero if workspace is incomplete after inspection")
    parser.add_argument("--fixtures-file", help="JSON fixture file containing root/children payloads")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(run_workspace(args))


if __name__ == "__main__":
    sys.exit(main())
