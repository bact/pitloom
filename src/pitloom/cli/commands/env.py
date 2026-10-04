# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pitloom.assemble import (
    generate_env_sbom,
)
from pitloom.cli.commands.utils import _print_sbom_output_path, cli_error_handler
from pitloom.cli.kv_output import log_verbose
from pitloom.cli.options import add_offline_argument
from pitloom.cli.options_config import explicit_config_and_options
from pitloom.core.inert_options import ENV, forward_options
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION


@cli_error_handler("deployed SBOM generation failed")
def _run_env_command(args: argparse.Namespace) -> int:
    """Generate a Deployed SBOM for the active installed environment."""
    pitloom_config, options = explicit_config_and_options(args)
    output_path = args.output or (
        Path.cwd() / f"deployed-environment{SPDX3_JSONLD_EXTENSION}"
    )

    if args.verbose:
        log_verbose(OUTPUT_PATH=output_path)

    generate_env_sbom(
        output_path=output_path,
        pitloom_config=pitloom_config,
        **forward_options(ENV, "env", generate_env_sbom, options),
    )
    _print_sbom_output_path(output_path)
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
    add_offline_argument(
        env_parser,
        " -- skip PyPI lookup, no error (local metadata already covers what it can).",
    )
    env_parser.set_defaults(func=_run_env_command)
