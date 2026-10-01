# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Bounds every AI model reader answers to, and what a reader raises when a
file exceeds one.

A model file is untrusted: what it declares (an entry count, an array
length, a header size) decides how much a parser allocates or loops. A
reader checks the declaration first and raises :class:`ModelLimitExceeded`;
the scanner reports it once and keeps a format-only entry.

See also: :mod:`pitloom.extract.scanner` (reports the exceptions) and
:mod:`pitloom.extract.ai_model.archive_member` (bounded archive reads).
"""

from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Callable, Iterator
from itertools import islice

from pitloom.core.ai_metadata import AiModelMetadata

#: Most entries kept per list or map of one model (inputs, outputs,
#: hyperparameters, properties, raw metadata). A real model has tens to a
#: few hundreds; the first ones, in source order, stay.
MAX_MODEL_ENTRIES = 1000


class ModelLimitExceeded(Exception):
    """A model file declares or holds more than a reader will process.

    Not a :class:`ValueError`: a reader's ``except Exception`` fallback must
    let it through (``except ModelLimitExceeded: raise`` first), so the
    scanner reports it once instead of each reader degrading quietly.

    Attributes:
        reason: What was exceeded, as one short phrase (no path).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ScanBudgetExceeded(ModelLimitExceeded):
    """A producer's overall extraction budget is spent. The producer has
    already logged the one warning for it; the scanner keeps a format-only
    entry, quietly."""

    def __init__(self) -> None:
        super().__init__("scan budget spent")


# Called with every byte count an archive-member read returns; raises
# ScanBudgetExceeded when the producer's budget is spent.
_charge: contextvars.ContextVar[Callable[[int], None] | None] = contextvars.ContextVar(
    "pitloom_model_read_charge", default=None
)


@contextlib.contextmanager
def charging_reads(charge: Callable[[int], None]) -> Iterator[None]:
    """Count, through *charge*, the bytes every bounded archive-member read
    in the block returns (see :func:`charge_read`)."""
    token = _charge.set(charge)
    try:
        yield
    finally:
        _charge.reset(token)


def charge_read(size: int) -> None:
    """Report *size* bytes read to the active :func:`charging_reads`, if any."""
    charge = _charge.get()
    if charge is not None:
        charge(size)


def cap_entries(meta: AiModelMetadata) -> list[str]:
    """Keep the first :data:`MAX_MODEL_ENTRIES` entries of each list and map
    of *meta*, in source order, and drop the provenance of the dropped
    keys. Returns the sorted names of the fields cut.

    A capped map is rebuilt, not trimmed: a dict never gives back the table
    it grew to, so deleting keys would keep a huge model's memory.
    """
    cut: list[str] = []
    for name in ("inputs", "outputs"):
        items = getattr(meta, name)
        if len(items) > MAX_MODEL_ENTRIES:
            del items[MAX_MODEL_ENTRIES:]  # a list does shrink
            cut.append(name)
    # Only the kept keys are collected: a set of the dropped ones would cost
    # as much as the map being cut.
    kept: dict[str, dict[str, object]] = {}
    for name in ("hyperparameters", "properties", "raw_metadata"):
        mapping = getattr(meta, name)
        if len(mapping) > MAX_MODEL_ENTRIES:
            kept[name] = dict(islice(mapping.items(), MAX_MODEL_ENTRIES))
            setattr(meta, name, kept[name])
            cut.append(name)
    if kept:
        meta.provenance = {
            key: value
            for key, value in meta.provenance.items()
            if _provenance_kept(key, kept)
        }
    return sorted(cut)


def _provenance_kept(key: str, kept: dict[str, dict[str, object]]) -> bool:
    """Whether provenance *key* (``"<field>.<entry>"`` or a plain field)
    survives the cut recorded in *kept*."""
    field, dot, entry = key.partition(".")
    return not dot or field not in kept or entry in kept[field]
