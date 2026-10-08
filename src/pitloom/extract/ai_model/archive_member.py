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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, NamedTuple

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

#: Member names of a model ZIP shown in ``properties.archive_contents``.
ARCHIVE_CONTENTS_SHOWN = 20


def record_archive_contents(
    names: list[str],
    source: str,
    properties: dict[str, str],
    provenance: dict[str, str],
) -> list[str]:
    """Record an archive whose members are *names* in *properties*: the
    first :data:`ARCHIVE_CONTENTS_SHOWN` names as ``archive_contents``
    (ending ``, ... (<N> total)`` when that cuts the list) and the count of
    members as ``archive_member_count``, each with its *provenance*.

    Returns:
        The names shown, for ``raw_metadata["archive_contents"]``.
    """
    shown = names[:ARCHIVE_CONTENTS_SHOWN]
    text = ", ".join(shown)
    if len(names) > ARCHIVE_CONTENTS_SHOWN:
        text += f", ... ({len(names)} total)"
    properties["archive_contents"] = text
    properties["archive_member_count"] = str(len(names))
    field = f"{source} | Field: ZIP archive structure"
    provenance["properties.archive_contents"] = field
    provenance["properties.archive_member_count"] = f"{field} | Method: member_count"
    return shown


# Most central-directory bytes allowed: the entry cap at 256 bytes an entry,
# several times a real entry's. ``zipfile`` reads the directory by its byte
# size, not by the entry count, so an archive may understate the count.
_MAX_ZIP_DIRECTORY_BYTES = MAX_MODEL_ZIP_ENTRIES * 256

_CENTRAL_HEADER = struct.Struct("<4s24x3H12x")  # signature; name/extra/comment
_CENTRAL_SIGNATURE = b"PK\x01\x02"
# Not in typeshed, so by name: the end-record function, the indexes of the
# directory size, the end record's position and its signature in what it
# returns, and the signature and sizes of the ZIP64 records.
_ZIPFILE_PRIVATES = (
    "_EndRecData",
    "_ECD_SIZE",
    "_ECD_LOCATION",
    "_ECD_SIGNATURE",
    "stringEndArchive64",
    "sizeEndCentDir64",
    "sizeEndCentDir64Locator",
)
_UNCHECKABLE = "ZIP archive not checkable: zipfile internals changed"
_MALFORMED = "malformed ZIP central directory"
_ZIP64_RECORD = struct.Struct("<4sQ2H2L4Q")
_ZIP64_LOCATOR = struct.Struct("<4sLQL")
_END_RECORD = struct.Struct("<4s4H2LH")


class _ZipfileApi(NamedTuple):
    """The private ``zipfile`` names this reads (see ``_ZIPFILE_PRIVATES``)."""

    end_record: Callable[[IO[bytes]], Any]
    size_at: int
    location_at: int
    signature_at: int
    zip64_signature: bytes
    zip64_record_size: int
    zip64_locator_size: int


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


def _zip64_start_shift(api: _ZipfileApi) -> int:
    """Bytes ``ZipFile`` takes off the directory start for a ZIP64 archive.

    Two conventions exist among releases of one Python version. With the
    CVE-2025-8291 fix ``zipfile._EndRecData`` rewrites the end record's
    position to the ZIP64 record's: no shift. Without it the position stays
    the plain end record's and ``ZipFile._RealGetContents`` takes the two
    ZIP64 records' sizes off. Asked of the running ``zipfile`` through an
    empty ZIP64 archive built here (record at 0, then locator, then end
    record), not guessed from a version number.

    Raises:
        pitloom.extract.ai_model.limits.ModelLimitExceeded: ``zipfile``
            answered by neither convention.
    """
    data = (
        _ZIP64_RECORD.pack(api.zip64_signature, 44, 45, 45, 0, 0, 0, 0, 0, 0)
        + _ZIP64_LOCATOR.pack(b"PK\x06\x07", 0, 0, 1)
        + _END_RECORD.pack(
            b"PK\x05\x06", 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0
        )
    )
    both = api.zip64_record_size + api.zip64_locator_size
    try:
        endrec = api.end_record(io.BytesIO(data))
        values = (
            endrec[api.signature_at],
            endrec[api.size_at],
            endrec[api.location_at],
        )
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        raise ModelLimitExceeded(_UNCHECKABLE) from exc
    signature, size, location = values
    if (signature, size) == (api.zip64_signature, 0) and location in (0, both):
        return both if location else 0
    raise ModelLimitExceeded(_UNCHECKABLE)


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
    prepended data) and, for a ZIP64 archive, :func:`_zip64_start_shift`.

    Raises:
        pitloom.extract.ai_model.limits.ModelLimitExceeded: ``zipfile`` has
            no such function or constants, or returned something else than
            the record this reads: the file cannot be checked, so it is not
            read.
    """
    try:
        api = _ZipfileApi(*(getattr(zipfile, name) for name in _ZIPFILE_PRIVATES))
    except AttributeError as exc:
        raise ModelLimitExceeded(_UNCHECKABLE) from exc
    shift = _zip64_start_shift(api)
    try:
        endrec = api.end_record(fh)
    except (OSError, zipfile.BadZipFile):
        return None  # ZipFile turns both into BadZipFile
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        raise ModelLimitExceeded(_UNCHECKABLE) from exc
    if not endrec:
        return None
    try:
        size, location = int(endrec[api.size_at]), int(endrec[api.location_at])
        is_zip64 = endrec[api.signature_at] == api.zip64_signature
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise ModelLimitExceeded(_UNCHECKABLE) from exc
    start = location - size - (shift if is_zip64 else 0)
    if start < 0:
        # zipfile refuses its own negative start, but ours being negative
        # while its is not would be a disagreement: refuse, never bypass.
        raise ModelLimitExceeded(_MALFORMED)
    return start, size


def _count_exceeds_cap(fh: IO[bytes], start: int, size: int, cap: int) -> bool:
    """Whether the central directory at *start* holds more than *cap* entries.

    Walked as ``ZipFile._RealGetContents`` walks it: header by header (46
    bytes, a name, an extra field and a comment each), until *size* bytes are
    consumed; the end record's own counts are not used, as ``zipfile``
    ignores them. Never holds more than one header.

    Raises:
        pitloom.extract.ai_model.limits.ModelLimitExceeded: A header is not
            one, or is cut short by the end of the directory or the file.
            ``zipfile`` raises on those too, but a disagreement about where
            the directory is must never end the walk as "within the cap".
    """
    count = consumed = 0
    while consumed < size:
        fh.seek(start + consumed)
        header = fh.read(_CENTRAL_HEADER.size)
        if (
            size - consumed < _CENTRAL_HEADER.size
            or len(header) != _CENTRAL_HEADER.size
            or not header.startswith(_CENTRAL_SIGNATURE)
        ):
            raise ModelLimitExceeded(_MALFORMED)
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
        pitloom.extract.ai_model.limits.ModelLimitExceeded: Over a bound,
            not checkable (see :func:`_directory_start_and_size`) or a
            directory that is not walkable (see :func:`_count_exceeds_cap`).
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
