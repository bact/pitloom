# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.project.installed.reconcile_installed_metadata.

Split out of test_installed.py (which covers discovery/parsing) purely to
stay under this repo's file-size soft limit -- see that module's docstring
for the shared fixtures directory and test_installed_integration.py for
read_project()/resolve_project_with_lockfile() end-to-end cases.
"""

# Explicit `== []`/`== {}` keeps the None-vs-empty distinction.
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.core.project import ProjectMetadata
from pitloom.extract._license import classify_license
from pitloom.extract.project._installed_reconcile import reconcile_installed_metadata


def _static(**overrides: object) -> ProjectMetadata:
    base = ProjectMetadata(name="pkg", version="1.0.0")
    base.provenance["name"] = "Source: pyproject.toml"
    base.provenance["version"] = "Source: pyproject.toml"
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_reconcile_genuine_version_conflict(tmp_path: Path) -> None:
    static = _static()
    installed = ProjectMetadata(name="pkg", version="1.0.1")
    installed.provenance["version"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.version == "1.0.0"
    assert merged.field_conflicts["version"] == [
        {"value": "1.0.0", "role": "declared", "source": "Source: pyproject.toml"},
        {"value": "1.0.1", "role": "declared", "source": "Source: pkg.egg-info"},
    ]


def test_reconcile_pep440_equivalent_not_a_conflict(tmp_path: Path) -> None:
    static = _static(version="1.0")
    static.provenance["version"] = "Source: pyproject.toml"
    installed = ProjectMetadata(name="pkg", version="1.0.0")
    installed.provenance["version"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.version == "1.0"
    assert merged.field_conflicts == {}


def test_reconcile_dynamic_version_gap_fill(tmp_path: Path) -> None:
    static = ProjectMetadata(name="pkg", version=None)
    installed = ProjectMetadata(name="pkg", version="2.5.0")
    installed.provenance["version"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.version == "2.5.0"
    assert merged.provenance["version"] == "Source: pkg.egg-info"
    assert merged.field_conflicts == {}


def test_reconcile_installed_not_declared_leaves_static_untouched(
    tmp_path: Path,
) -> None:
    static = _static()
    installed = ProjectMetadata(name="pkg", version=None)  # not declared

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.version == "1.0.0"
    assert merged.field_conflicts == {}


def test_reconcile_requires_python_conflict(tmp_path: Path) -> None:
    static = _static(requires_python=">=3.9")
    static.provenance["requires_python"] = "Source: pyproject.toml"
    installed = ProjectMetadata(name="pkg", version="1.0.0", requires_python=">=3.8")
    installed.provenance["version"] = "Source: pkg.egg-info"
    installed.provenance["requires_python"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.requires_python == ">=3.9"
    assert "requires_python" in merged.field_conflicts


def test_reconcile_requires_python_equivalent_reformatted(tmp_path: Path) -> None:
    static = _static(requires_python=">=3.9")
    static.provenance["requires_python"] = "Source: pyproject.toml"
    installed = ProjectMetadata(name="pkg", version="1.0.0", requires_python=">= 3.9")
    installed.provenance["version"] = "Source: pkg.egg-info"
    installed.provenance["requires_python"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.requires_python == ">=3.9"
    assert "requires_python" not in merged.field_conflicts


def test_reconcile_requires_python_declared_empty_vs_installed_conflict(
    tmp_path: Path,
) -> None:
    """Regression: `requires-python = ""` (PEP 621's explicit "no
    constraint" convention) collapses to `requires_python=None` in every
    static producer, but provenance still records it as declared. Must
    not crash (SpecifierSet(None) raises TypeError, not the
    InvalidSpecifier _requires_python_equal already catches) -- and must
    be treated as a real disagreement against installed's concrete
    constraint, static's None still winning."""
    static = _static(requires_python=None)
    static.provenance["requires_python"] = "Source: pyproject.toml"
    installed = ProjectMetadata(name="pkg", version="1.0.0", requires_python=">=3.9")
    installed.provenance["version"] = "Source: pkg.egg-info"
    installed.provenance["requires_python"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.requires_python is None
    assert "requires_python" in merged.field_conflicts
    assert merged.field_conflicts["requires_python"][0]["value"] == ""


def test_reconcile_requires_python_declared_empty_both_sides_not_a_conflict(
    tmp_path: Path,
) -> None:
    """Both sides explicitly declare "no constraint" -- not a conflict,
    and must not crash either (the same None-vs-comparator hazard, with
    the two normalized-empty values actually equal)."""
    static = _static(requires_python=None)
    static.provenance["requires_python"] = "Source: pyproject.toml"
    installed = ProjectMetadata(name="pkg", version="1.0.0", requires_python="")
    installed.provenance["version"] = "Source: pkg.egg-info"
    installed.provenance["requires_python"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.requires_python is None
    assert "requires_python" not in merged.field_conflicts


def test_reconcile_license_name_conflict_uses_spdx_normalization(
    tmp_path: Path,
) -> None:
    static = _static(license_name="MIT")
    static.provenance["license"] = "Source: pyproject.toml"
    installed = ProjectMetadata(name="pkg", version="1.0.0", license_name="Apache-2.0")
    installed.provenance["version"] = "Source: pkg.egg-info"
    installed.provenance["license"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.license_name == "MIT"
    # Keyed by "license" (the provenance-key alias), not "license_name" --
    # matches deps_license.py's own declared-vs-concluded conflict field
    # label for the same underlying concept.
    assert "license" in merged.field_conflicts
    assert "license_name" not in merged.field_conflicts


def test_reconcile_requires_python_installed_declared_empty_vs_static_conflict(
    tmp_path: Path,
) -> None:
    """Regression, mirror of the declared-empty-static case above: when
    *installed*'s own declared-but-empty Requires-Python has already been
    collapsed to None by the parser (the fix for the None-vs-empty-string
    convention bug), the comparator call must not crash (SpecifierSet(None)
    raises) and the disagreement must still be recorded, with the
    installed candidate's ``value`` normalized to ``""``, never ``None``."""
    static = _static(requires_python=">=3.9")
    static.provenance["requires_python"] = "Source: pyproject.toml"
    installed = ProjectMetadata(name="pkg", version="1.0.0", requires_python=None)
    installed.provenance["version"] = "Source: pkg.egg-info"
    installed.provenance["requires_python"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.requires_python == ">=3.9"
    assert "requires_python" in merged.field_conflicts
    assert merged.field_conflicts["requires_python"][1]["value"] == ""


def test_reconcile_requires_python_gap_fill_from_installed_declared_empty_is_none(
    tmp_path: Path,
) -> None:
    """Regression: gap-filling requires_python from an installed source
    whose own value was already collapsed to None by the parser (declared
    empty, PEP 621's "no constraint" convention) must leave
    merged.requires_python as None, not the raw empty string, matching
    every static producer's own convention for the same field."""
    static = ProjectMetadata(name="pkg", version="1.0.0")  # requires_python undeclared
    installed = ProjectMetadata(name="pkg", version="1.0.0", requires_python=None)
    installed.provenance["requires_python"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.requires_python is None
    assert merged.provenance["requires_python"] == "Source: pkg.egg-info"
    assert merged.field_conflicts == {}


def test_reconcile_version_gap_fill_from_installed_declared_empty_is_none(
    tmp_path: Path,
) -> None:
    """Regression: gap-filling version from an installed source whose own
    value was already collapsed to None by the parser (declared empty)
    must leave merged.version as None, not the raw empty string, matching
    every static producer's own convention for the same field."""
    static = ProjectMetadata(name="pkg")  # version undeclared
    installed = ProjectMetadata(name="pkg", version=None)
    installed.provenance["version"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.version is None
    assert merged.provenance["version"] == "Source: pkg.egg-info"
    assert merged.field_conflicts == {}


@pytest.mark.parametrize(
    ("static_value", "installed_value", "conflict"),
    [
        ("mit", "MIT", False),
        ("GPL-2.0+", "GPL-2.0-or-later", False),
        ("mit and apache-2.0", "Apache-2.0 AND MIT", False),
        ("MIT", "Apache-2.0", True),
        ("MIT", "NOASSERTION", True),
    ],
)
def test_reconcile_license_comparison_is_by_classified_value(
    tmp_path: Path, static_value: str, installed_value: str, conflict: bool
) -> None:
    static = _static(license_name=static_value)
    static.provenance["license"] = "Source: pyproject.toml"
    installed = ProjectMetadata(
        name="pkg", version="1.0.0", license_name=installed_value
    )
    installed.provenance["version"] = "Source: pkg.egg-info"
    installed.provenance["license"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert ("license" in merged.field_conflicts) is conflict


def test_reconcile_license_comparison_does_not_warn_about_the_value(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A comparison is not a record of the value: no "not an expression"
    ``WARNING:`` for text that only looks like a broken expression."""
    broken = "MIT with reconcile-compare-only"
    static = _static(license_name=broken)
    static.provenance["license"] = "Source: pyproject.toml"
    installed = ProjectMetadata(name="pkg", version="1.0.0", license_name="MIT")
    installed.provenance["version"] = "Source: pkg.egg-info"
    installed.provenance["license"] = "Source: pkg.egg-info"
    with caplog.at_level(logging.WARNING):
        reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)
        assert "not a valid SPDX license expression" not in caplog.text
        # Not vacuous: the value does warn when it is recorded.
        classify_license(broken)
        assert "not a valid SPDX license expression" in caplog.text


def test_reconcile_license_name_declared_empty_vs_installed_conflict(
    tmp_path: Path,
) -> None:
    """Regression: `license = ""` with no LICENSE file found (detection
    finds nothing) collapses to `license_name=None`, but provenance still
    records it as declared. Must not crash
    (a comparator given None raises) and must
    be treated as a real disagreement, static's None still winning."""
    static = _static(license_name=None)
    static.provenance["license"] = "Source: pyproject.toml"
    installed = ProjectMetadata(name="pkg", version="1.0.0", license_name="MIT")
    installed.provenance["version"] = "Source: pkg.egg-info"
    installed.provenance["license"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.license_name is None
    assert "license" in merged.field_conflicts
    assert merged.field_conflicts["license"][0]["value"] == ""


def test_reconcile_quiet_suppresses_warning_but_still_records_conflict(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    static = _static()
    installed = ProjectMetadata(name="pkg", version="1.0.1")
    installed.provenance["version"] = "Source: pkg.egg-info"

    with caplog.at_level(logging.WARNING):
        merged = reconcile_installed_metadata(
            static, installed, "pkg.egg-info", tmp_path, quiet=True
        )

    assert caplog.text == ""
    assert "version" in merged.field_conflicts


def test_reconcile_static_never_transiently_holds_installed_value(
    tmp_path: Path,
) -> None:
    """Regression guard: the merged result's static-wins field must equal
    static's own value throughout -- never briefly set to installed's
    value and "fixed back"."""
    static = _static()
    installed = ProjectMetadata(name="pkg", version="9.9.9")
    installed.provenance["version"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.version == static.version == "1.0.0"


def test_reconcile_gap_fill_field_disagreement_not_a_conflict(tmp_path: Path) -> None:
    """description is gap-fill-only -- both declared and disagreeing is
    not flagged; static's value wins unconditionally, no comparison."""
    static = _static(description="Static summary.")
    static.provenance["description"] = "Source: pyproject.toml"
    installed = ProjectMetadata(
        name="pkg", version="1.0.0", description="Installed summary."
    )
    installed.provenance["version"] = "Source: pkg.egg-info"
    installed.provenance["description"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.description == "Static summary."
    assert merged.field_conflicts == {}


def test_reconcile_gap_fill_field_fills_from_installed(tmp_path: Path) -> None:
    static = _static()
    installed = ProjectMetadata(
        name="pkg", version="1.0.0", description="Installed summary."
    )
    installed.provenance["version"] = "Source: pkg.egg-info"
    installed.provenance["description"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.description == "Installed summary."


def test_reconcile_keywords_declared_empty_both_sides(tmp_path: Path) -> None:
    static = _static(keywords=[])
    static.provenance["keywords"] = "Source: pyproject.toml"
    installed = ProjectMetadata(name="pkg", version="1.0.0", keywords=[])
    installed.provenance["version"] = "Source: pkg.egg-info"
    installed.provenance["keywords"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.keywords == []
    assert merged.provenance["keywords"] == "Source: pyproject.toml"


def test_reconcile_keywords_header_absent_never_overwrites_static(
    tmp_path: Path,
) -> None:
    static = _static(keywords=["static-kw"])
    static.provenance["keywords"] = "Source: pyproject.toml"
    installed = ProjectMetadata(name="pkg", version="1.0.0")  # no Keywords header

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.keywords == ["static-kw"]


def test_reconcile_unrelated_fields_never_touched(tmp_path: Path) -> None:
    """name, provenance keys for untouched fields, files,
    locked_dependencies, authors, dependencies, readme, field_conflicts
    itself: none of these participate."""
    static = _static(
        authors=[{"name": "Static Author"}],
        dependencies=["requests>=2"],
        readme="README.md",
    )
    installed = ProjectMetadata(
        name="different-name",
        version="1.0.0",
        authors=[{"name": "Installed Author"}],
        dependencies=["httpx>=1"],
        readme="OTHER.md",
    )
    installed.provenance["version"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.name == "pkg"
    assert merged.authors == [{"name": "Static Author"}]
    assert merged.dependencies == ["requests>=2"]
    assert merged.readme == "README.md"


def test_reconcile_field_conflicts_order_is_deterministic(tmp_path: Path) -> None:
    """field_conflicts insertion order follows dataclasses.fields()'s
    stable declaration order (version, requires_python, license -- the
    provenance-key alias for license_name), never a set's iteration
    order."""
    static = _static(requires_python=">=3.9", license_name="MIT")
    static.provenance["requires_python"] = "Source: pyproject.toml"
    static.provenance["license"] = "Source: pyproject.toml"
    installed = ProjectMetadata(
        name="pkg",
        version="1.0.1",
        requires_python=">=3.8",
        license_name="Apache-2.0",
    )
    installed.provenance["version"] = "Source: pkg.egg-info"
    installed.provenance["requires_python"] = "Source: pkg.egg-info"
    installed.provenance["license"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert list(merged.field_conflicts) == [
        "version",
        "requires_python",
        "license",
    ]


def test_reconcile_does_not_mutate_static_provenance(tmp_path: Path) -> None:
    """Regression for the dataclasses.replace() aliasing bug: replace()
    shares container-field objects with *static* verbatim unless a field
    is explicitly overridden, so a gap-fill write into merged.provenance
    must not silently leak back into static.provenance (the caller's own
    object) via a shared dict reference."""
    static = ProjectMetadata(name="pkg")  # requires_python left undeclared
    installed = ProjectMetadata(name="pkg", requires_python=">=3.9")
    installed.provenance["requires_python"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.provenance is not static.provenance
    assert merged.requires_python == ">=3.9"
    assert static.requires_python is None
    assert not static.provenance


def test_reconcile_gap_fill_does_not_alias_installed_container(tmp_path: Path) -> None:
    """Regression: gap-filling a container-valued field (keywords/urls)
    must copy installed's dict/list, never alias merged's field to
    installed's own object -- the same dataclasses.replace()-style
    aliasing hazard replace_with_fresh_containers() exists to close
    elsewhere. A later mutation of merged's container must not leak back
    into installed's."""
    static = ProjectMetadata(name="pkg", version="1.0.0")  # keywords undeclared
    installed = ProjectMetadata(
        name="pkg", version="1.0.0", keywords=["from-installed"]
    )
    installed.provenance["keywords"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.keywords == ["from-installed"]
    assert merged.keywords is not installed.keywords
    merged.keywords.append("mutated-after-merge")
    assert installed.keywords == ["from-installed"]


def test_reconcile_gap_fill_urls_does_not_alias_installed_container(
    tmp_path: Path,
) -> None:
    """Same aliasing regression as above, for the urls dict field."""
    static = ProjectMetadata(name="pkg", version="1.0.0")  # urls undeclared
    installed = ProjectMetadata(
        name="pkg", version="1.0.0", urls={"Homepage": "https://example.com"}
    )
    installed.provenance["urls"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.urls == {"Homepage": "https://example.com"}
    assert merged.urls is not installed.urls
    merged.urls["Tracker"] = "https://example.com/issues"
    assert installed.urls == {"Homepage": "https://example.com"}


def test_reconcile_does_not_mutate_static_field_conflicts(tmp_path: Path) -> None:
    """Same aliasing regression as above, for field_conflicts: a recorded
    conflict must land only on the returned merged object, never on the
    caller's own static input."""
    static = _static()
    installed = ProjectMetadata(name="pkg", version="1.0.1")
    installed.provenance["version"] = "Source: pkg.egg-info"

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    assert merged.field_conflicts is not static.field_conflicts
    assert merged.field_conflicts
    assert not static.field_conflicts
