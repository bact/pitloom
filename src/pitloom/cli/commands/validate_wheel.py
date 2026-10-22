# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``validate-wheel`` subcommand: schema and SHACL validation of a wheel's
embedded SBOM."""

from __future__ import annotations

import argparse
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from pitloom.assemble import VALIDATED_FORMATS, EmbeddedSbomLocation
from pitloom.cli.commands.utils import (
    _collect_wheel_paths,
    _locate_and_detect,
    _validate_spdx3_documents,
    cli_error_handler,
)
from pitloom.cli.kv_output import print_kv
from pitloom.core.quote_source import quote_source

log = logging.getLogger(__name__)

#: ``STATUS=`` per :func:`_validate_one_wheel` result.
_VALIDATE_STATUS = {True: "valid", None: "skipped", False: "failed"}


def _validate_location(
    wheel_path: Path,
    location: EmbeddedSbomLocation,
    sbom_format: str | None,
) -> bool | None:
    """Validate the embedded SBOM's content: ``True`` valid, ``False``
    invalid, ``None`` when no validator is registered for *sbom_format* (a
    skip, not a failure).

    *location* and *sbom_format* come from
    :func:`~pitloom.cli.commands.utils._locate_and_detect`, run once against
    the wheel on disk, so ``--verify`` and ``--validate`` share one read.
    """
    if sbom_format not in VALIDATED_FORMATS:
        log.warning(
            "%s: no validator registered for %s's format (%s); "
            "skipping content validation",
            quote_source(wheel_path.name),
            location.arcname,
            sbom_format or "unrecognized",
        )
        return None

    # delete=False + manual cleanup: on Windows, spdx3_validate can't reopen
    # the file by path while our own handle still holds it open (see
    # _rewrite_wheel_archive in _embed_wheel.py for the same pattern).
    with tempfile.NamedTemporaryFile(suffix=".spdx3.json", delete=False) as tmp:
        tmp.write(location.data)
        tmp_path = tmp.name
    try:
        return _validate_spdx3_documents([tmp_path], check_merged=False) == 0
    finally:
        os.unlink(tmp_path)


def _validate_one_wheel(wheel_path: Path, sbom_filename: str | None) -> bool | None:
    """Validate one wheel's embedded SBOM content.

    Returns ``True``/``False`` for validated/invalid, or ``None`` when no
    validator is registered for the detected format -- skipped, not a
    failure, but also not something the caller should report as "valid".
    """
    located = _locate_and_detect(wheel_path, sbom_filename)
    if located is None:
        return False
    location, sbom_format = located
    return _validate_location(wheel_path, location, sbom_format)


@cli_error_handler("wheel SBOM validation failed")
def _run_validate_wheel_command(args: argparse.Namespace) -> int:
    """Run `pitloom validate-wheel`.

    Content check only: validates a wheel's embedded SBOM against its
    format's schema/SHACL rules (currently SPDX3 JSON-LD only, via
    `spdx3-validate`). Does not check location/extension -- see
    `verify-wheel` for that.
    """
    wheel_paths = _collect_wheel_paths(args.wheel_files)
    if not wheel_paths:
        return 1

    statuses = []
    for wheel_path in wheel_paths:
        status = _VALIDATE_STATUS[_validate_one_wheel(wheel_path, args.sbom_filename)]
        print_kv(WHEEL=wheel_path.name, STATUS=status)
        statuses.append(status)

    if "failed" in statuses:
        return 1
    skipped = statuses.count("skipped")
    if skipped:
        log.info(
            "validate-wheel: %d wheel(s) valid, %d skipped "
            "(no validator for their format)",
            len(statuses) - skipped,
            skipped,
        )
    else:
        log.info("validate-wheel: %d wheel(s) valid", len(statuses))
    return 0


def add_parser(subparsers: Any, _parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``validate-wheel`` subcommand to the main parser."""
    validate_parser = subparsers.add_parser(
        "validate-wheel",
        help="Validate a wheel's embedded SBOM against schema and SHACL rules.",
    )
    validate_parser.add_argument(
        "wheel_files",
        type=str,
        nargs="+",
        help="Path(s) or glob pattern(s) of built .whl file(s) to validate.",
    )
    validate_parser.add_argument(
        "--sbom-filename",
        type=str,
        default=None,
        metavar="NAME",
        help="Expect this exact filename under .dist-info/sboms/.",
    )
    validate_parser.set_defaults(func=_run_validate_wheel_command)
