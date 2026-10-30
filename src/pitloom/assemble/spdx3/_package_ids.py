# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Registry pre-resolution for ``software_Package`` elements: the project's
own main package, its dependencies and its phantom dependencies.

Every package resolves through one lookup shape,
:func:`resolve_package_id` (claimant label, name and version, registry type
:data:`~pitloom.id_registry.PACKAGE_TYPE`): the key is the PEP 503 name and
the PEP 440 version the package states
(:func:`~pitloom.id_registry.package_key`), so a declared, an installed and
a bundled package of one name and release reach the same registry key --
the key ``IdRegistry`` harvest writes back for each of them -- and two
releases reach two keys. A package that states no version has a bare key,
which no versioned lookup hits.

A dependency named like the project adds no package (see
:class:`~pitloom.assemble.spdx3._dep_scope.DependencyScopes`). A non-PEP
508 dependency string whose fallback name is the project's, or a phantom
dependency named like the project or a dependency, never looks up: it
mints a fresh id, silently, and is recorded in
:attr:`~pitloom.export.spdx3_json.Spdx3JsonExporter.registry_non_readers`.
Run auto-harvest leaves it out, so the package owning the name is
written. A key held by several packages that do look up (two phantoms of
one name and version) is not written (see
:func:`pitloom.id_registry._ambiguous._ambiguous_keys`); an existing
pin for it goes to the first claimant, in the order main package,
dependencies, phantom dependencies.

Resolution runs before :func:`~pitloom.core.models.reserve_spdx_ids` (see
:func:`pitloom.assemble.spdx3.document.build`): an id looked up after
reservation could collide with one already minted.

See also: :mod:`pitloom.assemble.spdx3._document_deployed` (the
deployed-environment caller), :mod:`pitloom.assemble.spdx3._dep_groups`
(the dependency packages, resolved once), :mod:`pitloom.id_registry._session`
for the claim semantics.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from packaging.utils import canonicalize_name

from pitloom.assemble.spdx3._dep_groups import DependencyGroup
from pitloom.core.document import DocumentModel
from pitloom.id_registry import IdRegistrySession, warn_claim_collision

__all__ = [
    "DEPENDENCY_LABEL",
    "DependencyIdHits",
    "ProjectPackageIds",
    "dependency_package_id",
    "package_claimant",
    "resolve_package_id",
    "resolve_project_package_ids",
]

#: Claimant labels: what a ``WARNING: ID registry: ...`` names.
MAIN_PACKAGE_LABEL = "main package"
DEPENDENCY_LABEL = "dependency"
PHANTOM_LABEL = "phantom dependency"


def package_claimant(label: str, name: str, version: str | None) -> str:
    """What a claim ``WARNING:`` names a package by: its *label*, *name* and
    *version* (``unknown`` when it states none)."""
    return f"{label} {name} {version or 'unknown'}"


def resolve_package_id(
    session: IdRegistrySession, label: str, name: str, version: str | None
) -> str | None:
    """Claim the registry id for the package *name* at *version*, or ``None``
    (:meth:`~pitloom.id_registry.IdRegistrySession.lookup_package`: the key
    is the PEP 503 name and the PEP 440 version, bare for no version).

    *name* and *version* are passed verbatim; the registry normalises them.
    """
    return session.lookup_package(package_claimant(label, name, version), name, version)


# pylint: disable-next=too-few-public-methods
class DependencyIdHits:
    """Registry hits for dependency packages, keyed by package key (PEP 503
    name and PEP 440 version, :attr:`DependencyGroup.key`).

    One registry key backs one id, but a dependency list can hold two
    distinct packages under one key: an NFC and an NFD spelling of one
    unparsable version, which
    :func:`~pitloom.extract.lock.common.is_same_version` compares as text
    and the key as NFC. Each hit is therefore handed
    out once; a later package with the same key gets a fresh id and the
    standard claim ``WARNING:``. Harvest never writes such a key, so only a
    pinned entry produces a hit.
    """

    def __init__(
        self,
        hits: dict[str, str] | None = None,
        not_looked_up: frozenset[str] = frozenset(),
    ) -> None:
        self._hits = hits or {}
        self._not_looked_up = not_looked_up
        #: package key -> claimant label of the package that took its hit.
        self._taken: dict[str, str] = {}

    def looked_up(self, canonical_name: str) -> bool:
        """Whether a dependency named *canonical_name* looked the registry
        up; ``False`` when the main package owns the name."""
        return canonical_name not in self._not_looked_up

    def take(self, key: str, claimant: str) -> str | None:
        """Return the hit for the package *key*, once; ``None`` otherwise."""
        spdx_id = self._hits.get(key)
        if spdx_id is None:
            return None
        first = self._taken.get(key)
        if first is not None:
            warn_claim_collision(spdx_id, first, claimant)
            return None
        self._taken[key] = claimant
        return spdx_id


