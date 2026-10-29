# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One pass over an sdist archive: every member hashed, the root members
:mod:`pitloom.extract.project.sdist` reads (``PKG-INFO``, the config) and
the project's licence sources kept, each up to its cap.

See also: :mod:`pitloom.extract.project.sdist` (the reader) and
:mod:`pitloom.core.archive_member_names` (member names).
"""

from __future__ import annotations

import functools
import logging
import tarfile
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO, NamedTuple

from pitloom.core.archive_member_names import file_members, zip_file_members
from pitloom.core.file_hash import DigestHasher, FileDigests
from pitloom.core.project import ProjectFile, digest_fields
from pitloom.core.quote_source import quote_source
from pitloom.core.wheel_dist_info import HeaderBlockOverCap, read_header_block
from pitloom.extract._license_detect import (
    LICENSE_FILE_CAP,
    license_source_names,
)
from pitloom.logging_config import Cap, warn_over_cap

log = logging.getLogger(__name__)

#: Root members read: metadata (``PKG-INFO``'s header block) and the
#: project's own config (whole).
PKG_INFO = "PKG-INFO"
PYPROJECT = "pyproject.toml"
SETUP_CFG = "setup.cfg"
ROOT_MEMBERS = (PKG_INFO, PYPROJECT, SETUP_CFG)

#: Largest ``pyproject.toml``/``setup.cfg`` member read into memory. Real
#: ones are a few KiB; a larger one is a read failure, as invalid TOML is.
CONFIG_MEMBER_MAX_BYTES = 1024 * 1024

#: :data:`CONFIG_MEMBER_MAX_BYTES`, as the reader names it.
CONFIG_MEMBER_CAP = Cap(CONFIG_MEMBER_MAX_BYTES, "byte", "config-member")

_CHUNK_BYTES = 8192


class ArchiveMembers(NamedTuple):
    """Root members read (by basename), and every file's entry. A root
    member over its cap (see :func:`_read_member`) maps to that
    :class:`~pitloom.logging_config.Cap`.
    *licence* holds the project's licence sources by basename (see
    :func:`_licence_member_names`); one over the cap is left out."""

    root: dict[str, bytes | Cap]
    files: list[ProjectFile]
    licence: dict[str, bytes]


class _HashingReader:
    """*stream*, hashed as it is read."""

    def __init__(self, stream: IO[bytes]) -> None:
        self._stream = stream
        self._hasher = DigestHasher()

    def read(self, size: int, /) -> bytes:
        """Up to *size* bytes of the stream, hashed."""
        chunk = self._stream.read(size)
        self._hasher.update(chunk)
        return chunk

    def digests(self) -> FileDigests:
        """The digests of what has been read."""
        return self._hasher.digests()


def _read_capped(reader: _HashingReader, cap: Cap) -> bytes | Cap:
    """*reader*'s bytes, or *cap* past its limit (the rest not kept)."""
    kept = bytearray()
    while chunk := reader.read(_CHUNK_BYTES):
        kept += chunk
        if len(kept) > cap.limit:
            return cap
    return bytes(kept)


def _read_pkg_info(reader: _HashingReader) -> bytes | Cap:
    """A ``PKG-INFO``'s header block (:func:`read_header_block`, whose caps
    bound a header bomb as well as its size), or the cap it is over."""
    try:
        return read_header_block(reader)
    except HeaderBlockOverCap as over:
        return over.cap


_Keep = Callable[[_HashingReader], bytes | Cap]


def _keep_for(basename: str) -> _Keep:
    """How much of a kept member to read: a ``PKG-INFO``'s header block, a
    config member up to :data:`CONFIG_MEMBER_MAX_BYTES`, a licence source
    up to :data:`~pitloom.extract._license_detect.LICENSE_FILE_MAX_BYTES`."""
    if basename == PKG_INFO:
        return _read_pkg_info
    cap = CONFIG_MEMBER_CAP if basename in ROOT_MEMBERS else LICENSE_FILE_CAP
    return functools.partial(_read_capped, cap=cap)


def _read_member(
    stream: IO[bytes], keep: _Keep | None
) -> tuple[bytes | Cap | None, FileDigests]:
    """Hash *stream* in chunks; with *keep*, return what it reads too."""
    reader = _HashingReader(stream)
    kept: bytes | Cap | None = None
    with stream:
        if keep is not None:
            kept = keep(reader)
        while reader.read(_CHUNK_BYTES):
            pass
    return kept, reader.digests()


#: One archive file: (install-location name, opener).
_Entry = tuple[str, Callable[[], IO[bytes] | None]]


def _root_parts(name: str) -> tuple[str, str] | None:
    """``(top directory, basename)`` of a root-level member, else ``None``."""
    parts = name.split("/")
    return (parts[0], parts[1]) if len(parts) == 2 else None


def _top_directory(names: list[str], members: tuple[str, ...]) -> str | None:
    """The top directory holding the first root-level member of *members*
    (in that order, archive order within one), else ``None``."""
    roots = [parts for parts in map(_root_parts, names) if parts is not None]
    return next((t for m in members for t, base in roots if base == m), None)


