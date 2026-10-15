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

See also: :mod:`pitloom.core.file_hash` (the reader),
:mod:`pitloom.core.walk_rules` (the pruned names) and
:mod:`pitloom._loom_dataset` (the caller).
"""

from __future__ import annotations

import hashlib
import logging
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Literal

from pitloom.core.file_hash import ReadBudgetExceeded, sha256_digest_and_size
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

__all__ = ["DatasetDigest", "hash_dataset"]

_OMITTED = "dataset hash omitted"
_PURPOSE = "for dataset hashing"

#: A sorted member: its leaf name bytes, its path, its size.
_Member = tuple[bytes, str, int]


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
    """

    kind: Literal["file", "dir"] | None
    hex_digest: str | None = None
    file_count: int = 0
    excluded: bool = False


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
    """*relpath* as leaf bytes: UTF-8, the raw bytes of an undecodable POSIX
    name restored (``surrogateescape``), a Windows lone surrogate kept
    (``surrogatepass``)."""
    try:
        return relpath.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError:
        return relpath.encode("utf-8", "surrogatepass")


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
    path: Path, *, max_bytes: int, exclude: Path | None = None
) -> DatasetDigest:
    """Hash the dataset at *path* (absolute, or relative to the current
    directory).

    - A regular file: its SHA-256.
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
            return _hash_file(where, max_bytes)
    except ValueError:  # a NUL: a name, not a path
        return DatasetDigest(None)
    except OSError as exc:  # present, but stat() fails
        _warn_unreadable(where, exc)
        return DatasetDigest(None)
    if os.path.isdir(path):
        return _hash_directory(where, max_bytes, exclude)
    return DatasetDigest(None)


def _hash_file(where: str, max_bytes: int) -> DatasetDigest:
    """The SHA-256 of the regular file *where*, within *max_bytes*."""
    try:
        if _file_size(where) > max_bytes:
            _warn_over_ceiling("FILE", where, max_bytes)
            return DatasetDigest("file")
        digest, _read = sha256_digest_and_size(where, max_bytes=max_bytes)
    except ReadBudgetExceeded:
        _warn_over_ceiling("FILE", where, max_bytes)
        return DatasetDigest("file")
    except OSError as exc:
        if is_missing_errno(exc):  # gone since it was found
            return DatasetDigest(None)
        _warn_unreadable(where, exc)
        return DatasetDigest("file")
    return DatasetDigest("file", digest.hex(), 1)


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


def _leaves(top: str, members: list[_Member], max_bytes: int) -> list[bytes] | None:
    """The Merkle leaves of *members*, read within *max_bytes* in all; a
    leaf binds a file's path to its content. ``None`` after the warning
    when a file grew past what is left or cannot be read."""
    leaves: list[bytes] = []
    spent = 0
    for leaf_name, member, _size in members:
        try:
            digest, read = sha256_digest_and_size(member, max_bytes=max_bytes - spent)
        except ReadBudgetExceeded:
            _warn_over_ceiling("DIR", top, max_bytes)
            return None
        except OSError as exc:
            _warn_unreadable(member, exc)
            return None
        spent += read
        leaves.append(hashlib.sha256(leaf_name + b"\x00" + digest).digest())
    return leaves


def _hash_directory(top: str, max_bytes: int, exclude: Path | None) -> DatasetDigest:
    """The Merkle root of the directory *top*, within *max_bytes* in all."""
    members, excluded = _listed(top, exclude)
    unhashed = DatasetDigest("dir", excluded=excluded)
    if not members:
        return unhashed
    if sum(size for _, _, size in members) > max_bytes:
        _warn_over_ceiling("DIR", top, max_bytes)
        return unhashed
    leaves = _leaves(top, members, max_bytes)
    if leaves is None:
        return unhashed
    return DatasetDigest("dir", merkle_root(leaves), len(leaves), excluded)
