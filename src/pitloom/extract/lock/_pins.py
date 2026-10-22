# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Exact-pin handling shared by the lock and requirements extractors:
grouping entries by canonical name, judging a specifier or a requirement
string, and resolving pins that name one project more than once.

See also: :mod:`pitloom.extract.lock.common`, which re-exports these names.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, TypeVar

from packaging.requirements import InvalidRequirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from pitloom.core.pep508 import parse_requirement
from pitloom.extract._extract_utils import quote_source
from pitloom.extract.lock._common_warnings import warn_conflicting_versions
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

_CanonicalGroupT = TypeVar("_CanonicalGroupT", bound=tuple[str, ...])


def group_by_canonical_name(
    items: Iterable[_CanonicalGroupT],
) -> dict[str, list[_CanonicalGroupT]]:
    """Group tuples by PEP 503-canonicalized *name* (each tuple's first
    element), preserving file order both across and within groups.

    Comparing canonicalized (lowercased, ``-``/``_``/``.``-folded) names
    is required, not optional: ``Flask==1.0`` and ``flask==2.0`` name the
    same PyPI package under PEP 503, so a caller checking "does this name
    resolve to more than one version" must group them together or the
    check silently never fires for a mixed-case duplicate.

    Generic over tuple arity so :func:`resolve_pinned_dependencies`'s
    ``(name, version)`` pairs and ``(name, operator, version)`` triples
    and :mod:`pitloom.assemble.spdx3._document_locked_deps`'s
    ``(name, dep, pinned)`` triples share one implementation instead of a
    per-caller copy of the same loop.

    A caller decides what a multi-entry group means for its own format:
    :mod:`pitloom.extract.lock.pdm` collapses a group to one entry when
    every version agrees (its per-extra duplicate records always do) and
    skips just that name otherwise; ``requirements.txt`` treats any
    conflicting group as disqualifying its whole file.
    """
    by_canonical: dict[str, list[_CanonicalGroupT]] = {}
    for item in items:
        by_canonical.setdefault(canonicalize_name(item[0]), []).append(item)
    return by_canonical


#: PEP 440 operators that pin to exactly one release: ``==`` (the
#: ordinary case) and ``===`` (arbitrary-equality, for a legacy/
#: non-normalizable version string a resolver would otherwise reject --
#: rare in practice, but just as exact a pin as ``==`` once present).
_EXACT_PIN_OPERATORS = frozenset({"==", "==="})


def is_same_version(v1: str, v2: str) -> bool:
    """Return whether two version strings represent the same release.

    Uses :class:`packaging.version.Version` comparison so PEP 440
    equivalences (e.g. ``"1.0" == "1.0.0"``) compare equal rather than
    triggering spurious version-conflict warnings. Falls back to exact
    string comparison when either string is not a valid PEP 440 version
    (e.g. arbitrary-equality ``===`` strings).
    """
    try:
        return Version(v1) == Version(v2)
    except (InvalidVersion, TypeError):
        return v1 == v2


def single_exact_pin(specifier_set: SpecifierSet) -> tuple[str, str] | None:
    """Return ``(operator, version)`` when *specifier_set* contains exactly
    one non-wildcard exact-pin specifier (``==`` or PEP 440's arbitrary-
    equality ``===``, e.g. ``SpecifierSet("==2.31.0")`` ->
    ``("==", "2.31.0")``, ``SpecifierSet("===2021.01.01-legacy")`` ->
    ``("===", "2021.01.01-legacy")``), or ``None`` for anything looser than
    one exact pin -- a range, more than one specifier, or a prefix-match
    wildcard like ``"==2.31.*"`` (``packaging.specifiers.Specifier`` reports
    that as operator ``"=="`` too, but it pins a *range* of versions, not
    one exact release -- ``===`` has no wildcard form, so this check only
    matters for ``==``).

    Doesn't itself construct *specifier_set* from a raw string --
    :mod:`pitloom.extract.lock.pipfile` and
    :mod:`pitloom.extract.lock.requirements` both need a raw-string
    parse step first, and each wants different ``WARNING:`` wording for
    "unparseable" vs. "parseable but not a single exact pin" -- so
    parsing (and catching ``packaging.specifiers.InvalidSpecifier``)
    stays the caller's job; this function only judges an already-built
    ``SpecifierSet``.
    """
    specifiers = list(specifier_set)
    if (
        len(specifiers) != 1
        or specifiers[0].operator not in _EXACT_PIN_OPERATORS
        or "*" in specifiers[0].version
    ):
        return None
    return specifiers[0].operator, specifiers[0].version