def dependency_package_id(
    hits: DependencyIdHits | None,
    group: DependencyGroup,
    mint: Callable[[], str],
    non_readers: set[str],
) -> str:
    """The id of the dependency package *group*: its registry hit (see
    :meth:`DependencyIdHits.take`), else ``mint()``.

    The id of a package whose name never looked up is added to
    *non_readers*, so run auto-harvest leaves it out.
    """
    if hits is None:
        return mint()
    claimant = package_claimant(DEPENDENCY_LABEL, group.name, group.version)
    spdx_id = hits.take(group.key, claimant) or mint()
    if not hits.looked_up(group.canonical_name):
        non_readers.add(spdx_id)
    return spdx_id


@dataclass
class ProjectPackageIds:
    """Every ``software_Package`` hit pre-resolved before
    :func:`~pitloom.assemble.spdx3.document.build` reserves its ids."""

    main: str | None
    dependencies: DependencyIdHits
    #: One entry per phantom dependency, in ``doc.phantom_dependencies`` order.
    phantom: list[str | None]
    #: Indices into :attr:`phantom` of the phantoms that never looked up.
    phantom_not_looked_up: frozenset[int]


def _resolve_dependency_hits(
    session: IdRegistrySession, groups: Iterable[DependencyGroup], seen: set[str]
) -> DependencyIdHits:
    """Resolve the dependency packages *groups* once per package key, in the
    given (deterministic) order.

    *seen* holds the canonical names already claimed and is extended
    with each dependency's own. It starts with the project's name: a
    dependency named like the project itself (a self-referencing extra,
    ``demo[x]; extra == 'all'``) adds no package and is not grouped (see
    :class:`~pitloom.assemble.spdx3._dep_scope.DependencyScopes`). A
    non-PEP 508 string whose fallback name is the project's is grouped,
    but the main package owns that name's registry id: that dependency
    mints a fresh id and is a non-reader (:meth:`DependencyIdHits.looked_up`).
    A later package of an already-looked-up key shares that key's lookup
    instead (:meth:`DependencyIdHits.take`).
    """
    not_looked_up = frozenset(seen)
    hits: dict[str, str] = {}
    looked: set[str] = set()
    for group in groups:
        if group.canonical_name in not_looked_up:
            continue
        seen.add(group.canonical_name)
        if group.key in looked:
            continue
        looked.add(group.key)
        spdx_id = resolve_package_id(
            session, DEPENDENCY_LABEL, group.name, group.version
        )
        if spdx_id is not None:
            hits[group.key] = spdx_id
    return DependencyIdHits(hits, not_looked_up)


def _resolve_phantom_ids(
    session: IdRegistrySession,
    phantoms: Iterable[tuple[str, str | None]],
    seen: set[str],
) -> tuple[list[str | None], frozenset[int]]:
    """One registry hit (or ``None``) per phantom dependency (name and
    version), and the indices of the phantoms that never looked up.

    A phantom named like the project or a dependency (*seen*) never looks
    up: its name already belongs to another package of the document. Two
    phantoms of one name and version both look up, so the second gets the
    claim ``WARNING:``; two versions are two keys.
    """
    hits: list[str | None] = []
    not_looked_up: set[int] = set()
    for index, (name, version) in enumerate(phantoms):
        if canonicalize_name(name) in seen:
            hits.append(None)
            not_looked_up.add(index)
        else:
            hits.append(resolve_package_id(session, PHANTOM_LABEL, name, version))
    return hits, frozenset(not_looked_up)


def resolve_project_package_ids(
    doc: DocumentModel,
    dependencies: Iterable[DependencyGroup],
    session: IdRegistrySession,
) -> ProjectPackageIds:
    """Claim registry ids for the main package (its own version), then its
    declared and lock-resolved dependency packages (*dependencies*, the
    groups :func:`~pitloom.assemble.spdx3.deps.add_dependencies` builds, in
    that order), then its phantom dependencies (each its version) -- that
    order decides who wins a shared registry id."""
    main = (
        resolve_package_id(
            session, MAIN_PACKAGE_LABEL, doc.project.name, doc.project.version
        )
        if doc.identity_known
        else None
    )
    seen: set[str] = {canonicalize_name(doc.project.name)}
    dependency_hits = _resolve_dependency_hits(session, dependencies, seen)
    phantom, phantom_not_looked_up = _resolve_phantom_ids(
        session, [(dep.name, dep.version) for dep in doc.phantom_dependencies], seen
    )
    return ProjectPackageIds(main, dependency_hits, phantom, phantom_not_looked_up)
