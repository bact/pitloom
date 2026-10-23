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
from pitloom.core.quote_source import quote_source
from pitloom.extract.lock._common_warnings import warn_conflicting_versions
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

_CanonicalGroupT = TypeVar("_CanonicalGroupT", bound=tuple[str, ...])


def group_by_canonical_name(
    items: Iterable[_CanonicalGroupT],
) -> dict[str, list[_CanonicalGroupT]]:
    """Group tuples by their PEP 503-canonical first element (the name),
    keeping file order across and within groups. Generic over tuple arity.
    What a multi-entry group means is the caller's decision.
    """
    # ``Flask==1.0`` and ``flask==2.0`` name one package: a "more than one
    # version" check must group on the canonical name.
    by_canonical: dict[str, list[_CanonicalGroupT]] = {}
    for item in items:
        by_canonical.setdefault(canonicalize_name(item[0]), []).append(item)
    return by_canonical


#: Operators that pin one release: ``==`` and arbitrary equality ``===``.
_EXACT_PIN_OPERATORS = frozenset({"==", "==="})


def is_same_version(v1: str, v2: str) -> bool:
    """Whether two versions are the same release under PEP 440 (``"1.0"``
    equals ``"1.0.0"``); exact string comparison when either does not parse
    (e.g. a ``===`` string).
    """
    try:
        return Version(v1) == Version(v2)
    except (InvalidVersion, TypeError):
        return v1 == v2


def single_exact_pin(specifier_set: SpecifierSet) -> tuple[str, str] | None:
    """``(operator, version)`` when *specifier_set* is exactly one ``==`` or
    ``===`` specifier, else ``None`` (a range, several specifiers or a
    ``==2.31.*`` prefix match). The caller builds the ``SpecifierSet``.
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
    """``(canonical name, version)`` of an exact-pin string such as the
    ``name==version`` the pin extractors emit, else ``None``. Used by the
    hash companions (:mod:`pitloom.extract.lock.pylock_hash` and siblings).
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
    """Group pins by canonical name and format each as ``name<op>version``
    (``==`` for a ``(name, version)`` pair).

    Parameters:
        pins: ``(name, version)`` pairs or ``(name, op, version)`` triples.
        lock_file: Label for log messages (a name or a path).
        on_conflict: What to do when a name has several distinct PEP 440
            versions: ``"skip"`` warns and omits that package (lock files);
            ``"abort"`` warns and returns ``None``, disqualifying the whole
            file (``requirements.txt``).
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
