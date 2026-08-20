# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from pitloom.assemble import merge_fragments
from pitloom.cli.commands.utils import cli_error_handler
from pitloom.cli.constants import _SPDX3_JSON_EXT
from pitloom.export.spdx3_json import Spdx3JsonExporter


def _write_merge_output(sbom_json: str, output_path: Path) -> None:
    """Write merged SBOM output to stdout or file. Appends a newline to
    stdout output only when the JSON doesn't already end with one."""
    if str(output_path) == "-":
        sys.stdout.write(sbom_json)
        if not sbom_json.endswith("\n"):
            sys.stdout.write("\n")
    else:
        output_path.write_text(sbom_json, encoding="utf-8")


@cli_error_handler("fragment merge failed")
def _run_merge_command(args: argparse.Namespace) -> int:
    """Merge dynamic execution fragments into a combined SBOM."""
    fragments_dir: Path = args.fragments_dir.resolve()
    if not fragments_dir.exists():
        print(
            f"ERROR: fragments directory not found: {fragments_dir}",
            file=sys.stderr,
        )
        return 1

    fragment_files = [
        f.relative_to(fragments_dir).as_posix()
        for f in sorted(fragments_dir.glob("*.json"))
        if f.is_file()
    ]
    if not fragment_files:
        print(
            f"ERROR: no JSON fragment files found in {fragments_dir}",
            file=sys.stderr,
        )
        return 1

    exporter = Spdx3JsonExporter()
    merge_fragments(fragments_dir, fragment_files, exporter)

    sbom_json = exporter.to_json(pretty=bool(args.pretty))
    output_path: Path = args.output
    _write_merge_output(sbom_json, output_path)
    if str(output_path) != "-":
        print(f"pitloom: merged {len(fragment_files)} fragment(s) into {output_path}")
    return 0


def add_parser(subparsers: Any, _parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``merge`` subcommand."""
    # Note: Using 4-space indent
    # 6. Fragment Merger: loom merge <FRAGMENTS_DIR>
    merge_parser = subparsers.add_parser(
        "merge",
        help="Merge dynamic execution SBOM fragments into a combined SBOM.",
    )
    merge_parser.add_argument(
        "fragments_dir",
        type=Path,
        help="Directory containing .spdx3.json fragments.",
    )
    merge_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path.cwd() / f"merged{_SPDX3_JSON_EXT}",
        help="Output JSON-LD path.",
    )
    merge_parser.add_argument(
        "--pretty",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Indent JSON output with 2 spaces.",
    )
    merge_parser.set_defaults(func=_run_merge_command)
