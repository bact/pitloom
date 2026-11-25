# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``pitloom.*`` record is masked as it is made, for every handler: one on
a child logger, at ``DEBUG``, on the root. A filter on the handler of
``configure_logging`` once masked a record only when that handler took it,
after a child logger's handlers, and never below its level.

See also: tests/logging/test_credential_sinks_root.py,
src/pitloom/log_masking.py.
"""

from __future__ import annotations

import io
import logging
import sys
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest

from pitloom.log_masking import (
    UNSHOWN_MESSAGE,
    UNSHOWN_TRACEBACK,
    MaskingRecordFactory,
    mask_record,
)
from pitloom.logging_config import configure_logging, print_traceback

pytestmark = pytest.mark.platform

SECRET = "S3CRET"
URL = f"https://u:{SECRET}@h.example/x"
_CHILD = "pitloom.test_factory.child"
_PARENT = logging.getLogger("pitloom.test_factory")


# pylint: disable-next=too-few-public-methods
class _Sinks:
    """Plain handlers at ``DEBUG``: on the root and on a ``pitloom.*`` child
    logger."""

    def __init__(self) -> None:
        self.root, self.child = io.StringIO(), io.StringIO()

    def text(self) -> str:
        """All the handlers wrote."""
        return self.root.getvalue() + self.child.getvalue()


@pytest.fixture(name="sinks")
def _sinks() -> Iterator[_Sinks]:
    """A child logger at ``DEBUG`` with its own handler, a root handler at
    ``DEBUG``, the ``pitloom`` logger configured (``tests/conftest.py``
    resets it and the record factory)."""
    sinks = _Sinks()
    child = logging.getLogger(_CHILD)
    handlers = []
    for logger, stream in ((logging.getLogger(), sinks.root), (child, sinks.child)):
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        handlers.append((logger, handler))
    child.setLevel(logging.DEBUG)
    configure_logging()
    try:
        yield sinks
    finally:
        child.setLevel(logging.NOTSET)
        for logger, handler in handlers:
            logger.removeHandler(handler)


# pylint: disable-next=too-few-public-methods
class _Changing:
    """Clean on its first formatting, the URL on every later one."""

    def __init__(self) -> None:
        self.calls = 0

    def __str__(self) -> str:
        self.calls += 1
        return "clean" if self.calls == 1 else URL


def _log_exception(log: logging.Logger) -> None:
    try:
        raise ValueError(f"refused {URL}")
    except ValueError:
        log.exception("failed")


def _log_stack(log: logging.Logger) -> None:
    log.warning("x", stack_info=True)  # the stack shows https://u:S3CRET@h


_CASES: dict[str, Callable[[logging.Logger], None]] = {
    "debug": lambda log: log.debug("DEBUG l %s", URL),
    # On a logger with no handler of its own, Pitloom's formats it first.
    "changing-str": lambda _: _PARENT.warning("x %s", _Changing()),
    "url-in-msg": lambda log: log.warning(URL),
    "exception": _log_exception,
    "stack-info": _log_stack,
}


@pytest.mark.parametrize("case", sorted(_CASES), ids=str)
def test_no_handler_sees_the_secret(
    sinks: _Sinks, case: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Whatever the level, the handler or the argument, no handler and no
    stderr line shows the password."""
    _CASES[case](logging.getLogger(_CHILD))
    shown = sinks.text()
    assert shown.strip(), "nothing was logged"
    assert SECRET not in shown + capsys.readouterr().err


@pytest.mark.usefixtures("sinks")
@pytest.mark.parametrize("by_name", [False, True], ids=["tuple", "dict"])
def test_a_changing_argument_is_frozen(by_name: bool) -> None:
    """A record's text is built once: an argument whose text changes leaves
    ``msg`` final and ``args`` empty, so a later formatting is the same."""
    msg, args = (
        ("x %(v)s", ({"v": _Changing()},)) if by_name else ("x %s", (_Changing(),))
    )
    record = logging.getLogger(_CHILD).makeRecord(
        _CHILD, logging.INFO, "f", 1, msg, args, None
    )
    assert (record.msg, record.args) == ("x clean", ())
    assert record.getMessage() == "x clean"


@pytest.mark.usefixtures("sinks")
def test_a_named_argument_is_copied() -> None:
    """A record of plain named arguments keeps its template and a copy of
    them: a change to the caller's ``dict`` changes no later formatting."""
    args = {"v": "clean"}
    record = logging.getLogger(_CHILD).makeRecord(
        _CHILD, logging.INFO, "f", 1, "x %(v)s", (args,), None
    )
    args["v"] = URL
    assert record.msg == "x %(v)s" and record.getMessage() == "x clean"


