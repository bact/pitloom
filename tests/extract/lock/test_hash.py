# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract.lock._hash`."""

# Explicit `== []`/`== {}` keeps the None-vs-empty distinction.
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

from pitloom.extract.lock._common import version_key
from pitloom.extract.lock._hash import (
    index_packages_by_name_and_version,
    package_artifacts,
    resolve_locked_hashes,
    sha256_file_entry_candidates,
)


def test_index_packages_by_name_and_version_skips_malformed_entries() -> None:
    index = index_packages_by_name_and_version(
        [
            "not-a-dict",
            {"name": "onlyname"},
            {"version": "1.0"},
            {"name": "good", "version": "1.0"},
        ]
    )
    assert list(index.keys()) == [("good", version_key("1.0"))]


def test_index_packages_by_name_and_version_groups_by_name_and_version() -> None:
    packages = [
        {"name": "Requests", "version": "2.31.0", "marker": "a"},
        {"name": "requests", "version": "2.31.0", "marker": "b"},
        {"name": "requests", "version": "2.32.0"},
    ]

    index = index_packages_by_name_and_version(packages)

    assert index[("requests", version_key("2.31.0"))] == [packages[0], packages[1]]
    assert index[("requests", version_key("2.32.0"))] == [packages[2]]


def test_index_packages_by_name_and_version_pep440_equivalence() -> None:
    packages = [
        {"name": "foo", "version": "1.0"},
        {"name": "foo", "version": "1.0.0"},
    ]
    index = index_packages_by_name_and_version(packages)
    assert len(index) == 1
    assert index[("foo", version_key("1.0"))] == packages
    assert index[("foo", version_key("1.0.0"))] == packages


def test_sha256_file_entry_candidates_skips_non_dict_and_non_sha256() -> None:
    assert not sha256_file_entry_candidates("not-a-list")
    assert sha256_file_entry_candidates(
        [
            "not-a-dict",
            {"file": "pkg.whl", "hash": "md5:deadbeef"},
            {"file": "pkg.tar.gz", "hash": "sha256:" + "b" * 64},
        ]
    ) == [("pkg.tar.gz", "b" * 64)]


def test_sha256_file_entry_candidates_missing_filename_is_none() -> None:
    assert sha256_file_entry_candidates([{"hash": "sha256:" + "c" * 64}]) == [
        (None, "c" * 64)
    ]


def test_package_artifacts_collects_sdist_and_wheels() -> None:
    pkg = {
        "sdist": {"url": "https://example.com/foo-1.0.tar.gz"},
        "wheels": [
            {"url": "https://example.com/foo-1.0-py3-none-any.whl"},
            "not-a-dict",
            {"url": "https://example.com/foo-1.0-cp310-none-any.whl"},
        ],
    }
    artifacts = package_artifacts(pkg)
    assert len(artifacts) == 3
    assert artifacts[0]["url"] == "https://example.com/foo-1.0.tar.gz"
    assert artifacts[1]["url"] == "https://example.com/foo-1.0-py3-none-any.whl"
    assert artifacts[2]["url"] == "https://example.com/foo-1.0-cp310-none-any.whl"


def test_package_artifacts_handles_missing_or_malformed() -> None:
    assert package_artifacts({}) == []
    assert package_artifacts({"sdist": "not-a-dict", "wheels": "not-a-list"}) == []


def test_resolve_locked_hashes_basic() -> None:
    deps = ["foo==1.0", "bar==2.0", "baz==3.0"]
    hash_a = "a" * 64
    hash_b = "b" * 64

    def candidate_lookup(name: str, ver: str) -> list[tuple[str | None, str]]:
        if name == "foo" and ver == "1.0":
            return [("foo-1.0.whl", hash_a)]
        if name == "bar" and ver == "2.0":
            return [(None, hash_b)]
        return []

    hashes = resolve_locked_hashes(deps, candidate_lookup)
    assert hashes == {"foo": hash_a, "bar": hash_b}


def test_resolve_locked_hashes_skips_unparseable_or_no_candidates() -> None:
    deps = ["invalid requirement !!!", "foo>=1.0", "bar==2.0"]
    hashes = resolve_locked_hashes(deps, lambda name, ver: [])
    assert hashes == {}
