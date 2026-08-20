# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Direct unit tests for the low-level merge helpers in
:mod:`pitloom.assemble.spdx3._fragments_unify`, covering branches not
reached by the higher-level `merge_fragments()` integration tests in
:mod:`tests.core.test_fragments_misc`.
"""

from __future__ import annotations

import logging

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import _fragments_unify as unify


def test_sha256_hash_skips_non_sha256_algorithm() -> None:
    element = spdx3.software_File(name="a.py")
    element.verifiedUsing = [
        spdx3.Hash(algorithm=spdx3.HashAlgorithm.md5, hashValue="deadbeef")
    ]
    assert unify._sha256_hash(element) is None


def test_sha256_hash_skips_empty_hash_value() -> None:
    element = spdx3.software_File(name="a.py")
    element.verifiedUsing = [
        spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue="")
    ]
    assert unify._sha256_hash(element) is None


def test_normalize_value_plain_list() -> None:
    assert unify._normalize_value([1, 2]) == (2, ((3, "int", 1), (3, "int", 2)))


def test_is_empty_false_for_non_empty_scalar() -> None:
    assert unify._is_empty(5) is False


def test_paths_suffix_match_rejects_non_string_inputs() -> None:
    assert unify._paths_suffix_match(1, "a/b.py") is False
    assert unify._paths_suffix_match("a/b.py", 1) is False


def test_merge_scalar_sets_when_canonical_empty() -> None:
    canonical = spdx3.Agent(name="Pitloom")
    unify._merge_scalar(canonical, "comment", None, "from duplicate")
    assert canonical.comment == "from duplicate"


def test_merge_scalar_warns_on_real_conflict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    canonical = spdx3.software_File(name="a.py")
    with caplog.at_level(logging.WARNING, logger="pitloom.assemble.spdx3.fragments"):
        unify._merge_scalar(canonical, "name", "a.py", "b.py")
    assert any("conflicting" in r.message for r in caplog.records)


def test_merge_comment_sets_when_canonical_empty() -> None:
    canonical = spdx3.Agent(name="Pitloom")
    unify._merge_comment(canonical, None, "hello")
    assert canonical.comment == "hello"


def test_merge_comment_concatenates_when_both_present_and_differ() -> None:
    canonical = spdx3.Agent(name="Pitloom")
    unify._merge_comment(canonical, "first", "second")
    assert canonical.comment == "first; second"


def test_merge_list_skips_duplicate_shaclobject_by_spdx_id() -> None:
    canonical = spdx3.software_Package(name="pkg")
    existing_agent = spdx3.Agent(name="A1")
    existing_agent.spdxId = "urn:agent-1"
    canonical.originatedBy = [existing_agent]

    dup_agent = spdx3.Agent(name="A1")
    dup_agent.spdxId = "urn:agent-1"

    unify._merge_list(canonical, "originatedBy", canonical.originatedBy, [dup_agent])
    assert list(canonical.originatedBy) == [existing_agent]


def test_merge_list_appends_new_scalar_item() -> None:
    canonical = spdx3.software_Package(name="pkg")
    canonical.externalIdentifier = []
    unify._merge_list(canonical, "externalIdentifier", [], ["new-item"])
    assert list(canonical.externalIdentifier) == ["new-item"]


def test_merge_dictionary_entries_unions_by_key() -> None:
    canonical = spdx3.ai_AIPackage(name="model")
    canonical.ai_hyperparameter = [spdx3.DictionaryEntry(key="lr", value="0.1")]
    dup_entries = [
        spdx3.DictionaryEntry(key="lr", value="0.5"),
        spdx3.DictionaryEntry(key="epochs", value="10"),
    ]
    unify._merge_dictionary_entries(
        canonical, "ai_hyperparameter", canonical.ai_hyperparameter, dup_entries
    )
    entries = {
        e.key: e.value
        for e in canonical.ai_hyperparameter
        if isinstance(e, spdx3.DictionaryEntry)
    }
    assert entries == {"lr": "0.1", "epochs": "10"}


def test_merge_dictionary_entries_noop_when_duplicate_empty() -> None:
    canonical = spdx3.ai_AIPackage(name="model")
    canonical.ai_hyperparameter = [spdx3.DictionaryEntry(key="lr", value="0.1")]
    unify._merge_dictionary_entries(
        canonical, "ai_hyperparameter", canonical.ai_hyperparameter, []
    )
    assert len(canonical.ai_hyperparameter) == 1


def test_warn_if_same_name_different_hash_skips_different_names(
    caplog: pytest.LogCaptureFixture,
) -> None:
    obj = spdx3.software_File(name="a.py")
    obj.verifiedUsing = [
        spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue="aaa")
    ]
    other = spdx3.software_File(name="b.py")
    other.verifiedUsing = [
        spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue="bbb")
    ]
    object_set = spdx3.SHACLObjectSet()
    object_set.add(other)

    with caplog.at_level(logging.WARNING, logger="pitloom.assemble.spdx3.fragments"):
        unify._warn_if_same_name_different_hash(obj, object_set)
    assert not caplog.records


def test_warn_if_same_name_different_hash_skips_missing_existing_hash(
    caplog: pytest.LogCaptureFixture,
) -> None:
    obj = spdx3.software_File(name="a.py")
    obj.verifiedUsing = [
        spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue="aaa")
    ]
    other = spdx3.software_File(name="a.py")
    object_set = spdx3.SHACLObjectSet()
    object_set.add(other)

    with caplog.at_level(logging.WARNING, logger="pitloom.assemble.spdx3.fragments"):
        unify._warn_if_same_name_different_hash(obj, object_set)
    assert not caplog.records


def test_merge_dictionary_entries_keyless_duplicate_entry_is_kept() -> None:
    """A duplicate entry with no ``key`` at all is still appended to the
    merged list (it can never collide on a key), but must not be recorded
    in ``keys_seen`` -- covers the "key is None" branch inside the loop."""
    canonical = spdx3.ai_AIPackage(name="model")
    canonical_entries = [spdx3.DictionaryEntry(key="a", value="1")]
    canonical.ai_hyperparameter = canonical_entries
    dup_entries = [
        spdx3.DictionaryEntry(value="keyless"),
        spdx3.DictionaryEntry(key="b", value="2"),
    ]

    unify._merge_dictionary_entries(
        canonical, "ai_hyperparameter", canonical_entries, dup_entries
    )

    merged = canonical.ai_hyperparameter
    assert len(merged) == 3
    keys = [getattr(entry, "key", None) for entry in merged]
    assert keys.count(None) == 1
    assert "b" in keys


def test_merge_dictionary_entries_all_duplicate_keys_no_change() -> None:
    """When every duplicate entry's key already exists on canonical, the
    merged list has the same length as canonical's -- the function must
    exit without calling setattr() at all."""
    canonical = spdx3.ai_AIPackage(name="model")
    canonical_entries = [spdx3.DictionaryEntry(key="a", value="1")]
    canonical.ai_hyperparameter = canonical_entries
    dup_entries = [spdx3.DictionaryEntry(key="a", value="999")]

    unify._merge_dictionary_entries(
        canonical, "ai_hyperparameter", canonical_entries, dup_entries
    )

    merged = canonical.ai_hyperparameter
    assert len(merged) == 1
    assert merged[0] is canonical_entries[0]
