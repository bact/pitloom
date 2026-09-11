# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for
:func:`pitloom.assemble.spdx3.deps_installed.build_dependency_version_conflict`
and :func:`pitloom.assemble.spdx3.deps_installed.merge_conflict_candidates`
(G2 multi-source conflict, dependency-version field).

See also: test_deps_resolution_pins.py and test_deps_enrichment_names_versions.py
for the sibling ``_resolve_version`` warning-path tests this mirrors, and
test_generator_project_enrichment.py for the end-to-end SBOM assertion.
"""

from __future__ import annotations

from pitloom.assemble.spdx3.deps_installed import (
    build_dependency_version_conflict,
    merge_conflict_candidates,
)


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


def test_merge_conflict_candidates_none_when_nothing_conflicts() -> None:
    assert merge_conflict_candidates([None, None]) is None


def test_merge_conflict_candidates_dedupes_shared_locked_side() -> None:
    # Two extras of the same package, each independently conflicting with
    # the same locked version -- e.g. requests[a]>=2.0 and requests[b]>=3.0
    # both losing to a locked 1.5.0.
    first = build_dependency_version_conflict(
        "requests>=2.0",
        "1.5.0",
        dep_source="Source: pyproject.toml | Field: dependencies (extra: a)",
        locked_source="Source: requirements.txt | Method: resolved_lockfile",
    )
    second = build_dependency_version_conflict(
        "requests>=3.0",
        "1.5.0",
        dep_source="Source: pyproject.toml | Field: dependencies (extra: b)",
        locked_source="Source: requirements.txt | Method: resolved_lockfile",
    )
    merged = merge_conflict_candidates([first, second])

    assert merged is not None
    # Both distinct declared values kept, but the identical locked-side
    # candidate (same value/role/source in both inputs) collapses to one.
    assert len(merged) == 3
    values = [c["value"] for c in merged]
    assert values.count(">=2.0") == 1
    assert values.count(">=3.0") == 1
    assert values.count("1.5.0") == 1


def test_merge_conflict_candidates_skips_none_entries() -> None:
    conflicting = build_dependency_version_conflict(
        "requests>=3.0",
        "1.5.0",
        dep_source="Source: pyproject.toml | Field: dependencies",
        locked_source="Source: requirements.txt | Method: resolved_lockfile",
    )
    merged = merge_conflict_candidates([None, conflicting, None])

    assert merged == conflicting
