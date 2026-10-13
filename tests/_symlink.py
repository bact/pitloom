# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Whether this process may create a file symlink, for a ``skipif``: a
module constant computed once, never a POSIX-only call in a decorator;
and whether a directory's file system tells letter case apart."""

from __future__ import annotations

import tempfile
from pathlib import Path


def _can_symlink() -> bool:
    """Whether this process may create a file symlink (Windows needs a
    privilege)."""
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "target"
        target.write_bytes(b"")
        try:
            (Path(directory) / "link").symlink_to(target)
        except (OSError, NotImplementedError):
            return False
    return True


#: Whether a file symlink can be created here.
CAN_SYMLINK = _can_symlink()


def case_sensitive(directory: Path) -> bool:
    """Whether *directory* can hold two names differing only in case."""
    probe = directory / "case-probe"
    probe.mkdir()
    (probe / "a").write_bytes(b"")
    (probe / "A").write_bytes(b"")
    return len(list(probe.iterdir())) == 2
