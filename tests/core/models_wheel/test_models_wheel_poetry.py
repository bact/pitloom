# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Poetry-backed wheel file discovery
(:mod:`pitloom.core._models_wheel_poetry`).

See also: tests/core/models_wheel/test_models_wheel_dispatch.py for
the facade-level backend-dispatch/fallback-warning tests;
tests/core/models_wheel/test_models_wheel_setuptools.py for the
setuptools discovery module's own tests, which this file mirrors in shape.
"""

import logging
from pathlib import Path

import pytest

from pitloom.core._models_wheel_poetry import discover

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "projects"
SRC_LAYOUT_FIXTURE = FIXTURES / "sampleproject-poetry-src"
INCLUDE_EXCLUDE_FIXTURE = FIXTURES / "sampleproject-poetry-include-exclude"


def test_discover_src_layout_regression() -> None:
    """Regression: a ``packages = [{include = ..., from = "src"}]`` layout
    must resolve the distribution path without the ``src/`` prefix leaking
    in -- the same ``physical_path``/``distribution_path`` divergence
    setuptools' ``where=`` case guards against."""
    result = discover(SRC_LAYOUT_FIXTURE)

    assert result is not None
    distribution_paths = {f.distribution_path for f in result}
    assert distribution_paths == {"sampleproject_poetry_src/__init__.py"}
    assert not any(p.startswith("src/") for p in distribution_paths)


def test_discover_resolves_absolute_physical_paths() -> None:
    """``IncludedFile.path`` must be absolute, matching Hatchling's own
    ``IncludedFile.path`` contract."""
    result = discover(SRC_LAYOUT_FIXTURE)

    assert result is not None
    for included_file in result:
        assert Path(included_file.path).is_absolute()


def test_discover_honors_include_and_exclude() -> None:
    """``include`` pulls in a file outside the auto-discovered package
    directory; ``exclude`` drops a file that would otherwise be included
    by default. Both must take effect together, matching a real Poetry
    wheel build."""
    result = discover(INCLUDE_EXCLUDE_FIXTURE)

    assert result is not None
    distribution_paths = {f.distribution_path for f in result}
    assert distribution_paths == {
        "extra_data/included.txt",
        "sampleproject_poetry_include_exclude/__init__.py",
    }
    assert "sampleproject_poetry_include_exclude/data.json" not in distribution_paths
    assert not any(p.startswith("notes/") for p in distribution_paths)


def test_discover_accepts_pyproject_data_kwarg() -> None:
    """Interface-uniformity regression: matches
    :class:`~pitloom.core._models_wheel_types.BackendDiscoverer`'s shared
    call signature -- poetry-core's ``Factory`` reads ``pyproject.toml``
    itself, so the argument is accepted and ignored, not required."""
    result = discover(
        SRC_LAYOUT_FIXTURE, pyproject_data={"tool": {"poetry": {"name": "pkg"}}}
    )

    assert result is not None


def test_discover_returns_none_and_warns_on_non_poetry_project(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A project with no resolvable ``[tool.poetry]``/``[project]`` name
    or version fails poetry-core's own ``Factory`` -- discover() must
    catch that and return ``None`` with a warning, not propagate the
    exception, so the caller can fall back accordingly."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["poetry-core"]\n'
        'build-backend = "poetry.core.masonry.api"\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        result = discover(tmp_path)

    assert result is None
    assert "Poetry file discovery failed" in caplog.text
