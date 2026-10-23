# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""`loom id import --project-dir` roots a new registry at the project, so the
file names of an SBOM are looked up as a run looks them up.

See also: tests/id_registry/test_registry_import_keys.py (the keys written).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pitloom.__main__ import main

_PYPROJECT = (
    '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    '[project]\nname = "demo"\nversion = "{}"\n'
)


def _run(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return main()


def _file_ids(path: Path) -> set[str]:
    graph = json.loads(path.read_text(encoding="utf-8"))["@graph"]
    return {e["spdxId"] for e in graph if e["type"] == "software_File"}


@pytest.fixture(name="above")
def _above(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory holding the project `proj`, current for the test, with an
    SBOM of version 0.1 written next to it."""
    (tmp_path / "proj" / "demo").mkdir(parents=True)
    (tmp_path / "proj" / "pyproject.toml").write_text(_PYPROJECT.format("0.1"))
    (tmp_path / "proj" / "demo" / "__init__.py").write_text("x = 1\n")
    monkeypatch.chdir(tmp_path)
    assert _run(monkeypatch, "project", "proj", "-o", "first.json") == 0
    return tmp_path


@pytest.mark.parametrize(
    ("import_args", "kept"),
    [(["--project-dir", "proj"], True), ([], False)],
    ids=["with-project-dir", "from-above-without"],
)
def test_import_from_above_the_project(
    monkeypatch: pytest.MonkeyPatch,
    above: Path,
    import_args: list[str],
    kept: bool,
) -> None:
    """With `--project-dir` the next run keeps every file id; without it a
    registry rooted above the project cannot match (an SBOM does not say where
    its project was), so the files get new ids."""
    argv = ["id", "import", "first.json", "-o", "reg.json", *import_args]
    assert _run(monkeypatch, *argv) == 0
    (above / "proj" / "pyproject.toml").write_text(_PYPROJECT.format("0.2"))
    argv = ["project", "proj", "--id-registry", "reg.json", "-o", "second.json"]
    assert _run(monkeypatch, *argv) == 0
    second = above / "second.json"
    assert (_file_ids(above / "first.json") == _file_ids(second)) is kept


@pytest.mark.usefixtures("above")
def test_a_project_dir_that_is_not_a_directory_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["id", "import", "first.json", "-o", "r.json", "--project-dir", "absent"]
    assert _run(monkeypatch, *argv) == 1
    assert "ERROR: --project-dir absent is not a directory" in capsys.readouterr().err


@pytest.mark.usefixtures("above")
def test_a_project_dir_other_than_the_registry_root_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An existing registry keeps its root; a different explicit one errors."""
    base = ["id", "import", "first.json", "-o", "reg.json"]
    assert _run(monkeypatch, *base, "--project-dir", "proj") == 0
    assert _run(monkeypatch, *base, "--project-dir", ".") == 1
    assert "project root" in capsys.readouterr().err


def test_a_registry_declared_in_the_project_config_is_found_there(
    monkeypatch: pytest.MonkeyPatch, above: Path
) -> None:
    """Without `-o`, the registry the project's `[tool.pitloom]` declares is
    the one of `--project-dir`, written below it, and a run keeps the ids."""
    pyproject = above / "proj" / "pyproject.toml"
    pyproject.write_text(
        _PYPROJECT.format("0.1") + '[tool.pitloom]\nid-registry = "ids.json"\n'
    )
    assert _run(monkeypatch, "id", "import", "first.json", "--project-dir", "proj") == 0
    assert (above / "proj" / "ids.json").is_file()
    assert not (above / "ids.json").exists()
    assert _run(monkeypatch, "project", "proj", "-o", "second.json") == 0
    assert _file_ids(above / "first.json") == _file_ids(above / "second.json")
