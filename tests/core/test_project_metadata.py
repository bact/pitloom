# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.core.project: ProjectMetadata and merge_project_metadata()."""

import tempfile
from pathlib import Path

from pitloom.core.project import ProjectMetadata, merge_project_metadata
from pitloom.extract._license import resolve_license_concluded

# ---------------------------------------------------------------------------
# merge_project_metadata
# ---------------------------------------------------------------------------


def test_merge_project_metadata_primary_wins() -> None:
    """A truthy primary value is kept, even when secondary also has one."""
    primary = ProjectMetadata(name="primary-pkg", version="1.0.0")
    secondary = ProjectMetadata(name="secondary-pkg", version="2.0.0")
    merged = merge_project_metadata(primary, secondary)
    assert merged.version == "1.0.0"


def test_merge_project_metadata_secondary_fills_gaps() -> None:
    """A falsy primary field (None/empty) is filled from secondary."""
    primary = ProjectMetadata(name="pkg", version="1.0.0", description=None)
    secondary = ProjectMetadata(
        name="pkg", version="9.9.9", description="from secondary"
    )
    merged = merge_project_metadata(primary, secondary)
    assert merged.description == "from secondary"
    # Truthy primary field is untouched even though this asserts the same gap-fill call.
    assert merged.version == "1.0.0"


def test_merge_project_metadata_name_always_primary() -> None:
    """``name`` is special-cased: always primary's, even if empty -- never
    silently filled in from a secondary/fallback source."""
    primary = ProjectMetadata(name="")
    secondary = ProjectMetadata(name="secondary-name")
    merged = merge_project_metadata(primary, secondary)
    assert merged.name == ""


def test_merge_project_metadata_provenance_merged() -> None:
    """provenance dicts are merged, primary's entries winning on key conflict."""
    primary = ProjectMetadata(
        name="pkg", provenance={"name": "Source: primary", "version": "Source: primary"}
    )
    secondary = ProjectMetadata(
        name="pkg",
        provenance={"version": "Source: secondary", "description": "Source: secondary"},
    )
    merged = merge_project_metadata(primary, secondary)
    assert merged.provenance == {
        "name": "Source: primary",
        "version": "Source: primary",
        "description": "Source: secondary",
    }


def test_merge_project_metadata_empty_lists_filled_from_secondary() -> None:
    """An empty list/dict counts as falsy and is filled from secondary,
    same rule as scalar fields."""
    primary = ProjectMetadata(name="pkg", keywords=[], urls={}, dependencies=[])
    secondary = ProjectMetadata(
        name="pkg",
        keywords=["a", "b"],
        urls={"Homepage": "https://example.com"},
        dependencies=["requests>=2.0"],
    )
    merged = merge_project_metadata(primary, secondary)
    assert merged.keywords == ["a", "b"]
    assert merged.urls == {"Homepage": "https://example.com"}
    assert merged.dependencies == ["requests>=2.0"]


def test_merge_project_metadata_explicit_empty_container_preserved() -> None:
    """Per GEMINI.md, ``None`` vs ``[]``/``{}`` (empty-but-present) is a distinct
    signal: an empty container with provenance confirming it was explicitly
    declared in *primary* is authoritative (zero dependencies/keywords) and
    must NOT be overwritten by secondary."""
    primary = ProjectMetadata(
        name="pkg",
        dependencies=[],
        keywords=[],
        provenance={
            "dependencies": "Source: pyproject.toml | Field: project.dependencies",
            "keywords": "Source: pyproject.toml | Field: project.keywords",
        },
    )
    secondary = ProjectMetadata(
        name="pkg",
        dependencies=["requests>=2.0"],
        keywords=["tool", "utility"],
        urls={"Homepage": "https://example.com"},
        provenance={
            "dependencies": "Source: tool.poetry | Field: tool.poetry.dependencies",
            "keywords": "Source: tool.poetry | Field: tool.poetry.keywords",
            "urls": "Source: tool.poetry | Field: tool.poetry.urls",
        },
    )
    merged = merge_project_metadata(primary, secondary)
    assert merged.dependencies == []
    assert merged.keywords == []
    assert merged.urls == {"Homepage": "https://example.com"}
    assert merged.provenance["dependencies"] == (
        "Source: pyproject.toml | Field: project.dependencies"
    )
    assert merged.provenance["urls"] == (
        "Source: tool.poetry | Field: tool.poetry.urls"
    )


