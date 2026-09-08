# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for read_pyproject()'s [project]-focused parsing paths and its
private helpers (readme/author extraction, provenance building).

See also: test_pyproject_license.py for license-classifier-conflict
recovery and license-hint-resolution tests, split out to keep this file
under this repo's file-size soft limit; test_pyproject_dynamic.py for
PEP 621 ``dynamic`` field resolution
(:mod:`pitloom.extract._pyproject_dynamic`); test_poetry_pyproject.py
for the [tool.poetry] fallback/override behaviour; test_hatch_hook_metadata.py
for the Hatchling build-hook path.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest
from pyproject_metadata import StandardMetadata

from pitloom.core._config_types import PitloomConfig
from pitloom.extract._pyproject import (
    _build_provenance,
    _extract_authors,
    _extract_readme,
    _read_pyproject_fallback,
    _try_read_poetry,
    read_pyproject,
)

# ---------------------------------------------------------------------------
# read_pyproject -- no [project] section, no [tool.poetry] fallback
# ---------------------------------------------------------------------------


def test_read_pyproject_no_project_no_poetry_detects_license_from_dir() -> None:
    """No ``[project]``/``[tool.poetry]``: falls through to an empty
    ``ProjectMetadata`` whose license is detected independently from the
    project directory (line 85's ``license_prov`` truthy branch)."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text("[build-system]\n")
        (tmp_path / "LICENSE").write_text("MIT License", encoding="utf-8")
        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="MIT",
        ):
            metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    assert metadata.name == ""
    assert metadata.license_name == "MIT"
    assert "license" in metadata.provenance


def test_read_pyproject_resolves_license_files() -> None:
    """PEP 639 ``[project.license-files]`` resolves to a project-root-relative
    path list, mirroring real-world usage (see
    ``tests/fixtures/real-world-projects/setuptools/cachetools-7.1.8``)."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "LICENSE").write_text("MIT License", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\n'
            'license = "MIT"\nlicense-files = ["LICENSE"]\n',
            encoding="utf-8",
        )
        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    assert metadata.license_files == ["LICENSE"]
    assert metadata.provenance["license_files"] == (
        "Source: pyproject.toml | Field: project.license-files"
    )


def test_read_pyproject_no_license_files_declared() -> None:
    """No ``[project.license-files]`` key: resolves to an empty list, not
    ``None`` or a missing field."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\nlicense = "MIT"\n',
            encoding="utf-8",
        )
        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    assert not metadata.license_files
    assert "license_files" not in metadata.provenance


def test_read_pyproject_explicit_empty_requires_python_gets_provenance() -> None:
    """An explicit `requires-python = ""` (PEP 621's equivalent of Poetry's
    `python = "*"`) resolves to None but must still record provenance --
    merge_project_metadata() relies on that presence to treat the None as
    an authoritative "no constraint", not absent."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\nrequires-python = ""\n',
            encoding="utf-8",
        )
        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    assert metadata.requires_python is None
    assert metadata.provenance["requires_python"] == (
        "Source: pyproject.toml | Field: project.requires-python"
    )


def test_read_pyproject_explicit_empty_requires_python_survives_poetry_gap_fill() -> (
    None
):
    """The [project] table's explicit `requires-python = ""` must win over
    [tool.poetry]'s real constraint through the actual read_pyproject()
    merge -- the concrete, reachable regression this presence check
    exists to prevent, not just a synthetic unit-level scenario."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            'name = "pkg"\n'
            'version = "1.0.0"\n'
            'requires-python = ""\n'
            "\n"
            "[tool.poetry]\n"
            'name = "pkg"\n'
            'version = "1.0.0"\n'
            "\n"
            "[tool.poetry.dependencies]\n"
            'python = ">=3.8"\n',
            encoding="utf-8",
        )
        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    assert metadata.requires_python is None


def test_read_pyproject_no_requires_python_declared() -> None:
    """No `[project.requires-python]` key: resolves to None, and no
    provenance is recorded -- distinct from an explicit empty string."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )
        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    assert metadata.requires_python is None
    assert "requires_python" not in metadata.provenance


def test_read_pyproject_no_project_no_poetry_no_license_found() -> None:
    """No ``[project]``, no ``[tool.poetry]``, and nothing in the directory
    that looks like a license: ``license_prov`` stays falsy."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text("[build-system]\n")
        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    assert metadata.name == ""
    assert metadata.license_name is None


# ---------------------------------------------------------------------------
# read_pyproject -- dynamic version present but unresolvable
# ---------------------------------------------------------------------------


def test_read_pyproject_fallback_records_name_provenance() -> None:
    """``_read_pyproject_fallback`` records ``prov["name"]`` when a non-empty
    *name* is supplied even though there is no usable ``[project]`` section
    (e.g. a caller reusing a name resolved from elsewhere)."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text("[build-system]\n")
        metadata, _config = _read_pyproject_fallback(
            {},
            pyproject_path,
            "mypkg",
            PitloomConfig(),
            include_locked_dependencies=True,
        )
    assert metadata.name == "mypkg"
    assert metadata.provenance["name"] == "Source: pyproject.toml | Field: project.name"


