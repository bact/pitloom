# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.logging_config.configure_logging`."""

from __future__ import annotations

import logging
import os
import threading

import pytest

from pitloom.logging_config import (
    PITLOOM_DEBUG_ENV_VAR,
    apply_debug_override,
    configure_logging,
)

_LOG = logging.getLogger("pitloom.test_logging_config")


def test_configure_logging_prefixes_warning(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    _LOG.warning("something suboptimal happened")

    captured = capsys.readouterr()
    assert captured.err.strip() == "WARNING: something suboptimal happened"
    assert captured.out == ""


def test_configure_logging_prefixes_info(capsys: pytest.CaptureFixture[str]) -> None:
    """Regression: before this fix, INFO records never reached any handler
    (the ``pitloom`` logger's effective level defaulted to ``WARNING``,
    inherited from the root logger), so status messages like the
    Hatchling build hook's "staged SBOM" line were silently invisible --
    a real "no silent deviations" violation despite superficially being
    logged."""
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
    # process, exactly the class of bug this function exists to fix.
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
    """Regression for the exact bug this exists to fix: a CLI-level
    debug=True passed straight to configure_logging() (instead of routed
    through PITLOOM_DEBUG first) was silently discarded by a second,
    argument-less configure_logging() call downstream -- exactly what
    every generate_*_sbom() function does. Simulates that call sequence
    directly rather than only via the CLI-level test in
    tests/cli/test_cli_parser.py, to pin the mechanism, not just the
    end-to-end outcome."""
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
    """Regression: calling configure_logging() more than once in the same
    process (e.g. a build tool invoking the Hatchling hook repeatedly)
    must not stack handlers and duplicate every subsequent message."""
    configure_logging()
    configure_logging()
    _LOG.warning("only once")

    captured = capsys.readouterr()
    assert captured.err.count("only once") == 1


def test_configure_logging_concurrent_calls_never_stack_handlers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Regression: configure_logging() called from multiple threads at
    once (e.g. a library consumer starting several public generator
    functions concurrently) must never leave more than one handler
    attached -- the clear-then-add swap is serialized by a lock."""
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
    """Regression: a log record emitted on one thread while another
    thread is mid-reconfigure must never be silently dropped. The old
    ``handlers.clear()`` then ``addHandler()`` sequence had a window
    where the handler list was briefly empty; a record logged in that
    window vanished with no trace. The fix builds the new handler first
    and swaps ``logger.handlers`` in one assignment, so a concurrent
    record always sees either the fully-old or fully-new list."""
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
