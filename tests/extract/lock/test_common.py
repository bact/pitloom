# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract.lock.common` -- the helpers shared
across every lock/pin extractor (:mod:`pitloom.extract.lock.poetry`,
:mod:`pitloom.extract.lock.pylock`, :mod:`pitloom.extract.lock.uv`,
:mod:`pitloom.extract.lock.pdm`)."""

import logging
from pathlib import Path
from typing import Literal

import pytest
from packaging.specifiers import SpecifierSet

from pitloom.core.quote_source import quote_source
from pitloom.extract.lock.common import (
    canonical_name_and_pinned_version,
    default_group_included,
    find_first_present_key,
    group_by_canonical_name,
    has_required_top_level_table,
    is_format_version_number,
    is_same_version,
    is_usable_name,
    is_usable_version,
    parse_exact_pin_requirement,
    resolve_pinned_dependencies,
    shape_validated_package,
    single_exact_pin,
    version_key,
    warn_malformed_entry_not_table,
    warn_missing_name,
    warn_missing_version,
    warn_non_registry_source,
    warn_top_level_key_wrong_type,
)


def test_parse_exact_pin_requirement() -> None:
    assert parse_exact_pin_requirement("requests==2.31.0") == (
        "requests",
        "==",
        "2.31.0",
    )
    assert parse_exact_pin_requirement("pkg===1.0.0-legacy") == (
        "pkg",
        "===",
        "1.0.0-legacy",
    )
    assert parse_exact_pin_requirement("requests>=2.0") is None
    assert parse_exact_pin_requirement("pkg @ https://example.com/pkg.whl") is None
    assert parse_exact_pin_requirement("not a valid requirement !!!") is None


def test_resolve_pinned_dependencies_pairs_success() -> None:
    pairs = [("Requests", "2.31.0"), ("urllib3", "2.0.0")]
    assert resolve_pinned_dependencies(pairs, "test.lock") == [
        "Requests==2.31.0",
        "urllib3==2.0.0",
    ]


def test_resolve_pinned_dependencies_triples_success() -> None:
    triples = [("pkg1", "==", "1.0"), ("pkg2", "===", "2.0-legacy")]
    assert resolve_pinned_dependencies(triples, "test.lock") == [
        "pkg1==1.0",
        "pkg2===2.0-legacy",
    ]


def test_resolve_pinned_dependencies_pep440_equivalence_collapsed() -> None:
    pairs = [("foo", "1.0"), ("foo", "1.0.0")]
    assert resolve_pinned_dependencies(pairs, "test.lock") == ["foo==1.0"]


def test_resolve_pinned_dependencies_arbitrary_equality_compares_strings() -> None:
    """Two ``===`` pins agree only on the exact string (``===1.0`` is not
    ``===1.0.0``); an ``==`` pin is still compared as PEP 440."""
    arbitrary = [("foo", "===", "1.0"), ("foo", "===", "1.0.0"), ("bar", "==", "1.0")]
    assert resolve_pinned_dependencies(arbitrary, "test.lock") == ["bar==1.0"]
    same = [("foo", "===", "1.0"), ("foo", "===", "1.0")]
    assert resolve_pinned_dependencies(same, "test.lock") == ["foo===1.0"]
    # ``===`` on either side compares strings, whatever the order.
    mixed = [("foo", "===", "1.0"), ("foo", "==", "1.0.0")]
    assert resolve_pinned_dependencies(mixed, "test.lock") == []
    assert resolve_pinned_dependencies(mixed[::-1], "test.lock") == []
    assert resolve_pinned_dependencies(
        [("foo", "===", "1.0"), ("foo", "==", "1.0")], "test.lock"
    ) == ["foo===1.0"]


@pytest.mark.parametrize("on_conflict", ["skip", "abort"])
def test_resolve_pinned_dependencies_conflict_shows_versions_escaped(
    caplog: pytest.LogCaptureFixture, on_conflict: Literal["skip", "abort"]
) -> None:
    pins = [("a", "===", "x\x1b[31m"), ("A", "===", "y\nWARNING: forged")]
    with caplog.at_level(logging.WARNING):
        resolve_pinned_dependencies(pins, "test.lock", on_conflict=on_conflict)
    (message,) = caplog.messages
    assert "WARNING: forged" in message
    assert message.isprintable()


def test_resolve_pinned_dependencies_skip_policy(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pairs = [("foo", "1.0"), ("foo", "2.0"), ("bar", "3.0")]
    with caplog.at_level(logging.WARNING):
        deps = resolve_pinned_dependencies(pairs, "test.lock", on_conflict="skip")
    assert deps == ["bar==3.0"]
    assert (
        "Skipping test.lock entry 'foo': pinned to conflicting versions" in caplog.text
    )


def test_resolve_pinned_dependencies_abort_policy(
    caplog: pytest.LogCaptureFixture,
) -> None:
    triples = [("foo", "==", "1.0"), ("foo", "==", "2.0"), ("bar", "==", "3.0")]
    lock_file = Path("/path/to/requirements.txt")
    with caplog.at_level(logging.WARNING):
        deps = resolve_pinned_dependencies(triples, lock_file, on_conflict="abort")
    assert deps is None
    # str(lock_file), not a hardcoded POSIX literal: the warning logs the
    # Path object's native str() form, which renders with "\" on Windows.
    assert (
        f"{quote_source(lock_file)}: 'foo' pinned to conflicting versions (1.0, 2.0)"
        " -- ignoring requirements.txt" in caplog.text
    )


def test_version_key_parses_pep440_versions_as_equal() -> None:
    assert version_key("1.0") == version_key("1.0.0")
    assert version_key("1.0") != version_key("1.1")


def test_version_key_falls_back_to_raw_string_for_non_pep440() -> None:
    """A ``===``-pinned arbitrary-equality version (legal PEP 440, but not
    itself parseable as a `Version`) must still produce a usable, stable
    key -- the raw string itself -- rather than raising."""
    assert version_key("2021.01.01-legacy") == "2021.01.01-legacy"
    assert version_key("2021.01.01-legacy") != version_key("2021.01.02-legacy")


def test_group_by_canonical_name_folds_case_and_separator_runs() -> None:
    """PEP 503 canonicalization folds case AND ``-``/``_``/``.`` runs --
    both must land in the same group, preserving each tuple through grouping."""
    triples = [
        ("Flask", "==", "2.0"),
        ("flask", "===", "2.0-legacy"),
        ("python_dateutil", "==", "2.9.0"),
        ("python-dateutil", "==", "2.9.0"),
    ]

    result = group_by_canonical_name(triples)

    assert list(result) == ["flask", "python-dateutil"]
    assert result["flask"] == triples[:2]
    assert result["python-dateutil"] == triples[2:]
    assert not group_by_canonical_name([])


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
    [None, 1, 2.0, [], {}, "", "*", "not a version", "  ", "2.31.*", "latest"]
    + [" 1.0\n", "1.0 ", "\t2.0"],
)
def test_is_usable_version_rejects_non_pep440_values(version: object) -> None:
    """A value that's the wrong type, empty, or a syntactically-string
    but not-a-version value (a wildcard, whitespace, arbitrary text) must
    all be rejected -- otherwise a malformed lock entry would silently
    produce an invalid ``name==<garbage>`` dependency/PURL instead of
    being warned and skipped."""
    assert not is_usable_version(version)


@pytest.mark.parametrize(
    ("name", "usable"),
    [
        ("requests", True),
        ("a", True),
        ("Foo_bar.baz-1", True),
        ("bar baz\x1b[31m", False),
        ("a; python_version<'3'", False),
        ("b\nWARNING: x", False),
        ("foo\n", False),
        ("a @ http://evil/x", False),
        (" foo", False),
        ("-foo", False),
        ("foo-", False),
        ("foo[extra]", False),
        ("", False),
        (None, False),
        (5, False),
    ],
)
def test_is_usable_name_is_a_pep_508_name(name: object, usable: bool) -> None:
    assert is_usable_name(name) is usable


def test_is_format_version_number_excludes_booleans() -> None:
    assert [is_format_version_number(v) for v in (1, True, "1", None)] == [
        True,
        False,
        False,
        False,
    ]


def test_has_required_top_level_table_rejects_a_boolean_for_an_int() -> None:
    """``True`` is an ``int`` to ``isinstance``, never a format version."""
    assert not has_required_top_level_table(
        {"_meta": {"pipfile-spec": True}}, "_meta", "pipfile-spec", int
    )
    assert has_required_top_level_table(
        {"_meta": {"pipfile-spec": 6}}, "_meta", "pipfile-spec", int
    )


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
    """A present key with a wrong-shaped value (e.g. an int where the format's
    identifying field is a string) is rejected like an absent key."""
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


@pytest.mark.parametrize(
    "name", ["bar baz\x1b[31m", "a; python_version<'3'", "b\nWARNING: x"]
)
def test_shape_validated_package_invalid_name_is_one_escaped_warning(
    caplog: pytest.LogCaptureFixture, name: str
) -> None:
    """A name that is no PEP 508 name is skipped, shown escaped on one line."""
    with caplog.at_level(logging.WARNING):
        result = shape_validated_package({"name": name, "version": "1.0"}, "x.lock")

    assert result is None
    (message,) = caplog.messages
    assert "invalid 'name'" in message
    assert message.isprintable()  # no raw ESC or newline


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
    assert single_exact_pin(SpecifierSet(f"{operator}2.31.0")) == (operator, "2.31.0")


def test_single_exact_pin_accepts_arbitrary_equality_non_pep440_version() -> None:
    """The === operator explicitly supports non-PEP 440 version strings."""
    assert single_exact_pin(SpecifierSet("===2021.01.01-legacy")) == (
        "===",
        "2021.01.01-legacy",
    )


def test_is_same_version_pep440_equivalences() -> None:
    assert is_same_version("1.0", "1.0.0")
    assert is_same_version("1.0.0", "1.0")
    assert is_same_version("2.31.0", "2.31.0")
    assert not is_same_version("1.0", "1.1")


def test_is_same_version_non_pep440_fallback() -> None:
    assert is_same_version("2021.01.01-legacy", "2021.01.01-legacy")
    assert not is_same_version("2021.01.01-legacy", "2021.01.02-legacy")


def test_single_exact_pin_rejects_wildcard() -> None:
    assert single_exact_pin(SpecifierSet("==2.31.*")) is None


def test_single_exact_pin_rejects_range() -> None:
    assert single_exact_pin(SpecifierSet(">=2.31.0")) is None


def test_single_exact_pin_rejects_multiple_specifiers() -> None:
    assert single_exact_pin(SpecifierSet(">=2.31.0,<3.0.0")) is None


def test_canonical_name_and_pinned_version_exact_pin() -> None:
    assert canonical_name_and_pinned_version("Requests==2.31.0") == (
        "requests",
        "2.31.0",
    )


def test_canonical_name_and_pinned_version_canonicalizes_name() -> None:
    assert canonical_name_and_pinned_version("some_Package.Name==1.0") == (
        "some-package-name",
        "1.0",
    )


def test_canonical_name_and_pinned_version_unparseable_requirement() -> None:
    """A string ``Requirement()`` itself can't parse (not merely a loose
    specifier) returns ``None`` rather than raising."""
    assert canonical_name_and_pinned_version("not a valid == requirement !!!") is None


def test_canonical_name_and_pinned_version_not_single_exact_pin() -> None:
    """Parses fine as a ``Requirement`` but isn't a single exact pin
    (a range) -- also ``None``."""
    assert canonical_name_and_pinned_version("requests>=2.0") is None


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
