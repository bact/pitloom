# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Locked (e.g. ``poetry.lock``-resolved) dependency handling for
:func:`pitloom.assemble.spdx3.document.build` -- deduplication, conflict
detection, the exact-locked-version map, and the combined PyPI release-info
prefetch. Split out of :mod:`pitloom.assemble.spdx3.document` to keep that
module under this repo's file-size soft limit; every name here is
re-exported from there, so existing imports of these names from
``pitloom.assemble.spdx3.document`` keep working.

See also: :mod:`pitloom.extract._lock_common` for the shared
canonical-name-grouping and version-equality helpers this module builds on.
"""

from __future__ import annotations

from typing import Any

from packaging.utils import canonicalize_name

from pitloom.assemble.spdx3.deps import _parse_dep_name, _resolve_version
from pitloom.assemble.spdx3.deps_installed import _extract_exact_pin
from pitloom.assemble.spdx3.deps_pypi import _prefetch_pypi_release_infos
from pitloom.core.project import ProjectMetadata
from pitloom.extract._lock_common import (
    _group_by_canonical_name,
    is_same_version,
    warn_conflicting_versions,
)


def _dedup_and_locked_versions(
    locked_dependencies: list[str] | None,
) -> tuple[list[str], dict[str, str]]:
    """Collapse *locked_dependencies* to one entry per PEP 503-canonicalized
    name among its exact-pinned entries (preserving order), and map each
    surviving canonical name to its pinned version -- computed together so
    :func:`_extract_exact_pin` parses each entry's pin only once.

    A canonical name whose *pinned* entries disagree on PEP 440 version is
    a genuine conflict (e.g. two lock formats layered by hand into the
    same ``ProjectMetadata``, or a future extractor that forgets to
    dedupe before returning) -- warned via :func:`warn_conflicting_versions`
    and excluded entirely, the same "skip the ambiguous name, don't guess"
    policy every extractor already applies to its own duplicate entries.
    Neither of this function's callers (:func:`_extract_locked_version_map`,
    :func:`_locked_transitive_only_dependencies`) could otherwise safely
    pick a winner between two conflicting entries on its own -- and picking
    different winners in each would silently emit the ambiguous package
    twice, once per winner, into the assembled SPDX graph.

    An entry with no exact pin at all (unpinned, ranged, or unparseable --
    every shipped extractor always emits an exact pin, but this guards a
    future one that doesn't) has no version to compare and passes through
    the returned list unfiltered, but contributes nothing to the version
    map: only :func:`_extract_locked_version_map` needs a pin, and it
    already discards a pin-less entry on its own via
    :func:`_extract_exact_pin`'s own ``None`` return. A passthrough entry
    is dropped from the list, though, when its canonical name also has a
    pinned entry elsewhere in *locked_dependencies* -- the pin is strictly
    more informative, and keeping both would double-emit the same package
    (one from the pinned entry, one from the passthrough one).
    """
    pinned_triples: list[tuple[str, str, str]] = []
    for dep in locked_dependencies or []:
        _req, pinned = _extract_exact_pin(dep)
        if pinned is not None:
            pinned_triples.append((_parse_dep_name(dep), dep, pinned))
    by_canonical = _group_by_canonical_name(pinned_triples)

    excluded: set[str] = set()
    resolved: dict[str, str] = {}
    resolved_versions: dict[str, str] = {}
    for group_canon, group in by_canonical.items():
        name, dep, version = group[0]
        conflicting_versions = {
            v for _, _, v in group if not is_same_version(v, version)
        }
        if conflicting_versions:
            warn_conflicting_versions(
                "locked dependencies", name, {v for _, _, v in group}
            )
            excluded.add(group_canon)
        else:
            resolved[group_canon] = dep
            resolved_versions[group_canon] = version

    deduplicated: list[str] = []
    emitted: set[str] = set()
    for dep in locked_dependencies or []:
        canon = canonicalize_name(_parse_dep_name(dep))
        if canon in excluded:
            continue
        if canon in resolved:
            if canon in emitted:
                continue
            emitted.add(canon)
            deduplicated.append(resolved[canon])
            continue
        # No pinned entry anywhere for this canonical name -- pass
        # through as-is, at its own original position.
        deduplicated.append(dep)
    return deduplicated, resolved_versions


def _deduplicated_locked_dependencies(
    locked_dependencies: list[str] | None,
) -> list[str]:
    """Collapse *locked_dependencies* to one entry per PEP 503-canonicalized
    name among its exact-pinned entries, preserving order -- see
    :func:`_dedup_and_locked_versions`, which this delegates to.
    """
    return _dedup_and_locked_versions(locked_dependencies)[0]


def _locked_transitive_only_dependencies(
    metadata: ProjectMetadata,
    *,
    deduplicated_locked: list[str] | None = None,
) -> list[str]:
    """Return *metadata*'s locked (e.g. ``poetry.lock``-resolved) dependencies
    that aren't already a direct dependency, so a package declared both
    directly and in the lock gets one ``dependsOn`` edge, not two.

    Names are compared PEP 503-canonicalized (lowercased, ``-``/``_``/``.``
    folded to ``-``) since a lock file's resolved package names are
    normalized while the author's ``pyproject.toml`` spelling (e.g.
    ``"Django"``) may not be -- comparing raw, unnormalized names would
    treat those as different packages and double-emit the edge this
    function exists to avoid. See ``_try_read_poetry()`` in
    ``pitloom.extract._pyproject`` for why this is source-stage-only.

    *deduplicated_locked*, when given, is used as-is instead of calling
    :func:`_deduplicated_locked_dependencies` again -- :func:`build` computes
    both it and the locked version map once via :func:`_dedup_and_locked_versions`
    so a genuine name/version conflict in ``locked_dependencies`` only logs
    :func:`warn_conflicting_versions`'s warning once per document, not once
    per caller.
    """
    direct_names = {
        canonicalize_name(_parse_dep_name(dep)) for dep in metadata.dependencies
    }
    locked = (
        deduplicated_locked
        if deduplicated_locked is not None
        else _deduplicated_locked_dependencies(metadata.locked_dependencies)
    )
    return [
        dep
        for dep in locked
        if canonicalize_name(_parse_dep_name(dep)) not in direct_names
    ]


# pylint: disable=useless-return
def _locked_dependencies_completeness(metadata: ProjectMetadata) -> str | None:
    """Return the `RelationshipCompleteness` value for the locked-only
    `dependsOn` edges :func:`_locked_transitive_only_dependencies`
    produces, or `None` to leave it unset.

    Conservatively returns ``None`` (unset): while a resolver lock represents
    a resolved dependency graph, extractors may legitimately omit
    unrepresentable dependencies (such as VCS/path sources, non-default groups,
    or marker-ambiguous variants). Asserting ``complete`` would overstate
    completeness for partial closures, so leaving it unset makes no
    unverifiable claim.
    """
    del metadata
    return None


def _extract_locked_version_map(
    locked_dependencies: list[str] | None,
) -> dict[str, str]:
    """Map canonical package names to their exact locked version string.

    Enables direct dependencies declared as ranges (e.g. ``requests>=2.0``)
    to resolve to their authoritative locked version rather than falling back
    to introspecting Pitloom's host environment. See
    :func:`_dedup_and_locked_versions`, which this delegates to -- :func:`build`
    calls that shared helper directly instead of this function, so a
    dependency's pin is parsed once per document, not once per caller.
    """
    return _dedup_and_locked_versions(locked_dependencies)[1]


def _prefetch_combined_release_info(
    dependencies: list[str],
    transitive_only: list[str],
    locked_versions: dict[str, str] | None = None,
) -> dict[tuple[str, str | None], dict[str, Any] | None]:
    """Prefetch PyPI release info once for every dependency a document will
    emit -- direct and lock-resolved-transitive alike -- so the result can
    be shared across both :func:`add_dependencies` calls in :func:`build`
    instead of each call paying for its own network round-trip."""
    name_version_pairs = []
    for dep in dependencies:
        dep_name = _parse_dep_name(dep)
        locked_ver = (
            locked_versions.get(canonicalize_name(dep_name))
            if locked_versions is not None
            else None
        )
        dep_version, _version_note = _resolve_version(
            dep_name, dep, locked_version=locked_ver, warn=False
        )
        name_version_pairs.append((dep_name, dep_version))
    for dep in transitive_only:
        dep_name = _parse_dep_name(dep)
        dep_version, _version_note = _resolve_version(dep_name, dep, warn=False)
        name_version_pairs.append((dep_name, dep_version))

    return _prefetch_pypi_release_infos(name_version_pairs)
