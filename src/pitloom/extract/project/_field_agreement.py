# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""When two metadata sources agree on a field, and how a disagreement is
recorded -- the one rule for every producer of
:attr:`~pitloom.core.project.ProjectMetadata.field_conflicts`.

See also: :mod:`pitloom.extract.project._installed_reconcile` (static vs
in-tree installed metadata) and
:mod:`pitloom.extract.project._setuptools_options` (``setup.py`` vs
``setup.cfg``).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name

from pitloom.core.project import ConflictCandidate, ProjectMetadata
from pitloom.extract._license import classify_license, same_licence
from pitloom.extract.lock._common import is_same_version

#: Fields checked for a genuine disagreement between two sources: a real
#: conflict is recorded (never silently substituted).
CONFLICT_CHECKED_FIELDS = frozenset({"version", "requires_python", "license_name"})

#: Fields only ever gap-filled from a second source -- equality semantics
#: are too fuzzy to flag as a conflict (e.g. ``Summary`` free text).
GAP_FILL_ONLY_FIELDS = frozenset({"description", "keywords", "urls"})


def _requires_python_equal(a: str, b: str) -> bool:
    """PEP 440 specifier-set equality (``'>=3.9'`` == ``'>= 3.9'``), not
    raw string equality. Falls back to stripped-string equality if either
    side fails to parse as a :class:`~packaging.specifiers.SpecifierSet`
    (never raise)."""
    try:
        return SpecifierSet(a) == SpecifierSet(b)
    except InvalidSpecifier:
        return a.strip() == b.strip()


def is_weak_licence(value: str | None) -> bool:
    """Whether *value* is a placeholder (``NOASSERTION``/``UNKNOWN``), not a
    claim. ``NONE`` is a statement, not weak."""
    classified = classify_license(value, warn=False)
    return classified is not None and classified.kind == "noassertion"


def _license_equal(a: str, b: str) -> bool:
    """Same licence once classified (``mit`` == ``MIT``, ``GPL-2.0+`` ==
    ``GPL-2.0-or-later``, ``MIT License`` == ``MIT``; the rule the declared
    vs concluded check uses). ``NOASSERTION``/``UNKNOWN`` is weak: it agrees
    with anything, a blank value too. A value that states none compares as
    empty."""
    if is_weak_licence(a) or is_weak_licence(b):
        return True
    first, second = (classify_license(v, warn=False) for v in (a, b))
    if first is None or second is None:
        return first is None and second is None
    return same_licence(first.value, second.value)


_FIELD_COMPARATORS: dict[str, Callable[[str, str], bool]] = {
    "name": lambda a, b: canonicalize_name(a) == canonicalize_name(b),  # PEP 503
    "version": is_same_version,
    "license_name": _license_equal,
    "requires_python": _requires_python_equal,
}


def values_agree(field_name: str, a: str | None, b: str | None) -> bool:
    """Whether *a* and *b* are the same value of *field_name* (``name`` or
    one of :data:`CONFLICT_CHECKED_FIELDS`) as the ecosystem compares it,
    ``None`` compared as ``""``."""
    return _FIELD_COMPARATORS[field_name](a or "", b or "")


def add_conflict(
    metadata: ProjectMetadata, key: str, candidates: Sequence[ConflictCandidate]
) -> None:
    """Record *candidates* under *key* in *metadata*'s ``field_conflicts``,
    after any already recorded there, each once. The list is rebuilt, never
    extended in place: a shallow copy of the metadata may share it."""
    recorded = list(metadata.field_conflicts.get(key, []))
    for candidate in candidates:
        if candidate not in recorded:
            recorded.append(candidate)
    metadata.field_conflicts[key] = recorded
