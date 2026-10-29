# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Evidence levels of a recorded fact, and the one writer of their provenance
segment.

A fact is ``measured_stat`` (taken from the file system without reading),
``measured_read`` (computed by reading; written as no segment at all),
``declared`` (stated by metadata, not checked), ``lower_bound`` (a read stopped
at its limit) or ``not_measured`` (not safe to read, nothing declared).

:func:`evidence_segment` returns the ``Evidence:`` (and ``Reason:``) part of a
``"Source: X | Field: Y | Method: Z | Evidence: E | Reason: R"`` provenance
string; :func:`pitloom.core.provenance.parse_provenance_value` reads it back
under :data:`EVIDENCE_KEY` and :data:`REASON_KEY`.

:class:`Fact` is a value with its level and source, and writes its own
provenance through :func:`evidence_segment`; :func:`count_fact` makes one of
a byte size or count within Rule 3's bound; :func:`record_fact` records one
in an element's provenance by the levels' precedence, and
:func:`record_stated` adds what the sources stated without replacing it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from pitloom.core.provenance import parse_provenance_value

T = TypeVar("T")

MEASURED_STAT = "measured_stat"
MEASURED_READ = "measured_read"
DECLARED = "declared"
LOWER_BOUND = "lower_bound"
NOT_MEASURED = "not_measured"

EVIDENCE_LEVELS: frozenset[str] = frozenset(
    {MEASURED_STAT, MEASURED_READ, DECLARED, LOWER_BOUND, NOT_MEASURED}
)

#: Keys of the parsed provenance dict.
EVIDENCE_KEY = "evidence"
REASON_KEY = "reason"

#: The reason code of a fact over a read cap.
OVER_CAP = "over-cap"

#: Provenance field names of the facts a ``not_measured`` entry stands in
#: for: the hash (``verifiedUsing``) of a file, dataset or model, and a
#: dataset's size (``dataset_datasetSize``, ``DatasetMetadata.byte_size``).
VERIFIED_USING_FIELD = "verified_using"
BYTE_SIZE_FIELD = "byte_size"

#: Why a fact is ``not_measured``. The starting set the future message
#: catalogue adopts; a code is never free text, so it cannot carry untrusted
#: input into an SBOM.
REASON_CODES: frozenset[str] = frozenset(
    {
        OVER_CAP,
        "timeout",
        "network-failed",
        "lfs-pointer",
        "unreadable-file",
        "unlistable-dir",
    }
)


def evidence_segment(level: str, reason: str | None = None) -> str:
    """The provenance segment for an evidence *level*: ``"Evidence: <level>"``,
    or ``"Evidence: not_measured | Reason: <code>"``. The only writer.

    Raises:
        ValueError: *level* is not one of the levels, *reason* is not in
            :data:`REASON_CODES`, a *reason* comes with any level but
            ``not_measured``, or ``not_measured`` comes without one.
    """
    if level not in EVIDENCE_LEVELS:
        raise ValueError(f"unknown evidence level: {level!r}")
    if reason is None:
        if level == NOT_MEASURED:
            raise ValueError("evidence level not_measured needs a reason")
        return f"Evidence: {level}"
    if level != NOT_MEASURED:
        raise ValueError(f"a reason belongs to not_measured, not {level}")
    if reason not in REASON_CODES:
        raise ValueError(f"unknown evidence reason: {reason!r}")
    return f"Evidence: {level} | Reason: {reason}"


#: Precedence of a recorded level (Rule 1): measured beats declared beats a
#: lower bound beats not_measured. An entry with no ``Evidence:`` segment is
#: a source's statement, so declared.
_RANK: dict[str, int] = {
    MEASURED_STAT: 3,
    MEASURED_READ: 3,
    DECLARED: 2,
    LOWER_BOUND: 1,
    NOT_MEASURED: 0,
}


