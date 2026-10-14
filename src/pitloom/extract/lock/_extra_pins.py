# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Lock pins for the requirements of the project's own extras.

A lock's runtime closure leaves the project's extras out, so an extra's
requirement would keep only its declared range. When the winning lock
resolved that requirement for an extra, its exact pin is appended to
:attr:`~pitloom.core.project.ProjectMetadata.locked_dependencies`, and the
document layer applies it to the declared range as it does for a required
dependency. Only names the project declares are pinned, never an extra's
transitive closure, and a name the runtime closure already pins keeps that
pin.

See also: :mod:`pitloom.extract.lock.cascade` (the one caller of
:func:`apply_extra_pins`) and the per-format ``extract_*_extra_pins``
functions in :mod:`pitloom.extract.lock.uv`,
:mod:`pitloom.extract.lock.poetry` and :mod:`pitloom.extract.lock.pdm`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator, Set
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement
from packaging.utils import canonicalize_name

from pitloom.core.extra_gate import is_extra_gated
from pitloom.core.pep508 import parse_requirement
from pitloom.core.project import ProjectMetadata

log = logging.getLogger(__name__)

__all__ = [
    "ExtraPinExtractor",
    "apply_extra_pins",
    "packages_named",
    "requirement_names",
]

#: ``(project_dir, project name, wanted PEP 503 names) -> name==version
#: pins`` resolved for the project's extras, limited to *wanted*.
ExtraPinExtractor = Callable[[Path, str, frozenset[str]], list[str]]

_HashExtractor = Callable[[Path, list[str]], dict[str, str] | None]


def packages_named(packages: object, wanted: Set[str]) -> Iterator[dict[str, Any]]:
    """The table entries of a lock's package list whose ``name`` is one of
    *wanted* (PEP 503 names), in file order; anything else is skipped
    silently (the runtime-closure pass already warned about it)."""
    for raw in packages if isinstance(packages, list) else []:
        if (
            isinstance(raw, dict)
            and isinstance(raw.get("name"), str)
            and canonicalize_name(raw["name"]) in wanted
        ):
            yield raw


def requirement_names(
    dependencies: Iterable[object], *, gated: bool | None = None
) -> set[str]:
    """PEP 503 names of the PEP 508 strings in *dependencies*; anything
    else is ignored. *gated* ``True``: only those an extra gates
    (:func:`~pitloom.core.extra_gate.is_extra_gated`, the rule the edge
    kinds follow); ``False``: only the others; ``None``: all."""
    names: set[str] = set()
    for dep in dependencies:
        try:
            req = parse_requirement(dep) if isinstance(dep, str) else None
        except InvalidRequirement:
            continue
        if req is not None and gated in (None, is_extra_gated(req)):
            names.add(canonicalize_name(req.name))
    return names


def apply_extra_pins(
    metadata: ProjectMetadata,
    project_dir: Path,
    extractor: ExtraPinExtractor,
    hash_extractor: _HashExtractor,
) -> None:
    """Append the winning lock's pins for the project's extras to
    *metadata*'s ``locked_dependencies`` (sorted by PEP 503 name), and
    their hashes to ``locked_dependency_hashes``.

    Asked for: every name an extra gates, except the project's own, a
    required one (the runtime closure's pass read, pinned or warned about
    it: a required dependency wins and is pinned or warned about once) and
    those ``locked_dependencies`` already pins. Running twice adds nothing
    the second time.
    """
    wanted = frozenset(
        requirement_names(metadata.dependencies, gated=True)
        - requirement_names(metadata.dependencies, gated=False)
        - requirement_names(metadata.locked_dependencies)
        - {canonicalize_name(metadata.name)}
    )
    pins = sorted(
        extractor(project_dir, metadata.name, wanted),
        key=lambda pin: canonicalize_name(parse_requirement(pin).name),
    )
    if not pins:
        return
    log.debug("Lock pins for the project's extras: %s", ", ".join(pins))
    metadata.locked_dependencies = [*metadata.locked_dependencies, *pins]
    metadata.locked_dependency_hashes = {
        **metadata.locked_dependency_hashes,
        **(hash_extractor(project_dir, pins) or {}),
    }
