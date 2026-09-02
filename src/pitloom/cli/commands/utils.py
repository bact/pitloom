# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Utility functions for CLI commands."""

from __future__ import annotations

import argparse
import dataclasses
import glob
import sys
import traceback
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from pitloom.assemble import (
    EmbeddedSbomLocation,
    detect_sbom_format,
    find_embedded_sbom,
)
from pitloom.core.config import PitloomConfig
from pitloom.core.provenance import (
    ProvenanceConfig,
    normalize_max_source_metadata_bytes,
)


def cli_error_handler(
    error_msg: str,
) -> Callable[[Callable[..., int]], Callable[..., int]]:
    """Decorator to standardize CLI error handling and tracebacks."""

    def decorator(func: Callable[..., int]) -> Callable[..., int]:
        @wraps(func)
        def wrapper(args: Any, *pargs: Any, **kwargs: Any) -> int:
            try:
                return func(args, *pargs, **kwargs)
            # pylint: disable=broad-exception-caught
            except Exception as e:
                print(f"ERROR: {error_msg}: {e}", file=sys.stderr)
                if getattr(args, "verbose", False):
                    traceback.print_exc()
                return 1

        return wrapper

    return decorator


def resolve_effective_provenance(
    pitloom_config: PitloomConfig, args: argparse.Namespace
) -> ProvenanceConfig:
    """Apply --max-source-metadata-bytes onto the config-sourced ProvenanceConfig.

    Every [tool.pitloom.provenance] key besides this one is config-only (no
    CLI flag); this one gets a flag since a byte cap is an operational knob
    someone may want to override per-run without editing pyproject.toml.
    """
    provenance = pitloom_config.provenance
    override = getattr(args, "max_source_metadata_bytes", None)
    if override is not None:
        provenance = dataclasses.replace(
            provenance,
            max_source_metadata_bytes=normalize_max_source_metadata_bytes(override),
        )
    return provenance


def _print_sbom_output_path(output_path: Path | str) -> None:
    """Report the resolved SBOM output path in KEY=VALUE form (see CLAUDE.md).

    Lets callers (e.g. the GitHub Action) discover the filename a command's
    own default-naming logic picked, without re-deriving it themselves.
    Namespaced "PITLOOM_" so it reads unambiguously as this stdout line,
    distinct from the GitHub Action's own "sbom-path" output.
    """
    print(f"PITLOOM_SBOM_OUTPUT_PATH={output_path}")


def _collect_wheel_paths(patterns: list[str]) -> list[Path]:
    """Resolve and expand wheel file paths and glob patterns.

    Every pattern is validated before returning, and every error is
    reported here -- the caller can treat an empty return as "already
    explained on stderr", with no need to re-inspect the patterns itself.
    """
    wheel_paths: list[Path] = []
    had_error = False
    for pattern in patterns:
        if glob.has_magic(pattern):
            matched = [
                Path(p).resolve()
                for p in glob.glob(pattern)
                if Path(p).is_file() and p.endswith(".whl")
            ]
            if not matched:
                print(f"ERROR: no wheel files matched: {pattern}", file=sys.stderr)
                had_error = True
                continue
            wheel_paths.extend(matched)
        else:
            p = Path(pattern).resolve()
            if not p.exists():
                print(f"ERROR: wheel file not found: {p}", file=sys.stderr)
                had_error = True
                continue
            if not p.name.endswith(".whl"):
                print(f"ERROR: not a .whl file: {p}", file=sys.stderr)
                had_error = True
                continue
            wheel_paths.append(p)
    if had_error:
        return []
    return list(dict.fromkeys(wheel_paths))


def _locate_embedded_sbom_or_report(
    wheel_path: Path, sbom_filename: str | None
) -> EmbeddedSbomLocation | None:
    """Locate *wheel_path*'s embedded SBOM, reporting ``ERROR:`` on failure.

    Shared by ``verify-wheel`` and ``validate-wheel``'s per-wheel checks --
    same lookup, same malformed-wheel/ambiguous-match/missing-SBOM error
    reporting, so the two commands can't drift in wording. `find_embedded_sbom`
    raises ``ValueError`` for a bad wheel's *content* (malformed ZIP,
    missing/ambiguous ``.dist-info``) and ``OSError`` for an environment
    problem reading it (missing file, permission denied) -- the CLI
    doesn't need to distinguish those the way a library caller might, so
    both are caught here and reported the same way, letting one bad wheel
    in a multi-wheel run get reported per-wheel instead of aborting the
    whole batch via the outer `cli_error_handler`.
    """
    try:
        location = find_embedded_sbom(wheel_path, sbom_filename)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return None

    if location is None:
        print(
            f"ERROR: no SBOM found under .dist-info/sboms/ in {wheel_path.name}"
            + (f" matching {sbom_filename!r}" if sbom_filename else ""),
            file=sys.stderr,
        )
    return location


def _locate_and_detect(
    wheel_path: Path, sbom_filename: str | None
) -> tuple[EmbeddedSbomLocation, str | None] | None:
    """`_locate_embedded_sbom_or_report()` plus `detect_sbom_format()` on
    the result, since every caller of the former immediately needs the
    latter too. Returns ``None`` (having already reported the ``ERROR:``)
    when no SBOM is found, same as `_locate_embedded_sbom_or_report()`.
    """
    location = _locate_embedded_sbom_or_report(wheel_path, sbom_filename)
    if location is None:
        return None
    return location, detect_sbom_format(location.data)


def _import_spdx3_validate() -> Any | None:
    """Import ``spdx3_validate``, printing an install-hint ``ERROR:`` if missing.

    Split out of :func:`_validate_spdx3_documents` so ``fragment validate``
    can check for the dependency before its own path-existence check (the
    dependency is more fundamental than any one path being wrong) while
    :func:`_validate_spdx3_documents` still does the same check internally
    for callers, like ``validate-wheel``, that don't need to sequence it.
    """
    try:
        # pylint: disable=import-outside-toplevel
        import spdx3_validate
    except ImportError:
        print(
            "ERROR: the 'spdx3-validate' package is required for SPDX 3 "
            'validation. Install it with: pip install "pitloom[validate]"',
            file=sys.stderr,
        )
        return None
    return spdx3_validate


def _validate_spdx3_documents(paths: list[str], *, check_merged: bool) -> int:
    """Validate SPDX 3 JSON document(s) against schema and SHACL rules.

    Shared by ``pitloom fragment validate`` and ``pitloom validate-wheel``
    -- same underlying `spdx3_validate.validate()` call, same install-hint
    on missing dependency, same per-violation ``ERROR:`` line handling.
    Returns the CLI exit code (0 valid, 1 otherwise); prints nothing on
    success -- callers print their own success message.
    """
    spdx3_validate = _import_spdx3_validate()
    if spdx3_validate is None:
        return 1

    try:
        result = spdx3_validate.validate(paths, check_merged=check_merged)
    except spdx3_validate.SpdxValidateError as exc:
        # A document can't even be loaded/parsed (bad JSON, unrecognized
        # @context, incompatible versions across paths) -- distinct from a
        # ValidationResult carrying schema/SHACL findings below, but still
        # a validation failure the caller should report cleanly, not an
        # unhandled exception.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not result:
        for err in result.errors:
            # err.message can itself be multi-line (e.g. a SHACL violation's
            # Severity/Source Shape/Focus Node breakdown) -- tag every line
            # with ERROR: so no continuation line is left ungrep-able.
            header = f"{err.source}: [{err.kind}] {err.message}"
            for line in header.splitlines():
                print(f"ERROR: {line}", file=sys.stderr)
        return 1
    return 0
