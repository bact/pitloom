# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.logging_config.configure_logging`."""

from __future__ import annotations

import io
import logging
import os
import sys
import threading

import pytest

from pitloom import logging_config
from pitloom.logging_config import (
    PITLOOM_DEBUG_ENV_VAR,
    apply_debug_override,
    configure_logging,
    escape_controls,
    excerpt,
    one_line,
    print_error,
)

_LOG = logging.getLogger("pitloom.test_logging_config")


def test_configure_logging_prefixes_warning(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    _LOG.warning("something suboptimal happened")

    captured = capsys.readouterr()
    assert captured.err.strip() == "WARNING: something suboptimal happened"
    assert captured.out == ""


def test_configure_logging_prefixes_info(capsys: pytest.CaptureFixture[str]) -> None:
    """INFO records reach a handler (the ``pitloom`` logger's level does not
    default to the root's ``WARNING``), so status messages such as the
    Hatchling hook's "staged SBOM" line are visible."""
    configure_logging()
    _LOG.info("staged SBOM for wheel injection")

    captured = capsys.readouterr()
    assert captured.err.strip() == "INFO: staged SBOM for wheel injection"


def test_configure_logging_leaves_debug_suppressed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DEBUG stays a developer-only diagnostic, suppressed unless a
    caller opts in via debug=True or PITLOOM_DEBUG."""
    configure_logging()
    _LOG.debug("internal diagnostic detail")

    captured = capsys.readouterr()
    assert captured.err == ""


def test_configure_logging_debug_true_surfaces_debug_records(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(debug=True)
    _LOG.debug("internal diagnostic detail")

    captured = capsys.readouterr()
    assert captured.err.strip() == "DEBUG: internal diagnostic detail"


def test_configure_logging_debug_false_overrides_env_var(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An explicit debug=False (e.g. --debug omitted on the CLI) is not
    the same as debug=None -- only None consults PITLOOM_DEBUG."""
    monkeypatch.setenv("PITLOOM_DEBUG", "1")
    configure_logging(debug=False)
    _LOG.debug("internal diagnostic detail")

    captured = capsys.readouterr()
    assert captured.err == ""


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_configure_logging_env_var_truthy_values_enable_debug(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: str,
) -> None:
    """debug=None (every call site that doesn't parse CLI flags itself --
    the Hatchling hook, every public library-API generator) falls back
    to PITLOOM_DEBUG."""
    monkeypatch.setenv("PITLOOM_DEBUG", value)
    configure_logging()
    _LOG.debug("internal diagnostic detail")

    captured = capsys.readouterr()
    assert captured.err.strip() == "DEBUG: internal diagnostic detail"


@pytest.mark.parametrize("value", ["0", "false", "no", "", "garbage"])
def test_configure_logging_env_var_non_truthy_values_leave_debug_suppressed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: str,
) -> None:
    monkeypatch.setenv("PITLOOM_DEBUG", value)
    configure_logging()
    _LOG.debug("internal diagnostic detail")

    captured = capsys.readouterr()
    assert captured.err == ""


def test_apply_debug_override_true_sets_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # setenv (not delenv) even for a "start absent" baseline: only setenv
    # unconditionally records a teardown-restore entry (delenv/delitem
    # only records one when the name is already present) -- otherwise
    # apply_debug_override(True)'s direct os.environ[...] = "1" write
    # below would leak PITLOOM_DEBUG=1 into every later test in this
    # process.
    monkeypatch.setenv(PITLOOM_DEBUG_ENV_VAR, "0")
    apply_debug_override(True)
    assert os.environ[PITLOOM_DEBUG_ENV_VAR] == "1"


def test_apply_debug_override_false_sets_explicit_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Sets "0" rather than unsetting -- distinguishable from "never
    # configured" for anything downstream (a subprocess, another
    # PITLOOM_DEBUG reader) that treats the two states differently.
    monkeypatch.setenv(PITLOOM_DEBUG_ENV_VAR, "1")
    apply_debug_override(False)
    assert os.environ[PITLOOM_DEBUG_ENV_VAR] == "0"


def test_apply_debug_override_none_leaves_env_var_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PITLOOM_DEBUG_ENV_VAR, "yes")
    apply_debug_override(None)
    assert os.environ[PITLOOM_DEBUG_ENV_VAR] == "yes"

    monkeypatch.delenv(PITLOOM_DEBUG_ENV_VAR, raising=False)
    apply_debug_override(None)
    assert PITLOOM_DEBUG_ENV_VAR not in os.environ


