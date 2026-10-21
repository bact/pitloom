# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``uv.lock``'s root/workspace-member package selection
(:func:`pitloom.extract.lock.uv._scan_packages`'s root-candidate
collection and :func:`pitloom.extract.lock.uv._find_root_package`'s
selection among them) and single-entry pin resolution
(:func:`pitloom.extract.lock.uv._pinned_dep_for_package`).

See also: test_uv.py (extraction correctness) and test_uv_integration.py
(the workspace-disambiguation case exercised through the full
``read_project()`` cascade).
"""

import logging
import tempfile
from pathlib import Path
from typing import Any

import pytest

from pitloom.extract.lock.uv import (
    _expected_project_name,
    _find_root_package,
    _pinned_dep_for_package,
    _scan_packages,
)


def test_find_root_package_returns_none_for_empty_list() -> None:
    assert _find_root_package([], None) is None


def test_expected_project_name_returns_none_when_project_table_not_a_dict() -> None:
    """A malformed `[project]` value (e.g. a bare string instead of a
    table) can't carry a `name` -- treated as "can't determine", not a
    parse error."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            'project = "not-a-table"\n', encoding="utf-8"
        )

        assert _expected_project_name(tmp_path) is None


def test_scan_packages_ignores_malformed_entries_when_collecting_root_candidates() -> (
    None
):
    """A malformed top-level `[[package]]` entry (not a table, or
    missing/non-string `name`) is silently excluded from
    `_scan_packages()`'s root-candidate list (the same list
    `_find_root_package()` then searches)."""
    packages: list[object] = [
        "not-a-dict",
        {"version": "1.0.0"},  # missing name, still not editable/virtual
        {"name": "requests", "version": "2.31.0"},
    ]

    _by_name, root_candidates = _scan_packages(packages)

    assert _find_root_package(root_candidates, None) is None


def test_find_root_package_sole_candidate_needs_its_name_unless_unknown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The sole candidate is the project's own when the expected name is
    unknown or equal (PEP 503); another name is a different workspace
    member, whose dependencies are not this project's."""
    packages: list[dict[str, Any]] = [
        {"name": "actual-name", "source": {"editable": "."}},
    ]

    assert _find_root_package(packages, None) == packages[0]
    assert _find_root_package(packages, "Actual_Name") == packages[0]
    assert not caplog.messages
    with caplog.at_level(logging.WARNING):
        assert _find_root_package(packages, "different-name") is None
    assert "1 candidate" in caplog.text
    assert "different-name" in caplog.text


def test_find_root_package_prefers_name_match_among_multiple_candidates() -> None:
    packages: list[dict[str, Any]] = [
        {"name": "pkg-a", "source": {"editable": "."}},
        {"name": "pkg-b", "source": {"editable": "."}},
    ]

    assert _find_root_package(packages, "pkg-b") == packages[1]
    assert _find_root_package(packages, "Pkg_B") == packages[1]  # canonicalized


def test_find_root_package_multiple_candidates_no_name_match_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A shared uv workspace lock listing several local members, none matching
    the scanned project, does not attribute a member's dependencies to it
    (``packages[0]`` is not picked unconditionally)."""
    packages: list[dict[str, Any]] = [
        {"name": "pkg-a", "source": {"editable": "."}},
        {"name": "pkg-b", "source": {"editable": "."}},
    ]

    with caplog.at_level(logging.WARNING):
        result = _find_root_package(packages, "pkg-c")

    assert result is None
    assert "2 candidate" in caplog.text
    assert "pkg-c" in caplog.text


def test_pinned_dep_for_package_returns_none_when_source_not_a_dict() -> None:
    """Defensive: a `source` value that isn't a table (malformed) is
    skipped by the source-key check, not a crash -- version resolution
    still proceeds normally."""
    assert (
        _pinned_dep_for_package(
            {"name": "odd-pkg", "version": "1.0.0", "source": "not-a-table"}
        )
        == "odd-pkg==1.0.0"
    )
