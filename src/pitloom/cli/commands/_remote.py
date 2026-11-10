# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Git URL on the command line: fetched, then read as ``loom project``
reads a directory or ``loom model`` a model file, by what the URL names.

Shared by ``loom project <url>``, ``loom model <url>`` and ``loom generate
<url>``.

See also: :mod:`pitloom.extract.remote.git_target` (what the SBOM of a URL
describes) and :func:`pitloom.assemble.generate_git_sbom` (the library's
same route).
"""

from __future__ import annotations

import argparse
import logging

from pitloom.cli.commands.utils import _print_sbom_output_path
from pitloom.cli.options_resolve import load_explicit_config
from pitloom.core.build_options import REMOTE_REPOSITORY_REASON, BuildOptions
from pitloom.core.inert_options import GIT_MODEL
from pitloom.extract.remote import fetch_git_project
from pitloom.extract.remote.git_target import resolve_git_target
from pitloom.messages import CONFIG_UNSAFE, CONFIG_UNSAFE_REMOTE_LINE, emit

__all__ = ["run_remote"]

log = logging.getLogger(__name__)


def run_remote(
    args: argparse.Namespace, url: str, mode: str, build_options: BuildOptions
) -> int:
    """Generate the SBOM of what the Git URL *url* names under *mode*
    (:func:`~pitloom.extract.remote.git_target.resolve_git_target`): fetch
    the repository (or the folder of it the URL names), then read its
    project as ``loom project`` reads a directory, or its model file as
    ``loom model`` reads one, the output written where that command writes
    it (never into the clone).

    The repository is untrusted: its own ``[tool.pitloom]`` is ignored (only
    ``--config`` applies) and its build backend never runs (each flag of
    *build_options* warns once). ``--offline`` (or ``offline`` in
    ``--config``) forbids the fetch. ``--trust-model-files`` runs the model
    readers a hostile file could crash or hang on the repository's files;
    no config key sets it.
    """
    # Imported here: these modules call run_remote (an import cycle).
    # pylint: disable-next=import-outside-toplevel,cyclic-import
    from pitloom.cli.commands.model import generate_model_from_args

    # pylint: disable-next=import-outside-toplevel,cyclic-import
    from pitloom.cli.commands.project import generate_project_from_args

    explicit = load_explicit_config(args)
    offline = args.offline
    if offline is None and explicit is not None:
        offline = explicit.offline
    settled = build_options.settle_not_applicable(url, REMOTE_REPOSITORY_REASON)
    with fetch_git_project(
        url, offline=offline, trust_model_files=args.trust_model_files is True
    ) as checkout:
        with checkout.reading():
            target = resolve_git_target(checkout, mode, url)
            if target.model is not None:
                output = generate_model_from_args(
                    args,
                    target.model.path,
                    kind=GIT_MODEL,
                    subject=url,
                    shown=target.model.shown,
                )
            else:
                if explicit is None:
                    emit(
                        log, CONFIG_UNSAFE, logging.INFO, line=CONFIG_UNSAFE_REMOTE_LINE
                    )
                output = generate_project_from_args(
                    args, target.folder, settled, remote_url=url
                )
    _print_sbom_output_path(output)
    return 0
