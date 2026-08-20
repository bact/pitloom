# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for read_pyproject()'s [project]-focused parsing paths and its
private helpers (dynamic version resolution, license hint resolution,
readme/author extraction, provenance building).

See also: test_poetry_pyproject.py for the [tool.poetry] fallback/override
behaviour, and test_hatch_hook_metadata.py for the Hatchling build-hook path.
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
    _extract_and_detect_license,
    _extract_authors,
    _extract_dynamic_version,
    _extract_readme,
    _read_pyproject_fallback,
    _read_version_from_file,
    _resolve_license_hint,
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
            {}, pyproject_path, "mypkg", PitloomConfig()
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
# _resolve_license_hint -- direct unit tests for each license object shape
# ---------------------------------------------------------------------------


def test_resolve_license_hint_text_object() -> None:
    """A License object exposing ``.text`` (PEP 639 inline license text)."""
    license_obj = SimpleNamespace(text="Some custom license text.")
    with tempfile.TemporaryDirectory() as d:
        hint, base_prov, fallback = _resolve_license_hint(license_obj, Path(d))
    assert hint == "Some custom license text."
    assert base_prov.endswith(".text")
    assert fallback == ("Some custom license text.", None)


def test_resolve_license_hint_file_object_reads_content() -> None:
    """A License object exposing ``.file`` reads the referenced file's
    content as the detection hint."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "LICENSE.txt").write_text("MIT License text", encoding="utf-8")
        license_obj = SimpleNamespace(file="LICENSE.txt")
        hint, base_prov, fallback = _resolve_license_hint(license_obj, tmp_path)
    assert hint == "MIT License text"
    assert base_prov == "Source: LICENSE.txt"
    assert fallback == ("LICENSE.txt", None)


def test_resolve_license_hint_file_object_missing_file() -> None:
    """A License object whose ``.file`` does not exist on disk: the ``OSError``
    is caught, ``hint`` is ``None``, and the filename is preserved as
    fallback."""
    license_obj = SimpleNamespace(file="does-not-exist.txt")
    with tempfile.TemporaryDirectory() as d:
        hint, base_prov, fallback = _resolve_license_hint(license_obj, Path(d))
    assert hint is None
    assert base_prov == "Source: pyproject.toml | Field: project.license"
    assert fallback == ("does-not-exist.txt", None)


def test_resolve_license_hint_unrecognised_object() -> None:
    """A license object with neither ``.text`` nor ``.file`` falls through to
    the catch-all branch, stringifying the object as the fallback id."""
    license_obj = object()
    with tempfile.TemporaryDirectory() as d:
        hint, base_prov, fallback = _resolve_license_hint(license_obj, Path(d))
    assert hint is None
    assert base_prov == "Source: pyproject.toml | Field: project.license"
    assert fallback == (str(license_obj), None)


# ---------------------------------------------------------------------------
# _extract_and_detect_license -- branches around _resolve_license_hint /
# detect_license_for_project interplay
# ---------------------------------------------------------------------------


def test_extract_and_detect_license_hint_none_returns_fallback() -> None:
    """When ``_resolve_license_hint`` cannot produce a hint (missing license
    file), ``_extract_and_detect_license`` returns its fallback tuple
    directly (line 296)."""
    std = SimpleNamespace(license=SimpleNamespace(file="missing-license.txt"))
    with tempfile.TemporaryDirectory() as d:
        license_id, prov = _extract_and_detect_license(
            cast(StandardMetadata, std), Path(d)
        )
    assert license_id == "missing-license.txt"
    assert prov is None


def test_extract_and_detect_license_detected_differs_from_hint() -> None:
    """Free-text license hint that ``licenseid`` detection resolves to a
    *different* SPDX id: reports the detected id with a
    ``licenseid_detection`` provenance tag (lines 301-303)."""
    std = SimpleNamespace(license="Some custom license text that isn't SPDX")
    with tempfile.TemporaryDirectory() as d:
        with patch(
            "pitloom.extract._pyproject.detect_license_for_project",
            return_value=("Apache-2.0", "Source: detected"),
        ):
            license_id, prov = _extract_and_detect_license(
                cast(StandardMetadata, std), Path(d)
            )
    assert license_id == "Apache-2.0"
    assert prov == (
        "Source: pyproject.toml | Field: project.license | Method: licenseid_detection"
    )


def test_extract_and_detect_license_detected_equals_hint_uses_fallback_id() -> None:
    """Detection agrees with the hint (no new information): when the hint
    came from license *text* (so a non-``None`` ``fallback_id`` exists),
    the fallback id/provenance pair is returned instead (lines 305-307)."""
    std = SimpleNamespace(license=SimpleNamespace(text="MIT-like text"))
    with tempfile.TemporaryDirectory() as d:
        with patch(
            "pitloom.extract._pyproject.detect_license_for_project",
            return_value=("MIT-like text", "Source: irrelevant"),
        ):
            license_id, prov = _extract_and_detect_license(
                cast(StandardMetadata, std), Path(d)
            )
    assert license_id == "MIT-like text"
    assert prov is None


def test_extract_and_detect_license_detected_equals_hint_no_fallback_id() -> None:
    """Detection agrees with the hint and there is no ``fallback_id`` (plain
    string license hint): falls through to the final
    ``return detected, prov`` (line 308)."""
    std = SimpleNamespace(license="Some Custom License Text")
    with tempfile.TemporaryDirectory() as d:
        with patch(
            "pitloom.extract._pyproject.detect_license_for_project",
            return_value=("Some Custom License Text", "Source: detected-prov"),
        ):
            license_id, prov = _extract_and_detect_license(
                cast(StandardMetadata, std), Path(d)
            )
    assert license_id == "Some Custom License Text"
    assert prov == "Source: detected-prov"


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
# _extract_dynamic_version -- Hatchling version-path and fallback candidates
# ---------------------------------------------------------------------------


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
