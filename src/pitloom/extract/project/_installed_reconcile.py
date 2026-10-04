# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Reconciliation of parsed in-tree installed metadata
(:mod:`pitloom.extract.project.installed`) into the static metadata
(``pyproject.toml``/``setup.cfg``/``setup.py``) -- static always wins on a
genuine disagreement (recorded, never silently substituted); installed
only fills gaps the static source left undeclared.

See :mod:`pitloom.extract.project.installed` for discovery and parsing;
see ``working-docs/design/installed-dist-info-source.md`` for the full
design.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from pathlib import Path

from packaging.specifiers import InvalidSpecifier, SpecifierSet

from pitloom.core.project import ConflictCandidate, ProjectMetadata, provenance_key_for
from pitloom.extract._extract_utils import field_declared
from pitloom.extract._license import classify_license, same_licence
from pitloom.extract.lock._common import is_same_version

log = logging.getLogger(__name__)

#: Fields checked for a genuine disagreement between static and installed
#: metadata: a real conflict is recorded (never silently substituted) and
#: static's value wins.
_CONFLICT_CHECKED_FIELDS = frozenset({"version", "requires_python", "license_name"})

#: Fields only ever gap-filled from installed metadata when static left
#: them undeclared -- equality semantics are too fuzzy to flag as a
#: conflict (e.g. ``Summary`` free text), so no comparison is attempted.
_GAP_FILL_ONLY_FIELDS = frozenset({"description", "keywords", "urls"})


def _requires_python_equal(a: str, b: str) -> bool:
    """PEP 440 specifier-set equality (``'>=3.9'`` == ``'>= 3.9'``), not
    raw string equality. Falls back to stripped-string equality if either
    side fails to parse as a :class:`~packaging.specifiers.SpecifierSet`
    (never raise)."""
    try:
        return SpecifierSet(a) == SpecifierSet(b)
    except InvalidSpecifier:
        return a.strip() == b.strip()


def _license_equal(a: str, b: str) -> bool:
    """Same licence once classified (``mit`` == ``MIT``, ``GPL-2.0+`` ==
    ``GPL-2.0-or-later``, ``MIT License`` == ``MIT``; the rule the declared
    vs concluded check uses). ``NOASSERTION``/``UNKNOWN`` is weak: it agrees
    with anything, a blank value too, and :func:`_weak_static_licence` lets
    the real licence win. A value that states none compares as empty."""
    first, second = (classify_license(v, warn=False) for v in (a, b))
    if any(c is not None and c.kind == "noassertion" for c in (first, second)):
        return True
    if first is None or second is None:
        return first is None and second is None
    return same_licence(first.value, second.value)


def _weak_static_licence(static: ProjectMetadata, installed: ProjectMetadata) -> bool:
    """Whether static's licence is only ``NOASSERTION``/``UNKNOWN`` and the
    installed one states a real licence, which then wins."""
    first, second = (
        classify_license(v, warn=False)
        for v in (static.license_name, installed.license_name)
    )
    return (
        first is not None
        and first.kind == "noassertion"
        and second is not None
        and second.kind != "noassertion"
    )


_FIELD_COMPARATORS: dict[str, Callable[[str, str], bool]] = {
    "version": is_same_version,
    "license_name": _license_equal,
    "requires_python": _requires_python_equal,
}


def _reconcile_conflict_checked_field(
    merged: ProjectMetadata,
    static: ProjectMetadata,
    installed: ProjectMetadata,
    field_name: str,
    warn_subject: str,
    *,
    quiet: bool,
) -> None:
    """Reconcile one of :data:`_CONFLICT_CHECKED_FIELDS` in place on *merged*.

    *warn_subject* is the pre-formatted ``"<project_dir>: installed
    metadata (<label>)"`` prefix for the disagreement ``WARNING:`` --
    precomputed once by :func:`reconcile_installed_metadata` rather than
    passed as two separate parameters, to stay within this repo's
    max-args ratchet.
    """
    provenance_key = provenance_key_for(field_name)
    installed_declared = field_declared(installed.provenance, provenance_key)
    if not installed_declared:
        return
    static_declared = field_declared(static.provenance, provenance_key)
    installed_value = getattr(installed, field_name)
    if not static_declared:
        setattr(merged, field_name, installed_value)
        merged.provenance[provenance_key] = installed.provenance[provenance_key]
        return

    static_value = getattr(static, field_name)
    # Either side can be None even though its own *_declared is True: both
    # this module's own parser and every static producer collapse an
    # explicitly-declared-empty source value to None (`str(x) if x else
    # None` -- `requires-python = ""`, PEP 621's "no constraint" convention
    # matching Poetry's `python = "*"`; likewise an empty/undetected
    # `license`). None is not a valid comparator input -- SpecifierSet(None)
    # raises instead of comparing -- so compare against the empty string
    # it's semantically equivalent to. The real (possibly-None) values are still what's
    # logged; only the comparator call and the recorded candidates'
    # ``value`` (typed ``str``, never ``None``) use the normalized form.
    comparable_static_value = static_value if static_value is not None else ""
    comparable_installed_value = installed_value if installed_value is not None else ""
    comparator = _FIELD_COMPARATORS[field_name]
    if comparator(comparable_static_value, comparable_installed_value):
        if field_name == "license_name" and _weak_static_licence(static, installed):
            merged.license_name = installed.license_name
            merged.provenance[provenance_key] = installed.provenance[provenance_key]
        return

    static_source = static.provenance[provenance_key]
    installed_source = installed.provenance[provenance_key]
    candidates: list[ConflictCandidate] = [
        {"value": comparable_static_value, "role": "declared", "source": static_source},
        {
            "value": comparable_installed_value,
            "role": "declared",
            "source": installed_source,
        },
    ]
    # Keyed by provenance_key, not field_name, so license_name's conflict
    # lands under "license" -- matching deps_license.py's own declared-
    # vs-concluded conflict field label for the same underlying concept,
    # rather than a second, inconsistent "license_name" label for what a
    # consumer would otherwise read as two different fields.
    merged.field_conflicts[provenance_key] = candidates
    if not quiet:
        log.warning(
            "%s disagrees on %s (declared %r, installed %r) -- keeping declared",
            warn_subject,
            provenance_key,
            static_value,
            installed_value,
        )


