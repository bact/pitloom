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
    generate_project_sbom,
)
from pitloom.cli.commands.utils import cli_error_handler
from pitloom.cli.options import (
    _resolve_creation_metadata,
    _resolve_output_path,
    _resolve_project_paths,
)
from pitloom.cli.verbose import _print_verbose
from pitloom.extract.project import read_project


@cli_error_handler("SBOM generation failed")
def _run_project_command(args: argparse.Namespace) -> int:
    """Generate a Source SBOM from a project directory or sdist archive."""
    project_dir, config_path = _resolve_project_paths(args)
    if project_dir is None:
        return 1

    project_metadata, pitloom_config, config_path = read_project(project_dir)
    creation = _resolve_creation_metadata(args, pitloom_config)
    effective_pretty = pitloom_config.pretty if args.pretty is None else args.pretty
    effective_describe_relationship = (
        pitloom_config.describe_relationship
        if args.describe_relationship is None
        else args.describe_relationship
    )

    output_path = _resolve_output_path(args.output, project_metadata, pitloom_config)

    if args.verbose:
        _print_verbose(
            args,
            project_dir,
            output_path,
            pitloom_config,
            config_path,
            creation,
        )

    generate_project_sbom(
        project_dir,
        output_path=output_path,
        creation_metadata=creation.to_creation_metadata(),
        pretty=effective_pretty,
        describe_relationship=effective_describe_relationship,
        project_metadata=project_metadata,
        pitloom_config=pitloom_config,
        registry=args.registry,
        provenance=pitloom_config.provenance,
        enrich=args.enrich,
        offline=args.offline or None,
        extract_file_header=args.extract_file_header,
        content_type=args.content_type,
        content_type_method=args.content_type_method,
    )
    return 0


def add_parser(subparsers: Any, parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``project`` subcommand."""
    # Note: Using 4-space indent
    # 2. Project Source & Sdist: loom project [PATH]
    proj_parser = subparsers.add_parser(
        "project",
        parents=[parent_parser],
        help="Generate a Source SBOM from a project directory or sdist archive.",
    )
    proj_parser.add_argument(
        "project_dir",
        type=Path,
        nargs="?",
        default=Path.cwd(),
        help="Path to project directory or sdist archive (.tar.gz, .zip).",
    )
    proj_parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Forbid network access -- skip PyPI lookup, no error "
            "(local metadata already covers what it can)."
        ),
    )
    proj_parser.set_defaults(func=_run_project_command)
