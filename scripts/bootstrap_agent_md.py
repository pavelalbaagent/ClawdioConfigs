#!/usr/bin/env python3
"""Bootstrap agent markdown baseline files into a target workspace."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "baselines" / "agent_md"


def render_template(text: str) -> str:
    today = date.today().isoformat()
    return text.replace("{{TODAY}}", today)


def copy_tree(source: Path, target: Path, force: bool) -> tuple[list[Path], list[Path]]:
    created: list[Path] = []
    skipped: list[Path] = []

    for src in sorted(source.rglob("*")):
        rel = src.relative_to(source)
        if ".memory" in rel.parts:
            # Skip runtime state folders that should not be part of baseline templates.
            continue
        dst = target / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and not force:
            skipped.append(dst)
            continue

        try:
            content = src.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            skipped.append(dst)
            continue
        dst.write_text(render_template(content), encoding="utf-8")
        created.append(dst)

    return created, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap agent markdown baseline files")
    parser.add_argument("--target", default=".", help="target workspace path")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="source baseline directory")
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    target = Path(args.target).resolve()

    if not source.exists() or not source.is_dir():
        print(f"Source baseline directory not found: {source}")
        return 1

    created, skipped = copy_tree(source, target, args.force)

    print(f"Source: {source}")
    print(f"Target: {target}")
    print(f"Created/updated: {len(created)}")
    for path in created:
        print(f"- {path}")

    if skipped:
        print(f"Skipped existing: {len(skipped)}")
        for path in skipped:
            print(f"- {path}")

    print("Bootstrap complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
