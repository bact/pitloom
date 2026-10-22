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
alone) -- not from :func:`pitloom.extract.project.pyproject.read_pyproject`.
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
from typing import NamedTuple

from pitloom.core.file_identity import file_id
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import parse_provenance_value
from pitloom.extract._extract_utils import quote_source
from pitloom.extract.lock._extra_pins import ExtraPinExtractor, apply_extra_pins
from pitloom.extract.lock.common import POETRY_LOCK_SOURCE_NAME
from pitloom.extract.lock.pdm import (
    extract_pdm_lock_dependencies,
    extract_pdm_lock_extra_pins,
)
from pitloom.extract.lock.pdm_hash import extract_pdm_lock_hashes
from pitloom.extract.lock.pipfile import extract_pipfile_lock_dependencies
from pitloom.extract.lock.pipfile_hash import extract_pipfile_lock_hashes
from pitloom.extract.lock.poetry import (
    extract_poetry_lock_dependencies,
    extract_poetry_lock_extra_pins,
)
from pitloom.extract.lock.poetry_hash import extract_poetry_lock_hashes
from pitloom.extract.lock.pylock import extract_pylock_dependencies
from pitloom.extract.lock.pylock_hash import extract_pylock_hashes
from pitloom.extract.lock.requirements import (
    extract_pinned_requirements_dependencies,
)
from pitloom.extract.lock.uv import (
    extract_uv_lock_dependencies,
    extract_uv_lock_extra_pins,
)
from pitloom.extract.lock.uv_hash import extract_uv_lock_hashes

log = logging.getLogger(__name__)

__all__ = ["apply_locked_dependencies"]

_LockExtractor = Callable[[Path, str | None], list[str] | None]
_LockHashExtractor = Callable[[Path, list[str]], dict[str, str] | None]


def _ignore_expected_name(
    extractor: Callable[[Path], list[str] | None],
) -> _LockExtractor:
    """Adapt a single-argument extractor to :data:`_LockExtractor`'s
    uniform ``(project_dir, expected_name)`` shape.

    Only ``uv.lock``'s extractor needs *expected_name* (to pick the project
    among a workspace lock's local packages, see
    :func:`pitloom.extract.lock.uv.extract_uv_lock_dependencies`).
    """
    return lambda project_dir, _expected_name: extractor(project_dir)


class _LockSource(NamedTuple):
    """One lock/pin source of :data:`_LOCK_SOURCES`."""

    name: str
    extractor: _LockExtractor
    #: ``None`` for a source with no hash data of its own.
    hash_extractor: _LockHashExtractor | None
    #: Provenance ``Method:`` tag.
    method: str
    #: Pins for the project's own extras (see
    #: :mod:`pitloom.extract.lock._extra_pins`); ``None`` for a source
    #: that records none apart from its runtime closure.
    extra_pins: ExtraPinExtractor | None = None


def _ignore_project_name(
    extractor: Callable[[Path, frozenset[str]], list[str]],
) -> ExtraPinExtractor:
    """:func:`_ignore_expected_name`'s counterpart for an extras-pin
    extractor."""
    return lambda project_dir, _name, wanted: extractor(project_dir, wanted)


#: Full priority order (highest first) across every lock/pin source. A
#: hash extractor takes the winning cascade's own already-resolved
#: ``locked_dependencies`` result (never re-derives which packages
#: qualify -- see each ``_<format>_hashes`` module's own docstring) so hash
#: extraction can never disagree with the pin extraction that already
#: decided what's in scope. ``poetry.lock`` is registered with extractors
#: for Poetry 2.0+ and non-Poetry build backends, but bypassed when
#: ``_try_read_poetry()`` already extracted it during pyproject parsing.
#: This is the single place the *complete* order is declared -- both which
#: extractors this cascade tries, and where ``poetry.lock`` ranks relative
#: to them -- and a new lock format is wired for pins, hashes and extras
#: pins in one place, nothing to forget to keep in sync. ``pylock.toml``,
#: ``Pipfile.lock`` and ``requirements.txt`` have no extras pins:
#: none records the project's extras apart from what it installs.
_LOCK_SOURCES: list[_LockSource] = [
    _LockSource(
        "pylock.toml",
        _ignore_expected_name(extract_pylock_dependencies),
        extract_pylock_hashes,
        "resolved_lockfile",
    ),
    _LockSource(
        "uv.lock",
        extract_uv_lock_dependencies,
        extract_uv_lock_hashes,
        "resolved_lockfile",
        extract_uv_lock_extra_pins,
    ),
    _LockSource(
        POETRY_LOCK_SOURCE_NAME,
        _ignore_expected_name(extract_poetry_lock_dependencies),
        extract_poetry_lock_hashes,
        "resolved_lockfile",
        _ignore_project_name(extract_poetry_lock_extra_pins),
    ),
    _LockSource(
        "pdm.lock",
        _ignore_expected_name(extract_pdm_lock_dependencies),
        extract_pdm_lock_hashes,
        "resolved_lockfile",
        _ignore_project_name(extract_pdm_lock_extra_pins),
    ),
    _LockSource(
        "Pipfile.lock",
        _ignore_expected_name(extract_pipfile_lock_dependencies),
        extract_pipfile_lock_hashes,
        "resolved_lockfile",
    ),
    _LockSource(
        "requirements.txt",
        _ignore_expected_name(extract_pinned_requirements_dependencies),
        None,
        "pinned_requirements",
    ),
]


