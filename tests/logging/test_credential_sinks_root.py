# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``pitloom`` record reaches every handler masked, not only the one of
``configure_logging``: the record propagates to the root logger, where an
embedder's handler (``logging.basicConfig``, Sentry, a JSON handler) once
formatted the raw message and arguments.

See also: tests/logging/test_credential_sinks_cut.py,
tests/test_logging_config.py.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator

import pytest

from pitloom.logging_config import CODE_ATTR, configure_logging

SECRET = "PLANTSECRET"
URL = f"https://u:{SECRET}@h.example/o/r"
_LOG = logging.getLogger("pitloom.test_root_sink")


@pytest.fixture(name="root_stream")
def _root_stream() -> Iterator[io.StringIO]:
    """A plain handler on the root logger, as an embedder adds one; the
    ``pitloom`` logger configured (``tests/conftest.py`` resets it)."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    configure_logging()
    try:
        yield stream
    finally:
        root.removeHandler(handler)


def test_a_root_handler_sees_the_masked_message(
    root_stream: io.StringIO, capsys: pytest.CaptureFixture[str]
) -> None:
    """A secret in an argument, and in an exception's traceback, reaches
    neither the root's handler nor stderr."""
    _LOG.warning("cannot fetch %s (%d tries)", URL, 3)
    try:
        raise ValueError(f"refused {URL}")
    except ValueError:
        _LOG.exception("failed on %s", "the source")
    shown = root_stream.getvalue()
    assert "cannot fetch https://***:***@h.example/o/r (3 tries)" in shown
    assert "ValueError: refused https://***:***@h.example" in shown
    assert SECRET not in shown
    assert SECRET not in capsys.readouterr().err


def test_an_unformattable_record_shows_no_argument(
    root_stream: io.StringIO, capsys: pytest.CaptureFixture[str]
) -> None:
    """A call site's format error (``%d`` given a text) is written as the
    template and the failure's class, the argument left out."""
    _LOG.warning("bad %d", URL)
    shown = root_stream.getvalue()
    assert "bad %d (arguments not formatted: TypeError)" in shown
    assert SECRET not in shown + capsys.readouterr().err


def test_a_record_with_nothing_to_mask_is_kept(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``msg``, ``args`` and the code of a record holding no secret stay as
    logged; a masked record's message is final (``args`` empty)."""
    configure_logging()
    with caplog.at_level(logging.INFO, logger="pitloom"):
        _LOG.warning("plain %s", "value", extra={CODE_ATTR: "x-y"})
        _LOG.warning("secret %s", URL, extra={CODE_ATTR: "x-y"})
    plain, masked = caplog.records
    assert (plain.msg, plain.args) == ("plain %s", ("value",))
    assert masked.msg == "secret https://***:***@h.example/o/r"
    assert masked.args == ()
    assert getattr(masked, CODE_ATTR) == "x-y"


def test_a_failed_write_reports_no_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The handler's report of a failed write names the failure only:
    ``logging.Handler.handleError`` prints the message and arguments as
    given."""
    configure_logging()
    (handler,) = logging.getLogger("pitloom").handlers
    record = _LOG.makeRecord(_LOG.name, logging.WARNING, "f", 1, "x %s", (URL,), None)
    monkeypatch.setattr(logging, "raiseExceptions", True)
    try:
        raise OSError("closed stream")
    except OSError:
        handler.handleError(record)
    err = capsys.readouterr().err
    assert "Logging error: OSError" in err
    assert SECRET not in err and "x %s" not in err


def test_a_failed_write_is_quiet_when_logging_says_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``logging.raiseExceptions`` off (production): nothing is printed."""
    configure_logging()
    (handler,) = logging.getLogger("pitloom").handlers
    record = _LOG.makeRecord(_LOG.name, logging.WARNING, "f", 1, "x", (), None)
    monkeypatch.setattr(logging, "raiseExceptions", False)
    try:
        raise OSError("closed stream")
    except OSError:
        handler.handleError(record)
    assert not capsys.readouterr().err


def test_a_secret_in_the_stack_info_is_masked(
    root_stream: io.StringIO, capsys: pytest.CaptureFixture[str]
) -> None:
    """``stack_info`` holding a URL with a password (a source line shown in
    a stack) is masked, and a record already masked is passed on as it is."""
    (handler,) = logging.getLogger("pitloom").handlers
    record = _LOG.makeRecord(_LOG.name, logging.WARNING, "f", 1, "x", (), None)
    record.stack_info = f"Stack (most recent call last):\n  fetch({URL!r})"
    assert handler.filter(record)
    assert SECRET not in record.stack_info
    assert "https://***:***@h.example" in record.stack_info
    record.stack_info = f"changed {URL}"
    assert handler.filter(record)
    assert record.stack_info == f"changed {URL}"
    assert SECRET not in root_stream.getvalue() + capsys.readouterr().err


def test_a_failed_report_of_a_failed_write_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stderr that cannot be written to does not raise from the handler."""

    class _Broken(io.StringIO):
        def write(self, s: str, /) -> int:
            raise OSError("closed stream")

    configure_logging()
    (handler,) = logging.getLogger("pitloom").handlers
    record = _LOG.makeRecord(_LOG.name, logging.WARNING, "f", 1, "x", (), None)
    monkeypatch.setattr(logging, "raiseExceptions", True)
    monkeypatch.setattr("sys.stderr", _Broken())
    try:
        raise OSError("closed stream")
    except OSError:
        handler.handleError(record)
