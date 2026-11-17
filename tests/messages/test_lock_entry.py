# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``lock-entry-*`` families: a ``requirements.txt`` line by its number,
a value read from a lock escaped, masked and cut, a package said once per
memo by its PEP 503 name, and a conflict's dropped versions sorted.

See also: tests/messages/test_lock_file.py (the file as a whole).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.assemble.spdx3.document import _extract_locked_version_map
from pitloom.core.internal_error import InternalError
from pitloom.logging_config import CODE_ATTR, EXCERPT_CHARS
from pitloom.messages import trusted_message
from pitloom.messages.lock_files import (
    LOCK_ENTRY_CONFLICT,
    LOCK_ENTRY_MALFORMED,
    LOCK_ENTRY_UNUSABLE,
    MARKER_LINE,
    NOT_IN_TABLE_LINE,
    RANGE_LINE,
    REQUIREMENT_LINE,
    SPECIFIER_LINE,
    TOP_LEVEL_LINE,
    VERSION_LINE,
    VERSIONS_FILE_LINE,
    VERSIONS_LINE,
    say_lock_entry,
)

_LOG = logging.getLogger("pitloom.lock_entry_messages")


def _printed(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        f"{r.levelname}: {r.getMessage()} [{getattr(r, CODE_ATTR)}]"
        for r in caplog.records
    ]


