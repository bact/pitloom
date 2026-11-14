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

See also: ``AGENTS.md`` "CLI output"; :mod:`tests.kv_helpers` (the test-side
parser).
"""

from __future__ import annotations

import logging
from pathlib import PurePath

from pitloom.__about__ import __version__
from pitloom.core.given_path import GivenPath
from pitloom.core.quote_source import given_path_text
from pitloom.core.url_masking import masked_given_path
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


def _shown(value: object) -> str:
    """*value* as a ``-v`` detail writes it: a path (or a
    :class:`~pitloom.core.given_path.GivenPath`) as the user gave it
    (:func:`~pitloom.core.quote_source.given_path_text`), anything else
    (text, bytes, a list of paths) as ``str`` writes it; a URL in either
    without its credentials, text as a message line (an address after a
    URL is kept: :func:`~pitloom.core.url_masking.masked_given_path`)."""
    if isinstance(value, (PurePath, GivenPath)):
        return given_path_text(value)
    return masked_given_path(str(value), line=True)


def log_kv(**pairs: object) -> None:
    """Log one ``INFO: KEY=VALUE`` line to stderr, each value through
    :func:`_shown`: a ``-v`` detail names an argument as typed and shows no
    secret."""
    log.info("%s", kv_line(**{key: _shown(value) for key, value in pairs.items()}))


def log_verbose(**pairs: object) -> None:
    """``-v``: ``PITLOOM_VERSION``, then one ``INFO:`` line per pair."""
    log_kv(PITLOOM_VERSION=__version__)
    for key, value in pairs.items():
        log_kv(**{key: value})
