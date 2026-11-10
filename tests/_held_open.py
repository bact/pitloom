# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A temporary directory that cannot be removed, as on Windows when a file
in it is still held open (an antivirus scanner, an indexer, a process not
yet gone), for the tests of a removal that must not fail the run."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.core import temp_dirs

__all__ = ["hold_open"]


def hold_open(monkeypatch: pytest.MonkeyPatch, prefix: str) -> list[str]:
    """Make the removal of :mod:`pitloom.core.temp_dirs` (every temporary
    directory Pitloom removes goes through it) fail on a directory named
    with *prefix*: with ``ignore_errors`` it leaves the directory, without
    it raises ``PermissionError``, as Windows does. Patched on that module's
    own ``rmtree``, not on ``shutil`` (which would reach every thread of the
    process); every other path is removed as usual. Returns the names of
    the directories refused, as they are refused."""
    real: Callable[..., None] = temp_dirs.rmtree
    refused: list[str] = []

    def rmtree(path: str | Path, ignore_errors: bool = False, **kwargs: Any) -> None:
        if not Path(path).name.startswith(prefix):
            real(path, ignore_errors=ignore_errors, **kwargs)
            return
        refused.append(Path(path).name)
        if not ignore_errors:
            raise PermissionError(13, "The process cannot access the file", str(path))

    monkeypatch.setattr(temp_dirs, "rmtree", rmtree)
    return refused
