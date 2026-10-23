# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The default output file of `loom project` stays in the current directory
whatever a `setup.cfg` names the project (a `pyproject.toml` name is
validated; a `setup.cfg` one is not).

See also: tests/core/test_file_names.py (the name helper).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom.__main__ import main


@pytest.mark.parametrize(
    ("name", "version", "written"),
    [
        ("../../escaped", "1.0", ".._.._escaped-1.0.spdx3.json"),
        ("a/b", "1/2", "a_b-1_2.spdx3.json"),
        ("con", "", "sbom.spdx3.json"),
    ],
    ids=["dotdot", "separators", "device-name"],
)
def test_a_setup_cfg_name_cannot_choose_the_output_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    version: str,
    written: str,
) -> None:
    project, out = tmp_path / "proj", tmp_path / "a" / "b" / "out"
    project.mkdir()
    out.mkdir(parents=True)
    (project / "setup.py").write_text("from setuptools import setup\nsetup()\n")
    (project / "setup.cfg").write_text(
        f"[metadata]\nname = {name}\nversion = {version}\n", encoding="utf-8"
    )
    monkeypatch.chdir(out)
    monkeypatch.setattr(sys, "argv", ["loom", "project", str(project)])
    assert main() == 0
    assert [p.name for p in out.iterdir()] == [written]
    assert sorted(p.name for p in tmp_path.rglob("*.spdx3.json")) == [written]
