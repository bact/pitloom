# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Read a file the user named, with the coded error for each failure.

See also: :mod:`pitloom.id_registry._sbom_read` (``loom id import``) and
:mod:`pitloom._embed_generate` (``embed-wheel --sbom``), which read the
same SBOM file through it so both surfaces code a failure alike.
"""

from __future__ import annotations

import os

from pitloom.core.path_probe import is_missing_errno
from pitloom.messages.files import file_unreadable_error
from pitloom.messages.targets import input_not_found

__all__ = ["read_given_bytes"]


def read_given_bytes(path: str | os.PathLike[str], *, kind: str, use: str) -> bytes:
    """The bytes of the file at *path*, named *kind* (one of
    :data:`~pitloom.messages._field_tables.INPUT_KINDS`) when it is not
    there and read *use* (one of
    :data:`~pitloom.messages._field_tables.READ_USES`) when it cannot be read.

    Raises:
        pitloom.messages.CodedFileNotFoundError: Nothing is there
            (``input-not-found``).
        pitloom.messages.CodedValueError: The system refused the read
            (``file-unreadable``).
    """
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as exc:
        if is_missing_errno(exc):
            raise input_not_found(kind, path) from None
        raise file_unreadable_error(exc, file=path, use=use) from exc
