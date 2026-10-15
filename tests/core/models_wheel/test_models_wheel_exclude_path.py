# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``get_wheel_files(exclude_path=...)``: the declared Loom ID
registry is left out of the file set and the Merkle root.

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
from pitloom.core.walk_rules import REGISTRY_IN_FILE_SET_WARNING
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
) -> Path:
    """A ``uv_build`` project whose build-and-read discovery yields
    *copies* (wheel path -> bytes, ``None`` for a directory), extracted
    below *extracted_in* (outside the project, as a real build's are)."""
    project = tmp_path / "proj"
    project.mkdir()
    make_backend_project(project, "uv_build")
    extracted = tmp_path / extracted_in
    files = [
        IncludedFile(path=str(_write(extracted, name, data)), distribution_path=name)
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
    ],
    ids=["src-layout", "flat", "other-bytes", "longer", "other-dir", "outside"],
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
    ("copies", "extracted_in", "outcome"),
    [
        ({"pkg/reg.json": _REG, "reg.json": _REG}, "extracted", ([], 1)),
        ({"pkg/reg.json": _REG}, "proj/other", (["pkg/reg.json"], 0)),
        ({"pkg/reg.json": None}, "extracted", ([], 0)),
    ],
    ids=["two-copies", "in-project", "unreadable"],
)
def test_only_a_readable_copy_outside_the_project_is_the_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    copies: dict[str, bytes | None],
    extracted_in: str,
    outcome: tuple[list[str], int],
) -> None:
    """Every copy is left out, with one warning; a project file with the
    registry's bytes is another file, kept; one that cannot be read is not
    taken for the registry (the scan skips a directory silently)."""
    project = _built_copies(tmp_path, monkeypatch, copies, extracted_in)
    declared = _write(project, "src/pkg/reg.json", _REG)
    with caplog.at_level(logging.WARNING):
        _, files, cleanup = get_wheel_files(
            project, build_options=BuildOptions(allow=True), exclude_path=declared
        )
    cleanup()
    assert ([f.distribution_path for f in files], len(_warnings(caplog))) == outcome
