# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from pitloom.assemble import (
    _RECOMMENDED_EXTENSIONS,
    _detect_sbom_format,
    find_embedded_sbom,
)
from pitloom.cli.commands.utils import _collect_wheel_paths, cli_error_handler


def _check_one_wheel(wheel_path: Path, sbom_basename: str | None) -> bool:
    """Verify one wheel's embedded SBOM location/extension. Returns success."""
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
    recommended = _RECOMMENDED_EXTENSIONS.get(sbom_format) if sbom_format else None
    if recommended is None:
        print(
            f"WARNING: {wheel_path.name}: unrecognized SBOM format for "
            f"{location.arcname}; cannot check the recommended extension",
            file=sys.stderr,
        )
    elif not location.arcname.endswith(recommended):
        print(
            f"WARNING: {wheel_path.name}: {location.arcname} doesn't use "
            f"the recommended {recommended!r} extension for its format",
            file=sys.stderr,
        )
    return True


@cli_error_handler("wheel SBOM verification failed")
def _run_verify_wheel_command(args: argparse.Namespace) -> int:
    """Run `pitloom verify-wheel`.

    Format-neutral, structural check only: is an SBOM present at the PEP
    770 location (``.dist-info/sboms/``), and does its extension match
    the recommendation for its detected format. See `validate-wheel` for
    schema/SHACL content validation.
    """
    wheel_paths = _collect_wheel_paths(args.wheel_files)
    if not wheel_paths:
        return 1

    all_ok = True
    for wheel_path in wheel_paths:
        if not _check_one_wheel(wheel_path, args.sbom_basename):
            all_ok = False

    if all_ok:
        print(f"pitloom verify-wheel: {len(wheel_paths)} wheel(s) OK")
    return 0 if all_ok else 1


def add_parser(subparsers: Any, _parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``verify-wheel`` subcommand to the main parser."""
    verify_parser = subparsers.add_parser(
        "verify-wheel",
        help=(
            "Check a wheel's embedded SBOM is at the correct PEP 770 "
            "location and uses its format's recommended extension."
        ),
    )
    verify_parser.add_argument(
        "wheel_files",
        type=str,
        nargs="+",
        help="Path(s) or glob pattern(s) of built .whl file(s) to check.",
    )
    verify_parser.add_argument(
        "--sbom-basename",
        type=str,
        default=None,
        metavar="NAME",
        help="Expect this exact basename under .dist-info/sboms/.",
    )
    verify_parser.set_defaults(func=_run_verify_wheel_command)
