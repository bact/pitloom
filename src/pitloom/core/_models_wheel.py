# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Wheel file discovery facade and per-file metadata extraction.

Runs one shared per-file processing loop (hashing, header/content-type
extraction, Merkle root) over whatever file list
:mod:`pitloom.core._models_wheel_dispatch` resolves, regardless of
which backend or mechanism produced it.

See also: :mod:`pitloom.core._models_wheel_dispatch` for backend
dispatch (a registered backend's static module, the generic
``--allow-build`` mechanism, or the Hatchling-based heuristic
fallback) and :data:`~pitloom.core._models_wheel_lock._DISCOVERY_LOCK`;
:mod:`pitloom.core.models` for SPDX model identifiers and Merkle
calculation; :mod:`pitloom.core._models_wheel_types` for the shared
``IncludedFile``/``FileHeaderExtras``/``FileScanConfig`` types;
:mod:`pitloom.core.build_signals` for the termination guard that keeps a
build-and-read result from leaking.
"""

from __future__ import annotations

import hashlib
import logging
import operator
from collections.abc import Callable
from pathlib import Path

from pitloom.core._models_wheel_dispatch import (
    _discover_included_files,
    _noop_cleanup,
)
from pitloom.core._models_wheel_types import (
    FileHeaderExtras,
    FileScanConfig,
    IncludedFile,
)
from pitloom.core.build_options import BuildOptions
from pitloom.core.build_signals import TerminationGuard
from pitloom.core.content_type_config import ContentTypeOverride
from pitloom.core.project import ProjectFile

log = logging.getLogger(__name__)


def _resolve_file_header_extras(
    raw_bytes: bytes,
    filename: str,
    distribution_path: str,
    scan_config: FileScanConfig,
) -> FileHeaderExtras:
    """Resolve the optional per-file header/content-type fields for *raw_bytes*."""
    header = scan_config.parse_header(raw_bytes) if scan_config.parse_header else None
    content_type: str | None = None
    resolved_method: str | None = None
    if scan_config.detect_content:
        override = None
        if scan_config.content_type_overrides:
            # pylint: disable=import-outside-toplevel
            from pitloom.extract._file_headers import resolve_content_type_override

            override = resolve_content_type_override(
                distribution_path, scan_config.content_type_overrides
            )
        if override is not None:
            content_type = override.content_type
            resolved_method = "config_override"
        else:
            content_type, resolved_method = scan_config.detect_content(
                raw_bytes, filename, scan_config.content_type_method
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


def _discovery_failure_result() -> tuple[
    str | None, list[ProjectFile], Callable[[], None]
]:
    """The shared ``(None, [], _noop_cleanup)`` :func:`get_wheel_files`
    return value for every failure path (discovery raised, a per-file
    read raised, or discovery produced zero files) -- one spelling
    instead of three, so all three stay in sync if this contract ever
    changes."""
    return None, [], _noop_cleanup


def _build_project_file_entry(
    source: Path,
    included_file: IncludedFile,
    project_dir: Path,
    *,
    need_bytes: bool,
    skip_merkle_root: bool,
    scan_config: FileScanConfig,
) -> tuple[ProjectFile, bytes | None]:
    """Build one *source*'s :class:`ProjectFile` entry (and its digest, if hashed).

    *source* must already be known to exist as a regular file (the
    caller's ``source.is_file()`` check). When *need_bytes* is
    ``False``, *source* is still opened and immediately closed (no
    read) -- a genuine access failure (permissions, a TOCTOU race)
    still raises here, same as a full read would, instead of silently
    producing an entry for an unreadable file.

    Returns the built :class:`ProjectFile` and the raw SHA-256 digest
    bytes (or ``None`` when *skip_merkle_root* left it uncomputed).
    """
    distribution_path = included_file.distribution_path
    if need_bytes:
        raw_bytes = source.read_bytes()
    else:
        with source.open("rb"):
            pass
        raw_bytes = b""

    digest_bytes: bytes | None = None
    digest_sha256: str | None = None
    if not skip_merkle_root:
        digest_bytes = hashlib.sha256(raw_bytes).digest()
        digest_sha256 = digest_bytes.hex()

    try:
        rel_path = source.relative_to(project_dir).as_posix()
    except ValueError:
        rel_path = source.as_posix()

    extras = _resolve_file_header_extras(
        raw_bytes, source.name, distribution_path, scan_config
    )
    project_file = ProjectFile(
        physical_path=rel_path,
        distribution_path=distribution_path,
        digest_sha256=digest_sha256,
        **extras,
    )
    return project_file, digest_bytes


# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
def get_wheel_files(
    project_dir: Path,
    *,
    scan_file_headers: bool = False,
    detect_content_type: bool = False,
    content_type_method: str = "auto",
    content_type_overrides: tuple[ContentTypeOverride, ...] = (),
    assume_backend: str | None = None,
    skip_merkle_root: bool = False,
    build_options: BuildOptions = BuildOptions(),
) -> tuple[str | None, list[ProjectFile], Callable[[], None]]:
    """Get all files included in the wheel and compute their SHA-256 Merkle root.

    Returns ``(merkle_root, project_files, cleanup)``. ``cleanup`` MUST be
    called once the caller is done reading any returned
    :class:`~pitloom.core.project.ProjectFile`'s bytes from disk -- a
    no-op for every static backend, but for a build-and-read-sourced
    result (see *build_options* below) it removes the temporary extraction
    directory those files physically live in. Call it only after every
    downstream step that re-reads a file's bytes from
    ``physical_path`` finishes (e.g. AI-model scanning/enrichment) --
    calling it too early turns those re-reads into spurious "file not
    found" failures for build-and-read-sourced files specifically
    (their ``physical_path`` doesn't resolve under *project_dir* at
    all, unlike every other backend's).

    Until this returns, the extraction directory is removed on every exit
    path: a failure (the ``(None, [], ...)`` result carries a no-op), an
    error computing the Merkle root (propagated), ``KeyboardInterrupt``,
    or SIGTERM/SIGHUP/SIGBREAK (see
    :class:`~pitloom.core.build_signals.TerminationGuard`). After that it
    is the caller's: run ``cleanup`` in a ``finally``. A signal then
    ends the process without it under ``SIG_DFL``, unless the caller
    holds a ``TerminationGuard`` around both this call and its use of
    the files, as Pitloom's own entry points do.

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

    *skip_merkle_root* skips per-file SHA-256 hashing and the Merkle
    root computation: the returned root is always ``None`` and every
    returned :class:`~pitloom.core.project.ProjectFile` has
    ``digest_sha256=None``. Only meaningful when *scan_file_headers*
    and *detect_content_type* are both off too -- otherwise each
    file's bytes are already read for those scanners and hashing them
    on top is nearly free. A file that fails to open is still detected
    (a cheap open/close probe replaces the full read) so a genuine
    access failure still degrades the whole call to ``(None, [])``,
    same as when hashing is on.

    *build_options* (``allow`` on) opts into the build-and-read
    mechanism as a fallback when static discovery has no module for the
    backend or that backend's own static discovery fails -- this
    executes third-party build-time code from *project_dir* (subprocess;
    may install build-requires from the network unless ``no_isolation``),
    bounded by ``timeout``. Off by default; deliberately has no
    ``[tool.pitloom]`` config-file equivalent (unlike every other keyword
    here) -- the target project's own config must never be able to
    silently opt itself into code execution for whoever scans it. A
    ``no_isolation``/``timeout`` given without ``allow`` gets one
    ``WARNING:`` per flag from :meth:`~pitloom.core.build_options.BuildOptions.settle`,
    called here -- a no-op for a caller that already settled its build
    options earlier (e.g. a CLI command handler), so this is only ever
    the first (and only) warning for a direct library caller of this
    function.
    """
    project_dir = project_dir.resolve()
    build_options = build_options.settle(project_dir)
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

    scan_config = FileScanConfig(
        parse_header=parse_header,
        detect_content=detect_content,
        content_type_overrides=content_type_overrides,
        content_type_method=content_type_method,
    )

    # Owns signal handling until this returns, unless the caller entered
    # its own guard first (see pitloom.core.build_signals).
    with TerminationGuard():
        try:
            included_files, cleanup_discovery = _discover_included_files(
                project_dir,
                assume_backend=assume_backend,
                build=build_options.settings(),
            )
        # pylint: disable-next=broad-exception-caught
        except Exception:
            return _discovery_failure_result()

        scanned: tuple[str | None, list[ProjectFile]] | None = None
        try:
            scanned = _scan_included_files(
                included_files,
                project_dir,
                need_bytes=(
                    scan_file_headers or detect_content_type or not skip_merkle_root
                ),
                skip_merkle_root=skip_merkle_root,
                scan_config=scan_config,
            )
        finally:
            # Not handed over -- no readable file, an error, an interrupt
            # (KeyboardInterrupt included) -- so the caller never gets it.
            if scanned is None:
                cleanup_discovery()
        if scanned is None:
            return _discovery_failure_result()
        merkle_root, project_files = scanned
        return merkle_root, project_files, cleanup_discovery


def _scan_included_files(
    included_files: list[IncludedFile],
    project_dir: Path,
    *,
    need_bytes: bool,
    skip_merkle_root: bool,
    scan_config: FileScanConfig,
) -> tuple[str | None, list[ProjectFile]] | None:
    """Hash and scan *included_files*: ``(merkle_root, project_files)``,
    or ``None`` when a file fails to read or none of them is a regular
    file. See :func:`get_wheel_files` for *need_bytes*/*skip_merkle_root*."""
    project_files: list[ProjectFile] = []
    file_entries: list[tuple[str, bytes]] = []
    try:
        for included_file in included_files:
            source = Path(included_file.path)
            if not source.is_file():
                continue
            project_file, digest_bytes = _build_project_file_entry(
                source,
                included_file,
                project_dir,
                need_bytes=need_bytes,
                skip_merkle_root=skip_merkle_root,
                scan_config=scan_config,
            )
            project_files.append(project_file)
            if digest_bytes is not None:
                file_entries.append((project_file.distribution_path, digest_bytes))
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        # A genuine per-file read failure degrades to "no files".
        log.debug("file scan failed for %s: %s", project_dir, exc)
        return None
    if not project_files:
        return None

    # Discovery order isn't guaranteed stable across runs/filesystems
    # (e.g. setuptools' find_all_modules() uses glob.glob() with no
    # sort) -- sort both the Merkle-root input and the returned file
    # list by distribution_path so the SBOM is bit-for-bit identical
    # across builds of the same, unchanged project.
    project_files.sort(key=lambda project_file: project_file.distribution_path)
    if skip_merkle_root:
        return None, project_files

    file_entries.sort(key=operator.itemgetter(0))
    # pylint: disable-next=import-outside-toplevel,cyclic-import
    from pitloom.core.models import _build_merkle_tree

    return _build_merkle_tree([digest for _, digest in file_entries]), project_files
