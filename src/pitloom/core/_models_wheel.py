# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Wheel file discovery and per-file metadata extraction helpers.

Dispatches to a backend-specific discovery module based on the
project's declared build backend, then runs one shared per-file
processing loop (hashing, header/content-type extraction, Merkle
root) regardless of which backend resolved the file list.

See also: :mod:`pitloom.core.models` for SPDX model identifiers and
Merkle calculation; :mod:`pitloom.core._models_wheel_types` for the
shared ``IncludedFile``/``FileHeaderExtras`` types;
:mod:`pitloom.core._models_wheel_hatchling`/
:mod:`pitloom.core._models_wheel_setuptools` for the backend
implementations; ``working-docs/implementation/sbom-lifecycle-stages.md``
for why this stays a static-config read, never a build, for every
backend.
"""

from __future__ import annotations

import hashlib
import logging
import operator
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from pitloom.core import _models_wheel_hatchling
from pitloom.core._models_wheel_types import (
    BackendDiscoverer,
    FileHeaderExtras,
    IncludedFile,
    has_resolvable_pyproject_config,
)
from pitloom.core.content_type_config import ContentTypeOverride
from pitloom.core.project import ProjectFile

if TYPE_CHECKING:
    from pitloom.extract._file_headers import FileHeaderMetadata

log = logging.getLogger(__name__)


_WRITER_BACKENDS = frozenset({"setuptools", "pdm"})
"""Backend names whose ``discover()`` process-wide ``os.chdir()``s and must
therefore run under :meth:`_DiscoveryLock.write` (see its docstring). Every
backend NOT listed here -- Hatchling, Poetry, Flit, and any future addition
to ``backend_discoverers`` -- is assumed to be a "reader" and dispatches
under :meth:`_DiscoveryLock.read` instead. Add a backend here only when its
``discover()`` genuinely needs the working directory changed; the default
for a new backend should be to stay off this set. PDM-backend joined
setuptools here because its own package auto-discovery
(``pdm.backend.base._find_top_packages``) globs relative to the process
cwd, not the ``Builder``'s ``location`` -- see
:mod:`pitloom.core._models_wheel_pdm`."""


class _DiscoveryLock:
    """Multiple concurrent readers, or one exclusive writer -- never both.
    Writer-priority: once a writer is waiting, no *new* reader is admitted
    ahead of it, so a continuous stream of freshly-arriving readers can
    never starve a writer out indefinitely -- it only ever waits for
    readers already in flight at the moment it arrived.

    A "writer" (a backend listed in :data:`_WRITER_BACKENDS` -- currently
    setuptools and PDM-backend) process-wide ``os.chdir()``s for the
    duration of its call and must run with no other discoverer -- reader or
    writer -- active. A "reader" (every other backend, e.g. Hatchling's,
    Poetry's, or Flit's ``discover()``) never touches cwd itself
    (``get_wheel_files`` always resolves *project_dir* to an absolute path
    first), so readers never need to block each other -- only a concurrent
    writer. Held here, at the sole dispatch point every backend's
    ``discover()`` funnels through, so a future backend module needs no
    lock of its own to get the same guarantee; a future *writer*-style
    backend should add itself to :data:`_WRITER_BACKENDS` the same way
    setuptools/PDM-backend do.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition(threading.Lock())
        self._readers = 0
        self._writer_active = False
        self._writers_waiting = 0

    @contextmanager
    def read(self) -> Iterator[None]:
        with self._cond:
            while self._writer_active or self._writers_waiting > 0:
                self._cond.wait()
            self._readers += 1
        try:
            yield
        finally:
            with self._cond:
                self._readers -= 1
                if self._readers == 0:
                    self._cond.notify_all()

    @contextmanager
    def write(self) -> Iterator[None]:
        with self._cond:
            self._writers_waiting += 1
            try:
                while self._writer_active or self._readers > 0:
                    self._cond.wait()
            finally:
                self._writers_waiting -= 1
            self._writer_active = True
        try:
            yield
        finally:
            with self._cond:
                self._writer_active = False
                self._cond.notify_all()


