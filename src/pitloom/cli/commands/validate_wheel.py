# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from pitloom.assemble import _VALIDATED_FORMATS, _detect_sbom_format
from pitloom.cli.commands.utils import (
    _collect_wheel_paths,
    _locate_embedded_sbom_or_report,
    _validate_spdx3_documents,
    cli_error_handler,
)

log = logging.getLogger(__name__)


def _validate_one_wheel(wheel_path: Path, sbom_filename: str | None) -> bool | None:
    """Validate one wheel's embedded SBOM content.

    Returns ``True``/``False`` for validated/invalid, or ``None`` when no
    validator is registered for the detected format -- skipped, not a
    failure, but also not something the caller should report as "valid".
    """
    location = _locate_embedded_sbom_or_report(wheel_path, sbom_filename)
    if location is None:
        return False

    sbom_format = _detect_sbom_format(location.data)
    if sbom_format not in _VALIDATED_FORMATS:
        log.warning(
            "%s: no validator registered for %s's format (%s); "
            "skipping content validation",
            wheel_path.name,
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

    all_valid = True
    skipped = 0
    for wheel_path in wheel_paths:
        result = _validate_one_wheel(wheel_path, args.sbom_filename)
        if result is None:
            skipped += 1
        elif not result:
            all_valid = False

    if all_valid:
        validated = len(wheel_paths) - skipped
        if skipped:
            print(
                f"pitloom validate-wheel: {validated} wheel(s) valid, "
                f"{skipped} skipped (no validator for their format)"
            )
        else:
            print(f"pitloom validate-wheel: {validated} wheel(s) valid")
    return 0 if all_valid else 1


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
