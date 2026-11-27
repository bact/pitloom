# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Utility functions for CLI commands."""

from __future__ import annotations

import ast
import glob
import os
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
from pitloom.core.current_dir import absolute_path
from pitloom.core.file_identity import FileId, file_id
from pitloom.core.internal_error import reraise_internal
from pitloom.core.optional_libraries import (
    VALIDATE,
    import_failed,
    missing,
    not_installed,
)
from pitloom.core.path_probe import is_missing_errno
from pitloom.core.url_masking import masked_given_path
from pitloom.core.wheel_dist_info import (
    WheelRefused,
    is_wheel_path,
    looks_like_wheel_path,
    require_wheel_path,
)
from pitloom.logging_config import print_error, print_traceback
from pitloom.messages import SURFACE_CLI, CodedValueError, advice_surface, code_of
from pitloom.messages.files import SBOM_USE, file_unreadable_error
from pitloom.messages.models import (
    LIBRARY_MISSING,
    LIBRARY_UNUSABLE,
)
from pitloom.messages.targets import (
    INPUT_NOT_FOUND,
    NO_WHEEL_MATCH_LINE,
    WHEEL_PATTERN_TOO_DEEP_LINE,
    input_exists,
    input_not_found,
    is_input_file,
    relay_validator_text,
    say_input_not_found,
    say_validation_findings,
    say_validator_failure,
)
from pitloom.messages.wheel_sboms import wheel_sbom_missing


def cli_error_handler(func: Callable[..., int]) -> Callable[..., int]:
    """Decorator to standardise CLI error handling and tracebacks: an
    exception is one ``ERROR:`` line (its text, else its class name, then
    its code) and exit status 1. The line starts with the frame of the
    command (:func:`pitloom.logging_config.print_error`), set once for the
    run. A line said within names a command-line flag
    (:func:`pitloom.messages.advice_surface`), also for a handler called
    without :func:`pitloom.__main__.main`."""

    @wraps(func)
    def wrapper(args: Any, *pargs: Any, **kwargs: Any) -> int:
        try:
            with advice_surface(SURFACE_CLI):
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
    exists, or *given* is a :class:`~pitloom.core.given_path.TypedPath`
    given as empty (the input probe, :func:`input_exists`).

    Raises:
        pitloom.messages.CodedValueError: *given* cannot be looked at
            (``file-unreadable``).
        OSError: Resolving *given* failed for a cause other than a missing
            path (:func:`~pitloom.core.path_probe.is_missing_errno`).
    """
    if input_exists(given):
        return given
    try:
        # Python 3.10's Windows resolve() lets an invalid name (WinError
        # 123) escape: missing all the same.
        resolved = given.resolve()
    except OSError as exc:
        if is_missing_errno(exc):
            return None
        raise
    return resolved if input_exists(resolved, shown=given) else None


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
        found = (
            _pattern_wheels(pattern)
            if glob.has_magic(pattern)
            else _named_wheel(pattern)
        )
        if found is None:
            had_error = True
            continue
        wheel_paths.extend(found)
    if had_error:
        return []
    # One wheel once, however many spellings (letter case, hard links) reach
    # it; the first spelling is kept.
    unique: dict[FileId | Path, Path] = {}
    for wheel in wheel_paths:
        unique.setdefault(file_id(wheel) or wheel.resolve(), wheel)
    return list(unique.values())


def _pattern_wheels(pattern: str) -> list[Path] | None:
    """The wheels the glob *pattern* matches, or ``None`` having printed
    why there are none (a match not spelt ``.whl``, no match, a pattern
    ``glob`` cannot expand)."""
    hits = _glob_files(pattern)
    if hits is None:
        return None
    # A case-insensitive file system lets ``*.whl`` match ``x.WHL``.
    refused = [p for p in hits if refuse_non_wheel_like(p)]
    matched = [_given(p) for p in hits if is_wheel_path(p)]
    if refused:
        return None
    if not matched:
        print_error(
            NO_WHEEL_MATCH_LINE.render({"path": masked_given_path(pattern)}),
            code=INPUT_NOT_FOUND.code,
        )
        return None
    return matched


def _named_wheel(name: str) -> list[Path] | None:
    """The wheel file *name* (no pattern) as a list of one, or ``None``
    having printed why it is none."""
    if refuse_non_wheel(name):
        return None
    path = _given(name)
    # A regular file only: a directory named .whl is not a wheel.
    if not input_file_or_say(path, "wheel file", shown=name):
        return None
    return [path]


def _glob_files(pattern: str) -> list[str] | None:
    """The regular files *pattern* matches; *pattern* itself when it matches
    none but names a regular file as written (``dist[1]/x.whl``: a shell
    keeps a pattern that matches nothing, so its ``[1]`` reaches us as
    typed). ``None``, having printed the ``input-not-found`` ``ERROR:``,
    when ``glob`` cannot expand it (a pattern nested past its recursion
    limit)."""
    try:
        hits = [p for p in glob.glob(pattern) if os.path.isfile(p)]
    except RecursionError:
        print_error(
            WHEEL_PATTERN_TOO_DEEP_LINE.render({"path": masked_given_path(pattern)}),
            code=INPUT_NOT_FOUND.code,
        )
        return None
    if not hits and os.path.isfile(pattern):
        return [pattern]
    return hits


def _given(path: str) -> Path:
    """*path* made absolute, not normalised: a symlink is not followed and a
    ``..`` is left as it is. POSIX reads it through a symlinked directory;
    Win32 collapses it textually, as ``GetFullPathName`` does."""
    return absolute_path(path)


def report_error_line(exc: Exception) -> None:
    """Print one ``ERROR: <message>`` line to stderr -- the same shape for
    every per-wheel check, so one bad wheel of a batch never aborts the
    others. The text and code are *exc*'s own: a caller handing it an
    exception that may carry none codes it first
    (:func:`report_wheel_failure`)."""
    print_error(str(exc), code=code_of(exc))


def report_wheel_failure(exc: ValueError | OSError, wheel_path: Path) -> None:
    """:func:`report_error_line` for the failure *exc* of one wheel at
    *wheel_path*: an :class:`OSError` the system raised with no code of ours
    is a read (a refused write is coded where it is made) and is said as
    ``file-unreadable`` for the wheel (``input-not-found`` when it says the
    wheel is gone), named by its file name as the wheel's other lines name
    it, so every per-wheel ``ERROR:`` line carries a code.

    An :class:`~pitloom.core.internal_error.InternalError` (a ``ValueError``)
    is a bug in Pitloom, not a bad wheel: it is raised again, so it reaches
    the top handler and aborts the batch instead of being said as that
    wheel's own failure (:func:`~pitloom.core.internal_error.reraise_internal`,
    which each caller's handler also starts with)."""
    reraise_internal(exc)
    if isinstance(exc, OSError) and code_of(exc) is None:
        name = wheel_path.name
        gone = is_missing_errno(exc) or (
            exc.errno is None and isinstance(exc, FileNotFoundError)
        )
        exc = (
            input_not_found("wheel file", name)
            if gone
            else file_unreadable_error(exc, file=name, use=SBOM_USE)
        )
    report_error_line(exc)


