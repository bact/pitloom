# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import sys
import traceback
from typing import Any

from pitloom.assemble import (
    generate,
)
from pitloom.cli.options import (
    _resolve_generate_mode_settings,
)

_SPDX3_JSON_EXT = ".spdx3.json"
_PROJECT_PYPROJECT_SOURCE = "pyproject.toml"
_PROJECT_SETUP_CFG_SOURCE = "setup.cfg"
_PROJECT_SETUP_PY_SOURCE = "setup.py"


def _run_generate_command(args: argparse.Namespace) -> int:
    """Smart generate mode."""
    try:
        creation_metadata, pretty, describe_relationship = (
            _resolve_generate_mode_settings(args)
        )
        output_path = args.output
        generate(
            args.target,
            offline=args.offline or None,
            output_path=output_path,
            creation_metadata=creation_metadata,
            pretty=pretty,
            describe_relationship=describe_relationship,
            registry=args.registry,
            enrich=args.enrich,
            extract_file_header=args.extract_file_header,
            content_type=args.content_type,
            content_type_method=args.content_type_method,
        )
        return 0
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"ERROR: SBOM generation failed: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1


def add_parser(subparsers: Any, parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``generate`` subcommand."""
    # Note: Using 4-space indent
    # 1. Smart Entrypoint: loom generate [TARGET]
    gen_parser = subparsers.add_parser(
        "generate",
        parents=[parent_parser],
        help="Generate an SBOM with automatic target detection.",
    )
    gen_parser.add_argument(
        "target",
        type=str,
        nargs="?",
        default=".",
        help="Target path, sdist archive, .whl, model file, HF URL, or 'env'.",
    )
    gen_parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Forbid network access; effect depends on the resolved target -- "
            "HF URL/ID: error, no fetch attempted (no local fallback exists). "
            "project dir / .whl: skip PyPI lookup, no error (local metadata "
            "already covers what it can). "
            "local model file: no-op (no network path exists)."
        ),
    )
    gen_parser.set_defaults(func=_run_generate_command)
