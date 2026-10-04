# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from pitloom._sbom_io import STDOUT, write_sbom_output
from pitloom.assemble import merge_fragments
from pitloom.cli.commands.utils import _print_sbom_output_path, cli_error_handler
from pitloom.core.config import FragmentConfig
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION, Spdx3JsonExporter

log = logging.getLogger(__name__)


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
    merge_fragments(
        fragments_dir,
        [FragmentConfig(path=f) for f in fragment_files],
        exporter,
    )

    sbom_json = exporter.to_json(pretty=bool(args.pretty))
    output_path: Path = args.output
    write_sbom_output(sbom_json, output_path)
    if str(output_path) != STDOUT:
        _print_sbom_output_path(output_path)
    log.info("merge: merged %d fragment(s)", len(fragment_files))
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
        default=Path.cwd() / f"merged{SPDX3_JSONLD_EXTENSION}",
        help="Output JSON-LD path.",
    )
    merge_parser.add_argument(
        "--pretty",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Indent JSON output with 2 spaces.",
    )
    merge_parser.set_defaults(func=_run_merge_command)
