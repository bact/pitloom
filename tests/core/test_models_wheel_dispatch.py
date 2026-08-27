# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for get_wheel_files() backend dispatch and fallback-warning
behavior.

See also: tests/core/test_models_wheel_files.py for file-header
scanning and content-type detection tests;
tests/core/test_models_wheel_setuptools.py for the setuptools
discovery module's own tests.
"""

import logging
from pathlib import Path

import pytest
from hatchling.builders.wheel import WheelBuilder

from pitloom.core._models_wheel_types import IncludedFile
from pitloom.core.models import get_wheel_files


def _make_backend_project(tmp_path: Path, build_backend: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        f'[build-system]\nrequires = ["{build_backend.split(".", maxsplit=1)[0]}"]\n'
        f'build-backend = "{build_backend}"\n\n'
        '[project]\nname = "pkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )


def test_get_wheel_files_dispatches_setuptools_backend_to_its_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project whose backend is detected as ``setuptools`` routes
    through the setuptools discovery module, not the Hatchling
    heuristic."""
    _make_backend_project(tmp_path, "setuptools.build_meta")

    def _fake_discover(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile]:
        del project_dir, pyproject_data
        return [IncludedFile(path=str(tmp_path / "a.py"), distribution_path="pkg/a.py")]

    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "pitloom.core._models_wheel_setuptools.discover", _fake_discover
    )
    hatchling_called: list[Path] = []

    def _fail_if_called(project_dir: Path) -> list[IncludedFile]:
        hatchling_called.append(project_dir)
        return []

    monkeypatch.setattr(
        "pitloom.core._models_wheel_hatchling.discover", _fail_if_called
    )

    _root, files = get_wheel_files(tmp_path)

    assert not hatchling_called
    assert [f.distribution_path for f in files] == ["pkg/a.py"]


def test_get_wheel_files_setuptools_no_static_config_falls_back_with_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the setuptools module can't resolve static config (``None``),
    the facade falls back to the Hatchling heuristic and logs a
    warning -- not a silent, unexplained accuracy regression."""
    _make_backend_project(tmp_path, "setuptools.build_meta")
    monkeypatch.setattr(
        "pitloom.core._models_wheel_setuptools.discover",
        lambda project_dir, *, pyproject_data=None: None,
    )
    monkeypatch.setattr(WheelBuilder, "recurse_included_files", lambda _self: iter([]))

    with caplog.at_level(logging.WARNING):
        root, files = get_wheel_files(tmp_path)

    assert root is None
    assert not files
    assert "setuptools" in caplog.text
    assert "Hatchling" in caplog.text


def test_get_wheel_files_setuptools_no_pyproject_skips_doomed_hatchling_attempt(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A setup.py-only project (no pyproject.toml at all) is guaranteed
    to fail Hatchling's own discovery too (it requires a [project]
    table) -- skip that doomed attempt and its confusing
    Hatchling-branded error, logging one clear warning instead of two."""
    (tmp_path / "setup.py").write_text(
        'from setuptools import setup\nsetup(name="pkg", version="1.0.0")\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        root, files = get_wheel_files(tmp_path)

    assert root is None
    assert not files
    assert "no pyproject.toml present" in caplog.text
    assert "Hatchling" not in caplog.text


def test_get_wheel_files_unhandled_backend_falls_back_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A backend with no dedicated discovery module (e.g. Poetry, ahead
    of its own dedicated support landing) still gets a result via the
    Hatchling heuristic, but now with an explicit warning instead of
    silently risking an inaccurate file list -- closing the gap for
    every unhandled backend, not just setuptools."""
    _make_backend_project(tmp_path, "poetry.core.masonry.api")

    with caplog.at_level(logging.WARNING):
        root, files = get_wheel_files(tmp_path)

    assert root is None
    assert not files
    assert "poetry" in caplog.text
    assert "Hatchling" in caplog.text