def test_read_pyproject_dynamic_version_unresolvable() -> None:
    """``dynamic = ["version"]`` but no Hatchling path/``__about__.py`` found:
    the dynamic-version block is skipped (line 96->107) and
    ``pyproject-metadata`` is left to raise (dynamic version) or the field
    is simply absent from the parsed metadata."""
    content = """
[project]
name = "no-resolvable-version"
dynamic = ["version"]
"""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text(content)
        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    assert metadata.name == "no-resolvable-version"
    assert metadata.version is None


# ---------------------------------------------------------------------------
# read_pyproject -- StandardMetadata.from_pyproject() failure
# ---------------------------------------------------------------------------


def test_read_pyproject_invalid_metadata_raises_value_error() -> None:
    """A ``[project]`` section that ``pyproject-metadata`` cannot parse (here:
    an invalid PEP 440 version string) surfaces as ``ValueError``, not the
    raw underlying exception."""
    content = """
[project]
name = "bad-version-pkg"
version = "not-a-valid-version!!"
"""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text(content)
        with pytest.raises(ValueError, match="Failed to parse project metadata"):
            read_pyproject(tmp_path / "pyproject.toml")


# ---------------------------------------------------------------------------
# _build_provenance -- direct unit tests for branches unreachable/awkward
# to reach purely through read_pyproject()
# ---------------------------------------------------------------------------


def test_build_provenance_no_version_source_no_version_field() -> None:
    """Neither a resolved dynamic-version source nor a declared
    ``project.version`` field: the ``version`` key is omitted entirely
    (line 185->188)."""
    prov = _build_provenance({"name": "pkg"}, version_source=None)
    assert "version" not in prov


def test_build_provenance_license_override_without_declared_field() -> None:
    """``license_prov_override`` is set but ``project.license`` was never
    declared: the override still lands in ``prov["license"]`` via the
    fallback branch at the end of the function (line 198)."""
    prov = _build_provenance(
        {"name": "pkg"},
        version_source=None,
        license_prov_override="Source: LICENSE | Method: licenseid_detection",
    )
    assert prov["license"] == "Source: LICENSE | Method: licenseid_detection"


# ---------------------------------------------------------------------------
# _extract_readme -- inline readme text (PEP 621 {text = ...} table)
# ---------------------------------------------------------------------------


def test_extract_readme_inline_text() -> None:
    """A readme object exposing ``.text`` (no usable ``.file``) returns the
    inline text directly (lines 238-239)."""
    fake_readme = SimpleNamespace(file=None, text="Hello from inline readme.")
    std = SimpleNamespace(readme=fake_readme)
    result = _extract_readme(cast(StandardMetadata, std), override=None)
    assert result == "Hello from inline readme."


def test_extract_readme_no_file_no_text() -> None:
    """A readme object with neither a usable ``.file`` nor ``.text``
    resolves to ``None``."""
    fake_readme = SimpleNamespace(file=None, text=None)
    std = SimpleNamespace(readme=fake_readme)
    result = _extract_readme(cast(StandardMetadata, std), override=None)
    assert result is None


# ---------------------------------------------------------------------------
# _extract_authors -- entries that resolve to nothing get skipped
# ---------------------------------------------------------------------------


def test_extract_authors_skips_empty_entries() -> None:
    """An ``(name, email)`` pair that is entirely empty is dropped rather
    than appended as an empty dict (line 318->314)."""
    std = SimpleNamespace(authors=[("", ""), ("Bob", ""), ("", "carol@example.com")])
    result = _extract_authors(cast(StandardMetadata, std))
    assert result == [{"name": "Bob"}, {"email": "carol@example.com"}]


# ---------------------------------------------------------------------------
# _try_read_poetry -- extract_poetry_metadata failure paths
# ---------------------------------------------------------------------------


def test_try_read_poetry_value_error_returns_none() -> None:
    """``extract_poetry_metadata`` raising ``ValueError`` is swallowed and
    reported as "no poetry metadata available" (lines 391-392)."""
    data = {"tool": {"poetry": {"name": "pkg"}}}
    with tempfile.TemporaryDirectory() as d:
        with patch(
            "pitloom.extract._pyproject.extract_poetry_metadata",
            side_effect=ValueError("boom"),
        ):
            result = _try_read_poetry(data, Path(d))
    assert result is None


def test_try_read_poetry_key_error_returns_none() -> None:
    """Same as above, for ``KeyError``."""
    data = {"tool": {"poetry": {"name": "pkg"}}}
    with tempfile.TemporaryDirectory() as d:
        with patch(
            "pitloom.extract._pyproject.extract_poetry_metadata",
            side_effect=KeyError("missing"),
        ):
            result = _try_read_poetry(data, Path(d))
    assert result is None
