# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``get_wheel_files(exclude_path=...)``: the declared Loom ID
registry is left out of the file set and the Merkle root; and for
``RegistryCopy``/``registry_copy``, which recognise its copy among a built
wheel's or sdist's members.

See also: tests/core/test_walk_rules.py, tests/core/models_wheel/
test_models_wheel_files.py, tests/id_registry/test_surfaces_in_tree_registry.py.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest import mock

import pytest
from hatchling.builders.wheel import WheelBuilder

from pitloom.core._models_wheel_build_and_read import build_and_read_wheel
from pitloom.core._models_wheel_types import IncludedFile
from pitloom.core.build_options import BuildOptions
from pitloom.core.models import get_wheel_files, merkle_root_of_files
from pitloom.core.project import ProjectFile, project_relative_or_fallback
from pitloom.core.walk_rules import (
    REGISTRY_IN_FILE_SET_WARNING,
    RegistryCopy,
    without_registry_copies,
)
from pitloom.extract.wheel import read_wheel
from pitloom.id_registry import IdRegistry, registry_copy
from tests._symlink import CAN_SYMLINK, case_sensitive
from tests.assemble.conftest import _make_dummy_wheel
from tests.build_and_read_shared import BUILD_AND_READ, make_backend_project


def _project(tmp_path: Path, *, registry_in_package: bool = True) -> Path:
    """A Hatchling project whose package holds ``reg.json`` (or, when
    *registry_in_package* is false, one at the project root, which
    Hatchling does not include)."""
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        '[project]\nname = "pkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (root / "pkg" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    location = root / "pkg" if registry_in_package else root
    (location / "reg.json").write_text('{"files": {}}\n', encoding="utf-8")
    return root


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    needle = REGISTRY_IN_FILE_SET_WARNING.split("%s")[1]
    return [r.getMessage() for r in caplog.records if needle in r.getMessage()]


def test_in_tree_registry_is_left_out_of_files_and_root(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _project(tmp_path)
    registry = root / "pkg" / "reg.json"

    root_without_exclusion, files_without, cleanup = get_wheel_files(root)
    cleanup()
    with caplog.at_level(logging.WARNING):
        merkle_root, files, cleanup = get_wheel_files(root, exclude_path=registry)
    cleanup()

    names = [f.distribution_path for f in files]
    # Not vacuous: without the exclusion the registry is in the file set.
    assert "pkg/reg.json" in [f.distribution_path for f in files_without]
    assert merkle_root != root_without_exclusion
    assert "pkg/reg.json" not in names
    assert "pkg/__init__.py" in names
    assert len(_warnings(caplog)) == 1
    assert _warnings(caplog)[0].startswith(f"ID registry: {registry} is inside")


def test_exclusion_is_the_same_root_as_a_tree_without_the_registry(
    tmp_path: Path,
) -> None:
    with_registry = _project(tmp_path / "a")
    without_registry = _project(tmp_path / "b")
    (without_registry / "pkg" / "reg.json").unlink()

    root_with, _, cleanup = get_wheel_files(
        with_registry, exclude_path=with_registry / "pkg" / "reg.json"
    )
    cleanup()
    root_without, _, cleanup = get_wheel_files(without_registry)
    cleanup()
    assert root_with == root_without


def test_other_spelling_of_the_registry_path_matches(tmp_path: Path) -> None:
    root = _project(tmp_path)
    spelled = root / "pkg" / ".." / "pkg" / "reg.json"
    _, files, cleanup = get_wheel_files(root, exclude_path=spelled)
    cleanup()
    assert "pkg/reg.json" not in [f.distribution_path for f in files]


@pytest.mark.parametrize("where", ["outside", "not-discovered", "missing"])
def test_registry_not_in_the_file_set_is_silent_and_changes_nothing(
    where: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _project(tmp_path, registry_in_package=where != "not-discovered")
    registry = {
        "outside": tmp_path / "elsewhere.json",
        "not-discovered": root / "reg.json",
        "missing": root / "pkg" / "new-registry.json",
    }[where]
    expected_root, expected_files, cleanup = get_wheel_files(root)
    cleanup()

    with caplog.at_level(logging.WARNING):
        merkle_root, files, cleanup = get_wheel_files(root, exclude_path=registry)
    cleanup()

    assert merkle_root == expected_root
    assert [f.distribution_path for f in files] == [
        f.distribution_path for f in expected_files
    ]
    assert not _warnings(caplog)


def _built_copies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    copies: dict[str, bytes | None],
    extracted_in: str = "extracted",
    built: bool = True,
) -> Path:
    """A ``uv_build`` project whose build-and-read discovery yields
    *copies* (wheel path -> bytes, ``None`` for a directory), extracted
    below *extracted_in* (outside the project, as a real build's are,
    unless ``TMPDIR`` is inside it); *built* marks them as a build's."""
    project = tmp_path / "proj"
    project.mkdir()
    make_backend_project(project, "uv_build")
    extracted = tmp_path / extracted_in
    files = [
        IncludedFile(str(_write(extracted, name, data)), name, built=built)
        for name, data in copies.items()
    ]
    monkeypatch.setattr(
        BUILD_AND_READ,
        mock.create_autospec(build_and_read_wheel, return_value=(files, lambda: None)),
    )
    return project


def _write(root: Path, name: str, data: bytes | None) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if data is None:
        path.mkdir()
    else:
        path.write_bytes(data)
    return path


_REG = b'{"files": {}}\n'


@pytest.mark.parametrize(
    ("registry", "copy", "left_out"),
    [
        ("src/pkg/reg.json", ("pkg/reg.json", _REG), True),
        ("pkg/reg.json", ("pkg/reg.json", _REG), True),
        ("src/pkg/reg.json", ("pkg/reg.json", b"{}"), False),
        ("reg.json", ("pkg/reg.json", _REG), False),
        ("src/pkg/reg.json", ("other/reg.json", _REG), False),
        ("../reg.json", ("reg.json", _REG), False),
        ("src/pkg/data/reg.json", ("data/reg.json", _REG), False),
    ],
    ids=["src", "flat", "other-bytes", "longer", "other-dir", "outside", "short"],
)
def test_build_and_read_copy_of_the_registry_is_left_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    registry: str,
    copy: tuple[str, bytes],
    left_out: bool,
) -> None:
    """A build-and-read file is a copy outside the project: it is the
    registry when its wheel path is the registry's project-relative path,
    or a tail of it (src layout), and its bytes are the registry's."""
    project = _built_copies(
        tmp_path, monkeypatch, {"pkg/__init__.py": b"x = 1\n", copy[0]: copy[1]}
    )
    declared = _write(project, registry, _REG)
    with caplog.at_level(logging.WARNING):
        _, files, cleanup = get_wheel_files(
            project,
            build_options=BuildOptions(allow=True),
            exclude_path=declared,
        )
    cleanup()
    names = [f.distribution_path for f in files]
    assert "pkg/__init__.py" in names
    assert (copy[0] not in names) is left_out
    assert len(_warnings(caplog)) == int(left_out)


