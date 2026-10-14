# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Edge kind of a declared dependency: required (``dependsOn``) or optional
(``hasOptionalDependency``, gated by one or more extras).

The extra gate is read from the text of the requirement's marker
(:mod:`pitloom.core.extra_gate`), never by evaluating the marker.

See also: :func:`pitloom.assemble.spdx3.deps.add_dependencies`, the
caller.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.extra_gate import Gate, MarkerShapeError, read_gate
from pitloom.core.pep508 import parse_requirement
from pitloom.core.requirements import warn_joined_extra_entry

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DependencyEdge:
    """The relationship from the main package to one dependency package."""

    rel_type: str
    #: Lifecycle scope, or ``None`` for an optional dependency: an extra's
    #: lifecycle (runtime, development, test, ...) is not known.
    scope: str | None
    #: ``extras: a, b`` for an optional dependency, else ``None``.
    comment: str | None


REQUIRED_EDGE = DependencyEdge(
    rel_type=spdx3.RelationshipType.dependsOn,
    scope=spdx3.LifecycleScopeType.runtime,
    comment=None,
)


def _requirement(dep: str) -> Requirement | None:
    try:
        return parse_requirement(dep)
    except InvalidRequirement:
        return None


def _names_project(req: Requirement | None, canonical_project: str) -> bool:
    """Whether *req* (``None``: not PEP 508, never a self-reference) names
    the project."""
    return req is not None and canonicalize_name(req.name) == canonical_project


def _warn_required(message: str, *args: str) -> None:
    """``WARNING:`` that a dependency is recorded as required, *message*
    saying why."""
    log.warning(message + " -- recorded as a required dependency", *args)


def _gate(dep: str, req: Requirement | None, *, self_reference: bool) -> Gate:
    """*dep*'s extra gate. A marker whose gate cannot be isolated, or a
    *dep* that is not PEP 508 (*req* ``None``), counts as required, with a
    ``WARNING:`` worded for a *self_reference* or another dependency. One
    requiring several extras together is never installed without an extra:
    optional for any of them, with a ``WARNING:``
    (:func:`~pitloom.core.requirements.warn_joined_extra_entry`)."""
    if req is None:
        _warn_required("Dependency %r is not a valid PEP 508 requirement", dep)
        return None
    if req.marker is None:
        return None
    try:
        reading = read_gate(str(req.marker))
    except MarkerShapeError:
        if self_reference:
            log.warning(
                "Self-reference %r declared as %r has an extra marker that"
                " can't be isolated -- the requirements of the extras it"
                " requests are recorded as required dependencies",
                req.name,
                dep,
            )
        else:
            _warn_required(
                "Dependency %r declared as %r has an extra marker that can't"
                " be isolated",
                req.name,
                dep,
            )
        return None
    if reading.joined:
        warn_joined_extra_entry(dep, reading.joined)
    return reading.gate


# pylint: disable-next=too-few-public-methods
class _Closures:
    """Each gate plus every extra that includes one of its extras through a
    self-reference, worked out once per extra and once per gate."""

    def __init__(self, includes: Sequence[tuple[Gate, frozenset[str]]]) -> None:
        """*includes*: ``(gate of the self-reference, extras it requests)``."""
        self._including: dict[str, list[Gate]] = {}
        for including, requested in includes:
            for extra in requested:
                self._including.setdefault(extra, []).append(including)
        self._by_extra: dict[str, Gate] = {}
        self._by_gate: dict[frozenset[str], Gate] = {}

    def of(self, gate: Gate) -> Gate:
        """*gate*'s closure; ``None`` once a required self-reference
        includes one of its extras."""
        if gate is None:
            return None
        if gate not in self._by_gate:
            self._by_gate[gate] = self._union(gate)
        return self._by_gate[gate]

    def _union(self, gate: frozenset[str]) -> Gate:
        extras: set[str] = set()
        for extra in gate:
            closure = self._of_extra(extra)
            if closure is None:
                return None
            extras |= closure
        return frozenset(extras)

    def _of_extra(self, extra: str) -> Gate:
        if extra not in self._by_extra:
            self._by_extra[extra] = self._walk(extra)
        return self._by_extra[extra]

    def _walk(self, extra: str) -> Gate:
        extras = {extra}
        pending = [extra]
        while pending:
            for including in self._including.get(pending.pop(), []):
                if including is None:
                    return None
                new = including - extras
                extras |= new
                pending.extend(new)
        return frozenset(extras)


class DependencyScopes:
    """The edge kind of each dependency of one declared list.

    A dependency naming the project itself (``demo[dev]; extra == "full"``)
    is a self-reference: it adds no package and no edge. Every requirement
    of the extras it requests gets its gate instead, so ``foo; extra ==
    "dev"`` reads ``extras: dev, full``, the same as a wheel whose build
    backend expanded the self-reference (Hatchling).
    """

    def __init__(self, dependencies: Iterable[str], project_name: str) -> None:
        project = canonicalize_name(project_name)
        gates: dict[str, Gate] = {}
        includes: list[tuple[Gate, frozenset[str]]] = []
        self._self_references: set[str] = set()
        for dep in dict.fromkeys(dependencies):
            req = _requirement(dep)
            is_self = _names_project(req, project)
            gate = _gate(dep, req, self_reference=is_self)
            if req is not None and is_self:
                log.debug("Dependency %r is a self-reference: no package", dep)
                self._self_references.add(dep)
                includes.append(
                    (gate, frozenset(canonicalize_name(e) for e in req.extras))
                )
            else:
                gates[dep] = gate
        closures = _Closures(includes)
        self._gates = {dep: closures.of(gate) for dep, gate in gates.items()}

    def is_self_reference(self, dep: str) -> bool:
        """Whether *dep* names the project itself."""
        return dep in self._self_references

    def edge(self, declared: Sequence[str]) -> DependencyEdge:
        """The edge to the one package *declared* (non-self-referencing
        strings of the list given to the constructor) resolve to: required
        when any string is, else optional with the union of their extras."""
        gates = [self._gates[dep] for dep in declared]
        extra_gates = [gate for gate in gates if gate is not None]
        if not gates or len(extra_gates) != len(gates):
            return REQUIRED_EDGE
        extras = sorted(frozenset().union(*extra_gates))
        return DependencyEdge(
            rel_type=spdx3.RelationshipType.hasOptionalDependency,
            scope=None,
            comment=f"extras: {', '.join(extras)}",
        )


def is_self_reference(dep: str, project_name: str) -> bool:
    """Whether *dep* names the project *project_name* itself."""
    return _names_project(_requirement(dep), canonicalize_name(project_name))
