# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Any

from pitloom.__about__ import __version__
from pitloom.assemble import (
    generate_env_sbom,
)
from pitloom.cli.options import _resolve_creation_metadata
from pitloom.core.config import PitloomConfig

_SPDX3_JSON_EXT = ".spdx3.json"
_PROJECT_PYPROJECT_SOURCE = "pyproject.toml"
_PROJECT_SETUP_CFG_SOURCE = "setup.cfg"
_PROJECT_SETUP_PY_SOURCE = "setup.py"


def _run_env_command(args: argparse.Namespace) -> int:
    """Generate a Deployed SBOM for the active installed environment."""
    try:
        pitloom_config = PitloomConfig()
        creation = _resolve_creation_metadata(args, pitloom_config)
        effective_pretty = args.pretty if args.pretty is not None else False
        effective_describe = (
            bool(args.describe_relationship)
            if args.describe_relationship is not None
            else False
        )

        output_path = args.output or (
            Path.cwd() / f"deployed-environment{_SPDX3_JSON_EXT}"
        )

        if args.verbose:
            print(f"Pitloom version : {__version__}")
            print(f"Output path     : {output_path}")

        generate_env_sbom(
            output_path=output_path,
            creation_metadata=creation.to_creation_metadata(),
            pretty=effective_pretty,
            describe_relationship=effective_describe,
            registry=args.registry,
            offline=args.offline or None,
        )
        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"ERROR: deployed SBOM generation failed: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1


def add_parser(subparsers: Any, parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``env`` subcommand."""
    # Note: Using 4-space indent
    # 5. Deployed Environment: loom env
    env_parser = subparsers.add_parser(
        "env",
        parents=[parent_parser],
        help="Generate a Deployed SBOM for the active installed environment.",
    )
    env_parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Forbid network access -- skip PyPI lookup, no error "
            "(local metadata already covers what it can)."
        ),
    )
    env_parser.set_defaults(func=_run_env_command)
