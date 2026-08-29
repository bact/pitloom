# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared ``INFO:``/``WARNING:``/``ERROR:`` log-message formatting.

See also: :mod:`pitloom.__main__` (the ``loom`` CLI entry point),
:mod:`pitloom.plugins.hatch` (the Hatchling build-hook entry point), and
every public generator/enrich function in :mod:`pitloom.assemble` (the
library API) -- all call :func:`configure_logging` so ``log.info(...)``/
``log.warning(...)`` output looks the same regardless of which entry
point invoked Pitloom.
"""

from __future__ import annotations

import logging
import sys
import threading

# Guards the handlers.clear()/addHandler() swap below -- see
# configure_logging()'s docstring.
_CONFIG_LOCK = threading.Lock()


def configure_logging() -> None:
    """Prefix internal ``log.info(...)``/``log.warning(...)`` output with
    ``INFO: ``/``WARNING: ``.

    Without this, Python's last-resort handler either drops ``INFO``
    records entirely (the root logger's default effective level is
    ``WARNING``) or, for ``WARNING``, prints them to stderr with no
    prefix at all -- both break the shared grep-able ``LEVEL:
    <description>`` convention (see ``ERROR:``, used by the CLI's own
    ``print()`` calls) documented in ``CLAUDE.md``'s "CLI output"
    section. ``DEBUG`` stays suppressed by default -- it's a developer
    diagnostic, never meant to reach a normal invocation's stderr.
    Reconfigures on every call rather than guarding with a "configured
    once" flag, so repeated calls in the same process (e.g. across
    tests, or a build tool invoking the Hatchling hook more than once)
    don't stack duplicate handlers. The new handler is built first and
    ``logger.handlers`` is replaced with a whole new list in one
    assignment (never cleared-then-appended in place), so a concurrent
    ``log.warning(...)``/``log.info(...)`` call on another thread always
    sees either the fully-old or fully-new handler list -- never an
    empty one mid-swap -- without needing to lock log emission itself.
    A module-level lock still serializes the reconfiguration itself, so
    two threads each calling this at once can't race on ``setLevel()``
    or leave the logger in a state neither call intended. Propagation to
    the root logger is left untouched, so ``pytest``'s ``caplog``
    fixture still captures these records; a host application that
    already configures its own root logging may then see pitloom's
    ``INFO:``/``WARNING:`` lines twice (once via this handler, once via
    its own root handler) -- disabling propagation would fix that but
    silently break every test in this suite that captures pitloom's log
    output via bare ``caplog.at_level(...)`` (implicitly root-scoped),
    so it stays as a documented tradeoff rather than a silent one.
    """
    logger = logging.getLogger("pitloom")
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    with _CONFIG_LOCK:
        logger.setLevel(logging.INFO)
        logger.handlers = [handler]
