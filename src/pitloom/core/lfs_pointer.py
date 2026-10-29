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

import io
import os
import re
import stat
from dataclasses import dataclass
from typing import Final

from pitloom.core.path_confine import open_nonblocking

__all__ = [
    "LFS_OPENING_BYTES",
    "LFS_POINTER_MAX_BYTES",
    "LFS_POINTER_METHOD",
    "LfsPointer",
    "PrefixCapture",
    "opens_lfs_pointer",
    "parse_lfs_pointer",
    "read_lfs_pointer",
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
