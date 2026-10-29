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
"""

from __future__ import annotations

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
