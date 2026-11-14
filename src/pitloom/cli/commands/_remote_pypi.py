# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A PyPI project or release URL on the command line: the wheel or sdist of
the release is downloaded, verified and read as a local file is.

Shared by ``loom wheel <url>``, ``loom project <url>`` and ``loom generate
<url>``.

See also: :func:`pitloom.assemble.generate_pypi_sbom` (the library's same
route) and :mod:`pitloom.cli.commands._remote` (the Git URL analogue).
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from pitloom._sbom_io import write_sbom_output
from pitloom.assemble import PypiSbom, generate_pypi_sbom_with_download
from pitloom.cli.commands.utils import _print_sbom_output_path
from pitloom.cli.kv_output import log_kv, log_verbose
from pitloom.cli.options import _resolve_output_path, build_options_from_args
from pitloom.cli.options_config import explicit_config_and_options
from pitloom.core.build_options import BuildOptions
from pitloom.core.config import PitloomConfig
from pitloom.core.internal_error import InternalError
from pitloom.core.url_masking import sanitize_url
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.extract.remote.pypi import SDIST, WHEEL, sdist_hint
from pitloom.logging_config import print_error
from pitloom.messages.pypi import (
    EMBED_URL_LINE,
    PYPI_URL_UNUSABLE,
)

__all__ = ["refuse_embed_of_pypi_url", "run_pypi"]

log = logging.getLogger(__name__)


def refuse_embed_of_pypi_url(url: str) -> int:
    """Refuse ``--embed`` for the PyPI URL *url* (nothing is fetched): the
    wheel would be written into a temporary file that is removed on return.
    Returns the exit status 1."""
    print_error(
        EMBED_URL_LINE.render({"url": sanitize_url(url.strip())}),
        code=PYPI_URL_UNUSABLE.code,
    )
    return 1


def _default_output(
    result: PypiSbom, pitloom_config: PitloomConfig | None, explicit: Path | None
) -> Path:
    """Where the SBOM goes: *explicit* (``-o``), else where the local command
    of the download's kind writes it: a wheel's file name plus
    ``.spdx3.json`` in the current directory, a project's ``--config``
    ``sbom-basename``, else ``<name>-<version>.spdx3.json`` (``<name>``
    without a version) from the metadata read from the sdist."""
    if explicit is None and result.download.kind == WHEEL:
        return Path.cwd() / f"{result.download.filename}{SPDX3_JSONLD_EXTENSION}"
    return _resolve_output_path(
        explicit, result.metadata, pitloom_config or PitloomConfig()
    )


def run_pypi(
    args: argparse.Namespace, url: str, kind: str, *, hint: bool = False
) -> int:
    """Generate the SBOM of the *kind* (``"wheel"`` or ``"sdist"``) file of
    the release the PyPI URL *url* names, and write it where the local
    ``loom wheel`` (the downloaded file's name) or ``loom project``
    (``<name>-<version>``, ``<name>`` without a version) command writes
    theirs; ``-o`` overrides, ``-o -`` is stdout.

    The download is untrusted: its own ``[tool.pitloom]`` is ignored (only
    ``--config`` applies) and no build backend runs. ``--offline`` (or
    ``offline`` in ``--config``) forbids the fetch. *hint* adds the one
    ``INFO:`` that names ``loom project <url>`` for the sdist
    (``loom generate``).
    """
    if kind not in (WHEEL, SDIST):
        raise InternalError(f"kind must be {WHEEL!r} or {SDIST!r}, got {kind!r}")
    subject = url.strip()
    pitloom_config, options = explicit_config_and_options(args)
    if args.verbose:
        log_verbose(PYPI_URL=sanitize_url(subject))
    result = generate_pypi_sbom_with_download(
        subject,
        kind=kind,
        pitloom_config=pitloom_config,
        # `loom wheel` has no build flags.
        build_options=(
            build_options_from_args(args)
            if hasattr(args, "allow_build")
            else BuildOptions()
        ),
        **options,
    )
    output = _default_output(result, pitloom_config, args.output)
    if args.verbose:
        log_kv(OUTPUT_PATH=output)
    write_sbom_output(result.sbom, output)
    if hint:
        sdist_hint(subject)
    _print_sbom_output_path(output)
    return 0
