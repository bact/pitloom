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
from pitloom.cli.commands.utils import (
    _print_sbom_output_path,
    cli_error_handler,
    resolve_effective_provenance,
)
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
from pitloom.cli.verbose import _print_verbose
from pitloom.core.build_options import SDIST_TARGET_REASON


@cli_error_handler("SBOM generation failed")
def _run_project_command(args: argparse.Namespace) -> int:
    """Generate a Source SBOM from a project directory or sdist archive."""
    project_dir, config_path = _resolve_project_paths(args)
    if project_dir is None:
        return 1

    # Settle a stray --no-build-isolation/--build-timeout (given without
    # --allow-build) right now, before the metadata/lock-file read below,
    # for a real project directory -- not for an sdist archive target
    # (project_dir.is_file()), whose own "without --allow-build" wording
    # would misdescribe why the flags are ineffective there.
    build_options = build_options_from_args(
        args, None if project_dir.is_file() else project_dir
    )
    if project_dir.is_file():
        # sdist archive target: warn about any given build flag -- with
        # its own target-specific reason, not "without --allow-build" --
        # and reset to defaults right now, before the metadata/lock-file
        # read below, so this is the first thing the run logs.
        # generate_project_sbom()'s own settle_not_applicable() call for
        # the same target then finds nothing left to warn about.
        build_options = build_options.settle_not_applicable(
            project_dir, SDIST_TARGET_REASON
        )

    (
        project_metadata,
        pitloom_config,
        config_path,
        creation,
        effective_pretty,
        effective_describe_relationship,
    ) = _resolve_project_generation_settings(args, project_dir)

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
        update_registry=args.update_registry,
        provenance=resolve_effective_provenance(pitloom_config, args),
        enrich=args.enrich,
        offline=args.offline,
        extract_file_header=args.extract_file_header,
        content_type=args.content_type,
        content_type_method=args.content_type_method,
        build_options=build_options,
    )
    _print_sbom_output_path(output_path)
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
