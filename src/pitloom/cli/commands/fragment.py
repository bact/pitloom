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

from pitloom.cli.commands.utils import _validate_spdx3_documents, cli_error_handler


@cli_error_handler("fragment validate failed")
def _run_fragment_validate(args: argparse.Namespace) -> int:
    """Run `pitloom fragment validate`."""
    paths: list[Path] = args.paths
    not_files = [p for p in paths if not p.is_file()]
    if not_files:
        for p in not_files:
            kind = "directory" if p.is_dir() else "file not found"
            print(f"ERROR: {kind}: {p}", file=sys.stderr)
        return 1

    exit_code = _validate_spdx3_documents(
        [str(p) for p in paths], check_merged=not args.no_merge
    )
    if exit_code == 0:
        print(f"pitloom fragment validate: {len(paths)} document(s) valid")
    return exit_code


def _run_fragment_command(args: argparse.Namespace) -> int:
    """Dispatch `pitloom fragment <command> ...` arguments."""
    if args.fragment_command == "validate":
        return _run_fragment_validate(args)
    return 1


def add_parser(subparsers: Any, _parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``fragment`` subcommand to the main parser."""
    fragment_parser = subparsers.add_parser(
        "fragment",
        help="Work with dynamic execution SBOM fragments.",
        description=(
            "Work with dynamic execution SBOM fragments -- see also "
            "'pitloom merge' to combine fragments into one SBOM."
        ),
    )
    fragment_subparsers = fragment_parser.add_subparsers(
        dest="fragment_command", required=True
    )

    validate_parser = fragment_subparsers.add_parser(
        "validate",
        help="Validate SPDX 3 JSON document(s) against schema and SHACL rules.",
    )
    validate_parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        metavar="PATH",
        help="SPDX 3 JSON document(s) to validate.",
    )
    validate_parser.add_argument(
        "--no-merge",
        action="store_true",
        help=(
            "Skip the merged-graph check across multiple PATHs (which "
            "catches type errors across ExternalMap references); validate "
            "each document only in isolation."
        ),
    )

    fragment_parser.set_defaults(func=_run_fragment_command)