def _reconcile_gap_fill_field(
    merged: ProjectMetadata,
    static: ProjectMetadata,
    installed: ProjectMetadata,
    field_name: str,
) -> None:
    """Reconcile one of :data:`_GAP_FILL_ONLY_FIELDS` in place on *merged*."""
    provenance_key = provenance_key_for(field_name)
    if field_declared(static.provenance, provenance_key):
        return
    if not field_declared(installed.provenance, provenance_key):
        return
    value = getattr(installed, field_name)
    # keywords/urls are container-valued (list/dict) -- copy before handing
    # to merged, never alias *installed*'s own object directly. installed
    # is a throwaway ProjectMetadata discarded right after this call today,
    # so this is dormant, not a live bug -- but it's the same aliasing
    # hazard replace_with_fresh_containers() exists to close everywhere
    # else, and a future caller that retains *installed* (e.g. to log or
    # compare it afterwards) must not have merged's later mutations leak
    # back into it.
    if isinstance(value, (dict, list)):
        value = value.copy()
    setattr(merged, field_name, value)
    merged.provenance[provenance_key] = installed.provenance[provenance_key]


def reconcile_installed_metadata(
    static: ProjectMetadata,
    installed: ProjectMetadata,
    installed_label: str,
    project_dir: Path,
    *,
    quiet: bool = False,
) -> ProjectMetadata:
    """Fold *installed* (parsed from an in-tree ``.egg-info``/``.dist-info``)
    into *static* (``pyproject.toml``/``setup.cfg``/``setup.py``). *static*
    stays authoritative on any genuine disagreement; *installed* only fills
    gaps *static* left undeclared. A real disagreement is recorded in the
    result's ``field_conflicts`` and logged as a ``WARNING:``, never
    silently substituted.

    *project_dir* identifies the project in the ``WARNING:`` line (it is
    not part of the reconciliation logic itself) -- it is not literally
    part of the plan's own reconciliation pseudocode, but the plan's
    specified wording (``WARNING: %s: installed metadata ...``) needs a
    project label to fill that first ``%s``, so this signature adds it as
    an explicit parameter rather than reaching for a global.

    Only :data:`_CONFLICT_CHECKED_FIELDS` and :data:`_GAP_FILL_ONLY_FIELDS`
    participate -- iterated in :func:`dataclasses.fields`'s stable
    declaration order (never a ``set``'s iteration order, which is not
    guaranteed stable across processes) so the result -- including
    ``field_conflicts`` insertion order -- is deterministic. Every other
    field (``name``, ``provenance``, ``files``, ``locked_dependencies``,
    ``locked_dependency_hashes``, ``authors``, ``dependencies``,
    ``readme``, ``field_conflicts`` itself) is left untouched: a
    newly-added :class:`ProjectMetadata` field must not silently start
    participating here with no comparator/provenance thought through
    for it.
    """
    # replace_with_fresh_containers() (never a bare dataclasses.replace(),
    # which would alias every container field -- including provenance and
    # field_conflicts -- to *static*'s own object) gives every dict/list
    # field a fresh shallow copy up front, since this function writes into
    # both `merged.provenance[key] = ...` and
    # `merged.field_conflicts[field] = ...` below and neither write may
    # leak back into the caller's own *static* object (see
    # working-docs/design/installed-dist-info-source.md).
    merged = static.replace_with_fresh_containers()
    warn_subject = f"{project_dir}: installed metadata ({installed_label})"
    for f in dataclasses.fields(ProjectMetadata):
        if f.name in _CONFLICT_CHECKED_FIELDS:
            _reconcile_conflict_checked_field(
                merged, static, installed, f.name, warn_subject, quiet=quiet
            )
        elif f.name in _GAP_FILL_ONLY_FIELDS:
            _reconcile_gap_fill_field(merged, static, installed, f.name)
    return merged
