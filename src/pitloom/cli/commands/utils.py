# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Utility functions for CLI commands."""

from __future__ import annotations

import ast
import glob
from collections.abc import Callable, Mapping
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
from pitloom.core.optional_libraries import (
    VALIDATE,
    import_failed,
    missing,
    not_installed,
)
from pitloom.core.quote_source import quote_source
from pitloom.core.url_masking import masked_given_path
from pitloom.core.wheel_dist_info import (
    WheelRefused,
    is_wheel_path,
    looks_like_wheel_path,
    require_wheel_path,
)
from pitloom.logging_config import print_error, print_traceback
from pitloom.messages import CodedValueError, code_of
from pitloom.messages.models import (
    LIBRARY_MISSING,
    LIBRARY_UNUSABLE,
)
from pitloom.messages.targets import (
    INPUT_NOT_FOUND,
    NO_WHEEL_MATCH_LINE,
    is_input_file,
    say_input_not_found,
)


def cli_error_handler(func: Callable[..., int]) -> Callable[..., int]:
    """Decorator to standardise CLI error handling and tracebacks: an
    exception is one ``ERROR:`` line (its text, else its class name, then
    its code) and exit status 1. The line starts with the frame of the
    command (:func:`pitloom.logging_config.print_error`), set once for the
    run."""

    @wraps(func)
    def wrapper(args: Any, *pargs: Any, **kwargs: Any) -> int:
        try:
            return func(args, *pargs, **kwargs)
        # pylint: disable-next=broad-exception-caught
        except Exception as e:
            print_error(str(e) or type(e).__name__, code=code_of(e))
            if getattr(args, "verbose", False):
                print_traceback()
            return 1

    return wrapper


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
    """Report the resolved SBOM output path in KEY=VALUE form (see AGENTS.md).

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
                print_error(
                    NO_WHEEL_MATCH_LINE.render({"path": masked_given_path(pattern)}),
                    code=INPUT_NOT_FOUND.code,
                )
                had_error = True
                continue
            wheel_paths.extend(matched)
        else:
            if refuse_non_wheel(pattern):
                had_error = True
                continue
            p = _given(pattern)
            # A regular file only: a directory named .whl is not a wheel.
            if not input_file_or_say(p, "wheel file", shown=pattern):
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
    print_error(str(exc), code=code_of(exc))


def refuse_non_wheel(path: Path | str) -> bool:
    """Print the one ``ERROR: FILE=<path>: not a .whl file`` line and return
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


def input_file_or_say(
    path: Path, kind: str, *, shown: Path | str | None = None
) -> bool:
    """Whether a regular file is at *path* (the input probe), else print its
    one ``ERROR:`` line naming *shown* (default: *path*) as *kind*:
    ``input-not-found``, or ``file-unreadable`` where the system will not
    let Pitloom look. Never raises that error, so a loop over several paths
    reports every one."""
    named = path if shown is None else shown
    try:
        if is_input_file(path, shown=named):
            return True
        say_input_not_found(kind, named)
    except CodedValueError as exc:
        report_error_line(exc)
    return False


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
        print_error(
            f"no SBOM found under .dist-info/sboms/ in {quote_source(wheel_path.name)}"
            + (f" matching {quote_source(sbom_filename)}" if sbom_filename else "")
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
    """Import ``spdx3_validate``, printing the ``library-missing`` ``ERROR:``
    (the extra to install) if missing, ``library-unusable`` if
    it fails to import.

    Called directly by ``fragment validate`` before its own path-existence
    check, since a missing dependency is more fundamental than any one
    path being wrong; :func:`_validate_spdx3_documents` also calls this
    internally for callers, like ``validate-wheel``, that don't need to
    sequence it that way.
    """
    try:
        # pylint: disable=import-outside-toplevel
        import spdx3_validate
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:  # a broken install raises more than ImportError
        if not_installed(VALIDATE, exc):
            print_error(str(missing(VALIDATE)), code=LIBRARY_MISSING.code)
        else:
            error = import_failed(VALIDATE, exc)
            print_error(str(error), code=LIBRARY_UNUSABLE.code)
        return None
    return spdx3_validate


_NOT_IN_LIST = "not in list "
#: A list rendered by ``str()`` is searched for up to this many closing brackets.
_MAX_LIST_ENDS = 50


def _stable_message(message: str) -> str:
    """*message* with the values of a ``not in list [...]`` finding sorted:
    the validator builds that list from a set, so its order differs from run
    to run. A list that is not a list of strings is left as written."""
    start = message.find(_NOT_IN_LIST)
    if start < 0:
        return message
    begin = start + len(_NOT_IN_LIST)
    if message[begin : begin + 1] != "[":
        return message
    end = begin
    for _ in range(_MAX_LIST_ENDS):
        end = message.find("]", end + 1)
        if end < 0:
            return message
        try:
            values = ast.literal_eval(message[begin : end + 1])
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            continue
        if isinstance(values, list) and all(isinstance(v, str) for v in values):
            return message[:begin] + repr(sorted(values)) + message[end + 1 :]
        return message
    return message


def _validate_spdx3_documents(
    paths: list[str],
    *,
    check_merged: bool,
    names: Mapping[str, str] | None = None,
) -> int:
    """Validate SPDX 3 JSON document(s) against schema and SHACL rules.

    Shared by ``loom fragment validate`` and ``loom validate-wheel``
    -- same underlying `spdx3_validate.validate()` call, same install-hint
    on missing dependency, same per-violation ``ERROR:`` line handling.
    Returns the CLI exit code (0 valid, 1 otherwise); prints nothing on
    success -- callers print their own success message. *names* maps a path to
    the name shown in its place in the messages (a temporary copy of a wheel's
    member is shown as that member).
    """
    shown = names or {}

    def show(text: str) -> str:
        for path, name in shown.items():
            text = text.replace(path, name)
        return text

    spdx3_validate = _import_spdx3_validate()
    if spdx3_validate is None:
        return 1

    try:
        result = spdx3_validate.validate(paths, check_merged=check_merged)
    except spdx3_validate.SpdxValidateError as exc:
        # A document can't even be loaded/parsed (bad JSON, unrecognised
        # @context, incompatible versions across paths) -- distinct from a
        # ValidationResult carrying schema/SHACL findings below, but still
        # a validation failure the caller should report cleanly, not an
        # unhandled exception.
        print_error(show(str(exc)))
        return 1

    if not result:
        # The findings come back in hash order (they differ from run to run):
        # sorted, the same document gives the same lines.
        for err in sorted(
            result.errors,
            key=lambda e: (str(e.source), str(e.kind), _stable_message(e.message)),
        ):
            # err.message can itself be multi-line (e.g. a SHACL violation's
            # Severity/Source Shape/Focus Node breakdown) -- tag every line
            # with ERROR: so no continuation line is left ungrep-able.
            header = show(f"{err.source}: [{err.kind}] {_stable_message(err.message)}")
            for line in header.splitlines():
                print_error(line)
        return 1
    return 0
