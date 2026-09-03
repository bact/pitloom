# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for PEP 621 ``dynamic`` field resolution
(:mod:`pitloom.extract._pyproject_dynamic`).

See also: test_pyproject.py for ``read_pyproject()``'s own [project]-focused
parsing paths this module's ``prepare_dynamic_version()`` feeds into.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from pitloom.extract._pyproject_dynamic import (
    _extract_dynamic_version,
    _extract_setuptools_dynamic_version,
    _read_version_from_file,
    prepare_dynamic_version,
)

# ---------------------------------------------------------------------------
# _extract_dynamic_version -- [tool.setuptools.dynamic], Hatchling
# version-path, and fallback candidates
# ---------------------------------------------------------------------------


def test_extract_dynamic_version_setuptools_dynamic_attr(tmp_path: Path) -> None:
    """Regression: ``[tool.setuptools.dynamic] version = {attr =
    "pkg.__version__"}`` -- setuptools' own dynamic-version directive --
    must resolve even when a ``[project]`` table is present (found via
    real-world fixture netcal 1.4.0, which uses exactly this pattern;
    `StandardMetadata`'s backend-agnostic parsing has no concept of this
    setuptools-specific table, so nothing else on this path resolved it
    before this fix)."""
    pyproject_data = {
        "project": {"name": "pkg", "dynamic": ["version"]},
        "tool": {"setuptools": {"dynamic": {"version": {"attr": "pkg.__version__"}}}},
    }
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text(
        '__version__ = "1.4.0"\n', encoding="utf-8"
    )

    version, source = _extract_dynamic_version(tmp_path, pyproject_data)

    assert version == "1.4.0"
    assert source is not None
    assert "attr_directive" in source


def test_extract_dynamic_version_setuptools_dynamic_file(tmp_path: Path) -> None:
    """``[tool.setuptools.dynamic] version = {file = "VERSION"}`` -- the
    file-directive variant of the same setuptools-specific table."""
    pyproject_data = {
        "project": {"name": "pkg", "dynamic": ["version"]},
        "tool": {"setuptools": {"dynamic": {"version": {"file": "VERSION"}}}},
    }
    (tmp_path / "VERSION").write_text("2.0.0", encoding="utf-8")

    version, source = _extract_dynamic_version(tmp_path, pyproject_data)

    assert version == "2.0.0"
    assert source is not None
    assert "file_directive" in source


def test_extract_dynamic_version_setuptools_dynamic_missing_falls_through(
    tmp_path: Path,
) -> None:
    """When ``[tool.setuptools.dynamic] version``'s ``attr:`` target
    doesn't resolve to anything, extraction falls through to the
    generic Hatchling/candidate-file scan rather than giving up."""
    pyproject_data = {
        "project": {"name": "pkg", "dynamic": ["version"]},
        "tool": {
            "setuptools": {"dynamic": {"version": {"attr": "nonexistent.__version__"}}}
        },
    }
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__about__.py").write_text(
        '__version__ = "9.9.9"\n', encoding="utf-8"
    )

    version, source = _extract_dynamic_version(tmp_path, pyproject_data)

    assert version == "9.9.9"
    assert source is not None
    assert "dynamic_extraction" in source


def test_extract_dynamic_version_hatch_path_missing_file() -> None:
    """``[tool.hatch.version].path`` is declared but the file does not
    exist: falls through to the candidate-file scan (line 336->345)."""
    pyproject_data = {
        "project": {"name": "pkg"},
        "tool": {"hatch": {"version": {"path": "src/pkg/__about__.py"}}},
    }
    with tempfile.TemporaryDirectory() as d:
        version, source = _extract_dynamic_version(Path(d), pyproject_data)
    assert version is None
    assert source is None


def test_extract_dynamic_version_hatch_path_exists_no_version_line() -> None:
    """The Hatchling version file exists but has no ``__version__`` line:
    falls through to the candidate-file scan (line 338->345)."""
    pyproject_data = {
        "project": {"name": "pkg"},
        "tool": {"hatch": {"version": {"path": "VERSION.py"}}},
    }
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "VERSION.py").write_text("# no version here\n", encoding="utf-8")
        version, source = _extract_dynamic_version(tmp_path, pyproject_data)
    assert version is None
    assert source is None


def test_extract_dynamic_version_candidate_exists_without_version() -> None:
    """A candidate file (``__about__.py``) exists but has no ``__version__``
    line: the loop continues past it (line 359->356) and ultimately
    reports nothing found (line 366)."""
    pyproject_data = {"project": {"name": "pkg"}}
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "__about__.py").write_text("# empty\n", encoding="utf-8")
        version, source = _extract_dynamic_version(tmp_path, pyproject_data)
    assert version is None
    assert source is None


