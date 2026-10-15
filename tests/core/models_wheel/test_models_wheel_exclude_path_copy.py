# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``RegistryCopy``/``registry_copy``: recognising the registry's
copy among a built wheel's or sdist's members.

See also: test_models_wheel_exclude_path.py (``get_wheel_files(exclude_path=)``).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest
from hatchling.builders.wheel import WheelBuilder

from pitloom.core.models import get_wheel_files, merkle_root_of_files
from pitloom.core.project import ProjectFile
from pitloom.core.walk_rules import (
    REGISTRY_IN_FILE_SET_WARNING,
    RegistryCopy,
    without_registry_copies,
)
from pitloom.extract.wheel import read_wheel
from pitloom.id_registry import IdRegistry, registry_copy
from tests._symlink import CAN_SYMLINK, case_sensitive
from tests.assemble.conftest import _make_dummy_wheel
from tests.core.models_wheel._exclude_path_shared import REG, warnings_of, write_file


def _rooted(tmp_path: Path, rel: str) -> tuple[Path, Path]:
    """(project, registry): a registry file at *rel* below the project."""
    project = tmp_path / "proj"
    registry = write_file(project, rel, REG)
    return project, registry


@pytest.mark.parametrize(
    ("rel", "member", "in_sdist", "matches"),
    [
        ("demo/reg.json", "demo/reg.json", False, True),
        ("src/demo/reg.json", "demo/reg.json", False, True),
        ("demo/reg.json", "x/demo/reg.json", False, False),
        ("demo/reg.json", "other/reg.json", False, False),
        ("demo/reg.json", "demo/reg.jsonx", False, False),
        ("demo/reg.json", "demo-1.0/demo/reg.json", True, True),
        ("src/demo/reg.json", "demo-1.0/demo/reg.json", True, False),
        ("demo/reg.json", "demo-1.0/reg.json", True, False),
        ("demo/reg.json", "PKG-INFO", True, False),
        ("../reg.json", "reg.json", False, False),
        ("reg.json", "reg.json", False, True),
        ("demo/reg.json", "reg.json", False, False),
        ("src/demo/data/reg.json", "demo/data/reg.json", False, True),
        ("src/demo/data/reg.json", "data/reg.json", False, False),
        ("src/demo/data/reg.json", "reg.json", False, False),
    ],
    ids=[
        "flat",
        "src-tail",
        "longer",
        "other-dir",
        "other-name",
        "sdist",
        "sdist-tail",
        "sdist-short",
        "sdist-top-file",
        "outside",
        "top",
        "flat-name-only",
        "src-deep",
        "src-two-short",
        "src-name-only",
    ],
)
def test_registry_copy_member_rule(
    tmp_path: Path, rel: str, member: str, in_sdist: bool, matches: bool
) -> None:
    """A member is a copy when its path is the registry's below the root
    or (a wheel only) that path less its first part, a package directory
    and the file at least: never longer, never a sibling."""
    project, registry = _rooted(tmp_path, rel)
    assert RegistryCopy(registry, project).matches(member, in_sdist=in_sdist) is matches


@pytest.mark.parametrize(
    ("members", "in_sdist", "left_out"),
    [
        (["demo/reg.json", "src/demo/reg.json", "x/demo/reg.json"], False, 1),
        (["d-1/demo/reg.json", "d-1/src/demo/reg.json"], True, 1),
        (["reg.json", "x/reg.json"], False, None),
    ],
    ids=["longest", "sdist", "none"],
)
def test_one_member_per_archive_is_left_out(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    members: list[str],
    in_sdist: bool,
    left_out: int | None,
) -> None:
    """Of the members that may be the registry's copy, only the one with
    the longest path is; the others are files of the archive."""
    project, registry = _rooted(tmp_path, "src/demo/reg.json")
    files = [ProjectFile(physical_path=m, distribution_path=m) for m in members]
    with caplog.at_level(logging.WARNING):
        kept = without_registry_copies(
            files, RegistryCopy(registry, project), in_sdist=in_sdist
        )
    expected = [m for i, m in enumerate(members) if i != left_out]
    assert [f.distribution_path for f in kept] == expected
    assert len(warnings_of(caplog)) == int(left_out is not None)


