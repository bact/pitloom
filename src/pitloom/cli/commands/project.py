# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``project`` subcommand: a Source SBOM from a project directory, an sdist
archive or a Git URL."""

from __future__ import annotations

import argparse
import logging
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
from pitloom.cli.options_config import add_archive_project_dir_argument, run_options
from pitloom.cli.options_resolve import load_explicit_config
from pitloom.cli.verbose import log_verbose_options
from pitloom.core.build_options import REMOTE_REPOSITORY_REASON, BuildOptions
from pitloom.core.inert_options import GIT, settle_inert
from pitloom.extract.remote import (
    fetch_git_project,
    is_git_url,
    is_unsupported_remote_url,
)
from pitloom.extract.remote.git import CONFIG_IGNORED_INFO

log = logging.getLogger(__name__)


def generate_project_from_args(
    args: argparse.Namespace,
    project_dir: Path,
    build_options: BuildOptions,
    *,
    remote_url: str | None = None,
) -> Path:
    """Generate the SBOM for a project directory or sdist *project_dir* from
    parsed arguments; return the output path it was written to.

    Shared by ``loom project`` and ``loom generate`` on a project target, so
    the two resolve config, output name, ``--verbose`` and every option the
    same way. *build_options* must already be settled for *project_dir*.
    *remote_url* is set for a project fetched from that remote repository:
    its own ``[tool.pitloom]`` does not apply, and the options that have no
    effect on it are settled against the URL, not the temporary checkout.
    """
    project_metadata, pitloom_config, config_path, creation = (
        _resolve_project_generation_settings(
            args, project_dir, ignore_project_config=remote_url is not None
        )
    )
    output_path = _resolve_output_path(args.output, project_metadata, pitloom_config)
    if args.verbose:
        log_verbose_options(
            args, project_dir, output_path, pitloom_config, config_path, creation
        )
    options = run_options(args, pitloom_config)
    options["creation_metadata"] = creation.to_creation_metadata()
    if remote_url is not None:
        settled = settle_inert(GIT, remote_url, options)
        options = {k: v for k, v in options.items() if k not in settled}
    generate_project_sbom(
        project_dir,
        output_path=output_path,
        project_metadata=project_metadata,
        pitloom_config=pitloom_config,
        build_options=build_options,
        **options,
    )
    return output_path


def run_remote_project(args: argparse.Namespace, url: str) -> int:
    """Generate a Source SBOM for the project at the Git URL *url*: fetch the
    repository (or the folder of it the URL names), then read it as
    ``loom project`` reads a directory.

    Shared by ``loom project <url>`` and ``loom generate <url>``. The
    repository is untrusted: its own ``[tool.pitloom]`` is ignored (only
    ``--config`` applies) and its build backend never runs. ``--offline``
    (or ``offline`` in ``--config``) forbids the fetch.
    """
    explicit = load_explicit_config(args)
    offline = args.offline
    if offline is None and explicit is not None:
        offline = explicit.offline
    build_options = build_options_from_args(args).settle_not_applicable(
        url, REMOTE_REPOSITORY_REASON
    )
    with fetch_git_project(url, offline=offline) as checkout:
        if explicit is None:
            log.info(CONFIG_IGNORED_INFO)
        with checkout.explaining_failures():
            output = generate_project_from_args(
                args,
                Path(checkout.folder),
                build_options,
                remote_url=url,
            )
    _print_sbom_output_path(output)
    return 0


def _project_target(text: str) -> Path | str:
    """A ``project`` target: the text itself for a Git URL (a ``Path`` would
    collapse its ``//``) or any other remote address (refused with a message
    naming what is fetched), else a path."""
    if is_git_url(text) or (
        is_unsupported_remote_url(text) and not Path(text).exists()
    ):
        return text.strip()
    return Path(text)


@cli_error_handler("SBOM generation failed")
def _run_project_command(args: argparse.Namespace) -> int:
    """Generate a Source SBOM from a project directory, sdist archive or Git
    URL."""
    if isinstance(args.project_dir, str):
        return run_remote_project(args, args.project_dir)
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
        type=_project_target,
        nargs="?",
        default=Path.cwd(),
        help="Path to project directory or sdist archive (.tar.gz, .zip), or "
        "the http(s) URL of a Git repository or of one of its web pages (a "
        "branch, tag or commit and a folder may be named). A repository is "
        "fetched shallowly; its own [tool.pitloom] is ignored (--config "
        "applies) and its build backend never runs.",
    )
    add_offline_argument(
        proj_parser,
        " -- skip PyPI lookup, no error (local metadata already covers what it "
        "can). A Git URL: error, nothing is fetched.",
    )
    add_use_lockfile_argument(
        proj_parser,
        " -- fall back to direct dependencies + environment introspection "
        "only (no-op for an sdist archive target: no lock-file concept "
        "applies there)",
    )
    add_archive_project_dir_argument(proj_parser)
    add_allow_build_argument(proj_parser)
    add_no_build_isolation_argument(proj_parser)
    add_build_timeout_argument(proj_parser)
    proj_parser.set_defaults(func=_run_project_command)
