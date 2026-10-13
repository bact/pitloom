# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Whether a path lies inside a directory, and opening a file only when it
does: the one confinement check every reader of a project's own files
(licence sources, ``[tool.setuptools.dynamic]`` requirements files) uses.

See also: :mod:`pitloom.core.file_identity` (identity by
``(st_dev, st_ino)``).
"""

from __future__ import annotations

import errno
import os
import stat
from contextlib import ExitStack
from pathlib import Path, PurePath
from typing import BinaryIO

from pitloom.core.file_identity import file_id

#: Opens a FIFO without waiting for a writer (no such flag on Windows).
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
#: Opens the resolved path again, to compare it with the file opened.
_REOPEN_FLAGS = os.O_RDONLY | getattr(os, "O_BINARY", 0) | _NONBLOCK


class NotRegularFileError(OSError):
    """The file to read is not a regular file."""

    def __init__(self) -> None:
        super().__init__("not a regular file")


class OutsideRootError(OSError):
    """The file to read is outside the directory it must be in, or is not
    the file its path resolved to when it was checked."""

    def __init__(self) -> None:
        super().__init__("outside the project directory")


def is_inside(path: PurePath, root: PurePath) -> bool:
    """Whether *path* is *root* or lies below it, both already resolved.

    By spelling first, else by file identity: *path* or one of its
    ancestors is the file *root* is (a case-insensitive file system spells
    one directory two ways, and ``resolve()`` keeps a symlink target's
    spelling). A *root* with no identity (missing, or ``st_ino`` 0 on
    FAT/exFAT) is matched by spelling only. Never raises.
    """
    if path == root or root in path.parents:
        return True
    root_id = file_id(root)
    return root_id is not None and any(
        file_id(ancestor) == root_id for ancestor in (path, *path.parents)
    )


def _open_nonblocking(path: str, flags: int) -> int:
    return os.open(path, flags | _NONBLOCK)


def open_inside(written: Path, root: Path) -> BinaryIO:
    """*written*, opened for binary reading as written (the OS, not
    ``resolve()``, decides whether ``missing/../a.txt`` exists), when it is
    a regular file inside *root*.

    The check follows the open and is made on the opened file: *written*
    resolved then must be inside *root* (:func:`is_inside`) and, opened
    again, be the very file opened, by ``(st_dev, st_ino)``, so a symlink
    swapped while opening is refused rather than followed out. On a file
    system without file identity (``st_ino`` 0), only the resolved path is
    checked. A dangling symlink fails the open as missing.

    Raises:
        NotRegularFileError: *written* is not a regular file.
        OutsideRootError: it is outside *root*, or not the file opened.
        OSError: it cannot be opened, or resolved (a symlink loop).
        ValueError: its path holds a NUL.
    """
    if not stat.S_ISREG(os.stat(written).st_mode):
        raise NotRegularFileError
    with ExitStack() as refused:
        handle = refused.enter_context(open(written, "rb", opener=_open_nonblocking))
        _check_opened(handle, written, root)
        refused.pop_all()  # checked: the caller closes it
    return handle


def _check_opened(handle: BinaryIO, written: Path, root: Path) -> None:
    """Raise unless *handle*, opened from *written*, is a regular file
    inside *root* (see :func:`open_inside`)."""
    opened = os.fstat(handle.fileno())
    if not stat.S_ISREG(opened.st_mode):
        raise NotRegularFileError
    try:
        resolved = written.resolve()
        inside = is_inside(resolved, root.resolve())
    except RuntimeError as exc:  # a symlink loop, on 3.10-3.12
        raise OSError(errno.ELOOP, str(exc)) from exc
    if not inside or (opened.st_ino and not _opened_at(resolved, opened)):
        raise OutsideRootError


def _opened_at(resolved: Path, opened: os.stat_result) -> bool:
    """Whether *resolved*, opened again, is the file *opened* describes.

    Both identities come from ``fstat()``: on Windows ``stat()`` of a
    path may fill ``st_dev``/``st_ino`` from another API than ``fstat()``
    of a handle does."""
    try:
        fd = os.open(resolved, _REOPEN_FLAGS)
    except OSError:  # gone since: not the file checked
        return False
    try:
        now = os.fstat(fd)
    finally:
        os.close(fd)
    return (now.st_dev, now.st_ino) == (opened.st_dev, opened.st_ino)
