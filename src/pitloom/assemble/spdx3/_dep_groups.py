# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A document's declared dependency strings, resolved and grouped into the
packages they become, once per list: what the registry pre-resolution looks
up and what :func:`~pitloom.assemble.spdx3.deps.add_dependencies` builds.

Resolved once, so a version conflict or a marker that cannot be read warns
once, and the lookup and the package share one identity rule: the PEP 503
name and the PEP 440 version
(:func:`~pitloom.extract.lock.common.is_same_version`), the
:func:`~pitloom.id_registry.package_key` of each group.

See also: :mod:`pitloom.assemble.spdx3._package_ids` (the lookups),
:class:`~pitloom.assemble.spdx3._dep_scope.DependencyScopes` (edge kinds).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

from packaging.utils import canonicalize_name

from pitloom.assemble.spdx3._dep_scope import DependencyScopes
from pitloom.assemble.spdx3.deps_installed import (
    _DEFAULT_LOCKED_PROVENANCE,
    _resolve_dependency_with_conflict,
)
from pitloom.assemble.spdx3.provenance import ConflictCandidate
from pitloom.core.project import ProjectMetadata
from pitloom.extract.lock.common import is_same_version
from pitloom.id_registry import package_key

__all__ = [
    "Declared",
    "DependencyGroup",
    "DependencyGroups",
    "ProjectDependencies",
    "group_dependencies",
    "project_dependencies",
]


@dataclass(frozen=True)
class Declared:
    """One declared dependency string, resolved: its name, its version, the
    note on where the version came from and its G2 conflict candidates."""

    dep: str
    name: str
    version: str
    note: str | None
    conflict: list[ConflictCandidate] | None


@dataclass(frozen=True)
class DependencyGroup:
    """One package: the strings of one PEP 503 name whose versions are one
    PEP 440 release, in declared order; its version is the first's."""

    canonical_name: str
    version: str
    declared: tuple[Declared, ...]

    @property
    def name(self) -> str:
        """The name the package shows: its first string's."""
        return self.declared[0].name

    @property
    def key(self) -> str:
        """The package's registry key (:func:`~pitloom.id_registry.package_key`)."""
        return package_key(self.canonical_name, self.version)


@dataclass(frozen=True)
class DependencyGroups:
    """One dependency list, resolved: its edge kinds (*scopes*), every
    string that is not a self-reference (*resolved*, in order) and the
    packages they make (*groups*, by first appearance)."""

    scopes: DependencyScopes
    resolved: tuple[Declared, ...]
    groups: tuple[DependencyGroup, ...]


def group_dependencies(
    dependencies: Sequence[str],
    project_name: str,
    *,
    locked_versions: dict[str, str] | None = None,
    dep_provenance: str = "Unknown source",
    locked_provenance: str | None = None,
) -> DependencyGroups:
    """Resolve *dependencies* once
    (:func:`~pitloom.assemble.spdx3.deps_installed._resolve_dependency_with_conflict`,
    which logs its ``WARNING:`` lines) and group them by PEP 503 name and
    PEP 440 version; a string naming *project_name* itself adds no package
    (:class:`~pitloom.assemble.spdx3._dep_scope.DependencyScopes`)."""
    scopes = DependencyScopes(dependencies, project_name)
    resolved = tuple(
        Declared(
            *_resolve_dependency_with_conflict(
                dep, locked_versions, dep_provenance, locked_provenance
            )
        )
        for dep in dependencies
        if not scopes.is_self_reference(dep)
    )
    grouped: dict[tuple[str, str], list[Declared]] = {}
    for declared in resolved:
        canonical = canonicalize_name(declared.name)
        found = next(
            (
                (name, version)
                for name, version in grouped
                if name == canonical and is_same_version(version, declared.version)
            ),
            (canonical, declared.version),
        )
        grouped.setdefault(found, []).append(declared)
    groups = tuple(
        DependencyGroup(name, version, tuple(members))
        for (name, version), members in grouped.items()
    )
    return DependencyGroups(scopes, resolved, groups)


class ProjectDependencies(NamedTuple):
    """A project's dependency lists, resolved once: the declared ones
    (*direct*), the lock-resolved ones no declared string names
    (*transitive*), and the provenance of the lock file's versions."""

    direct: DependencyGroups
    transitive: DependencyGroups
    locked_provenance: str


def project_dependencies(
    metadata: ProjectMetadata,
    transitive_only: Sequence[str],
    locked_versions: dict[str, str],
) -> ProjectDependencies:
    """*metadata*'s declared dependencies, a range pinned by
    *locked_versions*, and its lock-resolved *transitive_only* ones, each
    list :func:`group_dependencies`'d once."""
    locked_provenance = metadata.provenance.get(
        "locked_dependencies", _DEFAULT_LOCKED_PROVENANCE
    )
    direct = group_dependencies(
        metadata.dependencies,
        metadata.name,
        locked_versions=locked_versions,
        dep_provenance=metadata.provenance.get("dependencies", "Unknown source"),
        locked_provenance=locked_provenance,
    )
    transitive = group_dependencies(
        transitive_only, metadata.name, dep_provenance=locked_provenance
    )
    return ProjectDependencies(direct, transitive, locked_provenance)
