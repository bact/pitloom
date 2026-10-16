# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.id_registry registry generation over a project's paths:
ignored directory names, the declared registry, symlinked and
out-of-project roots, names that are not UTF-8 and unreadable roots.

See also: test_registry_generate.py (indexing and ids),
_registry_generate_shared.py (shared helper).
"""

# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=too-few-public-methods

from __future__ import annotations

import io
import logging
import os
import sys
from pathlib import Path

import pytest

import pitloom.id_registry._generate as ids_mod
from pitloom.core.file_identity import FileId, file_id
from pitloom.id_registry import IdRegistry, keys, path_key, project_prefix
from pitloom.id_registry._types import _iter_files
from tests._unreadable import POSIX_NON_ROOT
from tests.id_registry._registry_generate_shared import (
    _make_project,
)
from tests.id_registry.shared import _files


def test_generate_indexes_a_project_below_an_ignored_directory_name(
    tmp_path: Path,
) -> None:
    """Only the project-relative directory names are ignored: a project
    under ``<tmp>/build/`` (or ``dist``, ``venv``) is indexed in full."""
    project = tmp_path / "build" / "dist" / "proj"
    project.mkdir(parents=True)
    root = _make_project(project)
    (root / "src" / "build").mkdir()
    (root / "src" / "build" / "skipped.py").write_bytes(b"x\n")

    registry = IdRegistry.new("proj")
    registry.generate([Path("src"), Path("data")], root)

    # Still ignored inside the project, below the walk root.
    assert set(_files(registry)) == {"src/a.py", "data/x.txt"}


def test_generate_leaves_out_the_declared_registry(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    declared = root / "src" / "my-ids.json"
    declared.write_text("{}", encoding="utf-8")

    unexcluded = IdRegistry.new("proj")
    unexcluded.generate([Path("src")], root)
    registry = IdRegistry.new("proj")
    registry.generate([Path("src")], root, exclude=declared)

    assert "src/my-ids.json" in _files(unexcluded)  # not vacuous
    assert set(_files(registry)) == {"src/a.py"}


def test_iter_files_exclude_matches_another_spelling(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    declared = root / "src" / "my-ids.json"
    declared.write_text("{}", encoding="utf-8")
    spelled = root / "data" / ".." / "src" / "my-ids.json"

    files = list(_iter_files([root / "src"], root, spelled))
    assert files == [root / "src" / "a.py"]


def test_iter_files_outside_the_project_ignores_names_below_the_walk_root(
    tmp_path: Path,
) -> None:
    project = tmp_path / "build" / "proj"
    project.mkdir(parents=True)
    outside = tmp_path / "build" / "other"
    (outside / "node_modules").mkdir(parents=True)
    (outside / "node_modules" / "skipped.js").write_bytes(b"x\n")
    (outside / "kept.txt").write_bytes(b"x\n")

    assert list(_iter_files([outside], project)) == [outside / "kept.txt"]


def test_generate_outside_the_project_root_is_a_clean_error(tmp_path: Path) -> None:
    (tmp_path / "proj").mkdir()
    root = _make_project(tmp_path / "proj")
    outside = tmp_path / "other.txt"
    outside.write_bytes(b"x")
    registry = IdRegistry.new("proj")

    with pytest.raises(ValueError, match="outside the project root") as excinfo:
        registry.generate([outside], root)

    assert "other.txt" in str(excinfo.value)
    assert str(root) in str(excinfo.value)
    assert not registry.elements


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege")
@pytest.mark.parametrize("spelling", ["root-link", "paths-link"])
def test_generate_compares_a_symlinked_project_root_by_realpath(
    tmp_path: Path, spelling: str
) -> None:
    (tmp_path / "real").mkdir()
    real = _make_project(tmp_path / "real")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    root, walked = (link, real) if spelling == "root-link" else (real, link)
    registry = IdRegistry.new("proj")

    registry.generate([walked / "src"], root)

    assert set(_files(registry)) == {"src/a.py"}


def test_generate_skips_a_name_that_is_not_utf8_with_one_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A lone surrogate (a non-UTF-8 file name) never reaches the table,
    and the logged name is escaped, so the log handler cannot crash."""
    root = _make_project(tmp_path)
    bad = root / "\udcff.txt"
    monkeypatch.setattr(
        ids_mod, "_iter_files", lambda *_a, **_k: iter([bad, root / "src" / "a.py"])
    )
    monkeypatch.setattr(ids_mod, "sha256_file", lambda _p: "c" * 64)
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    handler = logging.StreamHandler(stream)
    failures: list[object] = []
    monkeypatch.setattr(handler, "handleError", failures.append)
    logger = logging.getLogger("pitloom.id_registry")
    logger.addHandler(handler)
    registry = IdRegistry.new("proj")

    try:
        with caplog.at_level(logging.WARNING, logger="pitloom"):
            registry.generate([root], root)
    finally:
        logger.removeHandler(handler)

    (warning,) = [r.getMessage() for r in caplog.records]
    assert warning.startswith("FILE=") and "lone surrogate" in warning
    assert "\\udcff" in warning
    assert not failures
    assert set(_files(registry)) == {"src/a.py"}


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege")
def test_generate_keys_an_in_project_symlink_to_outside_by_project_path(
    tmp_path: Path,
) -> None:
    (tmp_path / "proj").mkdir()
    root = _make_project(tmp_path / "proj")
    outside = tmp_path / "bigdisk" / "models"
    outside.mkdir(parents=True)
    (outside / "w.bin").write_bytes(b"w")
    (root / "models").symlink_to(outside, target_is_directory=True)
    registry = IdRegistry.new("proj")

    registry.generate([root / "models" / "w.bin"], root)

    assert "models/w.bin" in _files(registry)


