# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Byte builders for the model-ZIP bound tests: central-directory headers and
the end records around them, laid out by hand.

See also: :mod:`tests.extract.ai_model.test_zip_bounds` and
:mod:`tests.extract.ai_model.test_zip_bounds_zipfile`.
"""

from __future__ import annotations

import io
import struct
import zipfile

CAP = 3
MAX_COMMENT = 0xFFFF
HEADER = 46
FFFF = 0xFFFF
FFFFFFFF = 0xFFFFFFFF


def header(name: int = 0, extra: int = 0, comment: int = 0) -> bytes:
    """One central-directory header (what ``zipfile`` reads, nothing more)."""
    fixed = struct.pack(
        "<4s4B4HL2L5H2L",
        b"PK\x01\x02",
        20, 0, 20, 0,
        0, 0, 0, 0,
        0, 0, 0,
        name, extra, comment, 0, 0,
        0, 0,
    )  # fmt: skip
    return fixed + b"n" * name + b"e" * extra + b"c" * comment


def directory(entries: int) -> bytes:
    return header() * entries


def directory_of(one_header: bytes, entries: int) -> bytes:
    d = one_header * entries
    return d + eocd(entries, len(d))


def eocd(
    count: int,
    size: int,
    offset: int = 0,
    comment: bytes = b"",
    *,
    disk: int = 0,
    disk_cd: int = 0,
) -> bytes:
    return struct.pack(
        "<4s4H2LH",
        b"PK\x05\x06", disk, disk_cd, count, count, size, offset, len(comment),
    ) + comment  # fmt: skip


def zip64_record(count: int, size: int, offset: int, extensible: bytes = b"") -> bytes:
    return struct.pack(
        "<4sQ2H2L4Q",
        b"PK\x06\x06", 44 + len(extensible), 45, 45, 0, 0, count, count, size, offset,
    ) + extensible  # fmt: skip


def locator(reloff: int, disks: int = 1) -> bytes:
    return struct.pack("<4sLQL", b"PK\x06\x07", 0, reloff, disks)


def archive(entries: int, comment: bytes = b"", prefix: bytes = b"") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.comment = comment
        for i in range(entries):
            zf.writestr(f"{i}", b"")
    return prefix + buf.getvalue()


def zip64_fixed(n: int) -> bytes:
    """The ZIP64 record at the fixed position behind the directory, no
    extensible data: the one layout every ``zipfile`` release reads alike."""
    d = directory(n)
    return d + zip64_record(n, len(d), 0) + locator(len(d)) + eocd(FFFF, FFFFFFFF)
