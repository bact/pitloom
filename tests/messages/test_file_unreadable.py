# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``file-unreadable`` family and ``dir-unlistable``: the entry chosen
by the exception, never for an absent path; what stopped the read written
from the exception, never its text (which quotes the path); the closed
table of uses; and no other module saying the family's wording.

See also: tests/test_unreadable_file_surfaces.py (every surface),
tests/messages/test_drift_sources.py (the drift guards).
"""

from __future__ import annotations

import ast
import errno
import logging
import sys

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.core.path_confine import NotRegularFileError, OutsideRootError
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    DIR_UNLISTABLE,
    FILE_UNREADABLE,
    FILE_UNREADABLE_NOT_UTF8,
    FILE_UNREADABLE_OUTSIDE,
    READ_USES,
    Message,
    trusted_message,
    warn_dir_unlistable,
    warn_file_unreadable,
)
from tests._message_drift import record_problem, source_modules, string_constants

#: A logger the record check of ``tests/conftest.py`` watches.
_LOG = logging.getLogger("pitloom.file_unreadable_check")
#: The path an OS error names: never printed.
_ABS = "/abs/proj/a.txt"
_DECODE = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
_DECODED = "'utf-8' codec can't decode byte 0xff in position 0: invalid start byte"

#: Modules whose own strings still hold the family's wording for a cause of
#: their own, not catalogued yet: path under ``src/pitloom``, with why.
#: Shrink only.
_OTHER_CAUSES = {
    "core/wheel_dist_info.py": "a wheel member that does not read (PR 15-16)",
    "extract/project/_requirements_files.py": "a listed file not found (PR 3)",
    "id_registry/_types.py": "a file name a registry cannot hold (PR 5-7)",
}


def _said(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    (record,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert record_problem(record) is None
    return record


def _check(record: logging.LogRecord, entry: Message, text: str) -> None:
    """*record* says *entry* as *text*, trusted read back, no path of the
    error in it."""
    assert getattr(record, CODE_ATTR) == entry.code
    assert record.getMessage() == text
    assert trusted_message(f"WARNING: {text} [{entry.code}]") is entry
    assert _ABS not in text


@pytest.mark.parametrize(
    ("exc", "entry", "tail"),
    [
        (
            PermissionError(13, "Permission denied", _ABS),
            FILE_UNREADABLE,
            "Permission denied",
        ),
        (
            OSError(errno.EIO, "Input/output error", _ABS),
            FILE_UNREADABLE,
            "Input/output error",
        ),
        (NotRegularFileError(), FILE_UNREADABLE, "not a regular file"),
        (ValueError(), FILE_UNREADABLE, "ValueError"),
        (_DECODE, FILE_UNREADABLE_NOT_UTF8, f"not UTF-8: {_DECODED}"),
        (OutsideRootError(), FILE_UNREADABLE_OUTSIDE, "outside the project directory"),
    ],
    ids=["denied", "io", "not-regular", "no-text", "not-utf8", "outside"],
)
@pytest.mark.parametrize(
    ("purpose", "said"),
    [
        ({"use": "for file scanning"}, "could not read for file scanning"),
        ({"field": "project.readme"}, "could not read for project.readme"),
    ],
    ids=["use", "field"],
)
def test_the_entry_and_the_failure_are_the_exceptions(
    caplog: pytest.LogCaptureFixture,
    exc: BaseException,
    entry: Message,
    tail: str,
    purpose: dict[str, str],
    said: str,
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_file_unreadable(_LOG, exc, file="a.txt", **purpose)
    _check(_said(caplog), entry, f"FILE=a.txt: {said}; {tail}")


def test_a_header_read_names_the_format_first(
    caplog: pytest.LogCaptureFixture,
) -> None:
    denied = PermissionError(13, "Permission denied", _ABS)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_file_unreadable(_LOG, denied, file="m.gguf", model_format="gguf")
    text = "FORMAT=gguf FILE=m.gguf: could not read header; Permission denied"
    _check(_said(caplog), FILE_UNREADABLE, text)


def test_a_directory_says_dir_unlistable(caplog: pytest.LogCaptureFixture) -> None:
    denied = PermissionError(13, "Permission denied", _ABS)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_dir_unlistable(_LOG, denied, directory="pkg/sub", use="for file discovery")
    text = "DIR=pkg/sub: could not list for file discovery; Permission denied"
    _check(_said(caplog), DIR_UNLISTABLE, text)


def _windows_missing() -> OSError:
    """An error Windows reports for a name that is no path
    (``ERROR_INVALID_NAME``, 123): absent, by its ``winerror``."""
    text = "The filename syntax is incorrect"
    if sys.platform == "win32":
        return OSError(errno.EINVAL, text, None, 123)
    exc = OSError(errno.EINVAL, text)
    vars(exc).update(winerror=123)  # what a Windows OSError carries
    return exc


@pytest.mark.parametrize(
    "exc",
    [
        FileNotFoundError(errno.ENOENT, "No such file or directory", _ABS),
        NotADirectoryError(errno.ENOTDIR, "Not a directory", _ABS),
        OSError(errno.ELOOP, "Too many levels of symbolic links", _ABS),
        _windows_missing(),
    ],
    ids=["enoent", "enotdir", "eloop", "winerror-123"],
)
def test_an_absent_path_never_carries_the_code(
    caplog: pytest.LogCaptureFixture, exc: OSError
) -> None:
    """Absent is quiet: the helpers refuse it, so a caller that forgot to
    ask :func:`~pitloom.core.path_probe.is_missing_errno` fails loudly."""
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        with pytest.raises(InternalError, match="absent"):
            warn_file_unreadable(_LOG, exc, file="a.txt", use="for file scanning")
        with pytest.raises(InternalError, match="absent"):
            warn_dir_unlistable(_LOG, exc, directory="d", use="for file discovery")
    assert not caplog.records


@pytest.mark.parametrize(
    "purpose",
    [{}, {"use": "for file scanning", "field": "project.readme"}],
    ids=["none", "two"],
)
def test_exactly_one_purpose_is_named(purpose: dict[str, str]) -> None:
    denied = PermissionError(13, "Permission denied")
    with pytest.raises(InternalError, match="one of"):
        warn_file_unreadable(_LOG, denied, file="a.txt", **purpose)


@pytest.mark.parametrize("use", ["for fun", "for file scanning ", "file scanning"])
def test_a_use_outside_the_table_is_refused(use: str) -> None:
    with pytest.raises(ValueError, match="is not a use"):
        warn_file_unreadable(_LOG, PermissionError(13, "x"), file="a.txt", use=use)


def test_a_file_named_twice_under_one_key_is_said_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The repeat is ``DEBUG``, never printed, and keeps the code."""
    denied = PermissionError(13, "Permission denied")
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        for _ in range(2):
            warn_file_unreadable(
                _LOG, denied, file="uv.lock", use="for dependency pins", once="k:u"
            )
    levels = [r.levelno for r in caplog.records]
    assert levels == [logging.WARNING, logging.DEBUG]
    assert {getattr(r, CODE_ATTR) for r in caplog.records} == {"file-unreadable"}