def parse_exact_pin_requirement(req_str: str) -> tuple[str, str, str] | None:
    """Parse a PEP 508 dependency string and return ``(name, operator, version)``
    when it represents a single exact ``==`` or ``===`` pin without a direct URL
    reference, or ``None`` otherwise."""
    try:
        req = parse_requirement(req_str)
    except (InvalidRequirement, TypeError):
        return None
    if req.url is not None:
        return None
    pin = single_exact_pin(req.specifier)
    if pin is None:
        return None
    op, version = pin
    return req.name, op, version


def canonical_name_and_pinned_version(dep: str) -> tuple[str, str] | None:
    """Parse an exact-pin dependency string -- one already known to carry a
    single exact pin, as every lock/pin extractor in this package formats
    its own output (e.g. ``f"{name}=={version}"``) -- back into
    ``(canonicalize_name(name), version)``, or ``None`` if it doesn't parse
    or isn't a single exact pin.

    Used by each format's hash-extraction companion
    (:mod:`pitloom.extract.lock.pylock_hash` and its siblings) to look a pin
    extractor's own already-resolved winning dependency back up in the raw
    lock data by name and version, so hash extraction never re-derives the
    pin extractor's own group/marker/non-registry-source filtering and
    conflicting-version exclusion a second time -- it only ever computes a
    hash for a package the pin extractor itself decided to include.
    """
    parsed = parse_exact_pin_requirement(dep)
    if parsed is None:
        return None
    name, _op, version = parsed
    return canonicalize_name(name), version


def _pin_operator(pin: tuple[str, str] | tuple[str, str, str]) -> str:
    """*pin*'s operator, ``"=="`` for a ``(name, version)`` pair."""
    return pin[1] if len(pin) == 3 else "=="


def _same_pin(
    pin: tuple[str, str] | tuple[str, str, str], op: str, version: str
) -> bool:
    """Whether *pin* names the release ``(op, version)`` does: PEP 440
    equality, except that a ``===`` (arbitrary equality) on either side
    compares the exact string (``===1.0`` is not ``1.0.0``)."""
    if "===" in (op, _pin_operator(pin)):
        return pin[-1] == version
    return is_same_version(pin[-1], version)


def resolve_pinned_dependencies(
    pins: Iterable[tuple[str, str] | tuple[str, str, str]],
    lock_file: str | Path,
    *,
    on_conflict: Literal["skip", "abort"] = "skip",
) -> list[str] | None:
    """Group pinned package tuples by canonical name, verify PEP 440 version
    consistency across same-name entries, and format each into an exact-pin
    PEP 508 string (``name==version`` or ``name<op>version``).

    Parameters:
        pins: An iterable of ``(name, version)`` pairs or ``(name, op, version)``
            triples. When pairs are passed, the operator defaults to ``"=="``.
        lock_file: Label for log messages (e.g. ``"poetry.lock"`` or the file's
            :class:`pathlib.Path`).
        on_conflict: Conflict handling policy when a canonical name has multiple
            entries with distinct PEP 440 versions:
            - ``"skip"``: Emit a warning, omit the conflicting package, and
              continue resolving remaining packages (standard for lock files).
            - ``"abort"``: Emit a warning and immediately return ``None``,
              disqualifying the whole file (standard for ``requirements.txt``).
    """
    file_label = lock_file.name if isinstance(lock_file, Path) else str(lock_file)
    dependencies: list[str] = []
    for group in group_by_canonical_name(pins).values():
        first = group[0]
        name = first[0]
        version = first[-1]
        op = _pin_operator(first)
        conflicting_versions = {
            item[-1] for item in group if not _same_pin(item, op, version)
        }
        all_versions = {item[-1] for item in group}

        if conflicting_versions:
            if on_conflict == "abort":
                log.warning(
                    "%s: %r pinned to conflicting versions (%s) -- ignoring %s",
                    quote_source(lock_file),
                    name,
                    loggable(", ".join(sorted(all_versions))),
                    file_label,
                )
                return None
            warn_conflicting_versions(file_label, name, all_versions)
            continue
        dependencies.append(f"{name}{op}{version}")
    return dependencies
