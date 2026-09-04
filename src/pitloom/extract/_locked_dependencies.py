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

``poetry.lock`` has no extractor entry in :data:`_LOCK_SOURCES` -- it
stays gated inside
:func:`pitloom.extract._pyproject._try_read_poetry`'s
``include_locked_dependencies`` build-stage flag, since it only ever
makes sense alongside a ``[tool.poetry]`` table, which requires
``pyproject.toml`` to exist regardless, so it's applied earlier, before
this cascade runs. It *is* still listed in :data:`_LOCK_SOURCES`, as a
placeholder entry with no extractor, purely to fix its rank in the one
priority order every source (cascade-tried or not) is compared against
-- see :func:`apply_locked_dependencies`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from pitloom.assemble.spdx3._provenance_encoders import parse_provenance_value
from pitloom.core.project import ProjectMetadata
from pitloom.extract._lock_common import POETRY_LOCK_SOURCE_NAME
from pitloom.extract._pdm_lock import extract_pdm_lock_dependencies
from pitloom.extract._pylock import extract_pylock_dependencies
from pitloom.extract._uv_lock import extract_uv_lock_dependencies

log = logging.getLogger(__name__)

__all__ = ["apply_locked_dependencies"]

_LockExtractor = Callable[[Path], list[str]]

#: Full priority order (highest first) across every lock/pin source,
#: including ``poetry.lock`` even though it has no extractor here (see
#: the module docstring). Each entry is ``(source name, extractor or
#: ``None``, provenance Method tag or ``None``)``. This is the single
#: place the *complete* order is declared -- both which extractors this
#: cascade tries, and where ``poetry.lock``'s already-applied result
#: ranks relative to them -- so the two can never drift apart the way
#: two independently-maintained lists could. See
#: ``working-docs/design/roadmap.md``'s "Remaining lock formats" item
#: for why this order was chosen (build-backend-agnostic and universal
#: beats tool-specific; a real resolver lock beats a merely-pinned file).
_LOCK_SOURCES: list[tuple[str, _LockExtractor | None, str | None]] = [
    ("pylock.toml", extract_pylock_dependencies, "resolved_lockfile"),
    ("uv.lock", extract_uv_lock_dependencies, "resolved_lockfile"),
    (POETRY_LOCK_SOURCE_NAME, None, None),
    ("pdm.lock", extract_pdm_lock_dependencies, "resolved_lockfile"),
]


def apply_locked_dependencies(metadata: ProjectMetadata, project_dir: Path) -> None:
    """Overlay the highest-priority available lock/pin source's resolved
    dependencies onto *metadata*, in place.

    Tries each extractor-bearing entry of :data:`_LOCK_SOURCES` in
    priority order; the first one that yields a non-empty result wins.
    Crucially, this respects *every* source's rank, not just the ones
    this cascade itself tries: once the already-applied source (e.g.
    ``poetry.lock``, applied earlier by ``_try_read_poetry()``) outranks
    every remaining untried entry, the loop stops -- a lower-priority
    format (``pdm.lock`` ranks below ``poetry.lock``) must never
    silently clobber a higher-priority result just because it happens
    to run later in this function's own loop.

    If *metadata* already carries a ``locked_dependencies`` result and a
    higher-or-equal-priority source here wins, that source replaces it
    and a ``WARNING:`` names the override -- and, per this repo's "no
    silent deviations" principle, the fact that a source was superseded
    is also recorded in the resulting ``provenance["locked_dependencies"]``
    string itself (as a trailing ``| Note: supersedes <name>``), not only
    logged, so a reader of the generated SBOM can see it too.
    """
    previous = metadata.provenance.get("locked_dependencies")
    previous_source = (
        parse_provenance_value(previous).get("source") if previous is not None else None
    )
    previous_rank = next(
        (
            rank
            for rank, (name, _, _) in enumerate(_LOCK_SOURCES)
            if name == previous_source
        ),
        None,
    )

    for rank, (source_name, extractor, method) in enumerate(_LOCK_SOURCES):
        if extractor is None:
            continue  # e.g. poetry.lock: applied earlier, not tried here
        if previous_rank is not None and rank > previous_rank:
            # Every remaining entry ranks below whatever's already set --
            # none of them can win, so stop instead of scanning further.
            break

        dependencies = extractor(project_dir)
        if not dependencies:
            continue

        provenance = f"Source: {source_name} | Method: {method}"
        if previous is not None:
            superseded = previous_source or "unknown source"
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
