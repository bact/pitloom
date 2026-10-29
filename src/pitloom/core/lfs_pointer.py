# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Git LFS pointer files: the line one opens with, its grammar, and reads
bounded to a pointer's size.

A Git checkout made with LFS off holds, for an LFS-tracked file, a short
text pointer instead of the content: the spec version, the SHA-256 of the
content (its ``oid``) and the content's size. Pitloom records what the
pointer states and never reads more than the pointer itself: the stated
size is only recorded, never used to read or allocate anything.

The grammar is the git-lfs pointer spec (``docs/spec.md``), read strictly:
what git-lfs itself would not write (a blank line, a ``+5`` size, upper-case
hex, trailing white space, a byte order mark) is not a pointer, though the
git-lfs non-strict decoder accepts some of it. An empty file is never a
pointer here (git-lfs reads it as the pointer of empty content).

See also: :mod:`pitloom.extract.ai_model.reader` (``is_git_lfs_pointer``,
the model gate) and :mod:`pitloom.core.file_hash` (the chunked hasher).
"""

from __future__ import annotations

import contextlib
import contextvars
import io
import logging
import os
import re
import stat
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from os.path import normcase, realpath
from typing import Final

from pitloom.core.file_identity import FileId, file_id
from pitloom.core.path_confine import open_nonblocking
from pitloom.logging_config import loggable
from pitloom.messages import LFS_POINTER, LFS_POINTER_SHIPPED, emit

__all__ = [
    "LFS_OPENING_BYTES",
    "LFS_POINTER_MAX_BYTES",
    "LFS_POINTER_METHOD",
    "LfsPointer",
    "PrefixCapture",
    "UnreadPointers",
    "log_pointer_not_read",
    "opens_lfs_pointer",
    "parse_lfs_pointer",
    "read_lfs_pointer",
    "reading_remote_clone",
    "size_text",
    "warn_pointers_not_read",
]

#: The provenance method of a hash copied from a pointer's ``oid``.
LFS_POINTER_METHOD: Final = "lfs_pointer"

#: A pointer is shorter than this many bytes (git-lfs's own cut-off); a
#: longer file is content, however it opens.
LFS_POINTER_MAX_BYTES: Final = 1024

# The spec URLs of the ``version`` line: the current one and the two earlier
# ones the git-lfs decoder still accepts. The whole value must match.
_VERSION_URLS: Final = (
    b"https://git-lfs.github.com/spec/v1",
    b"https://hawser.github.com/spec/v1",
    b"http://git-media.io/v/2",
)
_LINE_ENDS: Final = (b"\n", b"\r\n")
_OPENINGS: Final = tuple(
    b"version " + url + end for url in _VERSION_URLS for end in _LINE_ENDS
)

#: The bytes :func:`opens_lfs_pointer` needs: the longest opening line.
LFS_OPENING_BYTES: Final = max(map(len, _OPENINGS))

# The largest size git-lfs can state (a signed 64-bit integer).
_MAX_SIZE: Final = 2**63 - 1

# One pointer, whole: the version line, optional extension lines, then
# ``oid`` and ``size``, every line ending as the first does (LF or CRLF), the
# last line's ending optional. A bytes pattern, so ``[0-9]`` is ASCII only
# (no Arabic-Indic digits); a size is canonical (no sign, no ``_``, no
# leading zero) and at most 19 digits, so ``int()`` sees ASCII digits only.
_POINTER: Final = re.compile(
    rb"version (?:" + b"|".join(map(re.escape, _VERSION_URLS)) + rb")(?P<end>\r?\n)"
    rb"(?:ext-[0-9]-[0-9A-Za-z_]+ sha256:[0-9a-f]{64}(?P=end))*"
    rb"oid sha256:(?P<oid>[0-9a-f]{64})(?P=end)"
    rb"size (?P<size>0|[1-9][0-9]{0,18})(?:(?P=end))?"
)


_log = logging.getLogger(__name__)

#: Whether the run reads a temporary clone of a remote repository, where
#: ``git lfs pull`` has nothing to pull into.
_REMOTE_CLONE: Final[contextvars.ContextVar[bool]] = contextvars.ContextVar(
    "pitloom_lfs_remote_clone", default=False
)
_ADVICE_PULL: Final = "run 'git lfs pull' for the content"
_ADVICE_CLONE: Final = "clone with git lfs, then run on the directory"
_ADVICE_SHIPPED: Final = "the build did not pull LFS content"


@contextlib.contextmanager
def reading_remote_clone() -> Iterator[None]:
    """Mark the reads within as those of a temporary clone, so the warning
    for a pointer left unread (:func:`warn_pointers_not_read`) tells the
    user to clone with Git LFS instead of to pull."""
    token = _REMOTE_CLONE.set(True)
    try:
        yield
    finally:
        _REMOTE_CLONE.reset(token)


@dataclass(frozen=True)
class LfsPointer:
    """What a Git LFS pointer states about the content it stands in for."""

    #: The content's SHA-256, 64 lowercase hex digits.
    oid: str
    #: The content's size in bytes, as stated (never checked or read).
    size: int


def opens_lfs_pointer(header: bytes) -> bool:
    """Whether *header* opens with a complete pointer ``version`` line, its
    line ending included (``/spec/v1x`` is not one). Needs the first
    :data:`LFS_OPENING_BYTES` bytes; says nothing of the rest."""
    return header.startswith(_OPENINGS)


def parse_lfs_pointer(data: bytes) -> LfsPointer | None:
    """The pointer *data* is, whole, or ``None`` when it is not exactly one
    (see the module docstring); empty *data* is ``None``."""
    if len(data) >= LFS_POINTER_MAX_BYTES:
        return None
    match = _POINTER.fullmatch(data)
    if match is None:
        return None
    size = int(match["size"])
    if size > _MAX_SIZE:
        return None
    return LfsPointer(match["oid"].decode("ascii"), size)


def read_lfs_pointer(path: str | os.PathLike[str]) -> LfsPointer | None:
    """The pointer the file at *path* is, reading at most
    :data:`LFS_POINTER_MAX_BYTES` bytes of it (none when its size already
    rules a pointer out), or ``None``: not a pointer, or not a regular file
    (a FIFO is refused once open, without waiting for a writer).

    Raises:
        OSError: *path* cannot be opened (it is missing, or a directory)
            or read.
    """
    # Unbuffered, so the OS is asked for no more than the bytes wanted.
    with open(path, "rb", buffering=0, opener=open_nonblocking) as handle:
        status = os.fstat(handle.fileno())
        if not stat.S_ISREG(status.st_mode):
            return None
        if status.st_size >= LFS_POINTER_MAX_BYTES:
            return None
        return parse_lfs_pointer(_read_at_most(handle, LFS_POINTER_MAX_BYTES))


def _read_at_most(handle: io.RawIOBase, limit: int) -> bytes:
    """Up to *limit* bytes from *handle*, across short reads."""
    data = bytearray()
    while len(data) < limit:
        chunk = handle.read(limit - len(data))
        if not chunk:
            break
        data += chunk
    return bytes(data)


class PrefixCapture:
    """The leading bytes of a stream fed chunk by chunk, for a reader that
    hashes a file in one pass: holds at most :data:`LFS_POINTER_MAX_BYTES`
    bytes, however much is fed. Holding the cut-off itself, not one byte
    less, is what tells a longer stream from a pointer."""

    def __init__(self) -> None:
        self._prefix = bytearray()

    def feed(self, chunk: bytes) -> None:
        """Note *chunk*, the stream's next bytes."""
        room = LFS_POINTER_MAX_BYTES - len(self._prefix)
        if room > 0:
            self._prefix += chunk[:room]

    @property
    def retained(self) -> int:
        """The bytes held now."""
        return len(self._prefix)

    def pointer(self) -> LfsPointer | None:
        """The pointer the stream fed so far is, whole; ``None`` once
        :data:`LFS_POINTER_MAX_BYTES` or more bytes were fed."""
        return parse_lfs_pointer(bytes(self._prefix))


