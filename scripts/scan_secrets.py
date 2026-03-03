#!/usr/bin/env python3
"""Lightweight secret scanner for text files."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PATTERNS = [
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("slack_app_token", re.compile(r"xapp-[A-Za-z0-9-]{10,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("gateway_token", re.compile(r"OPENCLAW_GATEWAY_TOKEN\s*=\s*[A-Za-z0-9]{16,}")),
    (
        "generic_secret_assignment",
        re.compile(
            r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9._\-/]{16,}"
        ),
    ),
]

ALLOW_SUBSTRINGS = {
    "<REDACTED>",
    "<PRIVATE_PHONE>",
    "example",
    "placeholder",
    "dummy",
    "sample",
}

SKIP_DIRS = {".git", "external", "node_modules", "__pycache__"}


def get_default_files() -> list[Path]:
    cmd = ["git", "ls-files"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    files: list[Path] = []
    for raw in proc.stdout.splitlines():
        p = ROOT / raw
        if p.is_file():
            files.append(p)
    return files


def is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(2048)
        return b"\x00" in chunk
    except OSError:
        return True


def should_skip(path: Path) -> bool:
    rel_parts = path.relative_to(ROOT).parts
    return any(part in SKIP_DIRS for part in rel_parts)


def scan_file(path: Path) -> list[str]:
    findings: list[str] = []
    if should_skip(path) or is_binary(path):
        return findings

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return findings

    for idx, line in enumerate(lines, start=1):
        lowered = line.lower()
        if any(token in lowered for token in ALLOW_SUBSTRINGS):
            continue
        for name, pattern in PATTERNS:
            if pattern.search(line):
                findings.append(f"{path.relative_to(ROOT)}:{idx}: {name}")
                break
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan repository files for potential secrets")
    parser.add_argument("files", nargs="*", help="optional file list to scan")
    args = parser.parse_args()

    if args.files:
        paths = [(ROOT / f).resolve() if not os.path.isabs(f) else Path(f) for f in args.files]
        files = [p for p in paths if p.exists() and p.is_file()]
    else:
        files = get_default_files()

    all_findings: list[str] = []
    for file_path in files:
        all_findings.extend(scan_file(file_path))

    if all_findings:
        print("Potential secrets detected:")
        for item in all_findings:
            print(f"- {item}")
        return 1

    print("Secret scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
