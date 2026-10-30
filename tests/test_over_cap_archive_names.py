# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A warning names an archive by its file name, a licence file by its path
in its project: never by a directory of this machine (a built or
temporary archive sits in one). The once-per-input memory keys the real
path, so two archives of one name are each warned about.

See also: tests/test_over_cap_surfaces.py (the code on each surface);
tests/extract/test_license_detect.py (the licence file's own names).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.extract._license_detect import (
    LICENSE_FILE_MAX_BYTES,
    read_license_file,
    read_license_members,
)
from pitloom.extract.project.sdist import read_sdist
from pitloom.extract.wheel import read_wheel
from tests._lfs import lfs_pointer_bytes
from tests._raw_archive import METADATA, write_raw_zip
from tests.assemble.conftest import _make_sdist
from tests.assemble.embed_surfaces_shared import run_cli

_BIG = b"x" * (LICENSE_FILE_MAX_BYTES + 1)
_WHEEL = "demo-1.0.0-py3-none-any.whl"
_INFO = "demo-1.0.0.dist-info/"
_CAP = "larger than the 262144-byte license-detection cap; skipped"
_Make = Callable[[Path], Path]


def _wheel(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    members = {f"{_INFO}METADATA": METADATA, f"{_INFO}licenses/LICENSE": _BIG}
    return write_raw_zip(directory / _WHEEL, members)


def _sdist(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    return _make_sdist(directory, members={"LICENSE": _BIG})


def _read(archive: Path) -> object:
    reader = read_wheel if archive.suffix == ".whl" else read_sdist
    return reader(archive)


#: route -> (maker, the name shown for the archive and its member).
_ROUTES: dict[str, tuple[_Make, str]] = {
    "wheel": (_wheel, f"{_WHEEL}:{_INFO}licenses/LICENSE"),
    "sdist": (_sdist, "demo-1.0.0.tar.gz:demo-1.0.0/LICENSE"),
}
#: Where the archive sits: beside the test, or in a work directory of a
#: build (``--allow-build`` reads a wheel it made in a temporary one).
_PLACES = {"plain": "archives", "build-temp": "pitloom-build-x1y2z3"}


@pytest.mark.parametrize("place", _PLACES)
@pytest.mark.parametrize("route", _ROUTES)
def test_an_archive_member_over_the_cap_names_the_archive_by_its_file_name(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, route: str, place: str
) -> None:
    make, shown = _ROUTES[route]
    archive = make(tmp_path / _PLACES[place])
    with caplog.at_level(logging.WARNING):
        _read(archive)
    assert caplog.messages == [f"FILE={shown}: {_CAP}"]
    assert str(tmp_path) not in caplog.text
    assert _PLACES[place] not in caplog.text


@pytest.mark.parametrize("route", _ROUTES)
def test_two_archives_of_one_name_are_each_warned_about(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, route: str
) -> None:
    """The memory keys the archive's path, not the name shown: one name,
    two directories, two warnings; one archive read twice, one."""
    make, _ = _ROUTES[route]
    first, second = make(tmp_path / "one"), make(tmp_path / "two")
    assert first.name == second.name and first != second
    with caplog.at_level(logging.WARNING):
        for archive in (first, second, first):
            _read(archive)
    assert len(caplog.messages) == 2
    assert caplog.messages[0] == caplog.messages[1]
    assert str(tmp_path) not in caplog.text


def test_the_command_line_names_a_wheel_by_its_file_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = _wheel(tmp_path / "pitloom-build-x1y2z3")
    out = tmp_path / "out.spdx3.json"
    run_cli(["wheel", str(wheel), "--offline", "-o", str(out)], monkeypatch)
    err = capsys.readouterr().err
    (line,) = [x for x in err.splitlines() if "license-detection cap" in x]
    assert line.startswith(f"WARNING: FILE={_WHEEL}:{_INFO}licenses/LICENSE: ")
    assert str(tmp_path) not in err


def _pointer(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    licence = directory / "LICENSE"
    licence.write_bytes(lfs_pointer_bytes(b"MIT License\n"))
    return licence


def test_a_licence_pointer_is_named_below_its_project_in_the_debug_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _pointer(tmp_path)
    with caplog.at_level(logging.DEBUG):
        assert not read_license_members(tmp_path)
    (message,) = caplog.messages
    assert message.startswith("FILE=LICENSE: Git LFS pointer, content not read")
    assert str(tmp_path) not in message


@pytest.mark.parametrize("how", ["no-root", "shown"])
def test_a_licence_pointer_outside_a_project_is_named_without_its_directory(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, how: str
) -> None:
    licence = _pointer(tmp_path / "elsewhere")
    shown = "docs/LICENSE" if how == "shown" else None
    with caplog.at_level(logging.DEBUG):
        assert read_license_file(licence, shown=shown) is None
    (message,) = caplog.messages
    assert message.startswith(f"FILE={shown or 'LICENSE'}: Git LFS pointer, ")
    assert str(tmp_path) not in message


def test_the_command_line_names_a_licence_pointer_under_debug(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0"\n', encoding="utf-8"
    )
    _pointer(project)
    monkeypatch.setenv("PITLOOM_DEBUG", "1")
    run_cli(["project", str(project), "-o", str(tmp_path / "o.json")], monkeypatch)
    err = capsys.readouterr().err
    debug = [x for x in err.splitlines() if x.startswith("DEBUG: ")]
    lines = [x for x in debug if "Git LFS pointer, content not read" in x]
    assert lines  # the project's licence is read more than once
    for line in lines:
        assert line.startswith("DEBUG: FILE=LICENSE: Git LFS pointer, ")
        assert str(tmp_path) not in line
