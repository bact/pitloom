# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pitloom.__about__ import __version__
from pitloom.assemble import (
    generate_env_sbom,
)
from pitloom.cli.commands.utils import cli_error_handler
from pitloom.cli.constants import _SPDX3_JSON_EXT
from pitloom.cli.options import _resolve_common_options


@cli_error_handler("deployed SBOM generation failed")
def _run_env_command(args: argparse.Namespace) -> int:
    """Generate a Deployed SBOM for the active installed environment."""
    pitloom_config, creation, effective_pretty, effective_describe = (
        _resolve_common_options(args, load_project=False)
    )
    output_path = args.output or (Path.cwd() / f"deployed-environment{_SPDX3_JSON_EXT}")

    if args.verbose:
        print(f"Pitloom version : {__version__}")
        print(f"Output path     : {output_path}")

    generate_env_sbom(
        output_path=output_path,
        creation_metadata=creation,
        pretty=effective_pretty,
        describe_relationship=effective_describe,
        registry=args.registry,
        provenance=pitloom_config.provenance,
        offline=args.offline or None,
    )
    return 0


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
