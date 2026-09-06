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
from packaging.specifiers import SpecifierSet

from pitloom.extract._lock_common import (
    default_group_included,
    find_first_present_key,
    group_versions_by_canonical_name,
    has_required_top_level_table,
    index_packages_by_name,
    is_usable_version,
    load_lock_json,
    load_lock_toml,
    shape_validated_package,
    single_exact_pin,
    warn_malformed_entry_not_table,
    warn_missing_name,
    warn_missing_version,
    warn_non_registry_source,
    warn_top_level_key_wrong_type,
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


def test_load_lock_toml_invalid_utf8_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: tomllib/tomli's decode step raises a bare
    ``UnicodeDecodeError`` (not its own ``TOMLDecodeError``) for invalid
    UTF-8 bytes -- must still degrade to ``None`` with a ``WARNING:``,
    not propagate out and abort the whole cascade."""
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "some.lock"
        lock_path.write_bytes(b'name = "\xff\xfebad"\n')

        with caplog.at_level(logging.WARNING):
            result = load_lock_toml(lock_path)

        assert result is None
        assert "Failed to parse" in caplog.text


def test_load_lock_json_invalid_utf8_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: reading invalid UTF-8 bytes in text mode raises a
    bare ``UnicodeDecodeError`` (not ``json.JSONDecodeError``) -- must
    still degrade to ``None`` with a ``WARNING:``, not propagate out and
    abort the whole cascade."""
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "some.json"
        lock_path.write_bytes(b'{"name": "\xff\xfebad"}')

        with caplog.at_level(logging.WARNING):
            result = load_lock_json(lock_path)

        assert result is None
        assert "Failed to parse" in caplog.text


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


@pytest.mark.parametrize("version", ["2.31.0", "1.0", "0.1.0a1", "2024.1.1", "1!2.0"])
def test_is_usable_version_accepts_valid_pep440_versions(version: str) -> None:
    assert is_usable_version(version)


@pytest.mark.parametrize(
    "version",
    [None, 1, 2.0, [], {}, "", "*", "not a version", "  ", "2.31.*", "latest"],
)
def test_is_usable_version_rejects_non_pep440_values(version: object) -> None:
    """A value that's the wrong type, empty, or a syntactically-string
    but not-a-version value (a wildcard, whitespace, arbitrary text) must
    all be rejected -- otherwise a malformed lock entry would silently
    produce an invalid ``name==<garbage>`` dependency/PURL instead of
    being warned and skipped."""
    assert not is_usable_version(version)


def test_has_required_top_level_table_valid_type_returns_true() -> None:
    assert has_required_top_level_table(
        {"metadata": {"lock-version": "2.0"}}, "metadata", "lock-version", str
    )


def test_has_required_top_level_table_missing_table_returns_false() -> None:
    assert not has_required_top_level_table({}, "metadata", "lock-version", str)


def test_has_required_top_level_table_table_not_a_dict_returns_false() -> None:
    assert not has_required_top_level_table(
        {"metadata": "not-a-table"}, "metadata", "lock-version", str
    )


def test_has_required_top_level_table_missing_key_returns_false() -> None:
    assert not has_required_top_level_table(
        {"metadata": {}}, "metadata", "lock-version", str
    )


def test_has_required_top_level_table_wrong_value_type_returns_false() -> None:
    """Regression: a present key with the wrong-shaped value (e.g. an
    int where the format's own identifying field is always a string)
    must be rejected exactly like the key being absent -- not treated
    as a looser pass than outright absence."""
    assert not has_required_top_level_table(
        {"metadata": {"lock-version": 2}}, "metadata", "lock-version", str
    )


def test_shape_validated_package_valid_entry_returned_unchanged() -> None:
    pkg = {"name": "requests", "version": "2.31.0"}
    assert shape_validated_package(pkg, "poetry.lock") is pkg


def test_shape_validated_package_not_a_dict_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        result = shape_validated_package("not-a-dict", "poetry.lock")

    assert result is None
    assert "expected a table" in caplog.text


def test_shape_validated_package_missing_name_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        result = shape_validated_package({"version": "1.0.0"}, "poetry.lock")

    assert result is None
    assert "missing or non-string 'name'" in caplog.text


def test_shape_validated_package_missing_version_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        result = shape_validated_package({"name": "requests"}, "poetry.lock")

    assert result is None
    assert "missing or non-string 'version'" in caplog.text


def test_default_group_included_defaults_when_groups_absent() -> None:
    assert default_group_included(
        {"name": "requests"}, "poetry.lock", "main", "requests"
    )


def test_default_group_included_true_when_present_in_list() -> None:
    assert default_group_included(
        {"groups": ["main", "dev"]}, "poetry.lock", "main", "requests"
    )


def test_default_group_included_false_when_absent_from_list() -> None:
    assert not default_group_included(
        {"groups": ["dev"]}, "poetry.lock", "main", "requests"
    )


def test_default_group_included_not_a_list_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        result = default_group_included(
            {"groups": "main"}, "poetry.lock", "main", "requests"
        )

    assert result is None
    assert "'groups' is str, expected a list" in caplog.text


@pytest.mark.parametrize("operator", ["==", "==="])
def test_single_exact_pin_accepts_exact_operators(operator: str) -> None:
    assert single_exact_pin(SpecifierSet(f"{operator}2.31.0")) == "2.31.0"


def test_single_exact_pin_accepts_arbitrary_equality_non_pep440_version() -> None:
    """The === operator explicitly supports non-PEP 440 version strings."""
    assert single_exact_pin(SpecifierSet("===2021.01.01-legacy")) == "2021.01.01-legacy"


def test_single_exact_pin_rejects_wildcard() -> None:
    assert single_exact_pin(SpecifierSet("==2.31.*")) is None


def test_single_exact_pin_rejects_range() -> None:
    assert single_exact_pin(SpecifierSet(">=2.31.0")) is None


def test_single_exact_pin_rejects_multiple_specifiers() -> None:
    assert single_exact_pin(SpecifierSet(">=2.31.0,<3.0.0")) is None


def test_warn_non_registry_source_logs_expected_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        warn_non_registry_source("uv.lock", "requests", "git")

    assert "uv.lock" in caplog.text
    assert "'requests'" in caplog.text
    assert "git-sourced" in caplog.text


def test_warn_top_level_key_wrong_type_logs_expected_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        warn_top_level_key_wrong_type(
            Path("Pipfile.lock"), "default", "not-a-table", "a table", "Pipfile.lock"
        )

    assert "top-level 'default' key is str, expected a table" in caplog.text


def test_warn_missing_version_logs_expected_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        warn_missing_version("poetry.lock", "requests")

    assert "missing or non-string 'version'" in caplog.text
    assert "'requests'" in caplog.text


def test_warn_malformed_entry_not_table_logs_expected_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        warn_malformed_entry_not_table("uv.lock", "[[package]]", "not-a-table")

    assert "expected a table, got str" in caplog.text


def test_warn_missing_name_logs_expected_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        warn_missing_name("Skipping malformed poetry.lock entry", None)

    assert "missing or non-string 'name'" in caplog.text
