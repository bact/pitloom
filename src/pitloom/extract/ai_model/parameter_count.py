# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Reader-side parameter count: warn on a rejection, record what a sum shows.

See also: :mod:`pitloom.core.model_parameters` (the bounded arithmetic).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from pitloom.core.ai_metadata import model_cap
from pitloom.core.model_parameters import (
    PARAMETER_COUNT_CAP,
    PARAMETER_COUNT_PROVENANCE_KEY,
    TENSOR_ELEMENT_SUM_METHOD,
    ParameterCountRejected,
    tensor_element_sum,
)
from pitloom.logging_config import loggable
from pitloom.messages import warn_over_cap

_log = logging.getLogger(__name__)

#: What a rejected count leaves out, as a model warning says it.
PARAMETER_COUNT_SKIPPED = "parameter count not recorded"


def warn_parameter_count(
    log: logging.Logger,
    exc: ParameterCountRejected,
    where: str,
    fmt: str | None = None,
) -> None:
    """The one ``WARNING:`` for a rejected parameter count. With *fmt* it
    names the model (``FORMAT=<fmt> FILE=<where>``); without, only an
    over-cap one names *where*, and the scanner adds ``FORMAT=``/``FILE=``
    when it relays a reader's record (a direct reader call shows none)."""
    if exc.over_cap:
        cap = model_cap(PARAMETER_COUNT_CAP, fmt) if fmt else PARAMETER_COUNT_CAP
        warn_over_cap(log, cap, where, PARAMETER_COUNT_SKIPPED)
    elif fmt:
        log.warning(
            "FORMAT=%s FILE=%s: %s; %s",
            fmt,
            loggable(where),
            exc.reason,
            PARAMETER_COUNT_SKIPPED,
        )
    else:
        log.warning("%s; %s", exc.reason, PARAMETER_COUNT_SKIPPED)


def derived_parameter_count(
    shapes: Iterable[Sequence[object]],
    field: str,
    source: str,
    provenance: dict[str, str],
    where: str,
) -> int | None:
    """The sum of the elements of *shapes*, with its provenance set; ``None``
    (and no provenance) when there is no element, or, with one
    :func:`warn_parameter_count` ``WARNING:`` (no *fmt*: the scanner names
    the model when relaying it), when a shape is rejected.

    Args:
        shapes: One shape per tensor; may be a generator.
        field: Where the reader took the shapes from (a fixed literal).
        source: The ``Source: <file name>`` part of the provenance text.
        provenance: The reader's provenance map, set on a count.
        where: The model's path, for an over-cap warning.
    """
    try:
        count = tensor_element_sum(shapes)
    except ParameterCountRejected as exc:
        warn_parameter_count(_log, exc, where)
        return None
    if count is not None:
        provenance[PARAMETER_COUNT_PROVENANCE_KEY] = (
            f"{source} | Field: {field}{TENSOR_ELEMENT_SUM_METHOD}"
        )
    return count