@pytest.mark.parametrize(
    ("copies", "where", "outcome"),
    [
        ({"pkg/reg.json": _REG, "reg.json": _REG}, "extracted", (["reg.json"], 1)),
        (
            {"src/pkg/reg.json": _REG, "pkg/reg.json": _REG},
            "extracted",
            (["pkg/reg.json"], 1),
        ),
        ({"pkg/reg.json": _REG}, "proj/tmp", ([], 1)),
        ({"pkg/reg.json": _REG}, "", (["pkg/reg.json"], 0)),
        ({"pkg/reg.json": None}, "extracted", ([], 0)),
    ],
    ids=["tail-too-short", "longest", "tmpdir-in-project", "not-built", "unreadable"],
)
def test_one_readable_built_copy_is_the_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    copies: dict[str, bytes | None],
    where: str,
    outcome: tuple[list[str], int],
) -> None:
    """One copy at most is left out, the longest, with one warning, wherever
    the build extracted it (``TMPDIR`` inside the project included); a file
    no build produced (*where* empty: static discovery's ``extracted``)
    with the registry's bytes is another file, kept; one that cannot be
    read is not taken for the registry (the scan skips a directory
    silently)."""
    project = _built_copies(
        tmp_path, monkeypatch, copies, where or "extracted", built=bool(where)
    )
    declared = _write(project, "src/pkg/reg.json", _REG)
    with caplog.at_level(logging.WARNING):
        _, files, cleanup = get_wheel_files(
            project, build_options=BuildOptions(allow=True), exclude_path=declared
        )
    cleanup()
    assert ([f.distribution_path for f in files], len(_warnings(caplog))) == outcome


def test_registry_not_saved_yet_has_no_built_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A declared registry with no file yet (a library registry not saved):
    a built member at its path is no copy of it, kept, silently."""
    project = _built_copies(tmp_path, monkeypatch, {"pkg/reg.json": _REG})
    declared = project / "src" / "pkg" / "reg.json"
    with caplog.at_level(logging.WARNING):
        _, files, cleanup = get_wheel_files(
            project, build_options=BuildOptions(allow=True), exclude_path=declared
        )
    cleanup()
    assert ([f.distribution_path for f in files], _warnings(caplog)) == (
        ["pkg/reg.json"],
        [],
    )


def test_built_file_keeps_its_absolute_path_inside_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A build's file under a ``TMPDIR`` inside the project is still a
    build's: its ``physical_path`` is absolute, not a project-relative path
    naming the run's random extraction directory."""
    project = _built_copies(tmp_path, monkeypatch, {"pkg/m.py": b"x\n"}, "proj/tmp")
    _, files, cleanup = get_wheel_files(project, build_options=BuildOptions(allow=True))
    cleanup()
    (found,) = files
    assert Path(found.physical_path).is_absolute()
    assert project_relative_or_fallback(found.physical_path, "pkg/m.py") == "pkg/m.py"


def _rooted(tmp_path: Path, rel: str) -> tuple[Path, Path]:
    """(project, registry): a registry file at *rel* below the project."""
    project = tmp_path / "proj"
    registry = _write(project, rel, _REG)
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
    assert len(_warnings(caplog)) == int(left_out is not None)


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
        _write(project, marker, b"")
    path = _write(project, "src/demo/reg.json", _REG)
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
    _write(project, "pyproject.toml", _TAIL_NAMED_TOML)
    _write(project, "src/demo/__init__.py", b"x = 1\n")
    _write(project, "extra/reg.json", b'{"unrelated": true}\n')
    _write(project, "extra/reg2.json", b'{"other": 1}\n')
    path = _write(project, "src/demo/data/reg.json", _REG)
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
        _write(project, "demo/reg.json", _REG)
        (tmp_path / "alias").symlink_to(project, target_is_directory=True)
        registry, root = tmp_path / "alias" / "demo" / "reg.json", project
    else:
        target = _write(tmp_path, "elsewhere/reg.json", _REG)
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
        "sdist-file": _write(tmp_path, "demo-1.0.tar.gz", b""),
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
    assert _warnings(caplog) == [REGISTRY_IN_FILE_SET_WARNING % registry]