@pytest.mark.parametrize(
    ("msg", "args", "shown"),
    [
        ("BOOM", (), UNSHOWN_MESSAGE),
        ("x %s", ("BOOM",), "x %s (arguments not formatted: RuntimeError)"),
    ],
    ids=["msg", "arg"],
)
def test_a_raising_str_is_not_raised(
    sinks: _Sinks, msg: str, args: tuple[str, ...], shown: str
) -> None:
    """A ``msg`` or argument whose ``__str__`` raises never escapes the
    logging call; the message says it could not be shown."""

    # pylint: disable-next=too-few-public-methods
    class _Raising:
        def __str__(self) -> str:
            raise RuntimeError(URL)

    def real(value: str) -> object:
        return _Raising() if value == "BOOM" else value

    logging.getLogger(_CHILD).warning(real(msg), *map(real, args))
    assert shown in sinks.root.getvalue() and SECRET not in sinks.text()


# pylint: disable-next=inconsistent-return-statements
def _raised(exc: ValueError) -> object:
    """The ``sys.exc_info()`` of *exc*, raised."""
    try:
        raise exc
    except ValueError:
        return sys.exc_info()


@pytest.mark.uncoded_output(r"^ERROR: failed$")
def test_a_raw_exc_text_is_replaced(sinks: _Sinks) -> None:
    """A record whose ``exc_text`` holds the raw traceback (made outside the
    factory, ``logging.makeLogRecord``) reaches the root masked: the
    traceback is formatted afresh from ``exc_info``."""
    exc_info = _raised(ValueError(f"refused {URL}"))
    record = logging.makeLogRecord(
        {
            "name": "pitloom",
            "levelno": logging.ERROR,
            "levelname": "ERROR",
            "msg": "failed",
            "exc_info": exc_info,
            "exc_text": f"ValueError: refused {URL}",
        }
    )
    logging.getLogger("pitloom").handle(record)
    assert "refused https://***:***@h.example" in sinks.root.getvalue()
    assert SECRET not in sinks.root.getvalue()


def test_another_library_is_not_masked(sinks: _Sinks) -> None:
    """Documented scope: a record of a logger outside ``pitloom`` (a
    third-party library) is passed on as it was logged."""
    logging.getLogger("thirdparty.test_factory").warning("x %s", URL)
    assert URL in sinks.root.getvalue()


def test_configuring_twice_adds_one_factory() -> None:
    """``configure_logging`` wraps the factory installed before it, once,
    however often it is called; that factory still makes the record."""
    made: list[str] = []
    previous = logging.getLogRecordFactory()

    def own(*args: object, **kwargs: object) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        made.append(record.name)
        return record

    logging.setLogRecordFactory(own)
    configure_logging()
    configure_logging()
    factory = logging.getLogRecordFactory()
    assert isinstance(factory, MaskingRecordFactory) and factory.previous is own
    record = logging.getLogger(_CHILD).makeRecord(
        _CHILD, logging.INFO, "f", 1, "x %s", (URL,), None
    )
    assert made == [_CHILD] and SECRET not in record.getMessage()


def test_a_password_with_a_line_break_is_masked_whole(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``print_traceback`` masks the traceback before splitting it: a line
    break in a password once left ``https://u:S3`` and ``CRET@h`` on two
    lines, neither masked."""
    try:
        raise ValueError("refused https://u:S3\nCRET@h.example/x")
    except ValueError:
        print_traceback()
    err = capsys.readouterr().err
    assert "refused https://***:***@h.example" in err
    assert "u:S3" not in err and "CRET@" not in err


def _record(msg: str, args: Any = ()) -> logging.LogRecord:
    return logging.LogRecord("pitloom.x", logging.INFO, "f", 1, msg, args, None)


def test_a_dict_of_arguments_with_a_non_string_key_is_frozen() -> None:
    """The template of such a record is not kept: its text is final."""
    record = _record("%(a)s", ({"a": "plain"},))
    record.args = cast("Any", {1: "x", "a": "plain"})
    mask_record(record)
    assert not record.args and record.msg == "plain"


def test_a_cached_exception_text_is_masked() -> None:
    record = _record("m")
    record.exc_text = f"Trace: {URL}"
    mask_record(record)
    assert SECRET not in (record.exc_text or "")


# pylint: disable-next=too-few-public-methods
class _Unprintable:
    def __str__(self) -> str:
        raise ValueError(SECRET)


def test_an_exception_or_stack_that_cannot_be_shown_is_a_fixed_text() -> None:
    """A masking failure of the traceback or the stack gives a fixed text,
    never the raw one."""
    record = _record("m")
    record.exc_info = (ValueError, _Unprintable(), None)  # type: ignore[assignment]
    record.stack_info = URL
    mask_record(record)
    assert record.exc_text == UNSHOWN_TRACEBACK
    assert SECRET not in str(cast("Any", record).stack_info)


def test_a_stack_that_the_masker_rejects_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fail(text: str) -> str:
        calls.append(text)
        raise ValueError("boom")

    record = _record("m")
    record.stack_info = URL
    monkeypatch.setattr("pitloom.log_masking.masked_text", fail)
    mask_record(record)
    assert cast("Any", record).stack_info is None and calls
