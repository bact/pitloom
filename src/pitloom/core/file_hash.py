# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one chunked reader for a whole file's digests, optionally within a
byte budget, and the one hasher for bytes read some other way (an archive
member, a buffer).

Every whole-file hash Pitloom takes outside a project scan goes through it
(Loom ID registry entries, loom models, datasets and scripts, fragment
envelopes), so none loads a file whole and all refuse a FIFO alike.

A file Pitloom reads and then describes in an SBOM gets both its SHA-256
and its SHA-512 from the one pass (:func:`file_digests`,
:class:`DigestHasher`); a hash used only to key or gate something (the
registry, a dataset's budget check) stays SHA-256 only
(:func:`sha256_digest_and_size`). Neither invents a digest of bytes it did
not read: a dependency's hash copied from a lock file or an index stays
whatever that source gave (SHA-256), so such a dependency carries no
SHA-512, and an aggregate (a Merkle root) is not a file digest at all.

Each reader also keeps the file's first bytes, no more than a Git LFS
pointer can hold, and says whether the file is one (``lfs_pointer``), so
no caller reads a file twice to ask.

See also: :mod:`pitloom.core.lfs_pointer` (the pointer grammar);
:mod:`pitloom.core.dataset_hash` (the dataset ceiling) and
:func:`pitloom.id_registry.sha256_file` (the hex form).
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple

from pitloom.core.lfs_pointer import LfsPointer, PrefixCapture
from pitloom.core.path_confine import NotRegularFileError, open_nonblocking

__all__ = [
    "CHUNK_BYTES",
    "DigestHasher",
    "FileDigests",
    "HexDigests",
    "ReadBudgetExceeded",
    "Sha256Read",
    "file_digests",
    "sha256_digest",
    "sha256_digest_and_size",
    "sha256_read",
]

#: Bytes read per chunk.
CHUNK_BYTES = 1024 * 1024


class ReadBudgetExceeded(Exception):
    """A read went over its byte budget: the file holds more than its size
    said when it was checked (it grew)."""

    def __init__(self, budget: int) -> None:
        super().__init__(f"read more than {budget} bytes")
        #: The budget, in bytes.
        self.budget = budget


class HexDigests(NamedTuple):
    """A file's digests as an SBOM states them: lowercase hex.

    ``sha512`` is ``None`` when only a SHA-256 is known (a ``software_File``
    another producer wrote with one hash only).
    """

    sha256: str
    sha512: str | None = None


@dataclass(frozen=True)
class FileDigests:
    """The raw digests of one read of a file's content, and its size."""

    #: The raw 32-byte SHA-256 digest.
    sha256: bytes
    #: The raw 64-byte SHA-512 digest.
    sha512: bytes
    #: The bytes read.
    size: int
    #: What the bytes state when they are a Git LFS pointer, whole.
    lfs_pointer: LfsPointer | None = None

    def hex(self) -> HexDigests:
        """Both digests as lowercase hex."""
        return HexDigests(self.sha256.hex(), self.sha512.hex())


class Sha256Read(NamedTuple):
    """One SHA-256-only read of a file (:func:`sha256_read`)."""

    #: The raw 32-byte SHA-256 digest.
    sha256: bytes
    #: The bytes read.
    size: int
    #: What the bytes state when they are a Git LFS pointer, whole.
    lfs_pointer: LfsPointer | None


class DigestHasher:
    """SHA-256 and SHA-512 of a byte stream fed chunk by chunk, and the
    Git LFS pointer it is, if any (see :class:`PrefixCapture`)."""

    def __init__(self) -> None:
        self._sha256 = hashlib.sha256()
        self._sha512 = hashlib.sha512()
        self._prefix = PrefixCapture()
        self._size = 0

    def update(self, chunk: bytes) -> None:
        """Add *chunk* to both digests."""
        self._sha256.update(chunk)
        self._sha512.update(chunk)
        self._prefix.feed(chunk)
        self._size += len(chunk)

    def digests(self) -> FileDigests:
        """The digests of everything fed so far."""
        return FileDigests(
            self._sha256.digest(),
            self._sha512.digest(),
            self._size,
            self._prefix.pointer(),
        )


def _read_chunks(
    path: str | os.PathLike[str],
    max_bytes: int | None,
    update: Callable[[bytes], object],
) -> int:
    """Feed *path*'s content to *update* in :data:`CHUNK_BYTES` chunks;
    return the bytes read. Raises as :func:`sha256_digest_and_size`."""
    read = 0
    with open(path, "rb", opener=open_nonblocking) as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise NotRegularFileError
        while chunk := handle.read(CHUNK_BYTES):
            read += len(chunk)
            if max_bytes is not None and read > max_bytes:
                raise ReadBudgetExceeded(max_bytes)
            update(chunk)
    return read


def file_digests(
    path: str | os.PathLike[str], *, max_bytes: int | None = None
) -> FileDigests:
    """The SHA-256 and SHA-512 of *path*'s content and its size, from one
    chunked read: for a file an SBOM describes (its ``verifiedUsing``).

    Raises as :func:`sha256_digest_and_size`.
    """
    hasher = DigestHasher()
    _read_chunks(path, max_bytes, hasher.update)
    return hasher.digests()


def sha256_digest_and_size(
    path: str | os.PathLike[str], *, max_bytes: int | None = None
) -> tuple[bytes, int]:
    """The raw 32-byte SHA-256 digest of *path*'s content and the number of
    bytes read, in :data:`CHUNK_BYTES` chunks: for a hash that only keys or
    gates something (no SHA-512 is computed).

    Opened without waiting and checked to be a regular file once open, so a
    FIFO put in place after the caller's own check fails instead of hanging.

    Raises:
        ReadBudgetExceeded: *max_bytes* is given and more than that many
            bytes were read.
        NotRegularFileError: *path* is not a regular file once open.
        OSError: *path* cannot be opened or read.
    """
    sha256, read, _ = sha256_read(path, max_bytes=max_bytes)
    return sha256, read


def sha256_read(
    path: str | os.PathLike[str], *, max_bytes: int | None = None
) -> Sha256Read:
    """:func:`sha256_digest_and_size`, and the Git LFS pointer *path* is
    (``None`` when it is none), from the same read. Raises as it does."""
    digest = hashlib.sha256()
    prefix = PrefixCapture()

    def update(chunk: bytes) -> None:
        digest.update(chunk)
        prefix.feed(chunk)

    read = _read_chunks(path, max_bytes, update)
    return Sha256Read(digest.digest(), read, prefix.pointer())


def sha256_digest(
    path: str | os.PathLike[str], *, max_bytes: int | None = None
) -> bytes:
    """The raw SHA-256 digest of *path*'s content (see
    :func:`sha256_digest_and_size`, which also raises the same errors)."""
    return sha256_digest_and_size(path, max_bytes=max_bytes)[0]
