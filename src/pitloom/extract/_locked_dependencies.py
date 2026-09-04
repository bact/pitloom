# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Priority cascade choosing which lock/pin format supplies
:attr:`~pitloom.core.project.ProjectMetadata.locked_dependencies`.

Called once from :func:`pitloom.extract.project.read_project`, after
metadata resolution succeeds regardless of which source won
(``pyproject.toml``, a ``pyproject.toml``-with-no-usable-``[project]``
fallback to ``setup.cfg``/``setup.py``, or ``setup.cfg``/``setup.py``
alone) -- not from :func:`pitloom.extract._pyproject.read_pyproject`.
Several of the formats this module cascades over (``Pipfile.lock``,
pinned ``requirements.txt``) predate PEP 621 almost entirely and pair
with a bare ``setup.py`` in real projects, never a ``pyproject.toml``,
so a cascade wired only inside ``read_pyproject()`` would never see them.

``poetry.lock`` is *not* one of the sources listed here: it stays gated
inside :func:`pitloom.extract._pyproject._try_read_poetry`'s
``include_locked_dependencies`` build-stage flag, since it only ever
makes sense alongside a ``[tool.poetry]`` table, which requires
``pyproject.toml`` to exist regardless. This cascade runs *after* that
poetry.lock resolution, so a higher-priority format here can still
override an already-set poetry.lock result -- see
:data:`_LOCK_SOURCES`'s ordering.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from pitloom.assemble.spdx3._provenance_encoders import parse_provenance_value
from pitloom.core.project import ProjectMetadata
from pitloom.extract._pylock import extract_pylock_dependencies

log = logging.getLogger(__name__)

__all__ = ["apply_locked_dependencies"]

_LockExtractor = Callable[[Path], list[str]]

#: Priority-ordered (highest first) lock/pin sources this cascade
#: chooses among. Each entry is ``(source filename, extractor function,
#: provenance Method tag)``. The extractor always takes a project
#: directory and returns exact-pin PEP 508 strings, or an empty list
#: when the source is absent/unusable. See
#: ``working-docs/design/roadmap.md``'s "Remaining lock formats" item
#: for why this order was chosen (build-backend-agnostic and universal
#: beats tool-specific; a real resolver lock beats a merely-pinned file).
_LOCK_SOURCES: list[tuple[str, _LockExtractor, str]] = [
    ("pylock.toml", extract_pylock_dependencies, "resolved_lockfile"),
]


def apply_locked_dependencies(metadata: ProjectMetadata, project_dir: Path) -> None:
    """Overlay the highest-priority available lock/pin source's resolved
    dependencies onto *metadata*, in place.

    Tries each entry of :data:`_LOCK_SOURCES` in priority order; the
    first one that yields a non-empty result wins and every lower
    priority source is left unconsidered. If *metadata* already carries
    a ``locked_dependencies`` result (from an already-applied
    ``poetry.lock``, or nothing at all), a winning source here replaces
    it and a ``WARNING:`` names the override -- and, per this repo's "no
    silent deviations" principle, the fact that a source was superseded
    is also recorded in the resulting ``provenance["locked_dependencies"]``
    string itself (as a trailing ``| Note: supersedes <name>``), not only
    logged, so a reader of the generated SBOM can see it too.
    """
    for source_name, extractor, method in _LOCK_SOURCES:
        dependencies = extractor(project_dir)
        if not dependencies:
            continue

        provenance = f"Source: {source_name} | Method: {method}"
        previous = metadata.provenance.get("locked_dependencies")
        if previous is not None:
            superseded = parse_provenance_value(previous).get(
                "source", "unknown source"
            )
            log.warning(
                "%s: both %s and %s resolved-dependency data are present -- "
                "%s takes priority",
                project_dir,
                superseded,
                source_name,
                source_name,
            )
            provenance += f" | Note: supersedes {superseded}"

        metadata.locked_dependencies = dependencies
        metadata.provenance["locked_dependencies"] = provenance
        return
