# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""No catalogue template prints a bare count before a plural noun
(``%(number)s files``), which reads ``1 files`` at one, unless the count
cannot be one.

See also: tests/messages/test_messages_fields.py (the ``size`` and
``duration`` fields, which carry their unit and pluralise).
"""

from __future__ import annotations

import re
from typing import Final

from pitloom.messages import FIELDS, FRAMES, MESSAGES, SUMMARIES
from pitloom.messages._field_writers import number_text

#: A field followed by a word ending in ``s``.
_FIELD_THEN_PLURAL: Final = re.compile(r"%\((\w+)\)s (\w+s)\b")

_CAP: Final = "a fixed cap, never 1"
_TWO_OR_MORE: Final = "2 or more by construction"

#: (where, field and noun) -> why the count is never 1.
_ALLOWED: Final = {
    ("build-failed", "%(number)s wheels"): "0 or 2 or more: the line says 'not one'",
    ("file-ambiguous", "%(number)s sdists"): _TWO_OR_MORE,
    ("file-ambiguous", "%(number)s wheels"): _TWO_OR_MORE,
    ("metadata-invalid", "%(number)s digits"): _CAP,
    ("model-ambiguous/over-cap", "%(limit)s files"): _CAP,
    ("model-field-unreadable", "%(number)s characters"): "a text longer than "
    "its cap (limit)",
    ("option-invalid", "%(limit)s seconds"): _CAP,
    ("registry-key-ambiguous", "%(number)s files"): _TWO_OR_MORE,
    ("url-unsafe", "%(number)s redirects"): _CAP,
    ("wheel-sbom-ambiguous", "%(number)s SBOMs"): _TWO_OR_MORE,
}


def _templates() -> list[tuple[str, str]]:
    """Every template of the catalogue, with where it is."""
    found = [
        (code, line.template)
        for code, entry in MESSAGES.items()
        for line in entry.lines
    ]
    found += [("frame", frame.template) for frame in FRAMES]
    found += [("summary", summary.template) for summary in SUMMARIES]
    return found


def test_no_count_noun_plural_without_reason() -> None:
    counts = {name for name, field in FIELDS.items() if field.write is number_text}
    assert {"number", "limit"} <= counts
    found = {
        (where, match.group())
        for where, template in _templates()
        for match in _FIELD_THEN_PLURAL.finditer(template)
        if match.group(1) in counts
    }
    # Exact both ways: a new bare plural fails, and so does a stale entry.
    assert found == set(_ALLOWED)
