# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A catalogued code rides on the log record and the exception, and is
printed as a trailing `` [code]`` only when it is a code; the message text
itself (``getMessage()``, ``caplog``) is unchanged.

See also: tests/messages/test_messages_types.py (the entries),
tests/test_logging_config.py (the formatter without codes).
"""

from __future__ import annotations

import copy
import logging
import pickle  # nosec B403
from email.message import Message as EmailMessage
from urllib.error import HTTPError

import pytest

from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.logging_config import (
    CODE_ATTR,
    _code_suffix,
    configure_logging,
    print_error,
)
from pitloom.messages import (
    LFS_POINTER,
    LFS_POINTER_SHIPPED,
    CodedValueError,
    code_extra_of,
    code_of,
    emit,
)

_LOG = logging.getLogger("pitloom.test_messages_emit")


@pytest.mark.parametrize(
    ("code", "suffix"),
    [
        ("lfs-pointer", " [lfs-pointer]"),
        ("lfs-pointer.shipped", " [lfs-pointer.shipped]"),
        ("a", " [a]"),
        ("", ""),
        ("lfs pointer", ""),
        ("lfs-pointer\n", ""),
        ("a\nWARNING: forged", ""),
        ("LFS-pointer", ""),
        ("lfs-pointer]", ""),
        ("a] [b", ""),
        ("1st", ""),
        ("-a", ""),
        ("é", ""),
        (404, ""),
        (None, ""),
    ],
    ids=repr,
)
def test_only_a_code_is_printed(code: object, suffix: str) -> None:
    assert _code_suffix(code) == suffix


def _lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return capsys.readouterr().err.splitlines()


def test_an_emitted_record_ends_in_its_code_and_keeps_its_text(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    configure_logging()
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        emit(_LOG, LFS_POINTER, logging.WARNING, "FILE=%s: x", "a\nb")
        _LOG.warning("plain")
    assert _lines(capsys) == [
        "WARNING: FILE=a\\nb: x [lfs-pointer]",
        "WARNING: plain",
    ]
    coded, plain = caplog.records
    assert coded.getMessage() == "FILE=a\nb: x" and caplog.messages[1] == "plain"
    assert getattr(coded, CODE_ATTR) == "lfs-pointer"
    assert not hasattr(plain, CODE_ATTR)


def test_a_library_users_own_handler_reads_the_code() -> None:
    seen: list[tuple[str, object]] = []

    class _Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append((record.getMessage(), getattr(record, "pitloom_code", None)))

    handler = _Handler()
    _LOG.addHandler(handler)
    try:
        emit(_LOG, LFS_POINTER_SHIPPED, logging.WARNING, "FILE=%s: y", "w.bin")
    finally:
        _LOG.removeHandler(handler)
    assert seen == [("FILE=w.bin: y", "lfs-pointer.shipped")]


def test_a_repeat_said_once_is_debug_without_its_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(debug=True)
    for _ in range(2):
        emit(_LOG, LFS_POINTER, logging.WARNING, "FILE=%s: z", "m", once="k")
    assert _lines(capsys) == ["WARNING: FILE=m: z [lfs-pointer]", "DEBUG: FILE=m: z"]


def test_a_level_the_entry_is_not_said_at_is_refused() -> None:
    with pytest.raises(ValueError, match="not said at level"):
        emit(_LOG, LFS_POINTER_SHIPPED, logging.ERROR, "x")


@pytest.mark.parametrize(
    ("code", "tail"),
    [(None, "'m'"), ("lfs-pointer", "'m' [lfs-pointer]"), ("x y", "'m'")],
)
def test_print_error_appends_only_a_code(
    capsys: pytest.CaptureFixture[str], code: str | None, tail: str
) -> None:
    print_error("model command failed: 'm'", code=code)
    assert _lines(capsys) == [f"ERROR: model command failed: {tail}"]


def test_a_coded_error_is_a_value_error_with_its_code() -> None:
    exc = CodedValueError(LFS_POINTER, "'m.bin': header")
    assert isinstance(exc, ValueError) and str(exc) == "'m.bin': header"
    assert code_of(exc) == "lfs-pointer"
    assert code_extra_of(exc) == {CODE_ATTR: "lfs-pointer"}
    for again in (pickle.loads(pickle.dumps(exc)), copy.copy(exc)):  # nosec B301
        assert (str(again), code_of(again)) == (str(exc), "lfs-pointer")


def test_code_of_ignores_any_other_code_and_the_cause() -> None:
    """An HTTP status, an exit status, a code that is no text, an
    uncatalogued code, a code on the cause only: nothing to print."""
    with HTTPError("https://x.example/", 404, "Not Found", EmailMessage(), None) as e:
        assert e.code == 404 and code_of(e) is None
    wrapped = RuntimeError("wrapper")
    wrapped.__cause__ = CodedValueError(LFS_POINTER, "inner")

    class _Listed(ValueError):
        code: list[str] = ["lfs-pointer"]

    unhashable = _Listed("listed")
    for exc in (
        SystemExit(2),
        unhashable,
        RemoteSourceError("git.too-large", "too large"),
        ValueError("plain"),
        wrapped,
    ):
        assert code_of(exc) is None and code_extra_of(exc) is None
