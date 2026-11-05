# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`tests._logger_state`, the per-test ``pitloom`` logger
reset.

See also: tests/_logger_state.py, tests/test_environ_restore.py.
"""

import logging

import pytest

from pitloom.logging_config import configure_logging
from tests._logger_state import (
    UNCONFIGURED,
    logger_state,
    pitloom_logger_unconfigured,
)


@pytest.fixture(name="configured_for_the_module", scope="module")
def _configured_for_the_module() -> None:
    """What a module-scoped fixture that builds a wheel or runs a generator
    does to the logger, before any function-scoped fixture runs."""
    configure_logging()


@pytest.mark.usefixtures("configured_for_the_module")
def test_a_module_fixture_s_logging_setup_does_not_reach_the_test(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The test starts unconfigured: an ``INFO`` record logged outside a
    ``caplog.at_level`` block is not captured, a ``DEBUG`` one inside is."""
    assert logger_state() == UNCONFIGURED
    child = logging.getLogger("pitloom.test_logger_state")

    child.info("outside")
    with caplog.at_level(logging.DEBUG):
        child.debug("inside")

    assert caplog.messages == ["inside"]


@pytest.mark.parametrize("debug", [False, True], ids=["info", "debug"])
def test_pitloom_logger_unconfigured_undoes_a_configuration(debug: bool) -> None:
    """Whatever the logger was on entry or became inside, it ends
    unconfigured."""
    configure_logging(debug=debug)
    assert logger_state() != UNCONFIGURED

    with pitloom_logger_unconfigured():
        assert logger_state() == UNCONFIGURED
        configure_logging(debug=debug)

    assert logger_state() == UNCONFIGURED
    assert not logging.getLogger("pitloom.x").isEnabledFor(logging.INFO)


def test_unconfigured_is_a_fresh_logger_s_state() -> None:
    """:data:`UNCONFIGURED` is what :mod:`logging` gives a new logger."""
    fresh = logging.Logger("fresh")
    assert UNCONFIGURED.level == fresh.level
    assert UNCONFIGURED.handlers == tuple(fresh.handlers)
    assert (UNCONFIGURED.propagate, UNCONFIGURED.disabled) == (
        fresh.propagate,
        fresh.disabled,
    )


def test_restore_pitloom_logger_fixture_wraps_every_test(
    request: pytest.FixtureRequest,
) -> None:
    """``tests/conftest.py`` applies the reset to every test, autouse."""
    assert "_restore_pitloom_logger" in request.fixturenames
