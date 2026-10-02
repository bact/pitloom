# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Wheels with one member damaged in a way ``zipfile`` reports on reading:
a corrupt deflate stream, a bad CRC, an encryption flag, a name that is not
UTF-8 in the local header.

See also: tests/extract/test_wheel_identity.py and
tests/test_wheel_identity_surfaces.py (the users).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

WHEEL = "demo-1.0-py3-none-any.whl"
REAL = "Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n"


def patch_first(path: Path, old: bytes, new: bytes) -> None:
    data = path.read_bytes()
    assert old in data  # the damage is real
    path.write_bytes(data.replace(old, new, 1))


def corrupt_deflate(path: Path, member: str) -> None:
    with zipfile.ZipFile(path) as zf:
        info = zf.getinfo(member)
        start = info.header_offset + 30 + len(info.filename) + len(info.extra)
    data = bytearray(path.read_bytes())
    data[start : start + 8] = b"\xff" * 8  # an invalid deflate block type
    path.write_bytes(bytes(data))


def bad_crc(path: Path, member: str) -> None:
    with zipfile.ZipFile(path) as zf:
        info = zf.getinfo(member)
        start = info.header_offset + 30 + len(info.filename) + len(info.extra)
    data = bytearray(path.read_bytes())
    data[start] ^= 0xFF
    path.write_bytes(bytes(data))


def entry_offsets(path: Path, member: str) -> tuple[int, int]:
    """Offsets of *member*'s local and central header in the file *path*."""
    with zipfile.ZipFile(path) as zf:
        local = zf.getinfo(member).header_offset
    data = path.read_bytes()
    needle = member.encode()
    at = -1
    while (at := data.find(b"PK\x01\x02", at + 1)) != -1:
        length = int.from_bytes(data[at + 28 : at + 30], "little")
        if data[at + 46 : at + 46 + length] == needle:
            return local, at
    raise AssertionError("no central header")


def encrypted(path: Path, member: str) -> None:
    """Set the traditional-encryption flag on *member* alone."""
    local, central = entry_offsets(path, member)
    data = bytearray(path.read_bytes())
    data[local + 6] |= 0x01
    data[central + 8] |= 0x01
    path.write_bytes(bytes(data))


def bad_name(path: Path, _member: str) -> None:
    patch_first(path, "é".encode(), b"\xc3\xff")


DAMAGE = {
    "deflate": ("demo/bad.py", zipfile.ZIP_DEFLATED, corrupt_deflate),
    "crc": ("demo/bad.py", zipfile.ZIP_STORED, bad_crc),
    "encrypted": ("demo/bad.py", zipfile.ZIP_STORED, encrypted),
    "name": ("demo/é.py", zipfile.ZIP_STORED, bad_name),
}
METADATA = "demo-1.0.dist-info/METADATA"


def damaged_wheel(tmp_path: Path, kind: str, *, in_metadata: bool = False) -> Path:
    """A wheel with one damaged member: *kind*'s own, or its own METADATA."""
    member, compression, damage = DAMAGE[kind]
    if in_metadata:
        member = METADATA
    wheel = tmp_path / WHEEL
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("demo/__init__.py", "")
        zf.writestr(member, (REAL if in_metadata else "x = 1\n") * 40, compression)
        if not in_metadata:
            zf.writestr(METADATA, REAL)
    damage(wheel, member)
    return wheel
