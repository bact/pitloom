# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``merge`` subcommand: one SBOM from a directory of SPDX 3 fragments."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from pitloom.assemble import generate_merged_sbom
from pitloom.assemble.spdx3.fragments import fragment_files
from pitloom.cli.commands.utils import _print_sbom_output_path, cli_error_handler
from pitloom.core.given_path import TypedPath
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.logging_config import print_error
from pitloom.messages.targets import (
    INPUT_NOT_FOUND,
    NO_FRAGMENT_FILE_LINE,
    is_input_dir,
    say_input_not_found,
)

log = logging.getLogger(__name__)


@cli_error_handler
def _run_merge_command(args: argparse.Namespace) -> int:
    """Merge dynamic execution fragments into a combined SBOM."""
    fragments_dir: Path = args.fragments_dir.resolve()
    if not is_input_dir(fragments_dir, shown=args.fragments_dir):
        say_input_not_found("fragments directory", args.fragments_dir)
        return 1

    files = fragment_files(fragments_dir)
    if not files:
        print_error(
            NO_FRAGMENT_FILE_LINE.render({"path": args.fragments_dir}),
            code=INPUT_NOT_FOUND.code,
        )
        return 1

    output_path: Path = args.output
    generate_merged_sbom(
        fragments_dir, output_path=output_path, pretty=bool(args.pretty)
    )
    _print_sbom_output_path(output_path)
    log.info("merge: merged %d fragment(s)", len(files))
    return 0


def add_parser(subparsers: Any, _parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``merge`` subcommand."""
    # Fragment merger: loom merge <FRAGMENTS_DIR>
    merge_parser = subparsers.add_parser(
        "merge",
        help="Merge dynamic execution SBOM fragments into a combined SBOM.",
    )
    merge_parser.add_argument(
        "fragments_dir",
        type=TypedPath,
        help="Directory of SPDX 3 fragments (every *.json file in it).",
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
