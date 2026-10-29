# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hash a dataset path: a regular file's SHA-256, or a directory's Merkle
root over its files' paths and contents.

Knows nothing of loom or the Loom ID registry: the caller passes the ceiling
and the one file to leave out.

A directory's leaf is ``sha256(relpath + b"\\x00" + digest)``: *relpath* is
the file's path below the directory, ``/``-separated, UTF-8 (an undecodable
POSIX name keeps its bytes); *digest* is the file's raw 32-byte SHA-256.
Leaves are sorted by *relpath* bytes and combined by
:func:`~pitloom.core.models.merkle_root`. The path is in the leaf, so a
renamed file changes the root, and a one-file directory's root is not that
file's own hash.

A Git LFS pointer file (a checkout made with LFS off) stands in by its
``oid``, the SHA-256 of the content: as the file's hash, and as the
*digest* of its leaf, so the hash is the same after ``git lfs pull``; only
the pointer is read. The ceiling still compares the bytes on disk, never
the size a pointer states.

See also: :mod:`pitloom.core.file_hash` (the reader),
:mod:`pitloom.core.walk_rules` (the pruned names) and
:mod:`pitloom._loom_dataset` (the caller).
"""

from __future__ import annotations

import hashlib
import logging
import os
import stat
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Literal

from pitloom.core.file_hash import ReadBudgetExceeded, file_digests, sha256_read
from pitloom.core.lfs_pointer import LfsPointer
from pitloom.core.model_extract_limit import MAX_DATASET_HASH_BYTES_KEY
from pitloom.core.models import merkle_root
from pitloom.core.path_probe import (
    UNLISTABLE_DIR_WARNING,
    UNREADABLE_FILE_WARNING,
    is_missing_errno,
    is_regular_file,
    stat_if_present,
)
from pitloom.core.walk_rules import IGNORED_DIR_NAMES, SameFile
from pitloom.logging_config import Cap, loggable, one_line, warn_over_cap

log = logging.getLogger(__name__)

__all__ = ["DatasetDigest", "PointerAt", "hash_dataset"]

_OMITTED = "dataset hash omitted"
_PURPOSE = "for dataset hashing"

#: A sorted member: its leaf name bytes, its path, its size.
_Member = tuple[bytes, str, int]
#: A Git LFS pointer hashed by its ``oid``: its path, what it states.
PointerAt = tuple[str, LfsPointer]


@dataclass(frozen=True)
class DatasetDigest:
    """What :func:`hash_dataset` found at a path.

    Attributes:
        kind: ``"file"`` (a regular file), ``"dir"`` (a directory), or
            ``None`` (missing, neither, or not stat()-able).
        hex_digest: The file's SHA-256 or the directory's Merkle root,
            lowercase hex; ``None`` when not hashed.
        file_count: The files *hex_digest* covers.
        excluded: The walk met the *exclude* file below the directory and
            left it out, whether or not a root came of it.
        hex_sha512: The file's SHA-512 from the same read, lowercase hex,
            when :func:`hash_dataset` was asked for it (*sha512*); never
            for a directory (a Merkle root is SHA-256 only) or a Git LFS
            pointer (its content was not read).
        lfs_pointers: The Git LFS pointers among the files *hex_digest*
            covers, in leaf order, each hashed by its ``oid``; empty when
            not hashed.
    """

    kind: Literal["file", "dir"] | None
    hex_digest: str | None = None
    file_count: int = 0
    excluded: bool = False
    hex_sha512: str | None = None
    lfs_pointers: tuple[PointerAt, ...] = ()


class _Unlistable(Exception):
    """A directory below the dataset could not be listed."""

    def __init__(self, error: OSError) -> None:
        super().__init__(str(error))
        self.error = error


def _raise_unlistable(error: OSError) -> None:
    """``os.walk``'s *onerror*: stop the walk, a partial root is wrong."""
    raise _Unlistable(error)


