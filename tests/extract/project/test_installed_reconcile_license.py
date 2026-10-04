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

from pitloom.extract._license import classify_license
from pitloom.extract.project._installed_reconcile import reconcile_installed_metadata
from tests.extract.conftest import licence_pair


@pytest.mark.parametrize(
    ("static_value", "installed_value", "conflict", "kept"),
    [
        ("mit", "MIT", False, "mit"),
        ("GPL-2.0+", "GPL-2.0-or-later", False, "GPL-2.0+"),
        ("mit and apache-2.0", "Apache-2.0 AND MIT", False, "mit and apache-2.0"),
        ("MIT", "Apache-2.0", True, "MIT"),
        # `license = ""` with no LICENSE file found collapses to None but is
        # still declared: no crash, a real disagreement, static's None kept
        (None, "MIT", True, None),
        # NOASSERTION/UNKNOWN is weak: no conflict, the real licence wins
        ("MIT", "NOASSERTION", False, "MIT"),
        ("UNKNOWN", "noassertion", False, "UNKNOWN"),
        ("unknown", "MIT", False, "MIT"),
        # weak against declared-but-blank agrees too: static kept
        ("UNKNOWN", None, False, "UNKNOWN"),
        (None, "NOASSERTION", False, None),
        # a licence's SPDX List name and its id are one licence
        ("MIT", "MIT License", False, "MIT"),
        ("MIT License", "MIT", False, "MIT License"),
        ("Apache Software License", "Apache-2.0", True, "Apache Software License"),
    ],
)
def test_reconcile_license_comparison_is_by_classified_value(
    tmp_path: Path,
    static_value: str | None,
    installed_value: str | None,
    conflict: bool,
    kept: str | None,
) -> None:
    static, installed = licence_pair(static_value, installed_value)

    merged = reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)

    # Keyed by "license" (the provenance-key alias), not "license_name",
    # as deps_license.py labels the declared-vs-concluded conflict.
    assert ("license" in merged.field_conflicts) is conflict
    assert "license_name" not in merged.field_conflicts
    if conflict:  # the static candidate, a blank one as ""
        assert merged.field_conflicts["license"][0]["value"] == (static_value or "")
    assert merged.license_name == kept
    source = "pkg.egg-info" if kept != static_value else "pyproject.toml"
    assert merged.provenance["license"] == f"Source: {source}"


def test_reconcile_license_comparison_does_not_warn_about_the_value(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A comparison is not a record of the value: no "not an expression"
    ``WARNING:`` for text that only looks like a broken expression."""
    broken = "MIT with reconcile-compare-only"
    static, installed = licence_pair(broken, "MIT")
    with caplog.at_level(logging.WARNING):
        reconcile_installed_metadata(static, installed, "pkg.egg-info", tmp_path)
        assert "not a valid SPDX license expression" not in caplog.text
        # Not vacuous: the value does warn when it is recorded.
        classify_license(broken)
        assert "not a valid SPDX license expression" in caplog.text