@dataclass(frozen=True)
class Fact(Generic[T]):
    """A recorded value with its evidence level. Make one with
    :meth:`measured_read`, :meth:`measured_stat`, :meth:`declared` or
    :meth:`not_measured` (or :func:`count_fact` for a count).

    Attributes:
        value: The value; ``None`` exactly when ``not_measured``.
        level: :data:`MEASURED_READ`, :data:`MEASURED_STAT`,
            :data:`DECLARED` or :data:`NOT_MEASURED` (a lower bound needs a
            budget a fact does not carry yet).
        source: What the value was taken from (the provenance
            ``Source:``), sanitised against a forged segment; ``None``
            exactly for ``measured_read``, which writes no provenance.
        reason: Why ``not_measured``, a :data:`REASON_CODES` code; ``None``
            for every other level.

    Raises:
        ValueError: The fields do not fit together as above.
    """

    value: T | None
    level: str
    source: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.level not in _RANK or self.level == LOWER_BOUND:
            raise ValueError(f"no fact at evidence level {self.level!r}")
        evidence_segment(self.level, self.reason)  # raises on a misfit reason
        if (self.value is None) != (self.level == NOT_MEASURED):
            raise ValueError(f"a {self.level} fact: only not_measured has no value")
        if (self.source is None) != (self.level == MEASURED_READ):
            raise ValueError(f"a {self.level} fact: only measured_read has no source")
        if self.source is not None:
            # Moving to pitloom.core.provenance; extract sits above core.
            # pylint: disable-next=import-outside-toplevel
            from pitloom.extract._extract_utils import sanitize_provenance_text

            object.__setattr__(self, "source", sanitize_provenance_text(self.source))

    @classmethod
    def measured_read(cls, value: T) -> Fact[T]:
        """*value*, computed by reading the content within the caps."""
        return cls(value, MEASURED_READ)

    @classmethod
    def measured_stat(cls, value: T, source: str) -> Fact[T]:
        """*value*, taken from *source*'s file system entry unread."""
        return cls(value, MEASURED_STAT, source)

    @classmethod
    def declared(cls, value: T, source: str) -> Fact[T]:
        """*value* as *source* states it, unchecked."""
        return cls(value, DECLARED, source)

    @classmethod
    def not_measured(cls, source: str, reason: str) -> Fact[T]:
        """No value from *source*, for *reason* (a :data:`REASON_CODES`
        code)."""
        return cls(None, NOT_MEASURED, source, reason)

    def provenance(self) -> str | None:
        """The provenance entry: ``"Source: <source> | <segment>"``
        (:func:`evidence_segment`); ``None`` for ``measured_read``."""
        if self.source is None:
            return None
        return f"Source: {self.source} | {evidence_segment(self.level, self.reason)}"


def count_fact(value: int, level: str, source: str, field: str) -> Fact[int]:
    """A byte size or count *value* of *source*'s *field* at the evidence
    *level* (Rule 3): up to the largest integer canonical JSON writes; past
    it, ``not_measured`` (``over-cap``) after the one over-cap ``WARNING:``
    of :func:`pitloom.extract.dataset.values.stated_count`. *source* names
    a ``measured_read`` fact's file in that warning and fallback only.

    Raises:
        ValueError: *value* is not an ``int`` of zero or more (a ``bool``
            is not), or *level* is ``not_measured``.
    """
    # extract sits above core.
    # pylint: disable-next=import-outside-toplevel
    from pitloom.extract.dataset.values import stated_count

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"a count is a whole number of zero or more, not {value!r}")
    if stated_count(value, source, field) is None:
        return Fact.not_measured(source, OVER_CAP)
    return Fact(value, level, None if level == MEASURED_READ else source)


def _entry_rank(entry: str) -> int:
    """The precedence of a provenance *entry* already recorded."""
    level = parse_provenance_value(entry).get(EVIDENCE_KEY, DECLARED)
    return _RANK.get(level, _RANK[DECLARED])


def record_fact(
    provenance: dict[str, str],
    field: str,
    fact: Fact[T] | None,
    set_value: Callable[[T], object] | None = None,
    *,
    entry: str | None = None,
) -> None:
    """Record *fact* about *field* in an element's *provenance*, and its
    value through *set_value*, unless *field*'s entry there is of the same
    or a higher level: measured beats declared (a source's statement, an
    entry with no ``Evidence:``) beats ``not_measured``, which so never
    replaces a value. A winning fact's entry goes last (a ``measured_read``
    one writes none, so it only removes the entry it replaces); it is
    *entry* when given, for a fact still written in an older form (a Git
    LFS pointer's hash). A field with no entry is open: record a measured
    fact after the statements it may replace. Nothing for no *fact*."""
    if fact is None:
        return
    held = provenance.get(field)
    if held is not None and _RANK[fact.level] <= _entry_rank(held):
        return
    if fact.value is not None and set_value is not None:
        set_value(fact.value)
    provenance.pop(field, None)
    written = fact.provenance() if entry is None else entry
    if written is not None:
        provenance[field] = written


def record_stated(provenance: dict[str, str], stated: dict[str, str]) -> None:
    """Add the entries the sources *stated* to *provenance*, in order, each
    only where its field has none: a statement does not carry the value of
    an entry already recorded (the caller, the hash's evidence), so it never
    replaces one."""
    for field, entry in stated.items():
        provenance.setdefault(field, entry)