@pytest.mark.parametrize(
    ("given", "key"),
    [("d/../d/a.txt", "d/a.txt"), ("../out/o.txt", None)],
    ids=["dotdot-inside", "dotdot-outside"],
)
def test_generate_collapses_dotdot_before_keying(
    tmp_path: Path, given: str, key: str | None
) -> None:
    root = tmp_path / "proj"
    (root / "d").mkdir(parents=True)
    (root / "d" / "a.txt").write_bytes(b"a")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "o.txt").write_bytes(b"o")
    registry = IdRegistry.new("proj")

    if key is None:
        with pytest.raises(ValueError, match="outside the project root"):
            registry.generate([Path(given)], root)
    else:
        registry.generate([Path(given)], root)
        assert set(_files(registry)) == {key}


@pytest.mark.skipif(not POSIX_NON_ROOT, reason="needs POSIX, non-root")
def test_generate_unreadable_root_warns_unless_explicit(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _make_project(tmp_path)
    (root / "data").chmod(0)
    try:
        with caplog.at_level(logging.WARNING):
            registry = IdRegistry.new("proj")
            registry.generate([root / "data", root / "src"], root, explicit=False)
        with pytest.raises(ValueError, match="PATH data: could not be read"):
            IdRegistry.new("proj").generate([root / "data"], root)
    finally:
        (root / "data").chmod(0o755)

    assert set(_files(registry)) == {"src/a.py"}
    (warning,) = [r.getMessage() for r in caplog.records]
    assert warning.startswith("DIR=data")


@pytest.mark.skipif(not POSIX_NON_ROOT, reason="needs POSIX, non-root")
def test_generate_unreadable_root_file_warns_unless_explicit(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _make_project(tmp_path)
    locked = root / "data" / "x.txt"
    locked.chmod(0)
    try:
        with caplog.at_level(logging.WARNING):
            IdRegistry.new("proj").generate([locked], root, explicit=False)
    finally:
        locked.chmod(0o644)

    (warning,) = [r.getMessage() for r in caplog.records]
    assert warning.startswith("FILE=data/x.txt")


def _deleted_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    def deleted() -> str:
        raise FileNotFoundError("cwd is gone")

    monkeypatch.setattr(os, "getcwd", deleted)


def test_keys_without_a_root_survive_a_deleted_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A registry with no root and no file falls back to the current
    directory, which is gone: no key, no exception."""
    root = _make_project(tmp_path)
    registry = IdRegistry.new("proj")
    _deleted_cwd(monkeypatch)

    assert path_key(registry, root / "src" / "a.py") is None
    assert project_prefix(registry, root) is None


@pytest.mark.skipif(sys.platform == "win32", reason="ntpath.realpath reads the cwd")
def test_generate_with_a_root_survives_a_deleted_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``generate`` with the project root given still indexes."""
    root = _make_project(tmp_path)
    registry = IdRegistry.new("proj")
    _deleted_cwd(monkeypatch)

    registry.generate([root / "src"], root)

    assert set(_files(registry)) == {"src/a.py"}


def _case_blind(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the on-disk spelling step see a case-insensitive file system:
    a name is the file its lower-case spelling is."""
    real = file_id

    def identity(path: str) -> FileId | None:
        head, tail = os.path.split(path)
        return real(os.path.join(head, tail.lower()))

    monkeypatch.setattr(keys, "file_id", identity)


@pytest.mark.parametrize(
    "given", [["SRC"], ["src/A.PY"], ["SRC", "src/A.PY"]], ids=["dir", "file", "both"]
)
def test_generate_spells_each_path_as_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, given: list[str]
) -> None:
    """A PATH typed in another case keys as the disk lists it, so a later
    project run finds it and a second spelling adds nothing; the spelling
    lists the walk root's parts once, not each file's."""
    root = _make_project(tmp_path)
    others = {f"src/b{n}.py" for n in range(4)}
    for name in others:
        (root / name).write_bytes(name.encode())
    _case_blind(monkeypatch)
    calls: list[str] = []
    listdir = keys._listdir  # pylint: disable=protected-access

    def counted(directory: str) -> list[str]:
        calls.append(directory)
        return listdir(directory)

    monkeypatch.setattr(keys, "_listdir", counted)
    registry = IdRegistry.new("proj", project_root=root)

    for path in given:
        registry.generate([Path(path)], root)

    walked = others if "SRC" in given else set()
    assert set(_files(registry)) == {"src/a.py", *walked}
    assert len(calls) <= 2 * len(given)  # per walk root, never per file


@pytest.mark.skipif(
    not (Path(__file__).parent / "TEST_REGISTRY_GENERATE_PATHS.PY").exists(),
    reason="needs a case-insensitive file system",
)
def test_generate_spells_a_real_case_variant(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry = IdRegistry.new("proj", project_root=root)

    registry.generate([Path("SRC")], root)
    registry.generate([Path("src/A.PY")], root)

    assert set(_files(registry)) == {"src/a.py"}
