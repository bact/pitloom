# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The catalogue writes a message's line from the caller's values, and its
code rides on the log record and the exception; it is printed as a trailing
`` [code]`` only when it is a code, and the message text itself
(``getMessage()``, ``caplog``) holds none.

See also: tests/messages/test_messages_types.py (the entries),
tests/test_logging_config.py (the formatter without codes).
"""

from __future__ import annotations

import copy
import logging
import pickle  # nosec B403
from email.message import Message as EmailMessage
from typing import Any
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
    LFS_CLONE_LINE,
    LFS_POINTER,
    LFS_POINTER_MALFORMED,
    LFS_POINTER_SHIPPED,
    LFS_PULL_LINE,
    CodedValueError,
    Line,
    Message,
    code_extra_of,
    code_of,
    emit,
    relay_extra,
)

_LOG = logging.getLogger("pitloom.test_messages_emit")
_OID = "0f" * 32
_PULLED = "Git LFS pointer, content not read; run 'git lfs pull' for the content"
_SHIPPED = "Git LFS pointer shipped; the build did not pull LFS content"


@pytest.mark.parametrize(
    ("code", "suffix"),
    [
        ("lfs-pointer", " [lfs-pointer]"),
        ("lfs-pointer/shipped", " [lfs-pointer/shipped]"),
        ("a", " [a]"),
        ("git.too-large", ""),
        ("tool.poetry.dependencies", ""),
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
    """The catalogue writes each value (a file named with a newline is
    escaped once); the record keeps the template and the values apart."""
    configure_logging()
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        emit(
            _LOG, LFS_POINTER, logging.WARNING, line=LFS_PULL_LINE, file="a\nb", count=1
        )
        _LOG.warning("plain")
    assert _lines(capsys) == [
        f"WARNING: FILE='a\\nb': {_PULLED} [lfs-pointer]",
        "WARNING: plain",
    ]
    coded, plain = caplog.records
    assert coded.getMessage() == f"FILE='a\\nb': {_PULLED}"
    assert coded.msg == LFS_PULL_LINE.template and caplog.messages[1] == "plain"
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
        emit(_LOG, LFS_POINTER_SHIPPED, logging.WARNING, file="w.bin", count=3)
    finally:
        _LOG.removeHandler(handler)
    shipped = _SHIPPED.replace("shipped;", "shipped (3 files);")
    assert seen == [(f"FILE=w.bin: {shipped}", "lfs-pointer/shipped")]


def test_a_repeat_said_once_is_debug_without_its_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(debug=True)
    for _ in range(2):
        emit(_LOG, LFS_POINTER_SHIPPED, logging.WARNING, file="m", count=1, once="k")
    assert _lines(capsys) == [
        f"WARNING: FILE=m: {_SHIPPED} [lfs-pointer/shipped]",
        f"DEBUG: FILE=m: {_SHIPPED}",
    ]


@pytest.mark.parametrize(
    ("message", "level", "line", "values", "match"),
    [
        (LFS_POINTER_SHIPPED, logging.ERROR, None, {"file": "x", "count": 1}, "0 name"),
        (LFS_POINTER_SHIPPED, logging.WARNING, None, {"file": "x"}, "0 name"),
        (LFS_POINTER, logging.WARNING, None, {"file": "x", "count": 1}, "2 name"),
        (
            LFS_POINTER,
            logging.WARNING,
            LFS_POINTER_SHIPPED.lines[0],
            {"file": "x", "count": 1},
            "not one",
        ),
        (
            LFS_POINTER_SHIPPED,
            logging.WARNING,
            None,
            {"file": "x", "count": -1},
            "whole",
        ),
        (
            LFS_POINTER_SHIPPED,
            logging.WARNING,
            None,
            {"file": b"x", "count": 1},
            "path",
        ),
    ],
    ids=["level", "names", "which-line", "other-line", "count", "bytes"],
)
def test_a_message_said_with_values_it_has_no_line_for_is_refused(
    message: Message,
    level: int,
    line: Line | None,
    values: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        emit(_LOG, message, level, line=line, **values)


def test_the_line_says_which_action_of_a_message() -> None:
    """The checkout's line and the temporary clone's differ only in what to
    do: the caller names the line."""
    seen: list[str] = []

    class _Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(record.getMessage())

    handler = _Handler()
    _LOG.addHandler(handler)
    try:
        for line in (LFS_PULL_LINE, LFS_CLONE_LINE):
            emit(_LOG, LFS_POINTER, logging.WARNING, line=line, file="f", count=2)
    finally:
        _LOG.removeHandler(handler)
    assert [text.rpartition("; ")[2] for text in seen] == [
        "run 'git lfs pull' for the content",
        "clone with git lfs, then run on the directory",
    ]


@pytest.mark.parametrize(
    ("code", "tail"),
    [(None, "'m'"), ("lfs-pointer", "'m' [lfs-pointer]"), ("x y", "'m'")],
)
def test_print_error_appends_only_a_code(
    capsys: pytest.CaptureFixture[str], code: str | None, tail: str
) -> None:
    print_error("model command failed: 'm'", code=code)
    assert _lines(capsys) == [f"ERROR: model command failed: {tail}"]


@pytest.mark.parametrize(
    ("text", "printed"),
    [
        ("skipped x [lfs-pointer]", "skipped x \\x5blfs-pointer]"),
        ("skipped [a/b]", "skipped \\x5ba/b]"),
        ("a\n [b]", "a\\n \\x5bb]"),
        ("in [tool.poetry.dependencies]", "in [tool.poetry.dependencies]"),
        ("x [Not-a-code]", "x [Not-a-code]"),
        ("x[lfs-pointer]", "x[lfs-pointer]"),
        ("[lfs-pointer] first", "[lfs-pointer] first"),
        ("a [b] c", "a [b] c"),
    ],
    ids=repr,
)
def test_an_uncoded_line_never_ends_in_a_code(
    capsys: pytest.CaptureFixture[str], text: str, printed: str
) -> None:
    """Without a code, a trailing `` [x]`` that reads as one has its ``[``
    escaped, on a record of any level and on ``print_error`` (a code that
    is no code prints none)."""
    configure_logging(debug=True)
    _LOG.warning("%s", text)
    _LOG.debug("%s", text)
    print_error(text)
    print_error(text, code="not a code")
    assert _lines(capsys) == [
        f"WARNING: {printed}",
        f"DEBUG: {printed}",
        f"ERROR: {printed}",
        f"ERROR: {printed}",
    ]


def test_a_coded_line_keeps_a_value_that_ends_like_a_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The value is the record's own text; Pitloom's code comes last."""
    configure_logging()
    emit(_LOG, LFS_POINTER_MALFORMED, logging.WARNING, file="x [lfs-pointer]")
    print_error("x [lfs-pointer]", code="lfs-pointer")
    (warned, error) = _lines(capsys)
    assert warned.startswith("WARNING: FILE=x [lfs-pointer]: header looks like")
    assert warned.endswith("model [lfs-pointer-malformed]")
    assert error == "ERROR: x [lfs-pointer] [lfs-pointer]"


_RELAYED = (
    "FORMAT=gguf FILE=demo/m.gguf: FILE=m.gguf: header looks like a Git LFS "
    "pointer but is not a valid one; not listed as an AI model"
)


@pytest.mark.parametrize(
    ("code", "level", "text", "kept"),
    [
        ("lfs-pointer-malformed", "WARNING", _RELAYED, True),
        (
            "lfs-pointer-malformed",
            "WARNING",
            _RELAYED.replace("FILE=m", "\nFILE=m"),
            True,
        ),
        ("lfs-pointer-malformed", "WARNING", _RELAYED[:-5], False),
        ("lfs-pointer-malformed", "INFO", _RELAYED, False),
        ("lfs-pointer-malformed", "DEBUG", _RELAYED, False),
        ("lfs-pointer", "WARNING", _RELAYED, False),
        ("git.too-large", "WARNING", _RELAYED, False),
        (404, "WARNING", _RELAYED, False),
        (None, "WARNING", _RELAYED, False),
    ],
    ids=[
        "kept",
        "escaped",
        "text",
        "level",
        "debug",
        "other-entry",
        "uncatalogued",
        "not-a-str",
        "none",
    ],
)
def test_a_relayed_record_keeps_its_code_only_while_its_text_fits(
    code: object, level: str, text: str, kept: bool
) -> None:
    """The scan's relay of a reader's record: the code survives a frame
    before the text, not a text its message does not print."""
    extra = relay_extra(code, level, text)
    assert extra == ({CODE_ATTR: code} if kept else None)


def test_a_coded_error_is_a_value_error_with_its_code() -> None:
    exc = CodedValueError(LFS_POINTER, path="m.bin", oid=_OID, size=1)
    text = (
        f"'m.bin': header is a Git LFS pointer, content not pulled (oid sha256:{_OID}, "
        "size 1 byte); run 'git lfs pull'"
    )
    assert isinstance(exc, ValueError) and str(exc) == text
    assert exc.pitloom_code == code_of(exc) == "lfs-pointer"
    assert not hasattr(exc, "code")
    assert code_extra_of(exc) == {CODE_ATTR: "lfs-pointer"}
    for again in (pickle.loads(pickle.dumps(exc)), copy.copy(exc)):  # nosec B301
        assert isinstance(again, CodedValueError)
        assert (str(again), code_of(again)) == (text, "lfs-pointer")


@pytest.mark.parametrize(
    ("message", "values"),
    [
        (LFS_POINTER_SHIPPED, {"file": "x", "count": 1}),
        (LFS_POINTER, {"path": "m"}),
        (LFS_POINTER, {"path": "m", "oid": "zz", "size": 1}),
    ],
    ids=["no-error-line", "names", "shape"],
)
def test_a_coded_error_without_its_line_is_refused(
    message: Message, values: dict[str, Any]
) -> None:
    """The constructor refuses with a plain ValueError, never a coded one."""
    with pytest.raises(ValueError) as caught:
        raise CodedValueError(message, **values)
    assert not isinstance(caught.value, CodedValueError)


class _ClassCoded(OSError):
    pitloom_code = "lfs-pointer"


def _instance_coded() -> RemoteSourceError:
    exc = RemoteSourceError("git.too-large", "too large")
    setattr(exc, CODE_ATTR, "lfs-pointer/shipped")
    return exc


@pytest.mark.parametrize(
    ("exc", "code"),
    [(_ClassCoded("x"), "lfs-pointer"), (_instance_coded(), "lfs-pointer/shipped")],
    ids=["class", "instance"],
)
def test_any_exception_class_carries_a_code(exc: BaseException, code: str) -> None:
    """``pitloom_code`` on the class or the instance; an exception's own
    ``code`` (here ``git.too-large``) stays its own."""
    assert code_of(exc) == code and code_extra_of(exc) == {CODE_ATTR: code}


def test_code_of_ignores_any_other_code_and_the_cause() -> None:
    """An HTTP status, an exit status, a catalogued code in another
    attribute, a code that is no text, an uncatalogued code, a code on the
    cause only: nothing to print."""
    with HTTPError("https://x.example/", 404, "Not Found", EmailMessage(), None) as e:
        assert e.code == 404 and code_of(e) is None
    wrapped = RuntimeError("wrapper")
    wrapped.__cause__ = CodedValueError(LFS_POINTER_MALFORMED, path="inner")

    class _Listed(ValueError):
        pitloom_code: list[str] = ["lfs-pointer"]

    class _Uncatalogued(ValueError):
        pitloom_code = "git.too-large"

    for exc in (
        SystemExit(2),
        _Listed("listed"),
        _Uncatalogued("uncatalogued"),
        RemoteSourceError("lfs-pointer", "a catalogued code as .code"),
        ValueError("plain"),
        wrapped,
    ):
        assert code_of(exc) is None and code_extra_of(exc) is None
