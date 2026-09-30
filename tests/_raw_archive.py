# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Write wheel/sdist archive members under their exact raw names, on
every OS.

``ZipInfo(name)`` replaces ``os.sep`` with ``/`` on Windows, so a
backslash-separated name passed to ``writestr()`` is stored with ``/``
there and unchanged on POSIX. Setting ``filename`` after construction skips
that step, so the central directory holds *raw* byte-for-byte everywhere.

See also: tests/core/test_archive_member_names.py.
"""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

METADATA = b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n"

SDIST_ROOT = "demo-1.0.0"
#: An sdist with non-conforming root members and one unsafe member.
SDIST_MEMBERS = {
    f"{SDIST_ROOT}\\PKG-INFO": METADATA,
    f"././{SDIST_ROOT}/pyproject.toml": (
        b'[project]\nname = "demo"\nversion = "1.0.0"\n'
    ),
    f"{SDIST_ROOT}/demo/__init__.py": b"",
    f"{SDIST_ROOT}\\demo\\mod.py": b"mod = 1\n",
    f"{SDIST_ROOT}/../evil.py": b"evil = 1\n",
}
SDIST_FILES = {
    f"{SDIST_ROOT}/PKG-INFO",
    f"{SDIST_ROOT}/pyproject.toml",
    f"{SDIST_ROOT}/demo/__init__.py",
    f"{SDIST_ROOT}/demo/mod.py",
}
#: ``%r`` of each SDIST_MEMBERS name that warns.
SDIST_WARNED = (
    f"'{SDIST_ROOT}\\\\PKG-INFO'",
    f"'././{SDIST_ROOT}/pyproject.toml'",
    f"'{SDIST_ROOT}\\\\demo\\\\mod.py'",
    f"'{SDIST_ROOT}/../evil.py'",
)


def write_raw_member(zf: zipfile.ZipFile, raw: str, data: bytes) -> None:
    """Add *data* to *zf* under the exact member name *raw*."""
    info = zipfile.ZipInfo("placeholder")
    info.filename = raw
    zf.writestr(info, data)


def write_raw_zip(path: Path, members: dict[str, bytes]) -> Path:
    """Write a ZIP (wheel or sdist) at *path* whose members keep their raw
    names."""
    with zipfile.ZipFile(path, "w") as zf:
        for raw, data in members.items():
            write_raw_member(zf, raw, data)
    return path


def write_raw_tar(path: Path, members: dict[str, bytes]) -> Path:
    """Write a ``.tar.gz`` at *path*; ``tarfile`` keeps names raw on every
    OS."""
    with tarfile.open(path, "w:gz") as tf:
        for raw, data in members.items():
            info = tarfile.TarInfo(raw)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


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