@pytest.mark.parametrize(
    ("marker", "member", "in_sdist", "matches"),
    [
        ("pyproject.toml", "demo/reg.json", False, True),
        ("setup.py", "src/demo/reg.json", False, True),
        ("setup.cfg", "demo-1.0/src/demo/reg.json", True, True),
        ("pyproject.toml", "demo-1.0/pkgs/demo/src/demo/reg.json", True, False),
        ("pyproject.toml", "pkgs/demo/src/demo/reg.json", False, False),
        (None, "demo/reg.json", False, False),
    ],
    ids=["wheel", "setup-py", "sdist", "sdist-repo-path", "repo-path", "no-project"],
)
def test_registry_copy_root_in_a_monorepo(
    tmp_path: Path, marker: str | None, member: str, in_sdist: bool, matches: bool
) -> None:
    """A registry storing a root above its project (a monorepo) matches
    members below the nearest directory holding it that is a project
    (``pyproject.toml``, ``setup.cfg`` or ``setup.py``), up to the stored
    root; with none, below the stored root."""
    repo = tmp_path / "repo"
    project = repo / "pkgs" / "demo"
    if marker is not None:
        write_file(project, marker, b"")
    path = write_file(project, "src/demo/reg.json", REG)
    registry = IdRegistry.new("demo", project_root=repo)
    registry.save(path)
    copy = registry_copy(registry)
    assert copy is not None
    assert copy.matches(member, in_sdist=in_sdist) is matches


_TAIL_NAMED_TOML = b"""\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0"

[tool.hatch.build.targets.wheel]
packages = ["src/demo"]

[tool.hatch.build.targets.wheel.force-include]
"extra/reg.json" = "reg.json"
"extra/reg2.json" = "data/reg.json"
"""


def test_project_and_wheel_agree_beside_tail_named_files(tmp_path: Path) -> None:
    """The registry ``src/demo/data/reg.json``, and a wheel shipping two
    other files named by tails of its path, ``reg.json`` and
    ``data/reg.json``: discovery and the wheel's members leave out the
    registry's copy only, so their files and Merkle root are the same."""
    project = tmp_path / "proj"
    write_file(project, "pyproject.toml", _TAIL_NAMED_TOML)
    write_file(project, "src/demo/__init__.py", b"x = 1\n")
    write_file(project, "extra/reg.json", b'{"unrelated": true}\n')
    write_file(project, "extra/reg2.json", b'{"other": 1}\n')
    path = write_file(project, "src/demo/data/reg.json", REG)
    registry = IdRegistry.new("demo", project_root=project)
    registry.save(path)
    builder = WheelBuilder(str(project))
    wheel = next(builder.build(directory=str(tmp_path / "dist"), versions=["standard"]))
    root, discovered, cleanup = get_wheel_files(project, exclude_path=path)
    cleanup()
    _, members = read_wheel(Path(wheel))

    expected = ["data/reg.json", "demo/__init__.py", "reg.json"]
    assert "demo/data/reg.json" in [f.distribution_path for f in members]
    assert sorted(f.distribution_path for f in discovered) == expected
    for copy in (registry_copy(registry), registry_copy(registry, project)):
        kept = without_registry_copies(members, copy)
        assert sorted(f.distribution_path for f in kept) == expected
        assert merkle_root_of_files(kept) == root


def test_registry_copy_member_in_another_case(tmp_path: Path) -> None:
    """``Demo/REG.json`` is the registry where the file system folds case;
    elsewhere it is another file."""
    project, registry = _rooted(tmp_path, "demo/reg.json")
    folds = not case_sensitive(tmp_path)
    copy = RegistryCopy(registry, project)
    assert copy.matches("Demo/REG.json") is folds
    assert copy.matches("Demo/other.json") is False