def test_merge_project_metadata_explicit_empty_license_name_preserved() -> None:
    """Regression: every ``license_name`` producer
    (``_pyproject.py``/``_setuptools_py.py``/``_setuptools_cfg.py``) records
    its provenance under the literal key ``"license"``, not
    ``"license_name"`` -- the field/provenance-key name mismatch the
    ``_PROVENANCE_KEY_ALIASES`` map exists to bridge. An explicitly
    declared-but-empty ``license_name`` in *primary* (e.g. `license = ""`)
    with that provenance recorded must not be overwritten by *secondary*'s
    ``license_name``."""
    primary = ProjectMetadata(
        name="pkg",
        license_name="",
        provenance={"license": "Source: pyproject.toml | Field: project.license"},
    )
    secondary = ProjectMetadata(
        name="pkg",
        license_name="MIT",
        provenance={"license": "Source: tool.poetry | Field: tool.poetry.license"},
    )

    merged = merge_project_metadata(primary, secondary)

    assert merged.license_name == ""
    assert merged.provenance["license"] == (
        "Source: pyproject.toml | Field: project.license"
    )


def test_merge_project_metadata_license_concluded_preserved() -> None:
    """Regression for the specific bug this function was introduced to fix:
    a newly added field (license_concluded, for G2) must merge with the
    same default rule as every other field automatically -- no call site
    needs updating when the schema grows. Before this generic merge
    replaced the two hand-listed implementations, license_concluded was
    missing from one of them and silently dropped."""
    primary = ProjectMetadata(name="pkg", license_name="MIT", license_concluded=None)
    secondary = ProjectMetadata(
        name="pkg", license_name="MIT", license_concluded="Apache-2.0"
    )
    merged = merge_project_metadata(primary, secondary)
    assert merged.license_concluded == "Apache-2.0"


def test_merge_project_metadata_does_not_mutate_inputs() -> None:
    """Neither *primary* nor *secondary* is modified by the merge."""
    primary = ProjectMetadata(name="pkg", provenance={"name": "Source: primary"})
    secondary = ProjectMetadata(
        name="pkg", version="2.0.0", provenance={"version": "Source: secondary"}
    )
    merge_project_metadata(primary, secondary)
    assert primary.version is None
    assert primary.provenance == {"name": "Source: primary"}
    assert secondary.provenance == {"version": "Source: secondary"}


# ---------------------------------------------------------------------------
# resolve_license_concluded (the shared G2 entry point every extractor calls)
# ---------------------------------------------------------------------------


def test_resolve_license_concluded_no_declared_value_skips_scan() -> None:
    """When the caller has no declared value at all, there's nothing to
    compare a second opinion against -- no directory scan is performed."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
        concluded, concluded_prov = resolve_license_concluded(False, tmp_path)
    assert concluded is None
    assert concluded_prov is None


def test_resolve_license_concluded_declared_value_scans_directory() -> None:
    """When the caller *does* have a declared value, the directory is
    independently scanned for a second opinion."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
        concluded, concluded_prov = resolve_license_concluded(True, tmp_path)
    assert concluded == "MIT"
    assert concluded_prov is not None
    assert "LICENSE" in concluded_prov


def test_resolve_license_concluded_no_license_file_present() -> None:
    """A declared value with nothing in the directory to compare against
    yields no second opinion, not a spurious conflict."""
    with tempfile.TemporaryDirectory() as d:
        concluded, concluded_prov = resolve_license_concluded(True, Path(d))
    assert concluded is None
    assert concluded_prov is None
