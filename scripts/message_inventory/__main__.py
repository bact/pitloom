# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command line of the message inventory (see the package docstring)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import (
    BASELINE_PATH,
    collect_skill_quotes,
    compare,
    families,
    format_baseline,
    inventory,
    match_quotes,
    parse_baseline,
    summary,
    uncoded_counts,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_jsonl(rows: list[dict[str, Any]], target: str) -> None:
    text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    )
    if target == "-":
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()
    else:
        Path(target).write_bytes(text.encode("utf-8"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.message_inventory",
        description="Inventory of the messages src/pitloom emits.",
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root")
    parser.add_argument(
        "--baseline", type=Path, help=f"baseline file (default ROOT/{BASELINE_PATH})"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="run the ratchet")
    group.add_argument(
        "--write-baseline", action="store_true", help="rewrite the baseline"
    )
    group.add_argument("--jsonl", metavar="FILE", help="every site, '-' for stdout")
    group.add_argument("--quotes", metavar="FILE", help="skill quotes matched to sites")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command; the exit status (1: the ratchet failed)."""
    args = _parser().parse_args(argv)
    root: Path = args.root.resolve()
    baseline_path: Path = args.baseline or root / BASELINE_PATH
    records = inventory(root)
    if args.jsonl:
        _write_jsonl(records, args.jsonl)
    elif args.quotes:
        quotes = collect_skill_quotes(root)
        match_quotes(quotes, records)
        _write_jsonl(quotes, args.quotes)
    elif args.write_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        text = format_baseline(uncoded_counts(records))
        baseline_path.write_bytes(text.encode("utf-8"))
        try:
            shown: Path = baseline_path.relative_to(root)
        except ValueError:
            shown = baseline_path
        print(f"INFO: wrote {shown.as_posix()}", file=sys.stderr)
    elif args.check:
        problems = compare(
            parse_baseline(baseline_path.read_text(encoding="utf-8")),
            uncoded_counts(records),
        )
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 1 if problems else 0
    else:
        for key, value in summary(records).items():
            print(f"{key}={value}")
        for family, count in families(records).items():
            print(f"FAMILY={count} {family}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
