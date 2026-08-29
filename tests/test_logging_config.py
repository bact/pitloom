# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.logging_config.configure_logging`."""

from __future__ import annotations

import logging
import threading

import pytest

from pitloom.logging_config import configure_logging

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
    """DEBUG stays a developer-only diagnostic, never surfaced by default."""
    configure_logging()
    _LOG.debug("internal diagnostic detail")

    captured = capsys.readouterr()
    assert captured.err == ""


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