def test_a_newline_in_a_name_cannot_forge_a_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    denied = PermissionError(13, "Permission\ndenied")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_file_unreadable(
            _LOG, denied, file="a\nWARNING: x", use="for file scanning"
        )
        warn_dir_unlistable(
            _LOG, denied, directory="d\nWARNING: y", use="for file discovery"
        )
    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        "FILE='a\\nWARNING: x': could not read for file scanning; Permission denied",
        "DIR='d\\nWARNING: y': could not list for file discovery; Permission denied",
    ]


def _texts(tree: ast.Module) -> dict[str, str]:
    """*tree*'s module-level text constants, by name."""
    return {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def test_every_use_of_the_table_is_passed_and_no_other() -> None:
    """The table is closed and live: every ``use=`` a call of a helper
    passes is a text of it (a literal, or a module constant), and each of
    its uses is passed by some call."""
    helpers = {"warn_file_unreadable", "warn_dir_unlistable"}
    passed: set[str] = set()
    for path, tree in source_modules():
        texts = _texts(tree)
        for node in ast.walk(tree):
            name = getattr(node, "func", None)
            if getattr(name, "id", getattr(name, "attr", None)) not in helpers:
                continue
            for keyword in getattr(node, "keywords", []):
                if keyword.arg != "use":
                    continue
                value = keyword.value
                if isinstance(value, ast.Name):
                    passed.add(texts[value.id])
                else:
                    assert isinstance(value, ast.Constant), path
                    assert isinstance(value.value, str), path
                    passed.add(value.value)
    assert passed == set(READ_USES)


def test_no_module_says_the_family_wording_on_its_own() -> None:
    """Outside the catalogue, only a line for another cause, listed in
    :data:`_OTHER_CAUSES`, holds the family's wording."""
    found = {
        path
        for path, tree in source_modules()
        if any(
            "could not read " in text or "could not list " in text
            for text in string_constants(tree)
        )
    }
    assert found == set(_OTHER_CAUSES)
