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
from pitloom.cli.commands.utils import _print_sbom_output_path, cli_error_handler
from pitloom.cli.options import (
    _resolve_output_path,
    _resolve_project_generation_settings,
    _resolve_project_paths,
    add_allow_build_argument,
    add_build_timeout_argument,
    add_no_build_isolation_argument,
    add_offline_argument,
    add_use_lockfile_argument,
    build_options_from_args,
)
from pitloom.cli.options_config import run_options
from pitloom.cli.verbose import log_verbose_options
from pitloom.core.build_options import BuildOptions


def generate_project_from_args(
    args: argparse.Namespace, project_dir: Path, build_options: BuildOptions
) -> Path:
    """Generate the SBOM for a project directory or sdist *project_dir* from
    parsed arguments; return the output path it was written to.

    Shared by ``loom project`` and ``loom generate`` on a project target, so
    the two resolve config, output name, ``--verbose`` and every option the
    same way. *build_options* must already be settled for *project_dir*.
    """
    project_metadata, pitloom_config, config_path, creation = (
        _resolve_project_generation_settings(args, project_dir)
    )
    output_path = _resolve_output_path(args.output, project_metadata, pitloom_config)
    if args.verbose:
        log_verbose_options(
            args, project_dir, output_path, pitloom_config, config_path, creation
        )
    options = run_options(args, pitloom_config)
    options["creation_metadata"] = creation.to_creation_metadata()
    generate_project_sbom(
        project_dir,
        output_path=output_path,
        project_metadata=project_metadata,
        pitloom_config=pitloom_config,
        build_options=build_options,
        **options,
    )
    return output_path


@cli_error_handler("SBOM generation failed")
def _run_project_command(args: argparse.Namespace) -> int:
    """Generate a Source SBOM from a project directory or sdist archive."""
    # Settle before the path check and the metadata/lock-file read below,
    # so the build-flag WARNING: is the first thing the run logs -- and is
    # logged at all for a directory the check then rejects, as `generate`,
    # `embed-wheel` and the library surfaces all do;
    # generate_project_sbom()'s own settle then finds nothing left to warn
    # about.
    build_options = build_options_from_args(args).settle_target(
        args.project_dir.resolve()
    )

    project_dir, _config_path = _resolve_project_paths(args)
    if project_dir is None:
        return 1

    _print_sbom_output_path(
        generate_project_from_args(args, project_dir, build_options)
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
    add_offline_argument(
        proj_parser,
        " -- skip PyPI lookup, no error (local metadata already covers what it can).",
    )
    add_use_lockfile_argument(
        proj_parser,
        " -- fall back to direct dependencies + environment introspection "
        "only (no-op for an sdist archive target: no lock-file concept "
        "applies there)",
    )
    add_allow_build_argument(proj_parser)
    add_no_build_isolation_argument(proj_parser)
    add_build_timeout_argument(proj_parser)
    proj_parser.set_defaults(func=_run_project_command)
