# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.project.read_project()."""

from __future__ import annotations

import logging
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


def test_read_project_falls_back_past_build_system_only_pyproject(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: a ``pyproject.toml`` declaring only ``[build-system]``
    (a custom/legacy build backend, e.g. real-world PyYAML 6.0.3's
    ``_pyyaml_pep517`` wrapper) has no ``[project]`` table and no
    ``[tool.poetry]`` fallback -- ``read_pyproject()`` alone resolves to
    an empty, nameless stub. When ``setup.cfg``/``setup.py`` hold the
    project's real metadata, ``read_project()`` must fall back to
    :func:`~pitloom.extract._setuptools.read_setuptools` instead of
    silently returning that empty stub -- logging a ``WARNING:``, not
    deviating silently."""
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "custom_pep517_wrapper"\n',
        encoding="utf-8",
    )
    setup_cfg = tmp_path / "setup.cfg"
    setup_cfg.write_text(
        "[metadata]\nname = real-pkg\nversion = 1.2.3\n", encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING):
        metadata, _, config_path = read_project(tmp_path)

    assert metadata.name == "real-pkg"
    assert metadata.version == "1.2.3"
    assert config_path == setup_cfg
    assert "no usable [project] table" in caplog.text


def test_read_project_fallback_preserves_pyproject_pitloom_config(
    tmp_path: Path,
) -> None:
    """Regression: falling back to ``read_setuptools()`` for metadata
    (previous test) must not also discard a real ``[tool.pitloom]``
    section already resolved from ``pyproject.toml`` -- ``[tool.pitloom]``
    always lives there, never in ``setup.cfg``/``setup.py``, regardless
    of which source supplies the project metadata itself."""
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "custom_pep517_wrapper"\n\n'
        "[tool.pitloom]\n"
        'sbom-basename = "custom-name"\n',
        encoding="utf-8",
    )
    setup_cfg = tmp_path / "setup.cfg"
    setup_cfg.write_text(
        "[metadata]\nname = real-pkg\nversion = 1.2.3\n", encoding="utf-8"
    )

    metadata, pitloom_config, _config_path = read_project(tmp_path)

    assert metadata.name == "real-pkg"
    assert pitloom_config.sbom_basename == "custom-name"


def test_read_project_build_system_only_pyproject_no_setuptools_fallback(
    tmp_path: Path,
) -> None:
    """When a ``[build-system]``-only ``pyproject.toml`` has no
    ``setup.cfg``/``setup.py`` to fall back to either, ``read_project()``
    still returns ``read_pyproject()``'s (nameless) result -- no
    FileNotFoundError, matching prior behavior for this narrower case."""
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "custom_pep517_wrapper"\n',
        encoding="utf-8",
    )

    metadata, _, config_path = read_project(tmp_path)

    assert not metadata.name
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
