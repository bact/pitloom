# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Utility functions for CLI commands."""

from __future__ import annotations

import glob
import sys
import traceback
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from pitloom._sbom_io import is_stdout
from pitloom.assemble import (
    EmbeddedSbomLocation,
    detect_sbom_format,
    find_embedded_sbom,
)
from pitloom.cli.kv_output import print_kv
from pitloom.core.file_identity import FileId, file_id
from pitloom.core.wheel_dist_info import (
    WheelRefused,
    is_wheel_path,
    looks_like_wheel_path,
    require_wheel_path,
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
            # pylint: disable-next=broad-exception-caught
            except Exception as e:
                print(f"ERROR: {error_msg}: {e}", file=sys.stderr)
                if getattr(args, "verbose", False):
                    traceback.print_exc()
                return 1

        return wrapper

    return decorator


def existing_model_path(given: Path) -> Path | None:
    """The path to open for the model file named as *given*: *given* itself,
    so log lines name the file as the user wrote it, else its resolved form
    (``missing/../x`` collapses to ``x`` only there); ``None`` when neither
    exists."""
    if given.exists():
        return given
    resolved = given.resolve()
    return resolved if resolved.exists() else None


def _print_sbom_output_path(output_path: Path | str) -> None:
    """Report the resolved SBOM output path in KEY=VALUE form (see CLAUDE.md).

    Nothing is printed for ``-``: stdout is then the SBOM itself, and a line
    after it would break ``loom ... -o - | jq .``.

    Lets callers (e.g. the GitHub Action) discover the filename a command's
    own default-naming logic picked, without re-deriving it themselves.
    Namespaced "PITLOOM_" so it reads unambiguously as this stdout line,
    distinct from the GitHub Action's own "sbom-path" output.
    """
    if is_stdout(output_path):
        return
    print_kv(PITLOOM_SBOM_OUTPUT_PATH=output_path)


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
            hits = [p for p in glob.glob(pattern) if Path(p).is_file()]
            # A case-insensitive file system lets ``*.whl`` match ``x.WHL``.
            refused = [p for p in hits if refuse_non_wheel_like(p)]
            matched = [_given(p) for p in hits if is_wheel_path(p)]
            if refused:
                had_error = True
                continue
            if not matched:
                print(f"ERROR: no wheel files matched: {pattern}", file=sys.stderr)
                had_error = True
                continue
            wheel_paths.extend(matched)
        else:
            if refuse_non_wheel(Path(pattern)):
                had_error = True
                continue
            p = _given(pattern)
            if not p.exists():
                print(f"ERROR: wheel file not found: {p}", file=sys.stderr)
                had_error = True
                continue
            wheel_paths.append(p)
    if had_error:
        return []
    # One wheel once, however many spellings (letter case, hard links) reach
    # it; the first spelling is kept.
    unique: dict[FileId | Path, Path] = {}
    for wheel in wheel_paths:
        unique.setdefault(file_id(wheel) or wheel.resolve(), wheel)
    return list(unique.values())


def _given(path: str) -> Path:
    """*path* made absolute, not normalised: a symlink is not followed and a
    ``..`` is left as it is. POSIX reads it through a symlinked directory;
    Win32 collapses it textually, as ``GetFullPathName`` does."""
    return Path(path).absolute()


def report_error_line(exc: Exception) -> None:
    """Print one ``ERROR: <message>`` line to stderr -- the same shape for
    every per-wheel check, so one bad wheel of a batch never aborts the
    others."""
    print(f"ERROR: {exc}", file=sys.stderr)


def refuse_non_wheel(path: Path) -> bool:
    """Print the one ``ERROR: not a .whl file: <path>`` line and return
    ``True`` where *path* is not a wheel by name
    (:func:`~pitloom.core.wheel_dist_info.require_wheel_path`), the same line
    on every command that takes a wheel."""
    try:
        require_wheel_path(path)
    except WheelRefused as exc:
        report_error_line(exc)
        return True
    return False


def refuse_non_wheel_like(path: str) -> bool:
    """:func:`refuse_non_wheel` for *path* where it looks like a wheel in any
    letter case but is not spelt ``.whl``; ``False`` for any other file."""
    return looks_like_wheel_path(path) and refuse_non_wheel(Path(path))


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
        report_error_line(exc)
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

    Called directly by ``fragment validate`` before its own path-existence
    check, since a missing dependency is more fundamental than any one
    path being wrong; :func:`_validate_spdx3_documents` also calls this
    internally for callers, like ``validate-wheel``, that don't need to
    sequence it that way.
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