def _licence_member_names(names: list[str]) -> set[str]:
    """The licence sources (:func:`~pitloom.extract._license_detect.\
license_source_names`) among the root-level members of the project's top
    directory: the one holding the first root-level ``PKG-INFO``, else
    ``pyproject.toml``, else ``setup.cfg``, in archive order, as
    :func:`_scan` picks those."""
    top = _top_directory(names, ROOT_MEMBERS)
    basenames = [base for t, base in filter(None, map(_root_parts, names)) if t == top]
    return {f"{top}/{base}" for base in license_source_names(basenames)}


def _project_path(name: str, strip_top: str | None) -> str:
    """The project-relative path of member *name*: without its top
    directory *strip_top*; a member outside it keeps its name."""
    if strip_top is not None and name.startswith(f"{strip_top}/"):
        return name[len(strip_top) + 1 :]
    return name


_SHARED_PATHS_SHOWN = 5


def _warn_shared_paths(files: list[ProjectFile], archive: str) -> None:
    """One ``WARNING:`` when members of *archive* share a project path (a
    member outside the top directory next to one inside it, as in a
    malformed sdist), naming up to :data:`_SHARED_PATHS_SHOWN` of them."""
    seen: set[str] = set()
    shared: dict[str, None] = {}
    for file in files:
        if file.physical_path in seen:
            shared[file.physical_path] = None
        seen.add(file.physical_path)
    if shared:
        names = ", ".join(map(quote_source, list(shared)[:_SHARED_PATHS_SHOWN]))
        log.warning(
            "ARCHIVE=%s: members share a project path (%s%s); they would share "
            "one ID registry key",
            quote_source(Path(archive).name),
            names,
            ", ..." if len(shared) > _SHARED_PATHS_SHOWN else "",
        )


def _scan(
    entries: Iterator[_Entry],
    *,
    archive: str,
    root_only: bool = False,
) -> ArchiveMembers:
    """Hash every member; keep the first root-level member of each
    :data:`ROOT_MEMBERS` basename, archive order deciding a tie between
    two top-level directories, and the licence sources of
    :func:`_licence_member_names` (one over the cap warned about, as
    *archive*:name, and left out; a Git LFS pointer left out quietly). A
    file keeps its own digests, a pointer's too, as the archive holds it,
    flagged (``lfs_pointer``). Repeats of one name never get here:
    :func:`~pitloom.core.archive_member_names.file_members` keeps the
    last, as unpacking leaves it. With *root_only*, open only the root
    members and list no files or licence sources. Files come in archive
    order; :func:`~pitloom.extract.project.sdist.read_sdist` sorts them. A
    file's ``physical_path`` is its project-relative path: its name
    without the top directory holding the first root-level ``PKG-INFO``
    (none: no strip); a member outside it keeps its name."""
    entries_list = list(entries)
    strip_top = _top_directory([e[0] for e in entries_list], (PKG_INFO,))
    licence_names = (
        set() if root_only else _licence_member_names([e[0] for e in entries_list])
    )
    members = ArchiveMembers({}, [], {})
    for name, open_member in entries_list:
        basename = name.rsplit("/", 1)[-1]
        wanted = (
            _root_parts(name) is not None
            and basename in ROOT_MEMBERS
            and basename not in members.root
        )
        if root_only and not wanted:
            continue
        stream = open_member()
        if stream is None:
            continue
        keep = wanted or name in licence_names
        content, digest = _read_member(stream, _keep_for(basename) if keep else None)
        if wanted and content is not None:
            members.root[basename] = content
        elif isinstance(content, Cap):
            warn_over_cap(log, content, f"{archive}:{name}", once=True)
        elif content is not None and digest.lfs_pointer is None:
            members.licence[basename] = content
        if not root_only:
            members.files.append(
                ProjectFile(
                    physical_path=_project_path(name, strip_top),
                    distribution_path=name,
                    **digest_fields(digest, bytes_as_is=True),
                )
            )
    if not root_only:
        _warn_shared_paths(members.files, archive)
    return members


def _tar_entries(
    tf: tarfile.TarFile, logger: logging.Logger | None, archive_name: str
) -> Iterator[_Entry]:
    files = ((m.name, m.size, m) for m in tf.getmembers() if m.isfile())
    for name, member in file_members(files, archive_name, logger, dot_prefix_ok=True):
        yield name, functools.partial(tf.extractfile, member)


def _zip_entries(
    zf: zipfile.ZipFile, logger: logging.Logger | None, archive_name: str
) -> Iterator[_Entry]:
    for name, info in zip_file_members(zf, archive_name, logger):
        yield name, functools.partial(zf.open, info)


def scan_archive(sdist_path: Path, *, root_only: bool = False) -> ArchiveMembers:
    """Scan the archive's members under their normalised names. Member-name
    warnings come from the full scan only: a *root_only* read serves
    ``--verbose`` source reporting, whose run reads the archive in full."""
    logger = None if root_only else log
    if sdist_path.name.lower().endswith(".zip"):
        with zipfile.ZipFile(sdist_path, "r") as zf:
            entries = _zip_entries(zf, logger, sdist_path.name)
            return _scan(entries, root_only=root_only, archive=str(sdist_path))
    with tarfile.open(sdist_path, "r:*") as tf:
        entries = _tar_entries(tf, logger, sdist_path.name)
        return _scan(entries, root_only=root_only, archive=str(sdist_path))
