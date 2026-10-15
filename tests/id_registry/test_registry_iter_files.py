# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ``id generate`` walk, :func:`pitloom.id_registry._types._iter_files`:
a walk root that cannot be ``stat()``-ed fails the same way on every Python
version, and a subdirectory that cannot be listed is never skipped silently.

See also: tests/id_registry/test_registry_generate.py (what the walk
indexes), tests/core/test_walk_rules.py (the shared rules).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.id_registry._types import _iter_files
from tests._symlink import CAN_SYMLINK
from tests._unreadable import POSIX_NON_ROOT, STAT_MODES, deny, unlistable


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "src" / "sub").mkdir(parents=True)
    (root / "src" / "a.py").write_bytes(b"a\n")
    (root / "src" / "sub" / "b.py").write_bytes(b"b\n")
    return root


@pytest.mark.parametrize("mode", STAT_MODES)
def test_walk_root_that_cannot_be_stat_ed_raises_on_every_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    mode: str,
) -> None:
    """Present but not ``stat()``-able: the ``PermissionError`` (the CLI's
    ``ERROR:``), never "path not found" -- ``Path.exists()`` says ``False``
    for it on Python 3.14 only."""
    root = _project(tmp_path)
    walk_root = root / "src" / "a.py"
    with (
        caplog.at_level(logging.WARNING),
        deny(walk_root, mode, monkeypatch),
        pytest.raises(PermissionError),
    ):
        list(_iter_files([walk_root], root))
    assert "path not found" not in caplog.text


@pytest.mark.skipif(not POSIX_NON_ROOT, reason="needs POSIX permissions, non-root")
def test_unlistable_subdirectory_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A subdirectory the walk cannot list: the shared ``DIR=`` warning,
    the rest still indexed. An ignored one is never listed, so never
    warned about."""
    root = _project(tmp_path)
    sub = root / "src" / "sub"
    ignored = root / "src" / ".venv"
    ignored.mkdir()
    with caplog.at_level(logging.WARNING), unlistable(sub), unlistable(ignored):
        files = list(_iter_files([Path("src")], root))
    assert files == [root / "src" / "a.py"]
    (warning,) = [r.getMessage() for r in caplog.records]
    assert warning.startswith(f"DIR={sub}: could not list for ID registry indexing;")


def test_walk_is_sorted_and_prunes_ignored_names(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "src" / "node_modules").mkdir()
    (root / "src" / "node_modules" / "x.js").write_bytes(b"x\n")
    (root / "src" / "Z.py").write_bytes(b"z\n")
    assert list(_iter_files([Path("src")], root)) == sorted(
        [root / "src" / "a.py", root / "src" / "sub" / "b.py", root / "src" / "Z.py"]
    )


@pytest.mark.skipif(not CAN_SYMLINK, reason="needs symlinks")
def test_walk_skips_a_dangling_symlink_and_a_root_below_an_ignored_name(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path)
    (root / "src" / "dangling.py").symlink_to(root / "missing.py")
    (root / "build" / "x").mkdir(parents=True)
    (root / "build" / "x" / "c.py").write_bytes(b"c\n")
    assert list(_iter_files([Path("src"), Path("build/x")], root)) == [
        root / "src" / "a.py",
        root / "src" / "sub" / "b.py",
    ]