_DISCOVERY_LOCK = _DiscoveryLock()


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _resolve_file_header_extras(
    raw_bytes: bytes,
    filename: str,
    distribution_path: str,
    parse_header: Callable[[bytes], FileHeaderMetadata | None] | None,
    detect_content: Callable[[bytes, str, str], tuple[str | None, str | None]] | None,
    content_type_overrides: tuple[ContentTypeOverride, ...],
    content_type_method: str,
) -> FileHeaderExtras:
    """Resolve the optional per-file header/content-type fields for *raw_bytes*."""
    header = parse_header(raw_bytes) if parse_header else None
    content_type: str | None = None
    resolved_method: str | None = None
    if detect_content:
        override = None
        if content_type_overrides:
            # pylint: disable=import-outside-toplevel
            from pitloom.extract._file_headers import resolve_content_type_override

            override = resolve_content_type_override(
                distribution_path, content_type_overrides
            )
        if override is not None:
            content_type = override.content_type
            resolved_method = "config_override"
        else:
            content_type, resolved_method = detect_content(
                raw_bytes, filename, content_type_method
            )
    return FileHeaderExtras(
        copyright_text=header.copyright_text if header else None,
        copyright_source=header.copyright_source if header else None,
        file_contributors=header.file_contributors if header else [],
        file_type=header.file_type if header else None,
        spdx_license_identifier=(header.spdx_license_identifier if header else None),
        content_type=content_type,
        content_type_method=resolved_method,
    )


def _skip_hatchling_fallback(
    backend: str, pyproject_data: dict[str, object] | None, project_dir: Path
) -> bool:
    """Log the right ``WARNING:`` for a backend discoverer giving up
    (returning ``None``), and report whether the doomed Hatchling
    fallback attempt should be skipped entirely (``True``) or still
    tried (``False``).

    Hatchling's ``WheelBuilder`` requires a ``pyproject.toml``
    ``[project]`` table -- with none present at all, it is guaranteed to
    also fail, so the confusing "Hatchling"-branded error for a project
    that has nothing to do with Hatchling isn't worth it. Distinguishing
    *why* the backend's own discoverer already gave up -- a
    ``[tool.<backend>]`` table present (approximate but the best
    available signal -- every currently-registered backend names its
    config table after itself) means static config existed but
    introspection itself failed, not that nothing was declared at all --
    only changes the warning's wording, not this return value.
    """
    has_project_table = pyproject_data is not None and "project" in pyproject_data
    if has_project_table:
        log.warning(
            "No static %s config resolvable in %s -- falling back to "
            "Hatchling-based heuristic, file list may be inaccurate",
            backend,
            project_dir,
        )
        return False

    if pyproject_data is not None and has_resolvable_pyproject_config(
        pyproject_data, backend
    ):
        log.warning(
            "%s's static config failed introspection in %s -- file "
            "discovery is unsupported for this project this run "
            "(Hatchling's own WheelBuilder also requires a [project] "
            "table, so that fallback would fail too)",
            backend,
            project_dir,
        )
    else:
        log.warning(
            "No static %s config resolvable in %s and no [project] "
            "table present -- file discovery is unsupported for this "
            "project (packages only resolvable via an imperative "
            "setup.py build)",
            backend,
            project_dir,
        )
    return True


def _discover_included_files(
    project_dir: Path, *, assume_backend: str | None = None
) -> list[IncludedFile]:
    """Resolve the wheel's file list via the project's build backend.

    Any backend other than Hatchling that doesn't have a dedicated
    discovery module (or whose static config can't be resolved) falls
    back to the Hatchling-based heuristic, with a ``WARNING:`` since
    the result may not accurately reflect that backend's actual
    inclusion rules.

    *assume_backend*, when given, skips reading ``pyproject.toml`` and
    detecting the backend entirely and dispatches straight to that
    backend -- for callers that already know it by construction (e.g.
    the Hatchling build hook, which is definitionally always Hatchling).
    """
    # pylint: disable=import-outside-toplevel
    from pitloom.core._models_wheel_flit import discover as discover_flit
    from pitloom.core._models_wheel_pdm import discover as discover_pdm
    from pitloom.core._models_wheel_poetry import discover as discover_poetry
    from pitloom.core._models_wheel_setuptools import discover as discover_setuptools
    from pitloom.extract._setuptools import detect_build_backend, read_pyproject_toml

    backend_discoverers: dict[str, BackendDiscoverer] = {
        "setuptools": discover_setuptools,
        "poetry": discover_poetry,
        "flit": discover_flit,
        "pdm": discover_pdm,
    }

    pyproject_data: dict[str, object] | None
    if assume_backend is not None:
        backend: str | None = assume_backend
        pyproject_data = None
    else:
        # Parsed once and reused for backend detection and setuptools' own
        # static-config check below -- both read the same pyproject.toml.
        pyproject_data = read_pyproject_toml(project_dir)
        backend = detect_build_backend(project_dir, pyproject_data=pyproject_data)

    if backend not in (None, "hatchling"):
        discoverer = backend_discoverers.get(backend)
        if discoverer is None:
            log.warning(
                "File discovery for build backend %r is not yet "
                "backend-aware -- using Hatchling-based heuristic, file "
                "list may be inaccurate for this project",
                backend,
            )
        else:
            # Only a "writer" backend (setuptools, PDM) process-wide
            # os.chdir()s for the duration of its call and needs
            # _DISCOVERY_LOCK's exclusive write mode -- see the lock's own
            # docstring and _WRITER_BACKENDS' definition. Every other backend
            # (Poetry and Flit included: neither touches cwd) is a "reader"
            # and only needs to be kept out of a concurrent writer's chdir
            # window, not out of each other's way.
            lock_ctx = (
                _DISCOVERY_LOCK.write()
                if backend in _WRITER_BACKENDS
                else _DISCOVERY_LOCK.read()
            )
            with lock_ctx:
                files = discoverer(project_dir, pyproject_data=pyproject_data)
            if files is not None:
                return files
            if _skip_hatchling_fallback(backend, pyproject_data, project_dir):
                return []

    # Hatchling's discover() never touches cwd (project_dir is always
    # already absolute here -- see get_wheel_files), so concurrent
    # Hatchling calls only need to be kept out of a concurrent writer's
    # chdir window, never out of each other's way.
    with _DISCOVERY_LOCK.read():
        return _models_wheel_hatchling.discover(project_dir) or []


