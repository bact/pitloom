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
from pitloom.core.models import get_wheel_files
from pitloom.core.walk_rules import (
    SameFile,
    same_path,
    shortened_by,
    warn_registry_left_out,
)
from tests._unreadable import deny

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


@pytest.mark.parametrize("with_stat", [True, False], ids=["stat", "no-stat"])
def test_missing_target_is_no_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_stat: bool
) -> None:
    """A target not created yet (a new registry) cannot be an existing
    file: no ``realpath`` per candidate. Two missing paths still compare
    by ``realpath``."""
    others = [tmp_path / f"f{n}.bin" for n in range(3)]
    for other in others:
        other.write_bytes(b"")
    (tmp_path / "sub").mkdir()
    matcher = SameFile(tmp_path / "new.json")
    calls: list[object] = []

    def counting_realpath(path: str | os.PathLike[str]) -> str:
        calls.append(path)
        return os.path.realpath(path)

    fake_path = SimpleNamespace(realpath=counting_realpath, basename=os.path.basename)
    fake_os = SimpleNamespace(path=fake_path, fspath=os.fspath)
    monkeypatch.setattr(walk_rules, "os", fake_os)
    found = [matcher.matches(o, o.stat() if with_stat else None) for o in others]
    assert found == [False] * 3
    assert not calls
    assert matcher.matches(tmp_path / "sub" / ".." / "new.json")
    assert not matcher.matches(tmp_path / "other.json")


def test_target_without_identity_compares_by_realpath(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A target ``stat()`` fails on for another reason than its absence
    has no identity: compared by ``realpath``."""
    path = tmp_path / "reg.json"
    path.write_text("{}", encoding="utf-8")
    other = tmp_path / "other.json"
    other.write_text("{}", encoding="utf-8")
    with deny(path, "stat", monkeypatch):
        matcher = SameFile(path)
    assert matcher.matches(tmp_path / "sub" / ".." / "reg.json")
    assert not matcher.matches(other, other.stat())


def test_discovery_stats_each_file_once_for_the_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Project discovery hands the registry matcher the scan's own
    ``stat()`` result: no second one per file."""
    project = tmp_path / "proj"
    (project / "pkg").mkdir(parents=True)
    (project / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        '[project]\nname = "pkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (project / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    registry = project / "pkg" / "reg.json"
    registry.write_text("{}", encoding="utf-8")
    looked_up: list[object] = []
    real_file_id = file_identity.file_id

    def counting_file_id(path: Any) -> Any:
        looked_up.append(path)
        return real_file_id(path)

    monkeypatch.setattr(walk_rules, "file_id", counting_file_id)
    _, files, cleanup = get_wheel_files(project, exclude_path=registry)
    cleanup()
    assert [f.distribution_path for f in files] == ["pkg/__init__.py"]
    assert not looked_up


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


def test_project_files_are_shared_by_both_consumers() -> None:
    """``registry_copy`` and ``id generate``'s target resolution recognise
    a project by the same files, imported from one place."""
    # pylint: disable-next=import-outside-toplevel
    from pitloom.cli import _id_target

    # pylint: disable-next=import-outside-toplevel
    from pitloom.id_registry import resolve

    assert vars(_id_target)["PROJECT_FILES"] is walk_rules.PROJECT_FILES
    assert vars(resolve)["PROJECT_FILES"] is walk_rules.PROJECT_FILES


@pytest.mark.parametrize(
    ("longer", "shorter", "max_cut", "cut"),
    [
        ("a/b", "a/b", 0, 0),
        ("a", "a", 1, 0),
        ("s/a/b", "a/b", 1, 1),
        ("s/a/b", "a/b", 0, None),
        ("t/s/a/b", "a/b", 1, None),
        ("s/a", "a", 1, None),
        ("a", "a/b", 1, None),
        ("s/a/b", "a/c", 1, None),
    ],
    ids=[
        "equal",
        "one-part",
        "cut",
        "no-cut-allowed",
        "two-cut",
        "one-remains",
        "longer",
        "tail-differs",
    ],
)
def test_shortened_by(longer: str, shorter: str, max_cut: int, cut: int | None) -> None:
    """At most *max_cut* leading parts dropped; a directory and a file
    remain when any is; the rest equal."""
    assert shortened_by(longer.split("/"), shorter.split("/"), max_cut=max_cut) == cut
