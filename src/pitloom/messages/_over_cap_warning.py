# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one ``WARNING:`` for an input over a cap (:func:`warn_over_cap`),
and reading its cap back off a record (:func:`over_cap_of`).

See also: :mod:`pitloom.messages._over_cap` (:class:`Cap`).
"""

from __future__ import annotations

import logging

from pitloom.logging_config import loggable, warn_once
from pitloom.messages._over_cap import Cap

#: The one ``WARNING:`` for an input over a cap, logged by
#: :func:`warn_over_cap`. Arguments: the key naming the input
#: (:attr:`Cap.subject`), the input (through
#: :func:`~pitloom.logging_config.loggable`), the cap (:attr:`Cap.reason`),
#: and what was and was not read or done.
OVER_CAP_WARNING = "%s=%s: %s; %s"

# The LogRecord attribute holding (cap, outcome) of an OVER_CAP_WARNING.
_OVER_CAP_ATTR = "pitloom_over_cap"


def warn_over_cap(
    log: logging.Logger,
    cap: Cap,
    where: str,
    outcome: str = "skipped",
    *,
    once: bool = False,
    key: str | None = None,
) -> None:
    """The one ``WARNING:`` for an input over *cap*: *where* names the
    input (escaped through :func:`~pitloom.logging_config.loggable`),
    *outcome* what was read and what was not. *once*: through
    :func:`~pitloom.logging_config.warn_once`, once per cap and input in this
    process, the input known by *key* (default *where*) when two spellings
    name one input. The record carries *cap* and *outcome* for
    :func:`over_cap_of`."""
    args = (cap.subject, loggable(where), cap.reason, outcome)
    extra = {_OVER_CAP_ATTR: (cap, outcome)}
    if once:
        seen = f"over-cap:{cap.purpose}:{where if key is None else key}"
        warn_once(log, seen, OVER_CAP_WARNING, *args, extra=extra)
    else:
        log.warning(OVER_CAP_WARNING, *args, extra=extra)


def over_cap_of(record: logging.LogRecord) -> tuple[Cap, str] | None:
    """The cap and outcome of a record :func:`warn_over_cap` logged, so a
    caller relaying it can name the input in its own words; else ``None``."""
    found: tuple[Cap, str] | None = getattr(record, _OVER_CAP_ATTR, None)
    return found
