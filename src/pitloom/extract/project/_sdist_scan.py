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
import hashlib
import logging
import tarfile
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO, NamedTuple

from pitloom.core.archive_member_names import file_members, zip_file_members
from pitloom.core.project import ProjectFile
from pitloom.core.wheel_dist_info import HeaderBlockOverCap, read_header_block
from pitloom.extract._license_detect import (
    LICENSE_FILE_MAX_BYTES,
    license_source_names,
    warn_over_cap,
)

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

_CHUNK_BYTES = 8192


class ArchiveMembers(NamedTuple):
    """Root members read (by basename), and every file's entry. A root
    member over its cap (see :func:`_read_member`) maps to ``None``.
    *licence* holds the project's licence sources by basename (see
    :func:`_licence_member_names`); one over the cap is left out."""

    root: dict[str, bytes | None]
    files: list[ProjectFile]
    licence: dict[str, bytes]


class _HashingReader:
    """*stream*, hashed as it is read."""

    def __init__(self, stream: IO[bytes]) -> None:
        self._stream = stream
        self._hasher = hashlib.sha256()

    def read(self, size: int, /) -> bytes:
        """Up to *size* bytes of the stream, hashed."""
        chunk = self._stream.read(size)
        self._hasher.update(chunk)
        return chunk

    def hexdigest(self) -> str:
        """The SHA-256 of what has been read."""
        return self._hasher.hexdigest()


def _read_capped(reader: _HashingReader, limit: int) -> bytes | None:
    """*reader*'s bytes, or ``None`` past *limit* (the rest not kept)."""
    kept = bytearray()
    while chunk := reader.read(_CHUNK_BYTES):
        kept += chunk
        if len(kept) > limit:
            return None
    return bytes(kept)


def _read_pkg_info(reader: _HashingReader) -> bytes | None:
    """A ``PKG-INFO``'s header block (:func:`read_header_block`, whose caps
    bound a header bomb as well as its size); ``None`` over the cap."""
    try:
        return read_header_block(reader)
    except HeaderBlockOverCap:
        return None


_Keep = Callable[[_HashingReader], bytes | None]


def _keep_for(basename: str) -> _Keep:
    """How much of a kept member to read: a ``PKG-INFO``'s header block, a
    config member up to :data:`CONFIG_MEMBER_MAX_BYTES`, a licence source
    up to :data:`~pitloom.extract._license_detect.LICENSE_FILE_MAX_BYTES`."""
    if basename == PKG_INFO:
        return _read_pkg_info
    in_root = basename in ROOT_MEMBERS
    limit = CONFIG_MEMBER_MAX_BYTES if in_root else LICENSE_FILE_MAX_BYTES
    return functools.partial(_read_capped, limit=limit)


def _read_member(stream: IO[bytes], keep: _Keep | None) -> tuple[bytes | None, str]:
    """Hash *stream* in chunks; with *keep*, return what it reads too."""
    reader = _HashingReader(stream)
    kept: bytes | None = None
    with stream:
        if keep is not None:
            kept = keep(reader)
        while reader.read(_CHUNK_BYTES):
            pass
    return kept, reader.hexdigest()


#: One archive file: (install-location name, raw archive name, opener).
_Entry = tuple[str, str, Callable[[], IO[bytes] | None]]


def _root_parts(name: str) -> tuple[str, str] | None:
    """``(top directory, basename)`` of a root-level member, else ``None``."""
    parts = name.split("/")
    return (parts[0], parts[1]) if len(parts) == 2 else None


def _licence_member_names(names: list[str]) -> set[str]:
    """The licence sources (:func:`~pitloom.extract._license_detect.\
license_source_names`) among the root-level members of the project's top
    directory: the one holding the first root-level ``PKG-INFO``, else
    ``pyproject.toml``, else ``setup.cfg``, in archive order, as
    :func:`_scan` picks those."""
    roots = [parts for parts in map(_root_parts, names) if parts is not None]
    top = next(
        (t for member in ROOT_MEMBERS for t, base in roots if base == member), None
    )
    basenames = [base for t, base in roots if t == top]
    return {f"{top}/{base}" for base in license_source_names(basenames)}


def _scan(
    entries: Iterator[_Entry],
    *,
    root_only: bool = False,
    archive: str = "",
) -> ArchiveMembers:
    """Hash every member; keep the first root-level member of each
    :data:`ROOT_MEMBERS` basename, archive order deciding a tie between
    two top-level directories, and the licence sources of
    :func:`_licence_member_names` (one over the cap warned about, as
    *archive*:name, and left out). Repeats of one name never get here:
    :func:`~pitloom.core.archive_member_names.file_members` keeps the
    last, as unpacking leaves it. With *root_only*, open only the root
    members and list no files or licence sources. Files come in archive
    order; :func:`~pitloom.extract.project.sdist.read_sdist` sorts them. A
    file's ``physical_path`` is its raw archive name, so a registry keyed
    by it before names were normalised still hits."""
    entries_list = list(entries)
    licence_names = (
        set() if root_only else _licence_member_names([e[0] for e in entries_list])
    )
    members = ArchiveMembers({}, [], {})
    for name, raw, open_member in entries_list:
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
        if wanted:
            members.root[basename] = content
        elif keep and content is None:
            warn_over_cap(f"{archive}:{name}")
        elif keep and content is not None:
            members.licence[basename] = content
        if not root_only:
            members.files.append(
                ProjectFile(
                    physical_path=raw, distribution_path=name, digest_sha256=digest
                )
            )
    return members


def _tar_entries(
    tf: tarfile.TarFile, logger: logging.Logger | None, archive_name: str
) -> Iterator[_Entry]:
    files = ((m.name, m.size, m) for m in tf.getmembers() if m.isfile())
    for name, member in file_members(files, archive_name, logger, dot_prefix_ok=True):
        yield name, member.name, functools.partial(tf.extractfile, member)


def _zip_entries(
    zf: zipfile.ZipFile, logger: logging.Logger | None, archive_name: str
) -> Iterator[_Entry]:
    for name, info in zip_file_members(zf, archive_name, logger):
        yield name, info.orig_filename, functools.partial(zf.open, info)


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
