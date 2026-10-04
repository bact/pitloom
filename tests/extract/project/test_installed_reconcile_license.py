# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Licence reconciliation of installed into static metadata: the same
rule as the declared vs concluded check (classified value, SPDX List name
and id agree, NOASSERTION is weak).

See also: :mod:`tests.extract.project.test_installed_reconcile`.
"""

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


@pytest.mark.parametrize(
    ("static_value", "installed_value", "conflict", "kept"),
    [
        ("mit", "MIT", False, "mit"),
        ("GPL-2.0+", "GPL-2.0-or-later", False, "GPL-2.0+"),
        ("mit and apache-2.0", "Apache-2.0 AND MIT", False, "mit and apache-2.0"),
        ("MIT", "Apache-2.0", True, "MIT"),
        # NOASSERTION/UNKNOWN is weak: no conflict, the real licence wins
        ("MIT", "NOASSERTION", False, "MIT"),
        ("UNKNOWN", "noassertion", False, "UNKNOWN"),
        ("unknown", "MIT", False, "MIT"),
        # a licence's SPDX List name and its id are one licence
        ("MIT", "MIT License", False, "MIT"),
        ("Apache Software License", "Apache-2.0", True, "Apache Software License"),
    ],
)
def test_reconcile_license_comparison_is_by_classified_value(
    tmp_path: Path, static_value: str, installed_value: str, conflict: bool, kept: str
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
    assert merged.license_name == kept
    source = "pkg.egg-info" if kept != static_value else "pyproject.toml"
    assert merged.provenance["license"] == f"Source: {source}"


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
