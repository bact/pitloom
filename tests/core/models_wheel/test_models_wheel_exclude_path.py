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

from pitloom.core._models_wheel_build_and_read import build_and_read_wheel
from pitloom.core._models_wheel_types import IncludedFile
from pitloom.core.build_options import BuildOptions
from pitloom.core.models import get_wheel_files
from pitloom.core.project import project_relative_or_fallback
from tests.build_and_read_shared import BUILD_AND_READ, make_backend_project
from tests.core.models_wheel._exclude_path_shared import REG, warnings_of, write_file


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
    assert len(warnings_of(caplog)) == 1
    assert warnings_of(caplog)[0].startswith(f"ID registry: '{registry}' is inside")


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
    assert not warnings_of(caplog)


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
        IncludedFile(str(write_file(extracted, name, data)), name, built=built)
        for name, data in copies.items()
    ]
    monkeypatch.setattr(
        BUILD_AND_READ,
        mock.create_autospec(build_and_read_wheel, return_value=(files, lambda: None)),
    )
    return project


@pytest.mark.parametrize(
    ("registry", "copy", "left_out"),
    [
        ("src/pkg/reg.json", ("pkg/reg.json", REG), True),
        ("pkg/reg.json", ("pkg/reg.json", REG), True),
        ("src/pkg/reg.json", ("pkg/reg.json", b"{}"), False),
        ("reg.json", ("pkg/reg.json", REG), False),
        ("src/pkg/reg.json", ("other/reg.json", REG), False),
        ("../reg.json", ("reg.json", REG), False),
        ("src/pkg/data/reg.json", ("data/reg.json", REG), False),
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
    declared = write_file(project, registry, REG)
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
    assert len(warnings_of(caplog)) == int(left_out)


@pytest.mark.parametrize(
    ("copies", "where", "outcome"),
    [
        ({"pkg/reg.json": REG, "reg.json": REG}, "extracted", (["reg.json"], 1)),
        (
            {"src/pkg/reg.json": REG, "pkg/reg.json": REG},
            "extracted",
            (["pkg/reg.json"], 1),
        ),
        ({"pkg/reg.json": REG}, "proj/tmp", ([], 1)),
        ({"pkg/reg.json": REG}, "", (["pkg/reg.json"], 0)),
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
    declared = write_file(project, "src/pkg/reg.json", REG)
    with caplog.at_level(logging.WARNING):
        _, files, cleanup = get_wheel_files(
            project, build_options=BuildOptions(allow=True), exclude_path=declared
        )
    cleanup()
    assert ([f.distribution_path for f in files], len(warnings_of(caplog))) == outcome


def test_registry_not_saved_yet_has_no_built_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A declared registry with no file yet (a library registry not saved):
    a built member at its path is no copy of it, kept, silently."""
    project = _built_copies(tmp_path, monkeypatch, {"pkg/reg.json": REG})
    declared = project / "src" / "pkg" / "reg.json"
    with caplog.at_level(logging.WARNING):
        _, files, cleanup = get_wheel_files(
            project, build_options=BuildOptions(allow=True), exclude_path=declared
        )
    cleanup()
    assert ([f.distribution_path for f in files], warnings_of(caplog)) == (
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
