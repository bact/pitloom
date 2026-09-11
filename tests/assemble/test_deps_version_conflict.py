# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for
:func:`pitloom.assemble.spdx3.deps_installed.build_dependency_version_conflict`
(G2 multi-source conflict, dependency-version field).

See also: test_deps_resolution_pins.py and test_deps_enrichment_names_versions.py
for the sibling ``_resolve_version`` warning-path tests this mirrors, and
test_generator_project_enrichment.py for the end-to-end SBOM assertion.
"""

from __future__ import annotations

from pitloom.assemble.spdx3.deps_installed import build_dependency_version_conflict


def test_exact_pin_conflict_returns_declared_candidates() -> None:
    candidates = build_dependency_version_conflict(
        "requests==1.2.3",
        "1.2.4",
        dep_source="Source: pyproject.toml | Field: dependencies",
        locked_source="Source: requirements.txt | Method: resolved_lockfile",
    )
    assert candidates is not None
    assert len(candidates) == 2
    assert {c["role"] for c in candidates} == {"declared"}
    assert {c["value"] for c in candidates} == {"1.2.3", "1.2.4"}
    assert all("ref" not in c for c in candidates)


def test_exact_pin_pep440_equivalent_to_locked_is_not_a_conflict() -> None:
    assert (
        build_dependency_version_conflict(
            "requests==1.0",
            "1.0.0",
            dep_source="Source: pyproject.toml | Field: dependencies",
            locked_source="Source: requirements.txt | Method: resolved_lockfile",
        )
        is None
    )


def test_range_unsatisfied_by_locked_returns_specifier_and_locked_version() -> None:
    candidates = build_dependency_version_conflict(
        "requests>=2.0",
        "1.5.0",
        dep_source="Source: pyproject.toml | Field: dependencies",
        locked_source="Source: requirements.txt | Method: resolved_lockfile",
    )
    assert candidates is not None
    assert len(candidates) == 2
    assert {c["role"] for c in candidates} == {"declared"}
    values = {c["value"] for c in candidates}
    assert values == {">=2.0", "1.5.0"}


def test_range_satisfied_by_locked_is_not_a_conflict() -> None:
    assert (
        build_dependency_version_conflict(
            "requests>=2.0",
            "2.31.0",
            dep_source="Source: pyproject.toml | Field: dependencies",
            locked_source="Source: requirements.txt | Method: resolved_lockfile",
        )
        is None
    )


def test_unpinned_dependency_is_not_a_conflict() -> None:
    assert (
        build_dependency_version_conflict(
            "requests",
            "2.31.0",
            dep_source="Source: pyproject.toml | Field: dependencies",
            locked_source="Source: requirements.txt | Method: resolved_lockfile",
        )
        is None
    )


def test_unparseable_dependency_string_is_not_reported_as_conflict() -> None:
    # An unparseable, unpinned constraint can't be verified against the
    # locked version at all -- "can't confirm" must stay distinct from a
    # confirmed conflict, never collapsed into one.
    assert (
        build_dependency_version_conflict(
            "not a valid == requirement >= string",
            "2.31.0",
            dep_source="Source: pyproject.toml | Field: dependencies",
            locked_source="Source: requirements.txt | Method: resolved_lockfile",
        )
        is None
    )


def test_return_is_none_never_empty_list_on_agreement() -> None:
    result = build_dependency_version_conflict(
        "requests>=2.0",
        "2.31.0",
        dep_source="Source: pyproject.toml | Field: dependencies",
        locked_source="Source: requirements.txt | Method: resolved_lockfile",
    )
    assert result is None
