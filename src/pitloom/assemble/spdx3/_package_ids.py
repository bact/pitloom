# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Registry pre-resolution for ``software_Package`` elements: the project's
own main package, its dependencies and its phantom dependencies.

Every package resolves through one lookup shape,
:func:`resolve_package_id` (claimant label + raw name, registry type
:data:`~pitloom.id_registry.PACKAGE_ENTITY_TYPE`), so a declared, an
installed and a bundled package with the same PEP 503 name reach the same
registry key -- the key ``IdRegistry`` harvest writes back for each of
them.

A name held by several packages of one document is never harvested (see
:func:`pitloom.id_registry._ambiguous._ambiguous_entity_keys`); an existing
pin for it goes to the first claimant, in the order main package,
dependencies, phantom dependencies. A dependency named like the project,
or a phantom dependency named like the project or a dependency, never looks
up: it mints a fresh id, silently.

Resolution runs before :func:`~pitloom.core.models.reserve_spdx_ids` (see
:func:`pitloom.assemble.spdx3.document.build`): an id looked up after
reservation could collide with one already minted.

See also: :mod:`pitloom.assemble.spdx3._document_deployed` (the
deployed-environment caller), :mod:`pitloom.id_registry._session` for the
claim semantics.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from packaging.utils import canonicalize_name

from pitloom.assemble.spdx3.deps_installed import _parse_dep_name
from pitloom.core.document import DocumentModel
from pitloom.id_registry import (
    PACKAGE_ENTITY_TYPE,
    IdRegistrySession,
    warn_claim_collision,
)

__all__ = [
    "DEPENDENCY_LABEL",
    "DependencyIdHits",
    "ProjectPackageIds",
    "resolve_package_id",
    "resolve_project_package_ids",
]

#: Claimant labels: what a ``WARNING: ID registry: ...`` names.
MAIN_PACKAGE_LABEL = "main package"
DEPENDENCY_LABEL = "dependency"
PHANTOM_LABEL = "phantom dependency"


def resolve_package_id(session: IdRegistrySession, label: str, name: str) -> str | None:
    """Claim the registry id for the package *name*, or ``None``.

    *name* is passed verbatim; the registry PEP 503-canonicalizes it.
    """
    return session.entity_id(f"{label} {name}", [name], PACKAGE_ENTITY_TYPE)


# pylint: disable-next=too-few-public-methods
class DependencyIdHits:
    """Registry hits for dependency packages, keyed by PEP 503 name.

    One registry key backs one id, but a dependency list can hold two
    distinct packages under one name (two different pinned versions).
    Each hit is therefore handed out once; a later package with the same
    name gets a fresh id and the standard claim ``WARNING:``. Harvest
    never writes such a name, so only a pinned entry produces a hit.
    """

    def __init__(self, hits: dict[str, str] | None = None) -> None:
        self._hits = hits or {}
        #: canonical name -> claimant label of the package that took its hit.
        self._taken: dict[str, str] = {}

    def take(self, canonical_name: str, claimant: str) -> str | None:
        """Return the hit for *canonical_name*, once; ``None`` otherwise."""
        spdx_id = self._hits.get(canonical_name)
        if spdx_id is None:
            return None
        first = self._taken.get(canonical_name)
        if first is not None:
            warn_claim_collision(spdx_id, first, claimant)
            return None
        self._taken[canonical_name] = claimant
        return spdx_id


@dataclass
class ProjectPackageIds:
    """Every ``software_Package`` hit :func:`build` pre-resolved."""

    main: str | None
    dependencies: DependencyIdHits
    #: One entry per phantom dependency, in ``doc.phantom_dependencies`` order.
    phantom: list[str | None]


def _resolve_dependency_hits(
    session: IdRegistrySession, dependencies: Iterable[str], seen: set[str]
) -> DependencyIdHits:
    """Resolve *dependencies* (PEP 508 strings) once per canonical name,
    in the given (deterministic) order.

    *seen* holds the canonical names that never look up and is extended
    with each dependency's own. It starts with the project's name: a
    dependency named like the project itself (a self-referencing extra,
    ``demo[x]; extra == 'all'``) never looks up, because the main package
    owns that name, so it mints a fresh id without a claim ``WARNING:``.
    """
    hits: dict[str, str] = {}
    for dep in dependencies:
        name = _parse_dep_name(dep)
        canonical = canonicalize_name(name)
        if canonical in seen:
            continue
        seen.add(canonical)
        spdx_id = resolve_package_id(session, DEPENDENCY_LABEL, name)
        if spdx_id is not None:
            hits[canonical] = spdx_id
    return DependencyIdHits(hits)


def _resolve_phantom_ids(
    session: IdRegistrySession, phantoms: Iterable[str], seen: set[str]
) -> list[str | None]:
    """One registry hit (or ``None``) per phantom dependency name.

    A phantom named like the project or a dependency (*seen*) never looks
    up, same as a self-referencing extra: its name already belongs to
    another package of the document. Two phantoms of one name both look
    up, so the second gets the claim ``WARNING:``.
    """
    return [
        (
            None
            if canonicalize_name(name) in seen
            else resolve_package_id(session, PHANTOM_LABEL, name)
        )
        for name in phantoms
    ]


def resolve_project_package_ids(
    doc: DocumentModel,
    transitive_only: list[str],
    session: IdRegistrySession,
) -> ProjectPackageIds:
    """Claim registry ids for the main package, then its declared and
    lock-resolved (*transitive_only*) dependencies, then its phantom
    dependencies -- that order decides who wins a shared registry id."""
    main = resolve_package_id(session, MAIN_PACKAGE_LABEL, doc.project.name)
    dependencies = [*doc.project.dependencies, *transitive_only]
    seen: set[str] = {canonicalize_name(doc.project.name)}
    dependency_hits = _resolve_dependency_hits(session, dependencies, seen)
    phantom = _resolve_phantom_ids(
        session, [dep.name for dep in doc.phantom_dependencies], seen
    )
    return ProjectPackageIds(main, dependency_hits, phantom)
