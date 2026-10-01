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
import os
import struct
import zipfile
from pathlib import Path
from typing import IO

from pitloom.extract.ai_model.limits import ModelLimitExceeded, charge_read

#: Largest metadata member read whole: 8 MiB. A ``.keras`` ``config.json``,
#: a ``.pt`` ``data.pkl`` (structure only, the tensors are other members)
#: and a PT2 ``model.json`` are kilobytes to a few MiB even for a model with
#: thousands of layers; nothing Pitloom reads needs more.
MAX_ARCHIVE_MEMBER_BYTES = 8 * 1024 * 1024


#: Most entries a model ZIP (``.keras``, ``.pt``, ``.pt2``, ``.npz``) may
#: declare. ``zipfile`` builds a ``ZipInfo`` for every entry (about 600 bytes
#: each) before a reader looks at one; a real checkpoint has a file per
#: tensor, a few thousand at most.
MAX_MODEL_ZIP_ENTRIES = 100_000

# Most central-directory bytes allowed: the entry cap at 256 bytes an entry,
# several times a real entry's. ``zipfile`` reads the directory by its byte
# size, not by the entry count, so an archive may understate the count.
_MAX_ZIP_DIRECTORY_BYTES = MAX_MODEL_ZIP_ENTRIES * 256

_EOCD_SIGNATURE = b"PK\x05\x06"
_EOCD = struct.Struct("<4s4H2LH")  # signature, 4 counts, size, offset, comment
_ZIP64_LOCATOR_SIGNATURE = b"PK\x06\x07"
_ZIP64_LOCATOR_SIZE = 20
_ZIP64_EOCD_SIGNATURE = b"PK\x06\x06"
_ZIP64_EOCD = struct.Struct("<4sQ2H2L4Q")  # ... entries on disk, entries, size
_MAX_ZIP_COMMENT = 0xFFFF
_MAX_PLAIN_COUNT = 0xFFFF  # a plain count that overflowed: see the ZIP64 record
_MAX_PLAIN_SIZE = 0xFFFFFFFF


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


def _read_at(fh: IO[bytes], position: int, size: int) -> bytes:
    fh.seek(position)
    return fh.read(size)


def _declared_directory(fh: IO[bytes]) -> tuple[int, int] | None:
    """The entry count and byte size of the central directory a ZIP file
    declares, from its end-of-central-directory record (and the ZIP64 one
    when there is one); the larger where the fields disagree, a plain field
    that overflowed (its maximum) giving way to the ZIP64 one. ``None`` when
    there is no such record: ``zipfile`` then fails on its own.

    The record is found as ``zipfile`` finds it: the last signature in the
    final 64 KiB plus 22 bytes. Nothing else is read.
    """
    end = fh.seek(0, os.SEEK_END)
    base = max(0, end - (_EOCD.size + _MAX_ZIP_COMMENT))
    tail = _read_at(fh, base, end - base)
    start = tail.rfind(_EOCD_SIGNATURE)
    if start < 0 or len(tail) - start < _EOCD.size:
        return None
    _, _, _, on_disk, total, size, _, _ = _EOCD.unpack_from(tail, start)
    count = max(on_disk, total)
    # The ZIP64 record sits right before its locator, which sits right
    # before the end record.
    record_at = base + start - _ZIP64_LOCATOR_SIZE - _ZIP64_EOCD.size
    if record_at >= 0:
        locator = _read_at(fh, record_at + _ZIP64_EOCD.size, _ZIP64_LOCATOR_SIZE)
        record = _read_at(fh, record_at, _ZIP64_EOCD.size)
        if locator.startswith(_ZIP64_LOCATOR_SIGNATURE) and record.startswith(
            _ZIP64_EOCD_SIGNATURE
        ):
            _, _, _, _, _, _, on_disk64, total64, size64, _ = _ZIP64_EOCD.unpack(record)
            # A plain field at its maximum only says "see the ZIP64 record".
            plain = [c for c in (on_disk, total) if c != _MAX_PLAIN_COUNT]
            count = max(on_disk64, total64, *plain)
            size = size64 if size == _MAX_PLAIN_SIZE else max(size, size64)
    return count, size


def check_zip_bounds(path: Path) -> None:
    """Refuse a ZIP file declaring more than :data:`MAX_MODEL_ZIP_ENTRIES`
    entries, or a central directory too large for that many, before anything
    builds a ``ZipInfo`` per entry. Reads at most 64 KiB and some bytes.

    Raises:
        pitloom.extract.ai_model.limits.ModelLimitExceeded: Over a bound.
        OSError: The file cannot be read.
    """
    with path.open("rb") as fh:
        declared = _declared_directory(fh)
    if declared is None:
        return
    count, size = declared
    if count > MAX_MODEL_ZIP_ENTRIES:
        raise ModelLimitExceeded(f"ZIP archive of {count} entries")
    if size > _MAX_ZIP_DIRECTORY_BYTES:
        raise ModelLimitExceeded(f"ZIP central directory of {size} bytes")


def open_model_zip(path: Path) -> zipfile.ZipFile:
    """Open *path* as a ZIP archive, after :func:`check_zip_bounds`. Every
    reader that opens a model as a ZIP opens it through this.

    Raises:
        pitloom.extract.ai_model.limits.ModelLimitExceeded: Over a bound.
        zipfile.BadZipFile: Not a ZIP archive.
        OSError: The file cannot be read.
    """
    check_zip_bounds(path)
    return zipfile.ZipFile(str(path), "r")
