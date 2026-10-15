# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Order-matrix findings already accepted or tracked: a violation matching
one of these is reported as known (the check ends ``KNOWN``, with the
entries it matched), not ``FAIL``. Each entry names its item in
``working-docs/design/id-registry-followups.md``; drop it when the item
is done, so a regression fails again. Never add one without an item.

See also: ``_known.py`` (the runner's per-check list, whose ``O*`` entry
points here), ``_order_invariants.py``.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable
from dataclasses import dataclass

from _order_capture import PREFIX
from _order_invariants import Violation


@dataclass(frozen=True)
class Known:
    """One accepted finding: which violations, and why."""

    codes: tuple[str, ...]
    item: str
    applies: Callable[[Violation, str], bool]


def _per_document(violation: Violation, _profile: str) -> bool:
    return violation.key.split(" ", 1)[0] not in PREFIX


def _src_alias(violation: Violation, profile: str) -> bool:
    """A `src/`-layout file seen under its distribution path (no `src/`)
    by a wheel target or harvest, or any file key diverging under G."""
    if profile not in ("src", "setuptools") or not violation.key.startswith(
        "software_File "
    ):
        return False
    return violation.code.startswith("G/") or not violation.key.split(" ", 1)[
        1
    ].startswith("src/")


KNOWN: tuple[Known, ...] = (
    Known(
        ("A/*", "B/*"),
        "Harvest rewrites per-document entities (SoftwareAgent/Tool/"
        "Person/License ids carry each document's uuid; not a lookup type)",
        _per_document,
    ),
    Known(
        ("A/churn", "F/pinned", "E/disagree", "G/*"),
        "Wheel/sdist targets and src-layout registry file ids (a wheel "
        "target finds no `src/` key; `id generate` after a harvest mints a "
        "second id beside the distribution-path alias)",
        _src_alias,
    ),
)


def known_item(violation: Violation, profile: str) -> str | None:
    """The followups item *violation* is a known case of, if any."""
    for entry in KNOWN:
        if any(fnmatch.fnmatchcase(violation.code, c) for c in entry.codes):
            if entry.applies(violation, profile):
                return entry.item
    return None
