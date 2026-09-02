# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Flit-core-backed wheel file discovery
(:mod:`pitloom.core._models_wheel_flit`).

See also: tests/core/models_wheel/test_models_wheel_dispatch.py for
the facade-level backend-dispatch/fallback-warning tests;
tests/core/models_wheel/test_models_wheel_poetry.py, which this file
mirrors in shape.
"""

import logging
from pathlib import Path

import pytest

from pitloom.core._models_wheel_flit import discover

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "projects"
SRC_LAYOUT_FIXTURE = (FIXTURES / "sampleproject-flit").resolve()


def test_discover_src_layout_regression() -> None:
    """Regression: flit-core's own ``src/<name>`` search path must resolve
    the distribution path without the ``src/`` prefix leaking in -- the
    same ``physical_path``/``distribution_path`` divergence setuptools'
    ``where=`` case guards against."""
    result = discover(SRC_LAYOUT_FIXTURE)

    assert result is not None
    distribution_paths = {f.distribution_path for f in result}
    assert distribution_paths == {"sampleproject_flit/__init__.py"}
    assert not any(p.startswith("src/") for p in distribution_paths)


def test_discover_resolves_absolute_physical_paths() -> None:
    """``IncludedFile.path`` must be absolute, matching Hatchling's own
    ``IncludedFile.path`` contract."""
    result = discover(SRC_LAYOUT_FIXTURE)

    assert result is not None
    for included_file in result:
        assert Path(included_file.path).is_absolute()


def test_discover_accepts_pyproject_data_kwarg() -> None:
    """Interface-uniformity regression: matches
    :class:`~pitloom.core._models_wheel_types.BackendDiscoverer`'s shared
    call signature -- flit-core's ``read_flit_config()`` reads
    ``pyproject.toml`` itself, so the argument is accepted and ignored,
    not required."""
    result = discover(SRC_LAYOUT_FIXTURE, pyproject_data={"tool": {"flit": {}}})

    assert result is not None


def test_discover_returns_none_and_warns_on_non_flit_project(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A project with no ``[project]`` table fails flit-core's own
    ``read_flit_config()`` -- ``discover()`` must catch that and return
    ``None`` with a warning, not propagate the exception, so the caller
    can fall back accordingly."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["flit_core>=3.9"]\n'
        'build-backend = "flit_core.buildapi"\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        result = discover(tmp_path)

    assert result is None
    assert "Flit file discovery failed" in caplog.text


def test_discover_returns_none_when_module_not_found(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A ``[project] name`` with no matching module directory/file on
    disk fails ``Module.__init__`` -- caught the same way as any other
    resolution failure."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["flit_core>=3.9"]\n'
        'build-backend = "flit_core.buildapi"\n\n'
        '[project]\nname = "nonexistent_pkg"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        result = discover(tmp_path)

    assert result is None
    assert "Flit file discovery failed" in caplog.text
