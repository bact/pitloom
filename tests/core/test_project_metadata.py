# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.core.project: ProjectMetadata and merge_project_metadata()."""

# Explicit `== []`/`== {}` keeps the None-vs-empty distinction.
# pylint: disable=use-implicit-booleaness-not-comparison

import tempfile
from pathlib import Path

import pytest

from pitloom.core.project import (
    ConflictCandidate,
    ProjectMetadata,
    merge_project_metadata,
)
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
    (``project.pyproject``/``project.setuptools_py``/``project.setuptools_cfg``)
    records its provenance under the literal key ``"license"``, not
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


def test_merge_project_metadata_explicit_none_scalar_preserved() -> None:
    """A scalar field resolved to None with confirmed provenance (e.g.
    Poetry's `python = "*"`, meaning "explicitly no constraint") is a
    deliberate, authoritative answer -- not absent -- and must not be
    overwritten by secondary's real value, the same None-vs-[] distinction
    already applied to empty containers above."""
    primary = ProjectMetadata(
        name="pkg",
        requires_python=None,
        provenance={
            "requires_python": (
                "Source: pyproject.toml | Field: tool.poetry.dependencies.python"
            )
        },
    )
    secondary = ProjectMetadata(
        name="pkg",
        requires_python=">=3.8",
        provenance={
            "requires_python": "Source: setup.py | Field: setup(python_requires=...)"
        },
    )
    merged = merge_project_metadata(primary, secondary)
    assert merged.requires_python is None
    assert merged.provenance["requires_python"] == (
        "Source: pyproject.toml | Field: tool.poetry.dependencies.python"
    )


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


def test_merge_project_metadata_does_not_alias_field_conflicts() -> None:
    """Regression for the dataclasses.replace() aliasing bug: replace()
    shares container-field objects with *primary* verbatim unless a field
    is explicitly overridden. field_conflicts must get the same fresh-copy
    treatment as provenance -- a write into merged.field_conflicts (by any
    later caller, e.g. reconcile_installed_metadata) must never leak back
    into primary's or secondary's own field_conflicts dict."""
    primary = ProjectMetadata(name="pkg", version="1.0.0")
    secondary = ProjectMetadata(name="pkg", version="2.0.0")
    merged = merge_project_metadata(primary, secondary)

    assert merged.field_conflicts is not primary.field_conflicts
    assert merged.field_conflicts is not secondary.field_conflicts

    merged.field_conflicts["version"] = [
        {"value": "1.0.0", "role": "declared", "source": "Source: a"},
        {"value": "2.0.0", "role": "declared", "source": "Source: b"},
    ]
    assert primary.field_conflicts == {}
    assert secondary.field_conflicts == {}


def test_merge_project_metadata_field_conflicts_merged_primary_wins(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """field_conflicts is dict-merged like provenance (primary's entries
    winning on key conflict), and a genuine key collision is logged
    rather than silently dropping secondary's whole ConflictCandidate
    list with no signal -- the "no silent deviations" principle applied
    to a data loss, not just a value substitution."""
    primary_candidates: list[ConflictCandidate] = [
        {"value": "1.0.0", "role": "declared", "source": "Source: primary-static"},
        {"value": "1.0.1", "role": "declared", "source": "Source: primary-installed"},
    ]
    secondary_candidates: list[ConflictCandidate] = [
        {"value": "9.0.0", "role": "declared", "source": "Source: secondary-static"},
        {"value": "9.0.1", "role": "declared", "source": "Source: secondary-installed"},
    ]
    primary = ProjectMetadata(
        name="pkg", field_conflicts={"version": primary_candidates}
    )
    secondary = ProjectMetadata(
        name="pkg", field_conflicts={"version": secondary_candidates}
    )

    with caplog.at_level("WARNING"):
        merged = merge_project_metadata(primary, secondary)

    assert merged.field_conflicts == {"version": primary_candidates}
    assert "both sides have a field_conflicts entry" in caplog.text
    assert "['version']" in caplog.text


def test_merge_project_metadata_field_conflicts_no_collision_no_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Disjoint field_conflicts keys merge silently -- no collision, no
    data loss, no warning."""
    primary = ProjectMetadata(
        name="pkg",
        field_conflicts={
            "version": [{"value": "1.0.0", "role": "declared", "source": "Source: a"}]
        },
    )
    secondary = ProjectMetadata(
        name="pkg",
        field_conflicts={
            "license": [{"value": "MIT", "role": "declared", "source": "Source: b"}]
        },
    )

    with caplog.at_level("WARNING"):
        merged = merge_project_metadata(primary, secondary)

    assert set(merged.field_conflicts) == {"version", "license"}
    assert caplog.text == ""


def test_merge_project_metadata_hashes_bound_to_locked_dependencies() -> None:
    """`locked_dependency_hashes` shares `locked_dependencies` provenance,
    so an authoritative lock result with zero hashes is never polluted by
    secondary's hashes."""
    primary = ProjectMetadata(
        name="pkg",
        locked_dependencies=["foo==1.0"],
        locked_dependency_hashes={},
        provenance={
            "locked_dependencies": "Source: poetry.lock | Method: resolved_lockfile"
        },
    )
    secondary = ProjectMetadata(
        name="pkg",
        locked_dependencies=["bar==2.0"],
        locked_dependency_hashes={"bar": "a" * 64},
        provenance={
            "locked_dependencies": "Source: uv.lock | Method: resolved_lockfile"
        },
    )
    merged = merge_project_metadata(primary, secondary)
    assert merged.locked_dependencies == ["foo==1.0"]
    assert merged.locked_dependency_hashes == {}

    # When primary has no locked_dependencies at all, both fall back together
    unlocked_primary = ProjectMetadata(name="pkg")
    merged_fallback = merge_project_metadata(unlocked_primary, secondary)
    assert merged_fallback.locked_dependencies == ["bar==2.0"]
    assert merged_fallback.locked_dependency_hashes == {"bar": "a" * 64}


# ---------------------------------------------------------------------------
# resolve_license_concluded (the G2 entry point embed-wheel calls)
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