# pylint: disable=too-many-locals
def get_wheel_files(
    project_dir: Path,
    *,
    scan_file_headers: bool = False,
    detect_content_type: bool = False,
    content_type_method: str = "auto",
    content_type_overrides: tuple[ContentTypeOverride, ...] = (),
    assume_backend: str | None = None,
) -> tuple[str | None, list[ProjectFile]]:
    """Get all files included in the wheel and compute their SHA-256 Merkle root.

    Discovers the file set via the project's build backend (see
    :func:`_discover_included_files`), respecting that backend's own
    include/exclude/packages configuration, then hashes and extracts
    optional per-file metadata for each file.

    *assume_backend* (e.g. ``"hatchling"``) skips backend detection
    entirely -- pass it when the caller already knows the backend by
    construction, to avoid a redundant ``pyproject.toml`` parse.

    *project_dir* is resolved (canonicalized, symlinks followed) before
    use, so a relative or symlink-containing path can't produce a
    ``physical_path`` that diverges from *project_dir*'s own on-disk
    identity -- see :class:`~pitloom.core.project.ProjectFile`'s
    ``physical_path`` contract.
    """
    project_dir = project_dir.resolve()
    parse_header = None
    if scan_file_headers:
        # pylint: disable-next=import-outside-toplevel
        from pitloom.extract._file_headers import parse_file_header

        parse_header = parse_file_header

    detect_content = None
    if detect_content_type:
        # pylint: disable=import-outside-toplevel
        from pitloom.extract._file_headers import (
            guess_content_type,
            require_magika_available,
        )

        if content_type_method == "magika":
            require_magika_available()
        detect_content = guess_content_type

    try:
        included_files = _discover_included_files(
            project_dir, assume_backend=assume_backend
        )
        project_files: list[ProjectFile] = []
        file_entries: list[tuple[str, bytes]] = []
        for included_file in included_files:
            source = Path(included_file.path)
            if source.is_file():
                distribution_path = included_file.distribution_path
                raw_bytes = source.read_bytes()
                digest_bytes = hashlib.sha256(raw_bytes).digest()
                file_entries.append((distribution_path, digest_bytes))
                try:
                    rel_path = source.relative_to(project_dir).as_posix()
                except ValueError:
                    rel_path = source.as_posix()

                extras = _resolve_file_header_extras(
                    raw_bytes,
                    source.name,
                    distribution_path,
                    parse_header,
                    detect_content,
                    content_type_overrides,
                    content_type_method,
                )
                project_files.append(
                    ProjectFile(
                        physical_path=rel_path,
                        distribution_path=distribution_path,
                        digest_sha256=digest_bytes.hex(),
                        **extras,
                    )
                )
    # pylint: disable=broad-exception-caught
    except Exception:
        return None, []

    if not file_entries:
        return None, []

    # Discovery order isn't guaranteed stable across runs/filesystems
    # (e.g. setuptools' find_all_modules() uses glob.glob() with no
    # sort) -- sort both the Merkle-root input and the returned file
    # list by distribution_path so the SBOM is bit-for-bit identical
    # across builds of the same, unchanged project.
    file_entries.sort(key=operator.itemgetter(0))
    project_files.sort(key=lambda project_file: project_file.distribution_path)
    # pylint: disable-next=import-outside-toplevel,cyclic-import
    from pitloom.core.models import _build_merkle_tree

    merkle_root = _build_merkle_tree([digest for _, digest in file_entries])
    return merkle_root, project_files
