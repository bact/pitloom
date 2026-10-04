# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Whether two paths are one file, by identity rather than by spelling."""

from __future__ import annotations

import os
from pathlib import PurePath

FileId = tuple[int, int]


def file_id(path: PurePath | str) -> FileId | None:
    """``(st_dev, st_ino)`` of *path*, or ``None`` when it cannot be stat()ed
    or has no identity: ``st_ino`` is unique only when non-zero (FAT/exFAT
    and some network shares report 0 for every file).

    Unlike a resolved path, it is the same for a hard link and for a name
    spelt in another letter case on a case-insensitive file system.
    """
    try:
        result = os.stat(path)
    except OSError:
        return None
    return (result.st_dev, result.st_ino) if result.st_ino else None
