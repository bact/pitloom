# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""How much disk a checkout takes, and the cap on it.

See also: _git_run.py (stops ``git`` when the cap is passed).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

__all__ = ["SizeCap", "readable_bytes", "tree_bytes"]


@dataclass
class SizeCap:
    """At most *limit* bytes may be written below the directory *path*.
    *exceeded* is set by whoever notices it is not so."""

    path: str
    limit: int
    exceeded: bool = False


def tree_bytes(top: str) -> int:
    """The bytes of the files below *top*, symbolic links not followed.
    A file or directory that vanishes or cannot be read counts for nothing."""
    total = 0
    pending = [top]
    while pending:
        try:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def readable_bytes(count: int) -> str:
    """*count* as a whole number of bytes, KiB, MiB or GiB."""
    for unit, size in (("GiB", 1 << 30), ("MiB", 1 << 20), ("KiB", 1 << 10)):
        if count >= size and count % size == 0:
            return f"{count // size} {unit}"
    return f"{count} bytes"
