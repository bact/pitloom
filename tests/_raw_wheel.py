# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Write ZIP members under their exact raw names, on every OS.

``ZipInfo(name)`` replaces ``os.sep`` with ``/`` on Windows, so a
backslash-separated name passed to ``writestr()`` is stored with ``/``
there and unchanged on POSIX. Setting ``filename`` after construction skips
that step, so the central directory holds *raw* byte-for-byte everywhere.

See also: tests/extract/test_wheel_member_names.py.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

METADATA = b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n"


def write_raw_member(zf: zipfile.ZipFile, raw: str, data: bytes) -> None:
    """Add *data* to *zf* under the exact member name *raw*."""
    info = zipfile.ZipInfo("placeholder")
    info.filename = raw
    zf.writestr(info, data)


def write_raw_wheel(wheel_path: Path, members: dict[str, bytes]) -> Path:
    """Write a wheel at *wheel_path* whose members keep their raw names."""
    with zipfile.ZipFile(wheel_path, "w") as zf:
        for raw, data in members.items():
            write_raw_member(zf, raw, data)
    return wheel_path


def mimic_windows_infolist(
    zf: zipfile.ZipFile,
) -> list[zipfile.ZipInfo]:
    """What ``ZipFile.infolist()`` returns on Windows for the same archive.

    CPython cuts ``filename`` at a NUL, converts backslashes to ``/`` and
    keeps the raw name in ``orig_filename``.
    """
    infos = list(zf.filelist)
    for info in infos:
        info.filename = info.orig_filename.split("\0")[0].replace("\\", "/")
    return infos