def test_a_requirements_line_is_named_by_its_number(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    say_lock_entry(
        _LOG, RANGE_LINE, file="requirements.txt", line_number=3, package="flask"
    )
    (line,) = _printed(caplog)
    assert line == (
        "WARNING: FILE=requirements.txt LINE=3: flask is not one exact version; "
        "no pins read from it [lock-entry-unusable]"
    )
    assert trusted_message(line) is LOCK_ENTRY_UNUSABLE


@pytest.mark.parametrize("number", [0, -1, True, 1.0, "3"])
def test_a_line_number_is_a_whole_number_from_one(number: object) -> None:
    with pytest.raises(ValueError):
        say_lock_entry(
            _LOG, RANGE_LINE, file="requirements.txt", line_number=number, package="a"
        )


def test_a_why_is_masked_on_the_record(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    why = "Expected end or semicolon (after URL https://user:pass@h.example/x)"
    say_lock_entry(
        _LOG, REQUIREMENT_LINE, file="requirements.txt", line_number=1, why=why
    )
    (record,) = caplog.records
    assert "pass@" not in record.getMessage()
    assert all("pass@" not in str(arg) for arg in _args(record))
    assert "h.example" in record.getMessage()


def _args(record: logging.LogRecord) -> list[object]:
    args = record.args
    if isinstance(args, dict):
        return list(args.values())
    return list(args or ())


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        ("==1\n.0", r"'==1 .0'"),
        ("==1\x1b[31m", r"'==1\x1b[31m'"),
        ("==\ud800", r"'==\ud800'"),
    ],
    ids=["newline", "escape", "lone-surrogate"],
)
def test_a_value_from_a_lock_is_one_escaped_line(
    value: str, shown: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    say_lock_entry(
        _LOG, SPECIFIER_LINE, file="Pipfile.lock", package="a", lock_value=value
    )
    (line,) = _printed(caplog)
    assert f"version {shown} is not" in line
    assert line.isprintable()
    assert trusted_message(line) is LOCK_ENTRY_MALFORMED


@pytest.mark.parametrize(
    "package", ["a\nb", "a\x1bb", "a\ud800"], ids=["newline", "escape", "surrogate"]
)
def test_a_package_name_is_escaped(
    package: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    say_lock_entry(_LOG, VERSION_LINE, file="Pipfile.lock", package=package)
    (line,) = _printed(caplog)
    assert line.isprintable()


def test_a_10_kb_value_is_cut_to_120_characters(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    value = "=" * 2 + "1" * 10_240
    say_lock_entry(
        _LOG, SPECIFIER_LINE, file="Pipfile.lock", package="a", lock_value=value
    )
    (line,) = _printed(caplog)
    shown = f"'{value[:EXCERPT_CHARS]}'..."
    assert EXCERPT_CHARS == 120 and f"version {shown} is not" in line
    assert len(line) < 300


def test_a_url_credential_in_a_value_is_masked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    say_lock_entry(
        _LOG,
        SPECIFIER_LINE,
        file="Pipfile.lock",
        package="a",
        lock_value="https://user:pass@h.example/a.whl",
    )
    (record,) = caplog.records
    assert "pass@" not in record.getMessage()
    assert all("pass@" not in str(arg) for arg in _args(record))


def test_a_reference_met_twice_is_said_once(caplog: pytest.LogCaptureFixture) -> None:
    """The uv diamond: two references to one missing package in one walk."""
    caplog.set_level(logging.WARNING)
    said: set[tuple[str, ...]] = set()
    for name in ("Foo_Bar", "foo-bar", "foo.bar"):
        say_lock_entry(_LOG, NOT_IN_TABLE_LINE, file="uv.lock", package=name, said=said)
    assert len(caplog.records) == 1
    say_lock_entry(_LOG, VERSION_LINE, file="uv.lock", package="foo-bar", said=said)
    say_lock_entry(_LOG, NOT_IN_TABLE_LINE, file="uv.lock", package="other", said=said)
    assert len(caplog.records) == 3


def test_dropped_versions_are_sorted(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    for shape in (VERSIONS_LINE, VERSIONS_FILE_LINE):
        say_lock_entry(_LOG, shape, file="uv.lock", package="a", dropped={"2.0", "1.0"})
    lines = _printed(caplog)
    assert lines[0].endswith("; skipped, dropped '1.0', '2.0' [lock-entry-conflict]")
    assert lines[1].endswith(
        "; no pins read from it, dropped '1.0', '2.0' [lock-entry-conflict]"
    )
    assert all(trusted_message(line) is LOCK_ENTRY_CONFLICT for line in lines)


@pytest.mark.parametrize("dropped", [(), [1, 2], None])
def test_dropped_takes_texts(dropped: object) -> None:
    with pytest.raises(ValueError):
        say_lock_entry(
            _LOG, VERSIONS_LINE, file="uv.lock", package="a", dropped=dropped
        )


def test_a_line_of_another_helper_is_an_internal_error() -> None:
    with pytest.raises(InternalError):
        say_lock_entry(_LOG, TOP_LEVEL_LINE, file="uv.lock", value_type=[])


def test_layered_locked_dependencies_name_no_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The document's own guard has no lock file: no ``FILE=`` (once
    ``FILE=locked dependencies``, a space in a key's value)."""
    caplog.set_level(logging.WARNING)
    assert not _extract_locked_version_map(["bar==1.0", "bar==2.0"])
    (line,) = _printed(caplog)
    assert "FILE=" not in line
    assert line == (
        "WARNING: PACKAGE=bar: pinned to several versions in the locked "
        "dependencies; skipped, dropped '1.0', '2.0' [lock-entry-conflict]"
    )
    assert trusted_message(line) is LOCK_ENTRY_CONFLICT


def test_a_long_marker_failure_is_cut_and_masked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """packaging's message repeats the marker: cut, as the marker itself."""
    caplog.set_level(logging.WARNING)
    marker = "python_version > 'https://user:pass@h.example/" + "x" * 3000
    say_lock_entry(
        _LOG,
        MARKER_LINE,
        file="pylock.toml",
        package="a",
        lock_value=marker,
        failure=ValueError(f"Expected a marker variable: {marker}"),
    )
    (line,) = _printed(caplog)
    (record,) = caplog.records
    assert len(line) < 400 and line.count("...") == 2
    assert "pass@" not in line and "pass@" not in str(record.args)
    assert line.endswith("; kept, its marker read as true [lock-entry-malformed]")


def test_the_memo_tells_two_locks_apart(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    memo: set[tuple[str, ...]] = set()
    for file in ("uv.lock", "pylock.toml", "uv.lock"):
        say_lock_entry(_LOG, VERSION_LINE, file=file, package="a", said=memo)
    assert [m.split(":")[0] for m in caplog.messages] == [
        "FILE=uv.lock PACKAGE=a",
        "FILE=pylock.toml PACKAGE=a",
    ]