def _file_size(path: str | os.PathLike[str]) -> int:
    """*path*'s size from ``stat()``, before anything is opened."""
    return os.stat(path).st_size


def _leaf_name(relpath: str) -> bytes:
    """*relpath* as leaf bytes: NFC, UTF-8, the raw bytes of an undecodable
    POSIX name restored (``surrogateescape``), a Windows lone surrogate kept
    (``surrogatepass``)."""
    # NFC, as a registry key is: macOS lists a name decomposed.
    name = unicodedata.normalize("NFC", relpath)
    try:
        return name.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError:
        return name.encode("utf-8", "surrogatepass")


def _warn_over_ceiling(subject: str, where: str, max_bytes: int) -> None:
    warn_over_cap(
        log,
        Cap(max_bytes, "byte", MAX_DATASET_HASH_BYTES_KEY, subject),
        where,
        _OMITTED,
    )


def _warn_unreadable(where: str, exc: OSError) -> None:
    log.warning(UNREADABLE_FILE_WARNING, loggable(where), _PURPOSE, one_line(exc))


def hash_dataset(
    path: Path, *, max_bytes: int, exclude: Path | None = None, sha512: bool = False
) -> DatasetDigest:
    """Hash the dataset at *path* (absolute, or relative to the current
    directory).

    - A regular file: its SHA-256, and with *sha512* its SHA-512 from the
      same read (for a file an SBOM describes; a lookup key needs none).
    - A directory: the Merkle root over the regular files below it. Below
      *path*, a directory named in
      :data:`~pitloom.core.walk_rules.IGNORED_DIR_NAMES` is pruned and a
      symbolic link to a directory is not followed; the *exclude* file and
      every non-regular file (FIFO, socket, dangling symlink) are skipped,
      never opened.
    - Missing, neither, or not a path at all (a NUL): nothing, silently.

    *max_bytes* caps the bytes hashed, over a whole directory: sizes are
    checked before any file is opened, and every read keeps to what is left,
    so a file that grows is caught. Over it: one ``WARNING:`` and no hash. A
    file that cannot be read (one removed between the walk and its read
    included), or a directory below *path* that cannot be listed: the
    :mod:`~pitloom.core.path_probe` ``WARNING:`` and no hash -- a root over
    part of a directory would be wrong. An empty directory: no hash,
    silently.
    """
    where = os.fspath(path)
    try:
        if is_regular_file(path):
            return _hash_file(where, max_bytes, sha512=sha512)
    except ValueError:  # a NUL: a name, not a path
        return DatasetDigest(None)
    except OSError as exc:  # present, but stat() fails
        _warn_unreadable(where, exc)
        return DatasetDigest(None)
    if os.path.isdir(path):
        return _hash_directory(where, max_bytes, exclude)
    return DatasetDigest(None)


def _hash_file(where: str, max_bytes: int, *, sha512: bool) -> DatasetDigest:
    """The SHA-256 (with *sha512*, the SHA-512 too) of the regular file
    *where*, within *max_bytes*."""
    try:
        if _file_size(where) > max_bytes:
            _warn_over_ceiling("FILE", where, max_bytes)
            return DatasetDigest("file")
        if sha512:
            digests = file_digests(where, max_bytes=max_bytes)
            (hex_digest, hex_sha512), pointer = digests.stated(), digests.lfs_pointer
        else:
            read = sha256_read(where, max_bytes=max_bytes)
            hex_digest, hex_sha512 = read.stated_sha256().hex(), None
            pointer = read.lfs_pointer
    except ReadBudgetExceeded:
        _warn_over_ceiling("FILE", where, max_bytes)
        return DatasetDigest("file")
    except OSError as exc:
        if is_missing_errno(exc):  # gone since it was found
            return DatasetDigest(None)
        _warn_unreadable(where, exc)
        return DatasetDigest("file")
    pointers = () if pointer is None else ((where, pointer),)
    return DatasetDigest(
        "file", hex_digest, 1, hex_sha512=hex_sha512, lfs_pointers=pointers
    )


