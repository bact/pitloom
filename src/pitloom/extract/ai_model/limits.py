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
import logging
from collections.abc import Callable, Iterator
from itertools import islice

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata

log = logging.getLogger(__name__)

#: Most entries kept per list or map of one model (inputs, outputs,
#: hyperparameters, properties, raw metadata). A real model has tens to a
#: few hundreds; the first ones stay: in file order, or in key order for
#: Safetensors ``__metadata__``, which the library returns in no fixed order.
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
    of *meta*, and drop the provenance of the dropped keys. Returns the
    sorted names of the fields cut.

    "First" is the order a reader hands over: file order, which is the same
    on every run; a reader whose source has none (Safetensors
    ``__metadata__``) sorts by key before the cut.

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


def cap_and_warn(meta: AiModelMetadata, fmt: AiModelFormat, where: str) -> None:
    """Apply :func:`cap_entries` to *meta* and say so once, naming *where*
    (the model's loggable path). Every surface that reads a local model file
    calls this (the project and wheel scans, ``loom model`` and ``loom
    enrich``), so it is cut the same way, and announced in the same words, on
    each. A Hugging Face model (``read_huggingface``) is not cut."""
    cut = cap_entries(meta)
    if cut:
        log.warning(
            "FORMAT=%s FILE=%s: more than %d entries in %s; the first %d of "
            "each are kept",
            fmt,
            where,
            MAX_MODEL_ENTRIES,
            ", ".join(cut),
            MAX_MODEL_ENTRIES,
        )


def _provenance_kept(key: str, kept: dict[str, dict[str, object]]) -> bool:
    """Whether provenance *key* (``"<field>.<entry>"`` or a plain field)
    survives the cut recorded in *kept*."""
    field, dot, entry = key.partition(".")
    return not dot or field not in kept or entry in kept[field]
