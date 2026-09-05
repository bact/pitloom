# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``uv.lock``'s root/workspace-member package selection
(:func:`pitloom.extract._uv_lock._find_root_package`) and single-entry
pin resolution (:func:`pitloom.extract._uv_lock._pinned_dep_for_package`).

See also: test_uv_lock.py (extraction correctness this module's tests
were split from -- see that module's own docstring for the split
rationale) and test_uv_lock_integration.py (the workspace-disambiguation
regression exercised through the full ``read_project()`` cascade).
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract._uv_lock import (
    _expected_project_name,
    _find_root_package,
    _pinned_dep_for_package,
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


def test_find_root_package_ignores_malformed_entries() -> None:
    """A malformed top-level `[[package]]` entry (not a table) is
    silently skipped while searching for the root package -- see
    test_lock_common.py for the equivalent `index_packages_by_name()`
    coverage this and `_uv_lock.py`'s own extraction share."""
    packages: list[object] = [
        "not-a-dict",
        {"version": "1.0.0"},  # missing name, still not editable/virtual
        {"name": "requests", "version": "2.31.0"},
    ]

    assert _find_root_package(packages, None) is None


def test_find_root_package_single_candidate_used_even_without_name_match() -> None:
    """With exactly one editable/virtual candidate, it's used even when
    it doesn't match `expected_name` (or `expected_name` is unavailable)
    -- there's no ambiguity about *which* entry, only whether the name
    happens to match, so guessing wrong here isn't the workspace-mixup
    risk multiple candidates pose."""
    packages: list[object] = [
        {"name": "actual-name", "source": {"editable": "."}},
    ]

    assert _find_root_package(packages, "different-name") == packages[0]
    assert _find_root_package(packages, None) == packages[0]


def test_find_root_package_prefers_name_match_among_multiple_candidates() -> None:
    packages: list[object] = [
        {"name": "pkg-a", "source": {"editable": "."}},
        {"name": "pkg-b", "source": {"editable": "."}},
    ]

    assert _find_root_package(packages, "pkg-b") == packages[1]
    assert _find_root_package(packages, "Pkg_B") == packages[1]  # canonicalized


def test_find_root_package_multiple_candidates_no_name_match_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A shared uv workspace lock listing more than one local member,
    where none matches the project actually being scanned, must not
    silently attribute the wrong member's dependencies -- this is the
    regression case: picking `packages[0]` unconditionally here would
    misattribute `pkg-a`'s (or `pkg-b`'s) dependencies to `pkg-c`."""
    packages: list[object] = [
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