@dataclass
class _Walk:
    """What a directory walk found: its members, and whether it met the
    *exclude* file (kept when the walk fails part way)."""

    members: list[_Member] = field(default_factory=list)
    excluded: bool = False


def _members(top: str, exclude: Path | None, walk: _Walk) -> None:
    """Every regular file below *top* into *walk*, sorted by leaf name, and
    whether the *exclude* file was among them. One ``stat()`` per file
    gives its type, its identity and its size; one gone before it is
    skipped, as a dangling symlink is.

    Raises:
        _Unlistable: a directory could not be listed.
        OSError: a file's ``stat()`` failed for a reason other than its
            absence.
    """
    excluded_file = None if exclude is None else SameFile(exclude)
    members = walk.members
    for dirpath, dirnames, filenames in os.walk(top, onerror=_raise_unlistable):
        dirnames[:] = [name for name in dirnames if name not in IGNORED_DIR_NAMES]
        rel_dir = os.path.relpath(dirpath, top)
        prefix = "" if rel_dir == os.curdir else PurePath(rel_dir).as_posix() + "/"
        for name in filenames:
            member = os.path.join(dirpath, name)
            member_stat = stat_if_present(member)
            if member_stat is None or not stat.S_ISREG(member_stat.st_mode):
                continue
            if excluded_file is not None and excluded_file.matches(member, member_stat):
                walk.excluded = True
                continue
            members.append((_leaf_name(prefix + name), member, member_stat.st_size))
    members.sort()


def _listed(top: str, exclude: Path | None) -> tuple[list[_Member] | None, bool]:
    """:func:`_members`, and whether the walk met *exclude*; the members are
    ``None`` after the warning for a directory that could not be listed or
    a file that could not be ``stat()``-ed."""
    walk = _Walk()
    try:
        _members(top, exclude, walk)
        return walk.members, walk.excluded
    except _Unlistable as unlistable:
        error = unlistable.error
        log.warning(
            UNLISTABLE_DIR_WARNING,
            loggable(os.fspath(error.filename or top)),
            _PURPOSE,
            one_line(error),
        )
    except OSError as exc:
        _warn_unreadable(os.fspath(exc.filename or top), exc)
    return None, walk.excluded


def _leaves(
    top: str, members: list[_Member], max_bytes: int
) -> tuple[list[bytes], tuple[PointerAt, ...]] | None:
    """The Merkle leaves of *members*, read within *max_bytes* in all, and
    the Git LFS pointers among them; a leaf binds a file's path to its
    content (a pointer's ``oid``). ``None`` after the warning when a file
    grew past what is left or cannot be read."""
    leaves: list[bytes] = []
    pointers: list[PointerAt] = []
    spent = 0
    for leaf_name, member, _size in members:
        try:
            read = sha256_read(member, max_bytes=max_bytes - spent)
        except ReadBudgetExceeded:
            _warn_over_ceiling("DIR", top, max_bytes)
            return None
        except OSError as exc:
            _warn_unreadable(member, exc)
            return None
        spent += read.size
        if read.lfs_pointer is not None:
            pointers.append((member, read.lfs_pointer))
        digest = read.stated_sha256()
        leaves.append(hashlib.sha256(leaf_name + b"\x00" + digest).digest())
    return leaves, tuple(pointers)


def _hash_directory(top: str, max_bytes: int, exclude: Path | None) -> DatasetDigest:
    """The Merkle root of the directory *top*, within *max_bytes* in all."""
    members, excluded = _listed(top, exclude)
    unhashed = DatasetDigest("dir", excluded=excluded)
    if not members:
        return unhashed
    if sum(size for _, _, size in members) > max_bytes:
        _warn_over_ceiling("DIR", top, max_bytes)
        return unhashed
    read = _leaves(top, members, max_bytes)
    if read is None:
        return unhashed
    leaves, pointers = read
    return DatasetDigest(
        "dir", merkle_root(leaves), len(leaves), excluded, lfs_pointers=pointers
    )
