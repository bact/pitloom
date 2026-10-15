# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one chunked SHA-256 reader for a whole file, optionally within a
byte budget.

Every whole-file hash Pitloom takes outside a project scan goes through it
(Loom ID registry entries, loom datasets and scripts, fragment envelopes), so
none loads a file whole and all refuse a FIFO alike.

See also: :mod:`pitloom.core.dataset_hash` (the dataset ceiling) and
:func:`pitloom.id_registry.sha256_file` (the hex form).
"""

from __future__ import annotations

import hashlib
import os
import stat

from pitloom.core.path_confine import NotRegularFileError, open_nonblocking

__all__ = [
    "CHUNK_BYTES",
    "ReadBudgetExceeded",
    "sha256_digest",
    "sha256_digest_and_size",
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


def sha256_digest_and_size(
    path: str | os.PathLike[str], *, max_bytes: int | None = None
) -> tuple[bytes, int]:
    """The raw 32-byte SHA-256 digest of *path*'s content and the number of
    bytes read, in :data:`CHUNK_BYTES` chunks.

    Opened without waiting and checked to be a regular file once open, so a
    FIFO put in place after the caller's own check fails instead of hanging.

    Raises:
        ReadBudgetExceeded: *max_bytes* is given and more than that many
            bytes were read.
        NotRegularFileError: *path* is not a regular file once open.
        OSError: *path* cannot be opened or read.
    """
    digest = hashlib.sha256()
    read = 0
    with open(path, "rb", opener=open_nonblocking) as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise NotRegularFileError
        while chunk := handle.read(CHUNK_BYTES):
            read += len(chunk)
            if max_bytes is not None and read > max_bytes:
                raise ReadBudgetExceeded(max_bytes)
            digest.update(chunk)
    return digest.digest(), read


def sha256_digest(
    path: str | os.PathLike[str], *, max_bytes: int | None = None
) -> bytes:
    """The raw SHA-256 digest of *path*'s content (see
    :func:`sha256_digest_and_size`, which also raises the same errors)."""
    return sha256_digest_and_size(path, max_bytes=max_bytes)[0]
