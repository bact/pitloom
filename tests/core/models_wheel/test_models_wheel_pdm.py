# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for PDM-backend-backed wheel file discovery
(:mod:`pitloom.core._models_wheel_pdm`).

See also: tests/core/models_wheel/test_models_wheel_dispatch.py for
the facade-level backend-dispatch/fallback-warning tests;
tests/core/models_wheel/test_models_wheel_poetry.py, which this file
mirrors in shape.
"""

import logging
import subprocess
from pathlib import Path

import pytest

from pitloom.core._models_wheel_pdm import discover

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "projects"
SRC_LAYOUT_FIXTURE = (FIXTURES / "sampleproject-pdm").resolve()


def test_discover_src_layout_regression() -> None:
    """Regression: ``[tool.pdm.build] package-dir = "src"`` must resolve
    the distribution path without the ``src/`` prefix leaking in --
    ``WheelBuilder._collect_files()``'s own prefix-stripping override,
    not the plain ``Builder`` base class."""
    result = discover(SRC_LAYOUT_FIXTURE)

    assert result is not None
    distribution_paths = {f.distribution_path for f in result}
    assert distribution_paths == {"sampleproject_pdm/__init__.py"}
    assert not any(p.startswith("src/") for p in distribution_paths)


def test_discover_resolves_absolute_physical_paths() -> None:
    """``IncludedFile.path`` must be absolute, matching Hatchling's own
    ``IncludedFile.path`` contract."""
    result = discover(SRC_LAYOUT_FIXTURE)

    assert result is not None
    for included_file in result:
        assert Path(included_file.path).is_absolute()


def test_discover_excludes_dist_info_metadata() -> None:
    """``WheelBuilder.get_files()`` would also yield ``.dist-info/``
    metadata files -- ``discover()`` must never include them, matching
    every other backend's discoverer."""
    result = discover(SRC_LAYOUT_FIXTURE)

    assert result is not None
    assert not any(".dist-info/" in f.distribution_path for f in result)


def test_discover_never_writes_to_disk(tmp_path: Path) -> None:
    """Regression: calling ``WheelBuilder.get_files()`` directly would
    write ``METADATA``/``WHEEL``/``.gitignore`` into ``.pdm-build/`` as a
    build-time side effect (``_get_metadata_files()`` ->
    ``context.ensure_build_dir()``) -- ``discover()`` must stay a pure
    read, matching the "static-config read, never a build" contract
    every backend's discoverer follows."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["pdm-backend"]\n'
        'build-backend = "pdm.backend"\n\n'
        '[project]\nname = "pkg"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (project_dir / "pkg").mkdir()
    (project_dir / "pkg" / "__init__.py").write_text("", encoding="utf-8")

    result = discover(project_dir)

    assert result is not None
    assert not (project_dir / ".pdm-build").exists()


def test_discover_never_writes_scm_version_to_disk(tmp_path: Path) -> None:
    """Regression: ``[tool.pdm.version] source = "scm"`` combined with a
    ``write_to`` option makes pdm-backend's own
    ``DynamicVersionBuildHook.pdm_build_initialize()`` write the resolved
    version string to a real file under ``.pdm-build/`` as a side effect
    of resolving the version -- ``discover()`` must never trigger this
    (it doesn't need the resolved version at all to list files), the
    same "static rescan, never a build" contract
    ``test_discover_never_writes_to_disk`` already covers for the
    ``_get_metadata_files()`` case.

    Needs a real git repo with a tag -- pdm-backend's SCM version
    resolution only reaches the disk-writing step (``_write_version``)
    once it has actually resolved a version from SCM; a non-git
    directory fails earlier (``ConfigError: Cannot find the version
    from SCM``), which would pass this test for the wrong reason."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["pdm-backend"]\n'
        'build-backend = "pdm.backend"\n\n'
        '[project]\nname = "pkg"\ndynamic = ["version"]\n\n'
        '[tool.pdm.version]\nsource = "scm"\nwrite_to = "pkg/_version.py"\n',
        encoding="utf-8",
    )
    (project_dir / "pkg").mkdir()
    (project_dir / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    for cmd in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "test@example.com"],
        ["git", "config", "user.name", "test"],
        ["git", "add", "-A"],
        ["git", "commit", "-q", "-m", "init"],
        ["git", "tag", "v1.0.0"],
    ):
        subprocess.run(cmd, cwd=project_dir, check=True)

    result = discover(project_dir)

    assert result is not None
    assert not (project_dir / ".pdm-build").exists()


def test_discover_restores_cwd_when_discovery_fails(tmp_path: Path) -> None:
    """Regression: ``_chdir``'s ``os.chdir()`` back to the original
    directory must happen even when ``discover()`` fails *inside* the
    ``with _chdir(...)`` block (here: a project with no ``[project]``
    table, failing during ``WheelBuilder(project_dir)``/
    ``Config.from_pyproject()``) -- not just on the success path."""
    original_cwd = Path.cwd()
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["pdm-backend"]\nbuild-backend = "pdm.backend"\n',
        encoding="utf-8",
    )

    result = discover(tmp_path)

    assert result is None
    assert Path.cwd() == original_cwd


def test_discover_accepts_pyproject_data_kwarg() -> None:
    """Interface-uniformity regression: matches
    :class:`~pitloom.core._models_wheel_types.BackendDiscoverer`'s shared
    call signature -- pdm-backend's own ``Config.from_pyproject()`` reads
    ``pyproject.toml`` itself, so the argument is accepted and ignored,
    not required."""
    result = discover(SRC_LAYOUT_FIXTURE, pyproject_data={"tool": {"pdm": {}}})

    assert result is not None


def test_discover_returns_none_and_warns_on_non_pdm_project(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A project with no ``[project]`` table fails pdm-backend's own
    ``Config.from_pyproject()`` -- ``discover()`` must catch that and
    return ``None`` with a warning, not propagate the exception, so the
    caller can fall back accordingly."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["pdm-backend"]\nbuild-backend = "pdm.backend"\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        result = discover(tmp_path)

    assert result is None
    assert "PDM file discovery failed" in caplog.text
