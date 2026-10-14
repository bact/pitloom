# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for PEP 621 ``dynamic`` field resolution
(:mod:`pitloom.extract.project.pyproject_dynamic`).

See also: test_pyproject.py for ``read_pyproject()``'s own [project]-focused
parsing paths this module's ``prepare_dynamic_version()`` feeds into.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.extract.project.pyproject_dynamic import (
    _extract_dynamic_version,
    _extract_setuptools_dynamic_version,
    prepare_dynamic_version,
)
from pitloom.extract.project.setuptools import read_pyproject_toml
from tests._symlink import CAN_SYMLINK

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


@pytest.mark.parametrize(
    "content", ["# no version here\n", '__version__ = ""\n'], ids=["none", "empty"]
)
def test_extract_dynamic_version_hatch_path_exists_no_version_line(
    content: str,
) -> None:
    """The Hatchling version file exists but has no, or an empty,
    ``__version__``: falls through to the candidate-file scan."""
    pyproject_data = {
        "project": {"name": "pkg"},
        "tool": {"hatch": {"version": {"path": "VERSION.py"}}},
    }
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "VERSION.py").write_text(content, encoding="utf-8")
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
# Dynamic-version files: read inside the project only
# ---------------------------------------------------------------------------

_HATCH = "[tool.hatch.version]\npath = '{path}'\n"
_OUTSIDE = "outside the project directory"
_SYMLINK = pytest.mark.skipif(not CAN_SYMLINK, reason="cannot create a symlink")


def _link(proj: Path, name: str, out: Path) -> str:
    (proj / name).parent.mkdir(parents=True, exist_ok=True)
    (proj / name).symlink_to(out)
    return name


# Each case: pyproject.toml text ({out} is a version file outside the
# project; the backend reads the project file "v"), what the warning
# names, why the file was not read, files to set up.
_CASES: dict[str, tuple[str, str, str, Any]] = {
    "hatch-dotdot": (_HATCH, "tool.hatch.version.path", _OUTSIDE, "../out/v.py"),
    "hatch-absolute": (_HATCH, "tool.hatch.version.path", _OUTSIDE, None),
    "hatch-symlink": (_HATCH, "tool.hatch.version.path", _OUTSIDE, "link"),
    "hatch-directory": (_HATCH, "tool.hatch.version.path", "not a regular", "dir"),
    "attr-symlink": (
        "[tool.setuptools.dynamic]\nversion = {{attr = 'v.__version__'}}\n",
        "pyproject.toml tool.setuptools.dynamic.version",
        _OUTSIDE,
        "link",
    ),
    "flit-symlink": (
        "[build-system]\nbuild-backend = 'flit_core.buildapi'\n",
        "tool.flit.module",
        _OUTSIDE,
        "link",
    ),
    "pdm-absolute": (
        "[build-system]\nbuild-backend = 'pdm.backend'\n"
        "[tool.pdm.version]\nsource = 'file'\npath = '{path}'\n",
        "tool.pdm.version.path",
        _OUTSIDE,
        None,
    ),
}


@pytest.mark.parametrize(
    "case",
    [pytest.param(k, marks=_SYMLINK) if "symlink" in k else k for k in _CASES],
)
def test_dynamic_version_file_outside_project_not_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, case: str
) -> None:
    """A dynamic-version file outside the project (``..``, absolute, a
    symlink out) or not a regular file is not read: one ``WARNING:``, no
    version, no exception (an absolute ``path`` raised ``ValueError``),
    naming the file by a relative path unless written absolute (flit's
    module was named absolute)."""
    toml, what, reason, path = _CASES[case]
    proj, out = tmp_path / "proj", tmp_path / "out" / "v.py"
    out.parent.mkdir()
    proj.mkdir()
    out.write_text('"""Outside."""\n__version__ = "6.6.6"\n', encoding="utf-8")
    if path == "link":
        path = _link(proj, "v/__init__.py" if "attr" in case else "v.py", out)
    elif path == "dir":
        (proj / "v.py").mkdir()
        path = "v.py"
    head = "[project]\nname = 'v'\ndynamic = ['version', 'description']\n"
    (proj / "pyproject.toml").write_text(
        head + toml.format(path=path or out), encoding="utf-8"
    )
    data = read_pyproject_toml(proj)
    assert data is not None and isinstance(data["project"], dict)
    with caplog.at_level(logging.WARNING):
        _, dynamic, version_source, _ = prepare_dynamic_version(
            data, data["project"], proj / "pyproject.toml"
        )
    assert "version" in dynamic
    assert version_source is None
    [message] = [r.getMessage() for r in caplog.records]
    assert f": could not read for {what}; {reason}" in message
    assert (str(tmp_path) in message) is case.endswith("-absolute")


@pytest.mark.parametrize(
    ("path", "source"),
    [("./src/v.py", "src/v.py"), (None, "v.py")],
    ids=["relative", "absolute-inside"],
)
def test_dynamic_version_hatch_path_inside_project(
    tmp_path: Path, path: str | None, source: str
) -> None:
    """A ``[tool.hatch.version] path`` inside the project is read; its
    ``Source:`` is project-relative, an absolute one's its base name."""
    file = tmp_path / (path or "v.py")
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    data = {"tool": {"hatch": {"version": {"path": path or str(file)}}}}
    assert _extract_dynamic_version(tmp_path, data) == (
        "1.2.3",
        f"Source: {source} | Method: dynamic_extraction",
    )


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
            "pitloom.extract.project.pyproject_dynamic.detect_build_backend",
            return_value="flit",
        ),
        patch(
            "pitloom.extract.project.pyproject_dynamic.resolve_flit_dynamic_metadata",
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
            "pitloom.extract.project.pyproject_dynamic.detect_build_backend",
            return_value="pdm",
        ),
        patch(
            "pitloom.extract.project.pyproject_dynamic.resolve_pdm_dynamic_version",
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
