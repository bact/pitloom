# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Read a file the user named, with the coded error for each failure.

See also: :func:`pitloom._sbom_format.read_given_sbom` (an SBOM file read
through it for ``loom id import`` and ``embed-wheel --sbom``, so both
surfaces code a failure alike).
"""

from __future__ import annotations

import os
import stat
from typing import IO

from pitloom.core.path_confine import open_nonblocking
from pitloom.core.path_probe import is_missing_errno
from pitloom.messages import CodedValueError
from pitloom.messages.files import (
    OVER_CAP,
    SOURCE_LINE,
    Cap,
    file_unreadable_error,
)
from pitloom.messages.targets import input_not_found

__all__ = ["FETCH_MAX_BYTES", "read_given_bytes"]

#: Largest file or response read whole for parsing (an SBOM, a JSON source,
#: a lock or pin file); a caller over it fails with its own ``WARNING:`` or
#: error.
FETCH_MAX_BYTES = 50 * 1024 * 1024
#: The size of one read.
_CHUNK_BYTES = 8192


def _is_directory(exc: OSError, path: str | os.PathLike[str]) -> bool:
    """Whether *exc*, raised opening *path*, says *path* is a directory:
    ``IsADirectoryError`` (POSIX), or ``PermissionError`` on a directory
    (Windows opens none, with ``EACCES``)."""
    return isinstance(exc, IsADirectoryError) or (
        isinstance(exc, PermissionError) and os.path.isdir(path)
    )


def _read_capped(handle: IO[bytes], path: str | os.PathLike[str], use: str) -> bytes:
    """The bytes of *handle*, read in chunks up to :data:`FETCH_MAX_BYTES`
    (looked up now: a test lowers it).

    Raises:
        pitloom.messages.CodedValueError: There are more (``over-cap``).
    """
    limit = FETCH_MAX_BYTES
    data = bytearray()
    while chunk := handle.read(_CHUNK_BYTES):
        data += chunk
        if len(data) > limit:
            cap = Cap(limit, "byte", "JSON-document")
            raise CodedValueError(
                OVER_CAP, line=SOURCE_LINE, file=path, use=use, **cap.reason_values()
            )
    return bytes(data)


def read_given_bytes(path: str | os.PathLike[str], *, kind: str, use: str) -> bytes:
    """The bytes of the regular file at *path*, named *kind* (one of
    :data:`~pitloom.messages._field_tables.INPUT_KINDS`) when it is not
    there or not a regular file, and read *use* (one of
    :data:`~pitloom.messages._field_tables.READ_USES`) when it cannot be
    read. A FIFO opens without waiting for a writer and, like a device or a
    directory, is refused before any read.

    Raises:
        pitloom.messages.CodedFileNotFoundError: Nothing is there, or it is
            not a regular file (``input-not-found``).
        pitloom.messages.CodedValueError: The system refused the read
            (``file-unreadable``), or it is larger than
            :data:`FETCH_MAX_BYTES` (``over-cap``).
    """
    try:
        with open(path, "rb", opener=open_nonblocking) as handle:
            if stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return _read_capped(handle, path, use)
    except OSError as exc:
        if is_missing_errno(exc) or _is_directory(exc, path):
            raise input_not_found(kind, path) from None
        raise file_unreadable_error(exc, file=path, use=use) from exc
    raise input_not_found(kind, path)
