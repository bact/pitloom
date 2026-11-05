# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hold the ``pitloom`` logger at its unconfigured state around a test.

:func:`pitloom.logging_config.configure_logging` sets the logger's level to
``INFO`` (or ``DEBUG``) and binds a handler to the ``sys.stderr`` of the
moment. Every CLI command, the build hook and each library entry point call
it, and so does a module- or session-scoped fixture that builds a wheel or
runs a generator. Such a fixture runs before any function-scoped fixture of
its first test, so a restore that snapshots the logger when a test starts
takes the configured state for the clean one and keeps it for every later
test on the same xdist worker: an ``INFO`` record logged outside a
``caplog.at_level`` block is captured, a ``DEBUG`` one is dropped, and a
handler bound to a closed capture stream prints ``--- Logging error ---``.

:func:`pitloom_logger_unconfigured` therefore sets a fixed state,
:data:`UNCONFIGURED`, both before and after the test, whatever ran before.
``tests/conftest.py`` wraps every test in it.

See also: tests/test_logger_state.py, tests/_environ.py.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

LOGGER_NAME = "pitloom"


@dataclass(frozen=True)
class LoggerState:
    """The parts of a :class:`logging.Logger` a configuration changes."""

    level: int
    handlers: tuple[logging.Handler, ...]
    propagate: bool
    disabled: bool


#: A logger nothing has configured: what ``logging.getLogger`` makes.
UNCONFIGURED = LoggerState(
    level=logging.NOTSET, handlers=(), propagate=True, disabled=False
)


def logger_state(name: str = LOGGER_NAME) -> LoggerState:
    """The current :class:`LoggerState` of the logger *name*."""
    logger = logging.getLogger(name)
    return LoggerState(
        level=logger.level,
        handlers=tuple(logger.handlers),
        propagate=logger.propagate,
        disabled=logger.disabled,
    )


def set_logger_state(state: LoggerState, name: str = LOGGER_NAME) -> None:
    """Give the logger *name* the level, handlers and flags of *state*.

    ``setLevel`` (not a bare ``level`` write) clears every logger's cached
    ``isEnabledFor`` answers, so a child logger such as
    ``pitloom.id_registry`` sees the new level at once.
    """
    logger = logging.getLogger(name)
    logger.handlers = list(state.handlers)
    logger.propagate = state.propagate
    logger.disabled = state.disabled
    logger.setLevel(state.level)


@contextmanager
def pitloom_logger_unconfigured() -> Iterator[None]:
    """Run the block with the ``pitloom`` logger at :data:`UNCONFIGURED`,
    and leave it so, whatever state it was in on entry."""
    set_logger_state(UNCONFIGURED)
    try:
        yield
    finally:
        set_logger_state(UNCONFIGURED)
