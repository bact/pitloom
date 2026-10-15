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
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from _order_capture import FILE, PREFIX, Entry, Key
from _order_invariants import Violation

#: A registry the allow-list may look at: the one after the violation's
#: step, a sequence's last one for E, or one permutation's final one for G.
Registry = Mapping[Key, Entry]


@dataclass(frozen=True)
class Known:
    """One accepted finding: which violations, and why."""

    codes: tuple[str, ...]
    item: str
    applies: Callable[[Violation, str, Registry | None], bool]


def _per_document(violation: Violation, _profile: str, _reg: Registry | None) -> bool:
    return violation.key.split(" ", 1)[0] not in PREFIX


_SRC = "src/"


def _src_alias(violation: Violation, profile: str, registry: Registry | None) -> bool:
    """The documented src-layout alias shape only: a `software_File` key
    without `src/` (a distribution path) whose `src/`-prefixed twin is in
    *registry* with the same sha256 -- the alias a harvest writes, which a
    wheel target or a later run gives another id. G (convergence) names
    either key of the pair: whether the two share an id depends on the
    order. Any other violation on a file key, or one whose registry holds
    no such pair, is not this."""
    if profile not in ("src", "setuptools") or registry is None:
        return False
    type_name, _, name = violation.key.partition(" ")
    if type_name != FILE:
        return False
    if name.startswith(_SRC):
        if not violation.code.startswith("G/"):
            return False
        name = name[len(_SRC) :]
    alias, twin = registry.get((FILE, name)), registry.get((FILE, _SRC + name))
    return (
        alias is not None
        and twin is not None
        and alias.sha is not None
        and alias.sha == twin.sha
    )


KNOWN: tuple[Known, ...] = (
    Known(
        ("A/*", "B/*"),
        "Harvest rewrites per-document entities (SoftwareAgent/Tool/"
        "Person/License ids carry each document's uuid; not a lookup type)",
        _per_document,
    ),
    Known(
        (
            "A/churn",
            "F/pinned",
            "E/disagree",
            "G/key-sets-differ",
            "G/ids-not-a-type-preserving-bijection",
        ),
        "Wheel/sdist targets and src-layout registry file ids (a wheel "
        "target finds no `src/` key; `id generate` after a harvest mints a "
        "second id beside the distribution-path alias)",
        _src_alias,
    ),
)


def known_item(
    violation: Violation, profile: str, registry: Registry | None = None
) -> str | None:
    """The followups item *violation* is a known case of, if any; *registry*
    is what an entry may need to recognise its shape (see :data:`Registry`)."""
    for entry in KNOWN:
        if any(fnmatch.fnmatchcase(violation.code, c) for c in entry.codes):
            if entry.applies(violation, profile, registry):
                return entry.item
    return None
