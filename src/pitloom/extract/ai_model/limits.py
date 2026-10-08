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
from collections.abc import Callable, Iterator, Sequence
from itertools import islice

from pitloom.core.ai_metadata import (
    MAX_MODEL_ENTRIES,
    MAX_MODEL_NAME_CHARS,
    AiModelFormat,
    AiModelMetadata,
)
from pitloom.core.untrusted_text import escape_lone_surrogates_in
from pitloom.extract.ai_model.formats import Limits
from pitloom.logging_config import LONE_SURROGATES_WARNING, NAME_CUT_WARNING

__all__ = [
    "MAX_MODEL_ENTRIES",
    "ModelLimitExceeded",
    "ScanBudgetExceeded",
    "cap_and_warn",
    "cap_entries",
    "charge_read",
    "charging_reads",
    "recordable_labels",
    "settle_read_text",
    "warn_name_cut",
    "warn_no_label",
]

log = logging.getLogger(__name__)


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
    of *meta*, and drop the provenance and the ``raw_metadata_types`` of
    the dropped keys; add the number of ``raw_metadata`` keys dropped to
    ``raw_metadata_dropped``. Returns the sorted names of the fields cut.

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
            if name == "raw_metadata":
                meta.raw_metadata_dropped += len(mapping) - MAX_MODEL_ENTRIES
            kept[name] = dict(islice(mapping.items(), MAX_MODEL_ENTRIES))
            setattr(meta, name, kept[name])
            cut.append(name)
    if "raw_metadata" in kept:
        types = meta.raw_metadata_types
        meta.raw_metadata_types = {
            key: types[key] for key in kept["raw_metadata"] if key in types
        }
    if kept:
        meta.provenance = {
            key: value
            for key, value in meta.provenance.items()
            if _provenance_kept(key, kept)
        }
    return sorted(cut)


def cap_and_warn(meta: AiModelMetadata, fmt: AiModelFormat, where: str) -> None:
    """Apply :func:`cap_entries` to *meta* and say so once, naming *where*
    (the model's loggable path). Its one call site is
    :func:`pitloom.extract.scanner.read_model_candidate`, which every
    surface that reads a local model file goes through (the project and wheel
    scans, ``loom model`` and ``loom enrich``), so it is cut the same way, and
    announced in the same words, on each. A Hugging Face model
    (``read_huggingface``) is not cut. Then :func:`settle_read_text`, so
    the text is walked once cut."""
    cut = cap_entries(meta)
    settle_read_text(meta, fmt, where)
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


def recordable_labels(labels: Sequence[str], limits: Limits) -> tuple[str, ...]:
    """*labels*, or none of them when one is longer than
    ``limits.max_label_bytes`` in UTF-8, with one warning. A label is
    untrusted text of any length; the caller still records the label count
    it read. The scanner adds the ``FORMAT=``/``FILE=`` prefix."""
    cap = limits.max_label_bytes
    for label in labels:
        if len(label.encode("utf-8", "surrogatepass")) > cap:
            warn_no_label(f"a label over {cap} bytes")
            return ()
    return tuple(labels)


def warn_no_label(reason: str) -> None:
    """The one warning for a model whose labels are not recorded because
    *reason* (a bound exceeded, one short phrase); the caller still records
    the label count. The scanner adds the ``FORMAT=``/``FILE=`` prefix."""
    log.warning("%s; no label recorded", reason)


def settle_read_text(meta: AiModelMetadata, fmt: str, where: str) -> None:
    """The text rules for a model as read, each said once naming *where*:
    every lone surrogate, which no UTF-8 output can hold, written as text
    (:func:`~pitloom.core.untrusted_text.escape_lone_surrogates_in`), then
    :func:`warn_name_cut`. Called once per model, before anything is
    derived from its text (an id, a name): by :func:`cap_and_warn` for a
    model file, by ``read_huggingface`` for a Hugging Face model."""
    if escape_lone_surrogates_in(meta)[1]:
        log.warning(LONE_SURROGATES_WARNING, f"FORMAT={fmt} ", where)
    warn_name_cut(meta, fmt, where)


def warn_name_cut(meta: AiModelMetadata, fmt: str, where: str) -> None:
    """Say once, naming *where*, that the name *meta* shows was cut to
    :data:`~pitloom.core.ai_metadata.MAX_MODEL_NAME_CHARS` code points
    (:meth:`~pitloom.core.ai_metadata.AiModelMetadata.resolve_name`); quiet
    when it was not. Called once per model, by :func:`settle_read_text`."""
    length = meta.name_cut_length()
    if length is not None:
        log.warning(
            NAME_CUT_WARNING, fmt, where, "model name", length, MAX_MODEL_NAME_CHARS
        )


def _provenance_kept(key: str, kept: dict[str, dict[str, object]]) -> bool:
    """Whether provenance *key* (``"<field>.<entry>"`` or a plain field)
    survives the cut recorded in *kept*."""
    field, dot, entry = key.partition(".")
    return not dot or field not in kept or entry in kept[field]