def test_extract_dynamic_version_no_hatch_no_candidates() -> None:
    """Nothing declared and nothing found on disk: plain ``(None, None)``
    (line 366)."""
    with tempfile.TemporaryDirectory() as d:
        version, source = _extract_dynamic_version(Path(d), {"project": {}})
    assert version is None
    assert source is None


def test_extract_dynamic_version_finds_about_file() -> None:
    """Sanity check the successful candidate-scan path still works
    alongside the new failure-path coverage above."""
    pyproject_data = {"project": {"name": "pkg"}}
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__about__.py").write_text(
            '__version__ = "4.5.6"\n', encoding="utf-8"
        )
        version, source = _extract_dynamic_version(tmp_path, pyproject_data)
    assert version == "4.5.6"
    assert source is not None
    assert "dynamic_extraction" in source


# ---------------------------------------------------------------------------
# _read_version_from_file -- error handling
# ---------------------------------------------------------------------------


def test_read_version_from_file_missing_file_returns_none() -> None:
    """A nonexistent path raises ``FileNotFoundError`` (an ``OSError``
    subclass), caught and turned into ``None`` (lines 377-379)."""
    with tempfile.TemporaryDirectory() as d:
        result = _read_version_from_file(Path(d) / "does-not-exist.py")
    assert result is None


def test_read_version_from_file_directory_path_returns_none() -> None:
    """Passing a directory (``IsADirectoryError``, also an ``OSError``
    subclass) is likewise caught and turned into ``None``."""
    with tempfile.TemporaryDirectory() as d:
        result = _read_version_from_file(Path(d))
    assert result is None


# ---------------------------------------------------------------------------
# prepare_dynamic_version -- flit falsy/unexpected fields, PDM fallthrough
# ---------------------------------------------------------------------------


def test_prepare_dynamic_version_flit_falsy_field_skipped(tmp_path: Path) -> None:
    """A falsy or unrecognized field in the Flit resolver's return value is
    skipped rather than folded in (lines 84-85 and the loop continuing past
    the version/description ``elif`` with neither branch taken)."""
    project_data = {"name": "pkg", "dynamic": ["version", "description"]}
    data = {"project": project_data}
    with (
        patch(
            "pitloom.extract._pyproject_dynamic.detect_build_backend",
            return_value="flit",
        ),
        patch(
            "pitloom.extract._pyproject_dynamic.resolve_flit_dynamic_metadata",
            return_value={"version": "", "unexpected-field": "1.0"},
        ),
    ):
        _data, dynamic_fields, version_source, description_source = (
            prepare_dynamic_version(data, project_data, tmp_path / "pyproject.toml")
        )

    assert version_source is None
    assert description_source is None
    assert "version" in dynamic_fields
    assert "description" in dynamic_fields


def test_prepare_dynamic_version_pdm_unresolved_falls_back_to_generic(
    tmp_path: Path,
) -> None:
    """PDM's own resolver coming up empty (e.g. ``source = "call"``) falls
    through to the generic ``__about__.py``/``__version__.py`` heuristic
    (line 102's ``if version:`` false branch), which also finds nothing
    here."""
    project_data = {"name": "pkg", "dynamic": ["version"]}
    data = {"project": project_data}
    with (
        patch(
            "pitloom.extract._pyproject_dynamic.detect_build_backend",
            return_value="pdm",
        ),
        patch(
            "pitloom.extract._pyproject_dynamic.resolve_pdm_dynamic_version",
            return_value=(None, None),
        ),
    ):
        _data, dynamic_fields, version_source, _description_source = (
            prepare_dynamic_version(data, project_data, tmp_path / "pyproject.toml")
        )

    assert version_source is None
    assert dynamic_fields == ["version"]


# ---------------------------------------------------------------------------
# _extract_setuptools_dynamic_version -- directive present but empty
# ---------------------------------------------------------------------------


def test_extract_setuptools_dynamic_version_directive_without_attr_or_file(
    tmp_path: Path,
) -> None:
    """``[tool.setuptools.dynamic] version = {}`` -- a dict directive with
    neither ``attr`` nor ``file`` -- resolves to nothing."""
    pyproject_data: dict[str, Any] = {
        "tool": {"setuptools": {"dynamic": {"version": {}}}}
    }
    version, source = _extract_setuptools_dynamic_version(tmp_path, pyproject_data)
    assert version is None
    assert source is None
