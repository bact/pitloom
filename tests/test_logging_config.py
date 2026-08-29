# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.logging_config.configure_logging`."""

from __future__ import annotations

import logging

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
