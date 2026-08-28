# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared ``WARNING:``/``ERROR:`` log-message formatting.

See also: :mod:`pitloom.__main__` (the ``loom`` CLI entry point) and
:mod:`pitloom.plugins.hatch` (the Hatchling build-hook entry point) --
both call :func:`configure_logging` so ``log.warning(...)`` output looks
the same regardless of which process invoked Pitloom.
"""

from __future__ import annotations

import logging
import sys


def configure_logging() -> None:
    """Prefix internal ``log.warning(...)`` output with ``WARNING: ``.

    Without this, Python's last-resort handler prints library warnings
    (``pitloom.ids``, ``pitloom.loom``, etc.) to stderr with no prefix at
    all, breaking the shared grep-able ``LEVEL: <description>`` convention
    (see ``ERROR:``, used by the CLI's own ``print()`` calls). Reconfigures
    on every call rather than guarding with a "configured once" flag, so
    repeated calls in the same process (e.g. across tests, or a build tool
    invoking the Hatchling hook more than once) don't stack duplicate
    handlers. Propagation to the root logger is left untouched, so
    ``pytest``'s ``caplog`` fixture still captures these records.
    """
    logger = logging.getLogger("pitloom")
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)
