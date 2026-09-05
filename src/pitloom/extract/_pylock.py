# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for resolved dependencies from a PEP 751 ``pylock.toml``.

See also: :mod:`pitloom.extract._poetry_lock` (the ``poetry.lock``
extractor this module mirrors in shape -- same source-stage-only scoping,
same ``name==version`` output, same "no silent deviations" warning
policy) and :mod:`pitloom.extract._locked_dependencies` (the cascade
module that calls this extractor and overlays its output onto
``ProjectMetadata.locked_dependencies``, in priority order against every
other lock format).

``pylock.toml`` (PEP 751) is the build-backend-agnostic Python
interoperability standard for recording a fully resolved dependency set --
produced by tools like ``uv``, ``pdm``, and ``poetry`` (via ``export``),
consumed only by installers, never by a PEP 517 build backend. That makes
it a **source-stage-only** artifact, the same class as ``poetry.lock``:
appropriate for ``loom project``/``loom generate`` (a static file sitting
next to ``pyproject.toml``), never for ``loom wheel``/``embed-wheel`` (the
real wheel's own metadata is ground truth and never consults a lock) or
``loom env`` (live introspection of what's actually installed is strictly
more authoritative than a lock that may be stale relative to it).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from packaging.markers import InvalidMarker, Marker

from pitloom.extract._lock_common import (
    find_first_present_key,
    is_usable_version,
    load_lock_toml,
    warn_malformed_entry_not_table,
    warn_missing_name,
    warn_missing_version,
    warn_non_registry_source,
    warn_top_level_key_wrong_type,
)

log = logging.getLogger(__name__)

__all__ = ["extract_pylock_dependencies"]

_NON_REGISTRY_SOURCE_KEYS = ("vcs", "directory", "archive")

#: PEP 751 pseudo-environment marker variables naming which
#: extras/dependency-groups are active for a given consumption -- the
#: only two this extractor's marker handling understands (see
#: :func:`_group_marker_excludes`). Every other PEP 508 marker variable
#: (``python_version``, ``sys_platform``, etc.) is deliberately left
#: unevaluated, the same "no marker evaluation" limitation this format
#: shares with every sibling lock format -- evaluating those against
#: Pitloom's own running interpreter/platform would make the SBOM's
#: contents depend on which machine generated it, violating this repo's
#: determinism requirement.
_GROUP_MARKER_VARIABLES = frozenset({"extras", "dependency_groups"})

#: The highest ``lock-version`` this extractor understands, as
#: ``(major, minor)``. PEP 751 defines only ``"1.0"`` to date. A
#: consumer must reject a different *major* version outright (a future
#: 2.x could change the schema incompatibly) but may still read a newer
#: *minor* version within the same major (additive, backward-compatible
#: fields only, per PEP 751) -- with a warning that some of its content
#: may go unrecognized.
_SUPPORTED_LOCK_FILE_VERSION = (1, 0)


def _parse_lock_version(lock_version: str) -> tuple[int, int] | None:
    """Parse a ``lock-version`` string as ``(major, minor)``, or
    ``None`` if it isn't a plain ``major.minor`` pair of non-negative
    integers -- PEP 751's own grammar for this field, rejecting a value
    like ``"2"``, ``"1.0.0"``, or ``"garbage"`` that isn't shaped like a
    version at all."""
    parts = lock_version.split(".")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    return int(parts[0]), int(parts[1])


def extract_pylock_dependencies(project_dir: Path) -> list[str] | None:
    """Read ``pylock.toml`` next to ``pyproject.toml`` and return its
    resolved packages as exact-pin PEP 508 strings.

    Returns ``None`` when no ``pylock.toml`` is present, it can't be
    parsed, or its declared ``lock-version`` is unsupported -- this is
    optional enrichment, never a requirement, and ``None`` (as opposed
    to a valid-but-empty ``[]``) tells :mod:`pitloom.extract._locked_dependencies`'s
    cascade this source doesn't apply here, so a lower-priority source
    can still be tried, rather than a genuinely dependency-free lock
    file being confused with an absent/unusable one.

    Unlike ``poetry.lock``, PEP 751 has no ``groups``-style per-package
    membership *field*: a ``pylock.toml`` can bundle more than one
    dependency-group's packages in a single flattened ``[[packages]]``
    list, distinguished only by an optional per-package ``marker`` string
    referencing the pseudo-environment variables ``extras``/
    ``dependency_groups`` (e.g. ``"'dev' in dependency_groups"``). This
    extractor filters to the file's own declared ``default-groups`` (no
    extras) the same way ``poetry.lock``/``pdm.lock`` filter to their
    ``main``/``default`` group -- see :func:`_group_marker_excludes`.
    """
    lock_path = project_dir / "pylock.toml"
    data = load_lock_toml(lock_path)
    if data is None:
        return None

    raw_lock_version = data.get("lock-version")
    parsed_version = (
        _parse_lock_version(raw_lock_version)
        if isinstance(raw_lock_version, str)
        else None
    )
    if parsed_version is None:
        log.warning(
            "%s: missing or malformed top-level 'lock-version' key "
            "(%r, expected a 'major.minor' string) -- ignoring pylock.toml",
            lock_path,
            raw_lock_version,
        )
        return None
    major, minor = parsed_version
    supported_major, supported_minor = _SUPPORTED_LOCK_FILE_VERSION
    if major != supported_major:
        log.warning(
            "%s: 'lock-version' %r is major version %d, but this Pitloom "
            "release only understands major version %d -- ignoring "
            "pylock.toml",
            lock_path,
            raw_lock_version,
            major,
            supported_major,
        )
        return None
    if minor > supported_minor:
        log.warning(
            "%s: 'lock-version' %r is newer than the %d.%d schema this "
            "Pitloom release knows -- reading it anyway (PEP 751 minor "
            "versions are additive), but newer fields may be ignored",
            lock_path,
            raw_lock_version,
            supported_major,
            supported_minor,
        )

    packages = data.get("packages", [])
    if not isinstance(packages, list):
        warn_top_level_key_wrong_type(
            lock_path, "packages", packages, "a list", "pylock.toml"
        )
        return None

    environment = _default_group_environment(lock_path, data)
    dependencies: list[str] = []
    for pkg in packages:
        dep = _pinned_dep_for_package(pkg, environment)
        if dep is not None:
            dependencies.append(dep)
    return dependencies


def _default_group_environment(
    lock_path: Path, data: dict[str, Any]
) -> dict[str, frozenset[str]]:
    """Build the ``dependency_groups``/``extras`` pseudo-environment
    representing "no extras, only the file's own declared
    ``default-groups``" -- the same runtime-only scope
    ``poetry.lock``/``pdm.lock`` restrict to via their ``main``/
    ``default`` group filters. A missing or malformed ``default-groups``
    key is treated as ``[]`` (no default group at all) with a
    ``WARNING:``, rather than silently keeping every group active."""
    default_groups = data.get("default-groups", [])
    if not isinstance(default_groups, list) or not all(
        isinstance(g, str) for g in default_groups
    ):
        log.warning(
            "%s: top-level 'default-groups' key is %r, expected a list of "
            "strings -- treating as empty (no default dependency-group)",
            lock_path,
            default_groups,
        )
        default_groups = []
    return {"dependency_groups": frozenset(default_groups), "extras": frozenset()}


def _evaluate_group_leaf(
    node: tuple[Any, Any, Any], environment: dict[str, frozenset[str]]
) -> bool | None:
    """Evaluate one marker leaf ``(lhs, op, rhs)`` against *environment*,
    or ``None`` ("unknown") when it isn't an ``in``/``not in`` clause
    naming a ``extras``/``dependency_groups`` variable -- see
    :func:`_group_marker_excludes` for why every other PEP 508 marker
    variable is treated as unknown rather than really evaluated."""
    lhs, raw_op, rhs = node
    op = str(raw_op)
    if op not in ("in", "not in"):
        return None
    lhs_str, rhs_str = str(lhs), str(rhs)
    if rhs_str in _GROUP_MARKER_VARIABLES:
        variable, literal = rhs_str, lhs_str
    elif lhs_str in _GROUP_MARKER_VARIABLES:
        variable, literal = lhs_str, rhs_str
    else:
        return None
    member = literal in environment[variable]
    return member if op == "in" else not member


def _all3(values: list[bool | None]) -> bool | None:
    """3-valued ``all()``: ``False`` if any value is ``False``, else
    ``None`` if any value is ``None``, else ``True``."""
    if any(v is False for v in values):
        return False
    return None if any(v is None for v in values) else True


def _any3(values: list[bool | None]) -> bool | None:
    """3-valued ``any()``: ``True`` if any value is ``True``, else
    ``None`` if any value is ``None``, else ``False``."""
    if any(v is True for v in values):
        return True
    return None if any(v is None for v in values) else False


def _evaluate_group_node(
    node: Any, environment: dict[str, frozenset[str]]
) -> bool | None:
    """Recursively evaluate one node of a parsed
    ``packaging.markers.Marker``'s tree (a leaf tuple, or a list of
    nodes interleaved with ``"and"``/``"or"`` operator strings) using
    3-valued group/extras-only logic -- see :func:`_group_marker_excludes`.

    PEP 508 gives ``and`` higher precedence than ``or``, but
    ``Marker()._markers`` doesn't nest same-precedence-level terms to
    reflect that -- an unparenthesized ``A or B and C`` is one flat list
    ``[A, "or", B, "and", C]``, not ``[A, "or", [B, "and", C]]``. A plain
    left-to-right fold over that list would compute ``(A or B) and C``
    instead of the correct ``A or (B and C)``. Grouping every term at
    each ``"or"`` boundary into its own list -- mirroring
    ``packaging.markers._evaluate_markers()``'s own ``groups``
    algorithm, just with 3-valued ``all``/``any`` instead of Python's
    real ones -- restores that precedence regardless of how flat or
    nested the parsed tree is.
    """
    if isinstance(node, tuple):
        return _evaluate_group_leaf(node, environment)
    groups: list[list[bool | None]] = [[]]
    for item in node:
        if item == "or":
            groups.append([])
        elif item != "and":
            groups[-1].append(_evaluate_group_node(item, environment))
    return _any3([_all3(group) for group in groups])


def _group_marker_excludes(
    marker_str: str, environment: dict[str, frozenset[str]], name: str
) -> bool:
    """Return whether a package's PEP 751 ``marker`` string proves it's
    *not* part of the active ``dependency_groups``/``extras`` scope in
    *environment* -- ``True`` only when that's certain from the group/
    extras clauses alone.

    Uses 3-valued logic over the marker's parsed tree: a clause testing
    ``extras``/``dependency_groups`` membership evaluates to a concrete
    ``True``/``False`` against *environment*; every other PEP 508 marker
    variable (``python_version``, ``sys_platform``, etc.) evaluates to
    ``None`` ("unknown") rather than a real environment reading --
    evaluating those against Pitloom's own running interpreter/platform
    would make the result depend on which machine ran Pitloom, which
    this repo's "no marker evaluation" policy (shared by every sibling
    lock format) and its determinism requirement both rule out. A
    package is only excluded when the tree provably evaluates to
    ``False`` from the known group/extras clauses regardless of any
    unknown clause's real value; ``True``/``None`` both mean "include",
    the same marker-blind default every other format already applies to
    non-group markers.
    """
    try:
        # pylint: disable=protected-access
        tree = Marker(marker_str)._markers  # noqa: SLF001
    except InvalidMarker as exc:
        log.warning(
            "Skipping pylock.toml entry %r's 'marker' %r: %s -- treating "
            "as an unconstrained (included) marker",
            name,
            marker_str,
            exc,
        )
        return False
    return _evaluate_group_node(tree, environment) is False


def _pinned_dep_for_package(
    pkg: object, environment: dict[str, frozenset[str]]
) -> str | None:
    """Return ``name==version`` for one ``[[packages]]`` table entry, or
    ``None`` when it's malformed or sourced from a location that
    ``name==version`` can't represent.

    A package pinned via ``vcs``, ``directory``, or ``archive`` (PEP 751's
    non-registry source tables) has no meaningful PyPI version pin, so
    including it here would misrepresent it as an ordinary published
    release (wrong PURL, bogus PyPI enrichment lookup) -- mirrors
    ``poetry.lock``'s equivalent ``directory``/``file``/``git``/``url``
    skip in :func:`pitloom.extract._poetry_lock._pinned_dep_for_package`.
    A registry-resolved package sourced via ``sdist``/``wheels`` (or with
    no source table at all) is always included when it has a version.
    """
    if not isinstance(pkg, dict):
        warn_malformed_entry_not_table("pylock.toml", "[[packages]]", pkg)
        return None
    name = pkg.get("name")
    if not isinstance(name, str) or not name:
        warn_missing_name("Skipping malformed pylock.toml [[packages]] entry", name)
        return None
    version = pkg.get("version")
    if not is_usable_version(version):
        warn_missing_version("pylock.toml", name)
        return None
    marker = pkg.get("marker")
    if isinstance(marker, str) and _group_marker_excludes(marker, environment, name):
        return None
    non_registry_source = find_first_present_key(pkg, _NON_REGISTRY_SOURCE_KEYS)
    if non_registry_source is not None:
        warn_non_registry_source("pylock.toml", name, non_registry_source)
        return None
    return f"{name}=={version}"
