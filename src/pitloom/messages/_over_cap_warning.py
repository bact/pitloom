# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one ``WARNING:`` for an input over a cap (:func:`warn_over_cap`),
and reading its cap back off a record (:func:`over_cap_of`).

See also: :mod:`pitloom.messages._over_cap` (the ``over-cap`` entry and
:class:`~pitloom.messages.Cap`).
"""

from __future__ import annotations

import logging

from pitloom.messages._emit import emit
from pitloom.messages._over_cap import KEY_LINE, MODEL_LINE, OVER_CAP, Cap

#: The LogRecord attribute holding the (cap, outcome) of an over-cap warning.
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
    """The one ``WARNING:`` for an input over *cap*, ``[over-cap]``:
    *where* names the input (escaped), after its key, or after the model's
    format (:attr:`Cap.model_format`); *outcome* says what was read and what
    was not. *once*: once per cap and input in this process (a repeat is
    ``DEBUG``), the input known by *key* (default *where*) when two
    spellings name one input. The record carries *cap* and *outcome* for
    :func:`over_cap_of`."""
    values: dict[str, object] = {**cap.reason_values(), "outcome": outcome}
    if cap.model_format is None:
        line = KEY_LINE
        values.update(key=cap.subject, name=where)
    else:
        line = MODEL_LINE
        values.update(format=cap.model_format, file=where)
    seen = f"over-cap:{cap.purpose}:{where if key is None else key}" if once else None
    emit(
        log,
        OVER_CAP,
        logging.WARNING,
        line=line,
        once=seen,
        extra={_OVER_CAP_ATTR: (cap, outcome)},
        **values,
    )


def over_cap_of(record: logging.LogRecord) -> tuple[Cap, str] | None:
    """The cap and outcome of a record :func:`warn_over_cap` logged, so a
    caller relaying it can name the input in its own words; else ``None``."""
    found: tuple[Cap, str] | None = getattr(record, _OVER_CAP_ATTR, None)
    return found