def _apply_source_extra_pins(
    metadata: ProjectMetadata, project_dir: Path, source: _LockSource
) -> None:
    """Pin the project's extras from *source*, the winning lock."""
    if source.extra_pins is not None and source.hash_extractor is not None:
        apply_extra_pins(
            metadata, project_dir, source.extra_pins, source.hash_extractor
        )


def _declares_dependencies(
    metadata: ProjectMetadata, project_dir: Path, name: str
) -> bool:
    """Whether the lock source *name* is one of the files *metadata*'s
    dependencies were read from (``dependency_files``), known by identity
    or by path: the project's declared dependencies, not a lock."""
    lock = project_dir / name
    lock_id = file_id(lock)
    return any(
        project_dir / listed == lock
        or (lock_id is not None and file_id(project_dir / listed) == lock_id)
        for listed in metadata.dependency_files
    )


def apply_locked_dependencies(metadata: ProjectMetadata, project_dir: Path) -> None:
    """Overlay the highest-priority available lock/pin source's resolved
    dependencies onto *metadata*, in place.

    Tries each extractor-bearing entry of :data:`_LOCK_SOURCES` in priority
    order; the first to yield a result wins. A result is a ``list[str]``,
    even an empty one: a lock that resolves to zero runtime dependencies is
    an authoritative answer, so it wins outright. An extractor returns
    ``None`` when its source is absent, unparseable or unusable, and the next
    source is tried. The loop respects the rank of a source applied earlier
    (``poetry.lock``, by ``_try_read_poetry()``): once it outranks every
    untried entry the loop stops, so a lower-priority format (``pdm.lock``)
    never replaces a higher-priority result.

    Every extractor is called as ``extractor(project_dir, metadata.name)``,
    the name being resolved already, so ``uv.lock``'s workspace-root
    disambiguation need not parse ``pyproject.toml`` again. Extractors that
    ignore the name are wrapped by :func:`_ignore_expected_name` in
    :data:`_LOCK_SOURCES`.

    If *metadata* already carries a ``locked_dependencies`` result and a
    higher-priority source wins, that source replaces it, a ``WARNING:``
    names the override, and the resulting
    ``provenance["locked_dependencies"]`` ends in ``| Note: supersedes
    <name>``.

    A source the project reads its dependencies from
    (``[tool.setuptools.dynamic]`` naming ``requirements.txt``) is not a
    lock and is not tried: nothing in it is ignored.
    """
    previous = metadata.provenance.get("locked_dependencies")
    previous_source = (
        parse_provenance_value(previous).get("source") if previous is not None else None
    )
    previous_rank = next(
        (
            rank
            for rank, source in enumerate(_LOCK_SOURCES)
            if source.name == previous_source
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
            quote_source(project_dir),
            previous_source,
        )

    sources_to_try = (
        _LOCK_SOURCES if previous_rank is None else _LOCK_SOURCES[:previous_rank]
    )
    for source in sources_to_try:
        if _declares_dependencies(metadata, project_dir, source.name):
            continue
        dependencies = source.extractor(project_dir, metadata.name)
        if dependencies is None:
            continue

        provenance = f"Source: {source.name} | Method: {source.method}"
        if previous is not None:
            superseded = previous_source or "unknown source"
            log.warning(
                "%s: both %s and %s resolved-dependency data are present -- "
                "%s takes priority",
                quote_source(project_dir),
                superseded,
                source.name,
                source.name,
            )
            provenance += f" | Note: supersedes {superseded}"

        metadata.locked_dependencies = dependencies
        metadata.provenance["locked_dependencies"] = provenance
        # Always reset, even to `{}`: hashes from an earlier or lower-priority
        # source must not survive beside a different winning
        # `locked_dependencies`. An empty result is authoritative, not "no
        # update".
        metadata.locked_dependency_hashes = (
            source.hash_extractor(project_dir, dependencies) or {}
            if source.hash_extractor is not None
            else {}
        )
        _apply_source_extra_pins(metadata, project_dir, source)
        return
    if previous_rank is not None:
        # The source applied before this cascade (`_try_read_poetry()`)
        # still wins: pin the extras from it.
        _apply_source_extra_pins(metadata, project_dir, _LOCK_SOURCES[previous_rank])
