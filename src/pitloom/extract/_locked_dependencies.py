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

``poetry.lock`` is registered in :data:`_LOCK_SOURCES` with an extractor so
that Poetry 2.0+ PEP 621 projects (which lack a ``[tool.poetry]`` table) and
``setup.py`` projects discover ``poetry.lock`` through this cascade. When
``_try_read_poetry()`` already applied ``poetry.lock`` during pyproject reading,
this cascade preserves that result without redundant re-extraction.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from pitloom.assemble.spdx3._provenance_encoders import parse_provenance_value
from pitloom.core.project import ProjectMetadata
from pitloom.extract._lock_common import POETRY_LOCK_SOURCE_NAME
from pitloom.extract._pdm_lock import extract_pdm_lock_dependencies
from pitloom.extract._pipfile_lock import extract_pipfile_lock_dependencies
from pitloom.extract._poetry_lock import extract_poetry_lock_dependencies
from pitloom.extract._pylock import extract_pylock_dependencies
from pitloom.extract._requirements_txt import extract_pinned_requirements_dependencies
from pitloom.extract._uv_lock import extract_uv_lock_dependencies

log = logging.getLogger(__name__)

__all__ = ["apply_locked_dependencies"]

_LockExtractor = Callable[[Path, str | None], list[str] | None]


def _ignore_expected_name(
    extractor: Callable[[Path], list[str] | None],
) -> _LockExtractor:
    """Adapt a single-argument extractor to :data:`_LockExtractor`'s
    uniform ``(project_dir, expected_name)`` shape.

    Only ``uv.lock``'s extractor actually needs *expected_name* (to
    disambiguate a shared workspace lock's multiple local package
    entries -- see :func:`pitloom.extract._uv_lock.extract_uv_lock_dependencies`).
    Rather than widen every extractor's own signature with a parameter
    only one format uses, this adapter localizes the cascade's uniform-
    call requirement to this one module, keeping each format's own
    extractor signature as simple as its actual needs.
    """
    return lambda project_dir, _expected_name: extractor(project_dir)


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
    (
        "pylock.toml",
        _ignore_expected_name(extract_pylock_dependencies),
        "resolved_lockfile",
    ),
    ("uv.lock", extract_uv_lock_dependencies, "resolved_lockfile"),
    (
        POETRY_LOCK_SOURCE_NAME,
        _ignore_expected_name(extract_poetry_lock_dependencies),
        "resolved_lockfile",
    ),
    (
        "pdm.lock",
        _ignore_expected_name(extract_pdm_lock_dependencies),
        "resolved_lockfile",
    ),
    (
        "Pipfile.lock",
        _ignore_expected_name(extract_pipfile_lock_dependencies),
        "resolved_lockfile",
    ),
    (
        "requirements.txt",
        _ignore_expected_name(extract_pinned_requirements_dependencies),
        "pinned_requirements",
    ),
]


def apply_locked_dependencies(metadata: ProjectMetadata, project_dir: Path) -> None:
    """Overlay the highest-priority available lock/pin source's resolved
    dependencies onto *metadata*, in place.

    Tries each extractor-bearing entry of :data:`_LOCK_SOURCES` in
    priority order; the first one that yields a result at all (a
    ``list[str]``, even an empty one -- see the "no silent deviations"
    paragraph below) wins. Crucially, this respects *every* source's
    rank, not just the ones
    this cascade itself tries: once the already-applied source (e.g.
    ``poetry.lock``, applied earlier by ``_try_read_poetry()``) outranks
    every remaining untried entry, the loop stops -- a lower-priority
    format (``pdm.lock`` ranks below ``poetry.lock``) must never
    silently clobber a higher-priority result just because it happens
    to run later in this function's own loop.

    Every extractor is called uniformly as ``extractor(project_dir,
    metadata.name)`` -- ``metadata.name`` is already fully resolved by
    the time this runs (see :func:`pitloom.extract.project.read_project`),
    so passing it lets an extractor that needs it (currently only
    ``uv.lock``'s workspace-root disambiguation) skip re-reading and
    re-parsing ``pyproject.toml`` a second time just for that. Extractors
    that don't need it (``pylock.toml``, ``pdm.lock``) keep their
    simpler single-``project_dir`` signature and are wrapped with
    :func:`_ignore_expected_name` in :data:`_LOCK_SOURCES` above instead.

    If *metadata* already carries a ``locked_dependencies`` result and a
    higher-or-equal-priority source here wins, that source replaces it
    and a ``WARNING:`` names the override -- and, per this repo's "no
    silent deviations" principle, the fact that a source was superseded
    is also recorded in the resulting ``provenance["locked_dependencies"]``
    string itself (as a trailing ``| Note: supersedes <name>``), not only
    logged, so a reader of the generated SBOM can see it too.

    Each extractor returns ``None`` (not applicable here: absent,
    unparseable, or otherwise unusable -- try the next source) or a
    ``list[str]`` (this source *does* apply, even when that list is
    empty: a real lock resolving to zero runtime dependencies is a
    genuine, authoritative answer, and must win outright rather than
    being conflated with "no lock here" and letting a lower-priority
    source add dependencies the winning lock says don't exist).
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
    if previous is not None and previous_rank is None:
        # previous_source doesn't match any _LOCK_SOURCES entry -- a
        # provenance-string source name has drifted from this table (a
        # bug, not a real absence of a prior result). Without this,
        # every remaining rank's override-guard below would silently
        # never fire, letting even the lowest-priority format overwrite
        # an unrecognized-but-real prior result with no warning at all.
        log.warning(
            "%s: previously-resolved locked_dependencies source %r doesn't "
            "match any known lock source -- can't rank it, so any "
            "cascade-tried format may override it",
            project_dir,
            previous_source,
        )

    for rank, (source_name, extractor, method) in enumerate(_LOCK_SOURCES):
        if extractor is None:
            continue
        if previous_source == source_name:
            # Already extracted and set (e.g. by _try_read_poetry); keep it.
            return
        if previous_rank is not None and rank > previous_rank:
            # Every remaining entry ranks below whatever's already set --
            # none of them can win, so stop instead of scanning further.
            break

        dependencies = extractor(project_dir, metadata.name)
        if dependencies is None:
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
