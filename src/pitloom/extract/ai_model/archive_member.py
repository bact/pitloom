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
import struct
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

from pitloom.extract.ai_model.limits import ModelLimitExceeded, charge_read

#: Largest metadata member read whole: 8 MiB. A ``.keras`` ``config.json``,
#: a ``.pt`` ``data.pkl`` (structure only, the tensors are other members)
#: and a PT2 ``model.json`` are kilobytes to a few MiB even for a model with
#: thousands of layers; nothing Pitloom reads needs more.
MAX_ARCHIVE_MEMBER_BYTES = 8 * 1024 * 1024


#: Most entries a model ZIP (``.keras``, ``.pt``, ``.pt2``, ``.npz``) may
#: hold. ``zipfile`` builds a ``ZipInfo`` for every entry (about 600 bytes
#: each) before a reader looks at one; a real checkpoint has a file per
#: tensor, a few thousand at most.
MAX_MODEL_ZIP_ENTRIES = 100_000

# Most central-directory bytes allowed: the entry cap at 256 bytes an entry,
# several times a real entry's. ``zipfile`` reads the directory by its byte
# size, not by the entry count, so an archive may understate the count.
_MAX_ZIP_DIRECTORY_BYTES = MAX_MODEL_ZIP_ENTRIES * 256

_CENTRAL_HEADER = struct.Struct("<4s24x3H12x")  # signature; name/extra/comment
_CENTRAL_SIGNATURE = b"PK\x01\x02"
# Not in typeshed, so by name: the end-record function, and the indexes of
# the directory size and of the end record's position in what it returns.
_ZIPFILE_PRIVATES = ("_EndRecData", "_ECD_SIZE", "_ECD_LOCATION")
_UNCHECKABLE = "ZIP archive not checkable: zipfile internals changed"


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


def _directory_start_and_size(fh: IO[bytes]) -> tuple[int, int] | None:
    """Where ``zipfile`` will start reading the central directory of *fh*
    and its byte size, or ``None`` where ``zipfile`` itself will refuse the
    file (no end record, a multi-disk or corrupt ZIP64 one).

    The end record comes from ``zipfile._EndRecData``, the function
    ``ZipFile`` calls, so both always pick the same one (the ZIP64 record is
    found through its locator, the search window differs between Python
    versions) and nothing here parses an end record. The start is
    ``offset + concat`` of ``ZipFile._RealGetContents``, which is the end
    record's own position less the directory size (``concat`` absorbs any
    prepended data).

    Raises:
        pitloom.extract.ai_model.limits.ModelLimitExceeded: ``zipfile`` has
            no such function or constants, or returned something else than
            the record this reads: the file cannot be checked, so it is not
            read.
    """
    try:
        end_record_data, size_at, location_at = (
            getattr(zipfile, name) for name in _ZIPFILE_PRIVATES
        )
    except AttributeError as exc:
        raise ModelLimitExceeded(_UNCHECKABLE) from exc
    try:
        endrec = end_record_data(fh)
    except (OSError, zipfile.BadZipFile):
        return None  # ZipFile turns both into BadZipFile
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ModelLimitExceeded(_UNCHECKABLE) from exc
    if not endrec:
        return None
    try:
        size, location = int(endrec[size_at]), int(endrec[location_at])
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise ModelLimitExceeded(_UNCHECKABLE) from exc
    start = location - size
    return (start, size) if start >= 0 else None


def _count_exceeds_cap(fh: IO[bytes], start: int, size: int, cap: int) -> bool:
    """Whether the central directory at *start* holds more than *cap* entries.

    Walked as ``ZipFile._RealGetContents`` walks it: header by header (46
    bytes, a name, an extra field and a comment each), until *size* bytes are
    consumed; the end record's own counts are not used, as ``zipfile``
    ignores them. A header that is not one ends the walk: ``zipfile`` raises
    on it. Never holds more than one header.
    """
    count = consumed = 0
    while consumed < size:
        fh.seek(start + consumed)
        header = fh.read(_CENTRAL_HEADER.size)
        if len(header) != _CENTRAL_HEADER.size or not header.startswith(
            _CENTRAL_SIGNATURE
        ):
            return False
        count += 1
        if count > cap:
            return True
        _, *lengths = _CENTRAL_HEADER.unpack(header)
        consumed += _CENTRAL_HEADER.size + sum(lengths)
    return False


def check_zip_bounds(fh: IO[bytes]) -> None:
    """Refuse a ZIP file, open as *fh*, holding more than
    :data:`MAX_MODEL_ZIP_ENTRIES` entries or a central directory over its
    byte cap, before ``zipfile`` builds a ``ZipInfo`` per entry. The entries
    are counted as ``zipfile`` reads them, whatever the end record says.
    *fh* is left at an arbitrary position.

    Raises:
        pitloom.extract.ai_model.limits.ModelLimitExceeded: Over a bound, or
            not checkable (see :func:`_directory_start_and_size`).
        OSError: The file cannot be read.
    """
    found = _directory_start_and_size(fh)
    if found is None:
        return
    start, size = found
    if size > _MAX_ZIP_DIRECTORY_BYTES:
        raise ModelLimitExceeded(f"ZIP central directory of {size} bytes")
    # Looked up at call time: a test lowers the module constant.
    cap = MAX_MODEL_ZIP_ENTRIES
    if _count_exceeds_cap(fh, start, size, cap):
        raise ModelLimitExceeded(f"ZIP archive of more than {cap} entries")


@contextmanager
def open_model_binary(path: Path) -> Iterator[IO[bytes]]:
    """Open *path* for reading, after :func:`check_zip_bounds`, as the one
    handle the archive is then parsed from (a second open could see another
    file). For a reader that hands the handle to something other than
    ``zipfile``, such as ``numpy.load``.

    Raises:
        pitloom.extract.ai_model.limits.ModelLimitExceeded: Over a bound.
        OSError: The file cannot be read.
    """
    with path.open("rb") as fh:
        check_zip_bounds(fh)
        fh.seek(0)
        yield fh


@contextmanager
def open_model_zip(path: Path) -> Iterator[zipfile.ZipFile]:
    """Open *path* as a ZIP archive, after :func:`check_zip_bounds`, from the
    handle that was checked. Every reader that opens a model as a ZIP opens
    it through this or :func:`open_model_binary`.

    Raises:
        pitloom.extract.ai_model.limits.ModelLimitExceeded: Over a bound.
        zipfile.BadZipFile: Not a ZIP archive.
        OSError: The file cannot be read.
    """
    with open_model_binary(path) as fh, zipfile.ZipFile(fh, "r") as zf:
        yield zf
