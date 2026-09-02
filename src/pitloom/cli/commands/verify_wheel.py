# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from pitloom._sbom_format import check_spdx3_name_version
from pitloom._wheel_sbom_location import (
    _find_dist_info_prefix,
    _open_wheel_zip,
    read_wheel_name_version,
)
from pitloom.assemble import RECOMMENDED_EXTENSIONS, EmbeddedSbomLocation
from pitloom.cli.commands.utils import (
    _collect_wheel_paths,
    _locate_and_detect,
    cli_error_handler,
)

log = logging.getLogger(__name__)


def _check_location(
    wheel_path: Path,
    location: EmbeddedSbomLocation,
    sbom_format: str | None,
) -> bool:
    """Verify an *already disk-read* embedded SBOM's extension. Always
    succeeds (location/format problems are WARNING:, not a failure) --
    returns ``bool`` only for symmetry with :func:`_check_one_wheel`.

    *location* must come from a real `_locate_embedded_sbom_or_report`
    call against the wheel on disk -- never construct one from in-memory,
    pre-write data to skip that read (see `embed_wheel.py`'s
    `_run_post_embed_checks`: this split exists so `--verify --validate`
    together share ONE disk read, not to avoid the read).

    *sbom_format* is `detect_sbom_format(location.data)`'s result,
    computed by the caller -- required, not optional-with-a-lazy-fallback,
    because `None` is itself a valid detection result (unrecognized
    format): a `sbom_format is None` fallback couldn't tell "caller didn't
    detect it yet" from "caller detected it as unrecognized" and would
    silently re-detect on every unrecognized-format wheel.
    """
    recommended = RECOMMENDED_EXTENSIONS.get(sbom_format) if sbom_format else None
    if recommended is None:
        log.warning(
            "%s: unrecognized SBOM format for %s; cannot check the "
            "recommended extension",
            wheel_path.name,
            location.arcname,
        )
    elif not location.arcname.endswith(recommended):
        log.warning(
            "%s: %s doesn't use the recommended %r extension for its format",
            wheel_path.name,
            location.arcname,
            recommended,
        )
    return True


def _check_name_version(
    wheel_path: Path,
    wheel_name: str | None,
    wheel_version: str | None,
    location: EmbeddedSbomLocation,
    sbom_format: str | None,
    *,
    fail_on_mismatch: bool,
) -> bool:
    """Cross-check the embedded SBOM's declared subject name/version
    against the wheel's own ``.dist-info/METADATA`` name/version (see
    :func:`pitloom._sbom_format.check_spdx3_name_version`).

    Non-fatal (`WARNING:`, returns ``True``) unless *fail_on_mismatch* --
    matches `_check_location`'s severity convention. Extraction failures
    (unsupported SBOM format, or SPDX3 with an unexpected graph shape) are
    always non-fatal `WARNING:`s regardless of *fail_on_mismatch* --
    "couldn't check" is a different finding than "checked and it's
    wrong," and shouldn't be escalated by a flag meant for the latter.
    """
    mismatches, warnings = check_spdx3_name_version(
        wheel_name, wheel_version, location.data, sbom_format
    )
    for warning in warnings:
        log.warning("%s: %s", wheel_path.name, warning)

    if not mismatches:
        return True

    message = f"{wheel_path.name}: SBOM/wheel " + "; ".join(mismatches)
    if fail_on_mismatch:
        log.error(message)
        return False
    log.warning(message)
    return True


def _check_one_wheel(
    wheel_path: Path, sbom_filename: str | None, *, fail_on_mismatch: bool
) -> bool:
    """Verify one wheel's embedded SBOM location/extension and cross-check
    its declared name/version against the wheel's own METADATA. Returns
    success."""
    located = _locate_and_detect(wheel_path, sbom_filename)
    if located is None:
        return False
    location, sbom_format = located
    location_ok = _check_location(wheel_path, location, sbom_format)

    with _open_wheel_zip(wheel_path) as zf:
        dist_info = _find_dist_info_prefix(zf, wheel_path)
        wheel_name, wheel_version = read_wheel_name_version(zf, dist_info)

    version_ok = _check_name_version(
        wheel_path,
        wheel_name,
        wheel_version,
        location,
        sbom_format,
        fail_on_mismatch=fail_on_mismatch,
    )
    return location_ok and version_ok


@cli_error_handler("wheel SBOM verification failed")
def _run_verify_wheel_command(args: argparse.Namespace) -> int:
    """Run `pitloom verify-wheel`.

    Structural check: is an SBOM present at the PEP 770 location
    (``.dist-info/sboms/``), does its extension match the recommendation
    for its detected format, and does its declared subject name/version
    match the wheel's own ``.dist-info/METADATA`` (PEP 503/440-normalized).
    A name/version mismatch is a `WARNING:` by default; pass
    `--fail-on-mismatch` to make it an `ERROR:` (exit 1) instead. See
    `validate-wheel` for schema/SHACL content validation.
    """
    wheel_paths = _collect_wheel_paths(args.wheel_files)
    if not wheel_paths:
        return 1

    all_ok = True
    for wheel_path in wheel_paths:
        if not _check_one_wheel(
            wheel_path, args.sbom_filename, fail_on_mismatch=args.fail_on_mismatch
        ):
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
            "location, uses its format's recommended extension, and its "
            "declared name/version match the wheel's own METADATA."
        ),
    )
    verify_parser.add_argument(
        "wheel_files",
        type=str,
        nargs="+",
        help="Path(s) or glob pattern(s) of built .whl file(s) to check.",
    )
    verify_parser.add_argument(
        "--sbom-filename",
        type=str,
        default=None,
        metavar="NAME",
        help="Expect this exact filename under .dist-info/sboms/.",
    )
    verify_parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help=(
            "Exit non-zero if the SBOM's declared name/version doesn't "
            "match the wheel's .dist-info/METADATA (default: WARNING only)."
        ),
    )
    verify_parser.set_defaults(func=_run_verify_wheel_command)
