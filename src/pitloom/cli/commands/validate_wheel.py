# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from pitloom.assemble import _detect_sbom_format, find_embedded_sbom
from pitloom.cli.commands.utils import (
    _collect_wheel_paths,
    _validate_spdx3_documents,
    cli_error_handler,
)


def _validate_one_wheel(wheel_path: Path, sbom_basename: str | None) -> bool:
    """Validate one wheel's embedded SBOM content. Returns success."""
    try:
        location = find_embedded_sbom(wheel_path, sbom_basename)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return False

    if location is None:
        print(
            f"ERROR: no SBOM found under .dist-info/sboms/ in {wheel_path.name}"
            + (f" matching {sbom_basename!r}" if sbom_basename else ""),
            file=sys.stderr,
        )
        return False

    sbom_format = _detect_sbom_format(location.data)
    if sbom_format != "spdx3-jsonld":
        print(
            f"WARNING: {wheel_path.name}: no validator registered for "
            f"{location.arcname}'s format ({sbom_format or 'unrecognized'}); "
            "skipping content validation",
            file=sys.stderr,
        )
        return True

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
    for wheel_path in wheel_paths:
        if not _validate_one_wheel(wheel_path, args.sbom_basename):
            all_valid = False

    if all_valid:
        print(f"pitloom validate-wheel: {len(wheel_paths)} wheel(s) valid")
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
        "--sbom-basename",
        type=str,
        default=None,
        metavar="NAME",
        help="Expect this exact basename under .dist-info/sboms/.",
    )
    validate_parser.set_defaults(func=_run_validate_wheel_command)
