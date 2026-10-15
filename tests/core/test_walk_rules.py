# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.walk_rules`.

See also: tests/core/models_wheel/test_models_wheel_exclude_path.py (the
file-discovery use), tests/id_registry/test_registry_generate.py (``id
generate``), tests/id_registry/test_surfaces_in_tree_registry.py (every
surface).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pitloom.core import file_identity, walk_rules
from pitloom.core.walk_rules import SameFile, same_path, warn_registry_left_out

POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="symlinks need privilege on Windows"
)


def test_same_path_equal_different_and_missing(tmp_path: Path) -> None:
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")

    assert same_path(first, first)
    assert not same_path(first, second)
    # Neither side has to exist: a registry about to be created compares
    # lexically; a missing file never matches an existing one.
    assert same_path(tmp_path / "x" / "..", tmp_path)
    assert not same_path(first, tmp_path / "missing.json")


def test_same_path_lexical_dotdot_spelling(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    target = tmp_path / "pkg" / "reg.json"
    target.write_text("{}", encoding="utf-8")
    assert same_path(tmp_path / "pkg" / ".." / "pkg" / "reg.json", target)


@POSIX_ONLY
def test_same_path_follows_symlinks_on_both_sides(tmp_path: Path) -> None:
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    target = real_dir / "reg.json"
    target.write_text("{}", encoding="utf-8")
    link_dir = tmp_path / "link"
    link_dir.symlink_to(real_dir, target_is_directory=True)

    assert same_path(link_dir / "reg.json", target)
    assert same_path(target, link_dir / "reg.json")


def test_same_path_matches_one_inode_under_two_names(tmp_path: Path) -> None:
    """A case-insensitive file system names one file by two spellings that
    differ in ``os.path.realpath``; the ``(st_dev, st_ino)`` fallback
    catches it. A hard link is the portable stand-in."""
    first = tmp_path / "reg.json"
    second = tmp_path / "other.json"
    first.write_text("{}", encoding="utf-8")
    try:
        os.link(first, second)
    except OSError:
        pytest.skip("hard links unavailable on this file system")
    assert same_path(first, second)


def test_same_path_inode_zero_is_no_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FAT/exFAT report ``st_ino == 0`` for every file: never a match."""
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")

    def fake_stat(_path: Any) -> SimpleNamespace:
        return SimpleNamespace(st_ino=0, st_dev=1)

    # The module's own `os` name only: patching os.stat itself would
    # reach every thread in the process.
    fake_os = SimpleNamespace(path=os.path, stat=fake_stat)
    monkeypatch.setattr(file_identity, "os", fake_os)
    assert not same_path(first, second)
    assert not SameFile(second).matches(first, first.stat())


def test_same_file_resolves_its_target_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Built once, then one ``stat()`` result per candidate: no
    ``realpath`` for a candidate named otherwise than the target (the
    per-file cost of a large walk)."""
    target = tmp_path / "reg.json"
    target.write_text("{}", encoding="utf-8")
    others = [tmp_path / f"f{n}.bin" for n in range(3)]
    for other in others:
        other.write_bytes(b"")
    (tmp_path / "sub").mkdir()
    matcher = SameFile(tmp_path / "sub" / ".." / "reg.json")
    calls: list[object] = []

    def counting_realpath(path: str | os.PathLike[str]) -> str:
        calls.append(path)
        return os.path.realpath(path)

    # The module's own `os` name only (see above).
    fake_path = SimpleNamespace(realpath=counting_realpath, basename=os.path.basename)
    monkeypatch.setattr(walk_rules, "os", SimpleNamespace(path=fake_path))
    assert [matcher.matches(o, o.stat()) for o in others] == [False] * 3
    assert matcher.matches(target, target.stat())
    assert not calls


def test_warn_registry_left_out_wording(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    registry = tmp_path / "reg.json"
    with caplog.at_level(logging.WARNING):
        warn_registry_left_out(registry)
    assert [r.levelname for r in caplog.records] == ["WARNING"]
    assert caplog.records[0].getMessage() == (
        f"ID registry: {registry} is inside the project's file set; left out of it"
    )
