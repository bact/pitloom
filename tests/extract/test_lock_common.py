# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract._lock_common` -- the helpers shared
across every lock/pin extractor (:mod:`pitloom.extract._poetry_lock`,
:mod:`pitloom.extract._pylock`, :mod:`pitloom.extract._uv_lock`,
:mod:`pitloom.extract._pdm_lock`)."""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract._lock_common import (
    find_first_present_key,
    group_versions_by_canonical_name,
    index_packages_by_name,
    load_lock_toml,
)


def test_load_lock_toml_missing_file_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert load_lock_toml(Path(tmp) / "does-not-exist.lock") is None


def test_load_lock_toml_malformed_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "some.lock"
        lock_path.write_text("this is not [ valid toml", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = load_lock_toml(lock_path)

        assert result is None
        assert "Failed to parse" in caplog.text


def test_load_lock_toml_valid_file_returns_data() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "some.lock"
        lock_path.write_text('key = "value"\n', encoding="utf-8")

        assert load_lock_toml(lock_path) == {"key": "value"}


def test_index_packages_by_name_groups_by_name_preserving_order() -> None:
    packages = [
        {"name": "a", "version": "1.0.0"},
        {"name": "b", "version": "2.0.0"},
        {"name": "a", "version": "1.0.1", "extras": ["x"]},
    ]

    result = index_packages_by_name(packages)

    assert list(result.keys()) == ["a", "b"]
    assert result["a"] == [
        {"name": "a", "version": "1.0.0"},
        {"name": "a", "version": "1.0.1", "extras": ["x"]},
    ]
    assert result["b"] == [{"name": "b", "version": "2.0.0"}]


def test_index_packages_by_name_ignores_non_dict_entries() -> None:
    packages: list[object] = ["not-a-dict", ["still", "not", "a", "dict"]]

    assert not index_packages_by_name(packages)


def test_index_packages_by_name_ignores_entries_with_missing_or_bad_name() -> None:
    packages: list[object] = [
        {"version": "1.0.0"},  # missing name
        {"name": None, "version": "1.0.0"},  # non-string name
        {"name": "", "version": "1.0.0"},  # empty name
    ]

    assert not index_packages_by_name(packages)


def test_index_packages_by_name_empty_list_returns_empty_dict() -> None:
    assert not index_packages_by_name([])


def test_group_versions_by_canonical_name_groups_case_and_separator_variants() -> None:
    """PEP 503 canonicalization folds case AND ``-``/``_``/``.`` runs --
    both must land in the same group, not just a case-insensitive match."""
    pairs = [
        ("Flask", "2.0"),
        ("flask", "2.0"),
        ("python_dateutil", "2.9.0"),
        ("python-dateutil", "2.9.0"),
        ("idna", "3.7"),
    ]

    result = group_versions_by_canonical_name(pairs)

    assert list(result.keys()) == ["flask", "python-dateutil", "idna"]
    assert result["flask"] == [("Flask", "2.0"), ("flask", "2.0")]
    assert result["python-dateutil"] == [
        ("python_dateutil", "2.9.0"),
        ("python-dateutil", "2.9.0"),
    ]
    assert result["idna"] == [("idna", "3.7")]


def test_group_versions_by_canonical_name_empty_input_returns_empty_dict() -> None:
    assert not group_versions_by_canonical_name([])


def test_find_first_present_key_returns_first_match_in_key_order() -> None:
    """Order is determined by *keys*, not by the mapping's own key
    order -- callers rely on this to report a stable, predictable
    non-registry-source name even when the mapping has multiple such
    keys (shouldn't normally happen, but the tie-break must be
    deterministic)."""
    mapping = {"path": "x", "git": "y"}

    assert find_first_present_key(mapping, ("git", "path")) == "git"
    assert find_first_present_key(mapping, ("path", "git")) == "path"


def test_find_first_present_key_returns_none_when_no_key_present() -> None:
    assert find_first_present_key({"registry": "x"}, ("git", "path")) is None


def test_find_first_present_key_empty_mapping_returns_none() -> None:
    assert find_first_present_key({}, ("git", "path")) is None
