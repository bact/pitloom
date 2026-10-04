# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The CLI's two output shapes: a ``KEY=VALUE`` data line on stdout, and an
``INFO: KEY=VALUE`` line on stderr for ``-v`` details.

Every stdout line a command prints goes through :func:`print_kv`; counts,
summaries and hints are ``log.info(...)`` prose on stderr instead. A line
describing one record holds all its pairs, space-separated; a value is
printed as is (see :func:`kv_line`), so a value that may hold a space goes
last.

See also: ``CLAUDE.md`` "CLI output"; :mod:`tests.kv_helpers` (the test-side
parser).
"""

from __future__ import annotations

import logging

from pitloom.__about__ import __version__
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)


def kv_line(**pairs: object) -> str:
    """``KEY=VALUE`` pairs, space-separated, in the order given. Each value
    goes through :func:`~pitloom.logging_config.loggable`, so a value with a
    line break cannot forge a second line."""
    return " ".join(f"{key}={loggable(str(value))}" for key, value in pairs.items())


def print_kv(**pairs: object) -> None:
    """Print one ``KEY=VALUE`` data line to stdout."""
    print(kv_line(**pairs))


def log_kv(**pairs: object) -> None:
    """Log one ``INFO: KEY=VALUE`` line to stderr."""
    log.info("%s", kv_line(**pairs))


def log_verbose(**pairs: object) -> None:
    """``-v``: ``PITLOOM_VERSION``, then one ``INFO:`` line per pair."""
    log_kv(PITLOOM_VERSION=__version__)
    for key, value in pairs.items():
        log_kv(**{key: value})
