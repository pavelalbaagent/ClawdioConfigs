#!/usr/bin/env python3
"""Normalize dotenv-style env files into a canonical shell-safe form."""

from __future__ import annotations

import argparse
from pathlib import Path

from env_file_utils import dump_env_text, load_env_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize a dotenv-style env file")
    parser.add_argument("source", help="input env file")
    parser.add_argument("--output", help="optional output path; defaults to source")
    parser.add_argument("--no-sort", action="store_true", help="preserve input key order where possible")
    parser.add_argument("--check", action="store_true", help="validate and report; do not write")
    parser.add_argument(
        "--header-comment",
        default="normalized by scripts/normalize_env_file.py",
        help="optional header comment for written files",
    )
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    values = load_env_file(source, strict=True)
    output_text = dump_env_text(
        values,
        sort_keys=not args.no_sort,
        header_comment=None if args.check else args.header_comment,
    )

    if args.check:
        print(f"OK: {source}")
        print(f"keys={len(values)}")
        return 0

    output = Path(args.output).expanduser().resolve() if args.output else source
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(output_text, encoding="utf-8")
    print(f"Normalized env file written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