def size_text(size: int) -> str:
    """*size* as every message and comment states it: ``1 byte``, ``N bytes``."""
    return f"{size} byte" if size == 1 else f"{size} bytes"


def log_pointer_not_read(path: str, pointer: LfsPointer) -> None:
    """The per-file line of a pointer left unread (``--debug`` only)."""
    _log.debug(
        "FILE=%s: Git LFS pointer, content not read; oid sha256:%s, %s",
        loggable(path),
        pointer.oid,
        size_text(pointer.size),
    )


def warn_pointers_not_read(paths: Sequence[str], *, archive: bool = False) -> None:
    """One ``WARNING:`` for all the pointers a run met (none: silent), naming
    the first path in sorted order. *archive*: the pointers were shipped in a
    built artefact (the bytes are recorded as they are), not left by an
    unpulled checkout. Within :func:`reading_remote_clone` the advice for a
    checkout is to clone with Git LFS."""
    if not paths:
        return
    count = f" ({len(paths)} files)" if len(paths) > 1 else ""
    if archive:
        advice = _ADVICE_SHIPPED
    else:
        advice = _ADVICE_CLONE if _REMOTE_CLONE.get() else _ADVICE_PULL
    what = "Git LFS pointer shipped" if archive else "Git LFS pointer, content not read"
    message = LFS_POINTER_SHIPPED if archive else LFS_POINTER
    emit(
        _log,
        message,
        logging.WARNING,
        "FILE=%s: %s%s; %s",
        loggable(min(paths)),
        what,
        count,
        advice,
    )


class UnreadPointers:
    """The Git LFS pointers one run recorded by their ``oid``: the per-file
    ``DEBUG`` line (:func:`log_pointer_not_read`) when a file is first
    noted, and the one summary ``WARNING:`` (:func:`warn_pointers_not_read`)
    when the run ends. A file is one file however it is spelled."""

    def __init__(self) -> None:
        # File identity (st_dev, st_ino), or the real path case-folded by
        # the platform when the file has none, -> the path as first noted
        # (for the messages).
        self._paths: dict[FileId | str, str] = {}

    def note(self, path: str, pointer: LfsPointer, shown: str | None = None) -> None:
        """Note the pointer file at *path* (absolute, or from the current
        directory), stating *pointer*; the messages name it *shown*
        (default: *path*)."""
        key = file_id(path) or normcase(realpath(path))
        if key not in self._paths:
            self._paths[key] = path if shown is None else shown
            log_pointer_not_read(self._paths[key], pointer)

    def warn(self) -> None:
        """The summary warning for the files noted so far (none: silent),
        which are then forgotten, so it is said once."""
        paths = list(self._paths.values())
        self._paths.clear()
        warn_pointers_not_read(paths)
