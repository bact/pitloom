# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Bounded reads of a member inside a model archive (``.keras``, ``.pt``,
``.pt2``).

The archive is untrusted, and a member's declared size is not: a small
archive may inflate to gigabytes. Every reader reads a metadata member
through :func:`read_archive_member`, which never holds more than
:data:`MAX_ARCHIVE_MEMBER_BYTES` of it.

See also: :mod:`pitloom.extract.scanner` (reports
:class:`ArchiveMemberTooLarge` as one warning and keeps the model).
"""

from __future__ import annotations

import io
import zipfile

from pitloom.extract.ai_model.limits import ModelLimitExceeded, charge_read

#: Largest metadata member read whole: 8 MiB. A ``.keras`` ``config.json``,
#: a ``.pt`` ``data.pkl`` (structure only, the tensors are other members)
#: and a PT2 ``model.json`` are kilobytes to a few MiB even for a model with
#: thousands of layers; nothing Pitloom reads needs more.
MAX_ARCHIVE_MEMBER_BYTES = 8 * 1024 * 1024


class ArchiveMemberTooLarge(ModelLimitExceeded):
    """A member inside a model archive holds more than
    :data:`MAX_ARCHIVE_MEMBER_BYTES`.

    A :class:`~pitloom.extract.ai_model.limits.ModelLimitExceeded`: a
    reader's ``except Exception`` fallback must let it through.

    Attributes:
        member: The member's name in the archive.
        limit: The cap in bytes.
    """

    def __init__(self, member: str, limit: int) -> None:
        super().__init__(f"archive member larger than {limit} bytes")
        self.member = member
        self.limit = limit


def read_archive_member(zf: zipfile.ZipFile, name: str) -> bytes:
    """Return member *name* of *zf*.

    Raises:
        ArchiveMemberTooLarge: The member holds more than
            :data:`MAX_ARCHIVE_MEMBER_BYTES`; at most one byte more than
            that was read.
        pitloom.extract.ai_model.limits.ScanBudgetExceeded: A producer is
            counting reads and its budget is spent.
    """
    # Looked up at call time: a test lowers the module constant.
    limit = MAX_ARCHIVE_MEMBER_BYTES
    with zf.open(name) as fh:
        data = fh.read(limit + 1)
    if len(data) > limit:
        raise ArchiveMemberTooLarge(name, limit)
    charge_read(len(data))
    return data


def open_archive_member(zf: zipfile.ZipFile, name: str) -> io.BytesIO:
    """Member *name* of *zf* as a seekable in-memory stream (for a parser
    that wants one). Bounded as :func:`read_archive_member`."""
    return io.BytesIO(read_archive_member(zf, name))