def refuse_non_wheel(path: Path | str) -> bool:
    """Print the one ``ERROR: FILE=<path>: not a .whl file`` line and return
    ``True`` where *path* is not a wheel by name
    (:func:`~pitloom.core.wheel_dist_info.require_wheel_path`), the same line
    on every command that takes a wheel; the ``input-not-found`` line where
    *path* is given as empty."""
    try:
        require_wheel_path(path)
    except (WheelRefused, FileNotFoundError) as exc:
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
        reraise_internal(exc)
        report_wheel_failure(exc, wheel_path)
        return None

    if location is None:
        report_error_line(wheel_sbom_missing(wheel_path.name, sbom_filename))
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
        reraise_internal(exc)
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
        except (ValueError, SyntaxError, MemoryError, RecursionError) as exc:
            reraise_internal(exc)
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
    per_document: bool = True,
) -> int:
    """Validate SPDX 3 JSON document(s) against schema and SHACL rules.

    Shared by ``loom fragment validate`` and ``loom validate-wheel``
    -- same underlying `spdx3_validate.validate()` call, same install-hint
    on missing dependency, same relay of the validator's own text
    (:func:`~pitloom.messages.targets.say_validation_findings`: each line
    after ``spdx3-validate: ``, then one ``sbom-invalid`` line per document).
    Returns the CLI exit code (0 valid, 1 otherwise); prints nothing on
    success -- callers print their own success message. *names* maps a path
    to the name shown in its place in the messages (a temporary copy of a
    wheel's member is shown as that member), both raw. With *per_document*
    off the ``sbom-invalid`` lines are left to the caller, which says the
    document's own outcome.
    """
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
        if per_document:
            say_validator_failure(
                exc,
                file=paths[0] if len(paths) == 1 else None,
                names=names,
                paths=paths,
            )
        else:
            relay_validator_text(
                str(exc) or type(exc).__name__, names=names, paths=paths
            )
        return 1

    if not result:
        # The findings come back in hash order (they differ from run to run):
        # sorted, the same document gives the same lines.
        findings = [
            (str(err.source), str(err.kind), _stable_message(err.message))
            for err in sorted(
                result.errors,
                key=lambda e: (str(e.source), str(e.kind), _stable_message(e.message)),
            )
        ]
        say_validation_findings(findings, names=names, per_document=per_document)
        return 1
    return 0
