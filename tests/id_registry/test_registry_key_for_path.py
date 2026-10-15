# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.id_registry.registry_key_for_path`: a file's
registry key is its path from the registry's project root, whatever the
current directory and however the path is spelled.

See also: tests/core/test_loom_dataset.py (loom's use of it).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom.id_registry import FILE_TYPE, registry_key_for_path
from tests._symlink import CAN_SYMLINK, case_sensitive
from tests.registry_helpers import make_registry

# Windows refuses to delete the current directory.
_CAN_DELETE_CWD = sys.platform != "win32"
_NEEDS_SYMLINK = pytest.mark.skipif(not CAN_SYMLINK, reason="needs symlinks")


@pytest.fixture(name="project")
def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "data").mkdir(parents=True)
    (root / "sub").mkdir()
    (root / "data" / "t.txt").write_bytes(b"x")
    return root


@pytest.mark.parametrize(
    ("cwd", "given", "key"),
    [
        (".", "data/t.txt", "data/t.txt"),
        ("sub", "../data/t.txt", "data/t.txt"),
        ("sub", "./../data/./t.txt", "data/t.txt"),
        ("sub", "<root>/data/t.txt", "data/t.txt"),
        ("data", "missing.bin", "data/missing.bin"),
        ("sub", "..", "."),
    ],
    ids=["relative", "dotdot", "dots", "absolute", "missing", "root"],
)
def test_key_is_relative_to_the_root(
    project: Path, monkeypatch: pytest.MonkeyPatch, cwd: str, given: str, key: str
) -> None:
    """From any directory, any spelling: the ``/``-separated path from the
    root; a file need not exist; the root itself is ``"."``."""
    monkeypatch.chdir(project / cwd)
    registry = make_registry(project_root=project)
    path = Path(given.replace("<root>", str(project)))
    assert registry_key_for_path(registry, path) == key


@pytest.mark.parametrize(
    "given",
    ["<tmp>/elsewhere.txt", "../elsewhere.txt", "<tmp>/proj-other/x", "../a\0b"],
    ids=["absolute", "dotdot", "prefix-sibling", "nul"],
)
def test_outside_the_root_has_no_key(
    project: Path, monkeypatch: pytest.MonkeyPatch, given: str
) -> None:
    """Outside the root: ``None``, never a ``../`` key and never a raise --
    a sibling sharing the root's name as a string prefix is outside too."""
    monkeypatch.chdir(project)
    registry = make_registry(project_root=project)
    path = Path(given.replace("<tmp>", str(project.parent)))
    assert registry_key_for_path(registry, path) is None


def test_root_defaults_to_the_registry_file_directory(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no recorded project root, the saved registry's own directory
    is the root, not the current directory."""
    monkeypatch.chdir(project / "sub")
    saved = make_registry(path=project / "loom-id-registry.json")
    saved.project_root = None
    assert registry_key_for_path(saved, Path("../data/t.txt")) == "data/t.txt"


@pytest.mark.parametrize("spelling", ["relative", "real", "alias"])
@_NEEDS_SYMLINK
def test_in_project_directory_symlink_keys_lexically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spelling: str
) -> None:
    """A path through an in-root directory symlink keys by its own
    location, also when an ancestor of the root is spelt through a symlink
    (macOS ``/tmp`` is ``/private/tmp``): the remainder below the root is
    never resolved. ``id generate`` does not descend into a directory
    symlink, so this key has no entry; the file is found under its target."""
    real = tmp_path / "real"
    project = real / "proj"
    (project / "data").mkdir(parents=True)
    (project / "data" / "t.txt").write_bytes(b"x")
    (project / "link").symlink_to(project / "data", target_is_directory=True)
    (tmp_path / "alias").symlink_to(real, target_is_directory=True)
    monkeypatch.chdir(project)
    given = {
        "relative": Path("link/t.txt"),
        "real": project / "link" / "t.txt",
        "alias": tmp_path / "alias" / "proj" / "link" / "t.txt",
    }[spelling]
    registry = make_registry(project_root=project)
    assert registry_key_for_path(registry, given) == "link/t.txt"


@_NEEDS_SYMLINK
def test_in_project_file_symlink_key_hits_id_generate(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``id generate`` indexes a file symlink under its own path; loom's
    key for it is that path, so the lookup hits."""
    (project / "alias.txt").symlink_to(project / "data" / "t.txt")
    monkeypatch.chdir(project)
    registry = make_registry(project_root=project)
    registry.generate([project], project)
    key = registry_key_for_path(registry, Path("alias.txt"))
    assert key == "alias.txt"
    assert registry.get(FILE_TYPE, key) is not None


@pytest.mark.parametrize("alias_to", ["root", "data"], ids=["root", "subdir"])
@_NEEDS_SYMLINK
def test_alias_from_outside_keys_through_realpath(
    project: Path, monkeypatch: pytest.MonkeyPatch, alias_to: str
) -> None:
    """A path through a symlink outside the root that leads into it keys by
    where it leads (the realpath fallback)."""
    monkeypatch.chdir(project.parent)
    target = project if alias_to == "root" else project / "data"
    alias = project.parent / "alias"
    alias.symlink_to(target, target_is_directory=True)
    given = alias / ("data/t.txt" if alias_to == "root" else "t.txt")
    registry = make_registry(project_root=project)
    assert registry_key_for_path(registry, given) == "data/t.txt"


@_NEEDS_SYMLINK
def test_symlink_out_of_the_root_is_keyed_lexically(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An in-root symlink pointing outside keys by its own in-root
    location: the key names where the file is declared."""
    outside = project.parent / "outside.txt"
    outside.write_bytes(b"y")
    (project / "out.txt").symlink_to(outside)
    monkeypatch.chdir(project)
    registry = make_registry(project_root=project)
    assert registry_key_for_path(registry, Path("out.txt")) == "out.txt"


def test_other_case_spelling_of_the_root_keys_by_identity(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a case-insensitive file system, a path spelling the root's
    directory in another case is still inside it (by file identity)."""
    if case_sensitive(project.parent):
        pytest.skip("needs a case-insensitive file system")
    monkeypatch.chdir(project.parent)
    registry = make_registry(project_root=project)
    assert registry_key_for_path(registry, Path("PROJ/data/t.txt")) == "data/t.txt"


@pytest.mark.skipif(not _CAN_DELETE_CWD, reason="Windows keeps the cwd")
@pytest.mark.parametrize(
    ("absolute", "key"),
    [(False, None), (True, "data/t.txt")],
    ids=["relative", "absolute"],
)
def test_deleted_current_directory_never_raises(
    project: Path, monkeypatch: pytest.MonkeyPatch, absolute: bool, key: str | None
) -> None:
    """With the current directory gone, a relative path has no key (``None``,
    not ``FileNotFoundError``); an absolute one needs no cwd."""
    gone = project.parent / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    registry = make_registry(project_root=project)
    path = project / "data" / "t.txt" if absolute else Path("data/t.txt")
    assert registry_key_for_path(registry, path) == key