def test_registry_copy_member_in_another_case_by_identity(tmp_path: Path) -> None:
    """Where the file system keeps case, a member spelt in another case is
    the registry only if that spelling is the registry's own inode (a hard
    link): the rule a case-insensitive file system applies by itself."""
    if not case_sensitive(tmp_path):
        pytest.skip("case folding is covered by the test above")
    project, registry = _rooted(tmp_path, "demo/reg.json")
    alias = project / "Demo" / "REG.json"
    alias.parent.mkdir()
    try:
        os.link(registry, alias)
    except OSError:
        pytest.skip("hard links unavailable on this file system")
    write_file(project, "Demo/Reg.json", REG)  # same letters, another file
    copy = RegistryCopy(registry, project)
    assert copy.matches("Demo/REG.json")
    assert not copy.matches("Demo/Reg.json")


@pytest.mark.skipif(not CAN_SYMLINK, reason="needs a symlink")
@pytest.mark.parametrize(
    "link", ["root", "registry"], ids=["linked-root", "linked-registry"]
)
def test_registry_copy_through_a_symlink(tmp_path: Path, link: str) -> None:
    """A root reached through a symlink, or a registry that is a symlink
    to a file outside the project: its path as spelt still names the
    member."""
    project = tmp_path / "proj"
    (project / "demo").mkdir(parents=True)
    if link == "root":
        write_file(project, "demo/reg.json", REG)
        (tmp_path / "alias").symlink_to(project, target_is_directory=True)
        registry, root = tmp_path / "alias" / "demo" / "reg.json", project
    else:
        target = write_file(tmp_path, "elsewhere/reg.json", REG)
        registry, root = project / "demo" / "reg.json", project
        registry.symlink_to(target)
    assert RegistryCopy(registry, root).matches("demo/reg.json")


@pytest.mark.parametrize(
    ("root", "given", "found"),
    [
        ("stored", None, True),
        ("stored", "sdist-file", True),
        ("own-dir", None, False),
        ("own-dir", "project", True),
        ("unsaved", None, False),
        ("in-memory", "project", False),
    ],
    ids=["stored", "file-dir", "own-dir", "dir-wins", "unsaved", "in-memory"],
)
def test_registry_copy_root(
    tmp_path: Path, root: str, given: str | None, found: bool
) -> None:
    """The root is the given project directory, else the one the registry
    stores; no file or no stored root leaves nothing out."""
    project, path = _rooted(tmp_path, "demo/reg.json")
    stored = project if root == "stored" else None
    registry = IdRegistry.new("demo", project_root=stored)
    if root in ("stored", "own-dir"):
        registry.save(path)
    elif root == "unsaved":
        registry.path = path
    project_dir = {
        None: None,
        "project": project,
        "sdist-file": write_file(tmp_path, "demo-1.0.tar.gz", b""),
    }[given]
    copy = registry_copy(registry, project_dir)
    assert (copy is not None and copy.matches("demo/reg.json")) is found
    assert registry_copy(None, project) is None


def test_backslash_member_of_a_wheel_is_the_registry(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``demo\\reg.json`` (a Windows-written raw name) is installed at
    ``demo/reg.json``: the copy is left out, once, by its install name."""
    project, registry = _rooted(tmp_path, "demo/reg.json")
    wheel = _make_dummy_wheel(
        tmp_path / "dist", "demo", "1.0", extra_members={"demo\\reg.json": b"{}"}
    )
    _, files = read_wheel(wheel)
    assert "demo/reg.json" in [f.distribution_path for f in files]  # not vacuous

    with caplog.at_level(logging.WARNING):
        kept = without_registry_copies(files, RegistryCopy(registry, project))
    assert "demo/reg.json" not in [f.distribution_path for f in kept]
    assert len(kept) == len(files) - 1
    assert warnings_of(caplog) == [REGISTRY_IN_FILE_SET_WARNING % registry]
