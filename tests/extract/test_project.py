# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.project.read_project()."""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.extract.project import read_project


def test_read_project_uses_pyproject_when_present(tmp_path: Path) -> None:
    """pyproject.toml wins when present, regardless of setup.cfg/setup.py."""
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        """
[project]
name = "pyproject-pkg"
version = "1.0.0"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = setup-cfg-pkg\nversion = 2.0.0\n", encoding="utf-8"
    )

    metadata, _, config_path = read_project(tmp_path)

    assert metadata.name == "pyproject-pkg"
    assert config_path == pyproject_path


def test_read_project_falls_back_to_setup_cfg(tmp_path: Path) -> None:
    """setup.cfg is used when no pyproject.toml exists."""
    setup_cfg = tmp_path / "setup.cfg"
    setup_cfg.write_text(
        "[metadata]\nname = setup-cfg-pkg\nversion = 2.0.0\n", encoding="utf-8"
    )

    metadata, _, config_path = read_project(tmp_path)

    assert metadata.name == "setup-cfg-pkg"
    assert config_path == setup_cfg


def test_read_project_falls_back_to_setup_py(tmp_path: Path) -> None:
    """setup.py is used when no pyproject.toml or setup.cfg exists."""
    setup_py = tmp_path / "setup.py"
    setup_py.write_text(
        "from setuptools import setup\nsetup(name='setup-py-pkg', version='3.0')\n",
        encoding="utf-8",
    )

    metadata, _, config_path = read_project(tmp_path)

    assert metadata.name == "setup-py-pkg"
    assert config_path == setup_py


def test_read_project_no_source_raises(tmp_path: Path) -> None:
    """Raises FileNotFoundError when no metadata source exists at all."""
    with pytest.raises(FileNotFoundError):
        read_project(tmp_path)


def test_read_project_malformed_pitloom_config_raises(tmp_path: Path) -> None:
    """A malformed [tool.pitloom] section propagates as ValueError, not
    silently discarded or falling back to a different source."""
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "x"

[tool.pitloom]
creator-name = 123
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        read_project(tmp_path)
