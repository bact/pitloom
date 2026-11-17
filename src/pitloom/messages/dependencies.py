# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Dependencies"
(``dependencies`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines and the helpers that say them.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._dependency import (
    CAUSE_LINES,
    DEPENDENCY_LOCAL_SOURCE_LINE,
    DEPENDENCY_NAME_AMBIGUOUS,
    DEPENDENCY_NOT_CONVERTIBLE_LINE,
    DEPENDENCY_NOT_PEP_508_LINE,
    DEPENDENCY_UNLISTED_OPTIONAL_LINE,
    DIRECT_REFERENCE_LINE,
    EXTRA_CYCLE_LINE,
    EXTRA_GATE_AMBIGUOUS,
    EXTRA_GATE_UNUSABLE,
    EXTRA_MARKER_LINE,
    EXTRA_NOT_PEP_508_LINE,
    EXTRA_UNDECLARED_DEPENDENCY_LINE,
    EXTRA_UNDECLARED_EXTRA_LINE,
    GATE_LINE,
    JOINED_LINE,
    REQUIRED_LINE,
    REQUIREMENT_INVALID,
    REQUIREMENT_UNUSABLE,
    SELF_GATE_LINE,
)
from pitloom.messages._lock_say import (
    Cause,
    say_direct_reference,
    warn_extra_gate_ambiguous,
    warn_extra_gate_unusable,
    warn_required_not_pep508,
    warn_skipped_dependency,
    warn_skipped_extra_entry,
)

__all__ = [
    "CAUSE_LINES",
    "Cause",
    "DEPENDENCY_LOCAL_SOURCE_LINE",
    "DEPENDENCY_NAME_AMBIGUOUS",
    "DEPENDENCY_NOT_CONVERTIBLE_LINE",
    "DEPENDENCY_NOT_PEP_508_LINE",
    "DEPENDENCY_UNLISTED_OPTIONAL_LINE",
    "DIRECT_REFERENCE_LINE",
    "EXTRA_CYCLE_LINE",
    "EXTRA_GATE_AMBIGUOUS",
    "EXTRA_GATE_UNUSABLE",
    "EXTRA_MARKER_LINE",
    "EXTRA_NOT_PEP_508_LINE",
    "EXTRA_UNDECLARED_DEPENDENCY_LINE",
    "EXTRA_UNDECLARED_EXTRA_LINE",
    "GATE_LINE",
    "JOINED_LINE",
    "REQUIRED_LINE",
    "REQUIREMENT_INVALID",
    "REQUIREMENT_UNUSABLE",
    "SELF_GATE_LINE",
    "say_direct_reference",
    "warn_extra_gate_ambiguous",
    "warn_extra_gate_unusable",
    "warn_required_not_pep508",
    "warn_skipped_dependency",
    "warn_skipped_extra_entry",
]