def test_apply_debug_override_survives_a_second_bare_configure_logging(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A debug override routed through PITLOOM_DEBUG survives a second,
    argument-less configure_logging() call (what every generate_*_sbom()
    does); a bare ``debug=True`` would be discarded. Pins the mechanism
    directly, beside the CLI-level test in tests/cli/test_cli_parser.py."""
    # setenv, not delenv -- see test_apply_debug_override_true_sets_env_var.
    monkeypatch.setenv(PITLOOM_DEBUG_ENV_VAR, "0")

    apply_debug_override(True)  # what __main__.main() does for --debug
    configure_logging()  # __main__.main()'s own call

    configure_logging()  # e.g. generate_project_sbom()'s internal call
    _LOG.debug("internal diagnostic detail")

    captured = capsys.readouterr()
    assert captured.err.strip() == "DEBUG: internal diagnostic detail"


def test_configure_logging_reentrant_no_duplicate_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Calling configure_logging() repeatedly in one process (e.g. a build
    tool invoking the Hatchling hook) must not stack handlers or duplicate
    messages."""
    configure_logging()
    configure_logging()
    _LOG.warning("only once")

    captured = capsys.readouterr()
    assert captured.err.count("only once") == 1


def test_configure_logging_concurrent_calls_never_stack_handlers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """configure_logging() called from several threads at once must never
    leave more than one handler attached: the clear-then-add swap is
    serialised by a lock."""
    threads = [threading.Thread(target=configure_logging) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    logger = logging.getLogger("pitloom")
    assert len(logger.handlers) == 1

    _LOG.warning("only once, even after concurrent (re)configuration")
    captured = capsys.readouterr()
    assert captured.err.count("only once, even after concurrent") == 1


def test_configure_logging_concurrent_reconfigure_never_drops_a_record(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A record emitted while another thread reconfigures is never dropped:
    the new handler is built first and ``logger.handlers`` swapped in one
    assignment, so a concurrent record sees the old or the new list, never
    an empty one."""
    stop = threading.Event()

    def _reconfigure_loop() -> None:
        while not stop.is_set():
            configure_logging()

    reconfigurer = threading.Thread(target=_reconfigure_loop)
    reconfigurer.start()

    emitted = 200
    for i in range(emitted):
        _LOG.warning("record %d", i)

    stop.set()
    reconfigurer.join(timeout=5)

    captured = capsys.readouterr()
    seen = captured.err.count("WARNING: record ")
    assert seen == emitted, f"expected {emitted} records, saw {seen} (some dropped)"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("a\n\n  b\r\nc", "a b c", id="multi_line_str"),
        pytest.param(ValueError("x\ny"), "x y", id="multi_line_exception"),
        pytest.param(ValueError(), "ValueError", id="empty_exception"),
        pytest.param("", "", id="empty_str"),
    ],
)
def test_one_line(value: object, expected: str) -> None:
    assert one_line(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("six>=1", "'six>=1'"),
        ("a" * 120, repr("a" * 120)),
        ("a" * 121, repr("a" * 120) + "..."),
        ("a\n  b", "'a b'"),
        ("\x1b[31m", "'\\x1b[31m'"),
        ("\x1b" * 200, ascii("\x1b" * 120) + "..."),
        (5, "5"),
    ],
    ids=["short", "at-cap", "over-cap", "multi-line", "escaped", "escaped-cut", "int"],
)
def test_excerpt(value: object, expected: str) -> None:
    """One literal, escaped once, cut after :data:`EXCERPT_CHARS`."""
    assert excerpt(value) == expected


@pytest.mark.parametrize(
    ("text", "escaped"),
    [
        ("plain caf\u00e9 / path", "plain caf\u00e9 / path"),
        ("a\nWARNING: forged", "a\\nWARNING: forged"),
        ("a\r\nb", "a\\r\\nb"),
        ("x\x1b[31m", "x\\x1b[31m"),
        ("a\u202eb", "a\\u202eb"),
        ("tab\there", "tab\\there"),
    ],
)
def test_escape_controls_keeps_text_and_escapes_controls(
    text: str, escaped: str
) -> None:
    """Only what is not printable, or a display control, is written as an
    escape; no quotes are added and non-ASCII letters stay."""
    assert escape_controls(text) == escaped


@pytest.mark.parametrize("method", ["warning", "info", "error"])
def test_a_record_is_one_tagged_line_whatever_it_holds(
    capsys: pytest.CaptureFixture[str], method: str
) -> None:
    """The handler's formatter backstops every call site: a newline in an
    interpolated path cannot start a second line or forge a tag."""
    configure_logging()
    getattr(_LOG, method)("bad dir %s: failed", "x\nERROR: forged\x1b[0m")
    lines = capsys.readouterr().err.splitlines()
    assert lines == [f"{method.upper()}: bad dir x\\nERROR: forged\\x1b[0m: failed"]


def test_a_traceback_is_still_appended_whole(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging()
    try:
        raise ValueError("boom")
    except ValueError:
        _LOG.exception("failed")
    err = capsys.readouterr().err
    assert err.startswith("ERROR: failed\nTraceback")
    assert "ValueError: boom" in err


def test_print_error_is_one_error_line(capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI's one way to write an error: tagged, on stderr, on one line."""
    print_error("bad 'a\nWARNING: forged'\x1b[0m")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: bad 'a\\nWARNING: forged'\\x1b[0m\n"


# pylint: disable-next=too-few-public-methods
class _Proxy:
    """A stand-in for the capture proxy: a stream that points at another."""

    def __init__(self, behind: object) -> None:
        self._behind = behind

    @property
    def uncaptured_stderr(self) -> object:
        return self._behind


def test_uncaptured_stderr_sees_through_proxies_and_a_missing_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A handler is bound to the stream behind any chain of capture proxies,
    and to a null stream when the proxies have none behind them."""
    real = io.StringIO()
    monkeypatch.setattr(sys, "stderr", _Proxy(_Proxy(real)))
    # pylint: disable-next=protected-access
    assert logging_config._uncaptured_stderr() is real
    monkeypatch.setattr(sys, "stderr", _Proxy(_Proxy(None)))
    # pylint: disable-next=protected-access
    nothing = logging_config._uncaptured_stderr()
    nothing.write("dropped")
    assert isinstance(nothing, io.StringIO)
    assert nothing is not real


def test_warn_once_keys_are_scoped_to_their_logger(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One key on two loggers is said once at each; the repeat is DEBUG."""
    first, second = logging.getLogger("a.once"), logging.getLogger("b.once")
    with caplog.at_level(logging.DEBUG):
        for log in (first, second, first):
            logging_config.warn_once(log, "key", "said")
    levels = [(r.name, r.levelno) for r in caplog.records if r.name.endswith(".once")]
    assert levels == [
        ("a.once", logging.WARNING),
        ("b.once", logging.WARNING),
        ("a.once", logging.DEBUG),
    ]
