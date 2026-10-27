# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Direct unit tests for the low-level merge helpers in
:mod:`pitloom.assemble.spdx3._fragments_unify` and `_fragments_props`, covering
branches not reached by the higher-level `merge_fragments()` integration tests in
:mod:`tests.core.test_fragments_misc`.
"""

# pylint: disable=protected-access

from __future__ import annotations

import logging
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import _fragments_hashes as hashes
from pitloom.assemble.spdx3 import _fragments_props as props
from pitloom.assemble.spdx3 import _fragments_unify as unify
from pitloom.export.spdx3_json import Spdx3JsonExporter, sha256_hash


def test_merge_index_unifies_hashes_differing_only_in_case() -> None:
    upper, lower = "AB" * 32, "ab" * 32
    assert upper != lower
    exporter = Spdx3JsonExporter()
    first = spdx3.software_File(name="a.py")
    first.verifiedUsing = [sha256_hash(lower)]
    exporter.object_set.add(first)
    second = spdx3.software_File(name="a.py")
    # Built directly: sha256_hash() would lowercase it.
    raw = spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=upper)
    second.verifiedUsing = [raw]
    assert raw.hashValue == upper
    assert unify._MergeIndex(exporter).find_by_hash(second) is first


def test_normalize_value_plain_list() -> None:
    assert props._normalize_value([1, 2]) == (2, ((3, "int", 1), (3, "int", 2)))


def test_is_empty_false_for_non_empty_scalar() -> None:
    assert props._is_empty(5) is False


def test_paths_suffix_match_rejects_non_string_inputs() -> None:
    assert props._paths_suffix_match(1, "a/b.py") is False
    assert props._paths_suffix_match("a/b.py", 1) is False


def test_merge_scalar_sets_when_canonical_empty() -> None:
    canonical = spdx3.Agent(name="Pitloom")
    props._merge_scalar(canonical, "comment", None, "from duplicate")
    assert canonical.comment == "from duplicate"


def test_merge_scalar_warns_on_real_conflict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    canonical = spdx3.software_File(name="a.py")
    with caplog.at_level(logging.WARNING, logger="pitloom.assemble.spdx3.fragments"):
        props._merge_scalar(canonical, "name", "a.py", "b.py")
    assert any("conflicting" in r.message for r in caplog.records)


def test_merge_comment_sets_when_canonical_empty() -> None:
    canonical = spdx3.Agent(name="Pitloom")
    props._merge_comment(canonical, None, "hello")
    assert canonical.comment == "hello"


def test_merge_comment_concatenates_when_both_present_and_differ() -> None:
    canonical = spdx3.Agent(name="Pitloom")
    props._merge_comment(canonical, "first", "second")
    assert canonical.comment == "first; second"


def _agent(spdx_id: str = "urn:agent-1") -> spdx3.Agent:
    agent = spdx3.Agent(name="A1")
    agent.spdxId = spdx_id
    return agent


def _sha256(value: str = "ab") -> spdx3.Hash:
    return spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=value)


@pytest.mark.parametrize(
    ("prop", "existing", "duplicate", "added"),
    [
        ("originatedBy", _agent, _agent, False),
        ("originatedBy", lambda: "urn:agent-1", _agent, False),
        ("originatedBy", _agent, lambda: "urn:agent-1", False),
        ("originatedBy", _agent, lambda: _agent("urn:agent-2"), True),
        ("verifiedUsing", _sha256, _sha256, False),
        ("verifiedUsing", _sha256, lambda: _sha256("cd"), True),
    ],
    ids=["object", "id-then-object", "object-then-id", "other", "hash", "hash-new"],
)
def test_merge_list_keys_an_element_by_id_and_a_hash_by_content(
    prop: str, existing: Any, duplicate: Any, added: bool
) -> None:
    """An element reference is present whether held as the object or its id;
    an object with no id (a ``Hash``) is present when equal in content."""
    canonical = spdx3.software_Package(name="pkg")
    setattr(canonical, prop, [existing()])
    props._merge_list(canonical, prop, getattr(canonical, prop), [duplicate()])
    assert len(getattr(canonical, prop)) == (2 if added else 1)


def test_merge_scalar_reference_forms_do_not_conflict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    canonical = spdx3.software_Package(name="pkg")
    with caplog.at_level(logging.WARNING):
        props._merge_scalar(canonical, "suppliedBy", "urn:agent-1", _agent())
    assert not caplog.records


def test_merge_list_appends_new_scalar_item() -> None:
    canonical = spdx3.software_Package(name="pkg")
    canonical.externalIdentifier = []
    props._merge_list(canonical, "externalIdentifier", [], ["new-item"])
    assert list(canonical.externalIdentifier) == ["new-item"]


def test_merge_dictionary_entries_unions_by_key() -> None:
    canonical = spdx3.ai_AIPackage(name="model")
    canonical.ai_hyperparameter = [spdx3.DictionaryEntry(key="lr", value="0.1")]
    dup_entries = [
        spdx3.DictionaryEntry(key="lr", value="0.5"),
        spdx3.DictionaryEntry(key="epochs", value="10"),
    ]
    props._merge_dictionary_entries(
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
    props._merge_dictionary_entries(
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
        hashes.warn_if_same_name_different_hash(obj, object_set)
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
        hashes.warn_if_same_name_different_hash(obj, object_set)
    assert not caplog.records


def test_merge_dictionary_entries_keyless_duplicate_entry_is_kept() -> None:
    """A duplicate entry with no ``key`` at all is still appended to the
    merged list (it can never collide on a key), but must not be recorded
    in ``by_key`` -- covers the "key is None" branch inside the loop."""
    canonical = spdx3.ai_AIPackage(name="model")
    canonical_entries = [spdx3.DictionaryEntry(key="a", value="1")]
    canonical.ai_hyperparameter = canonical_entries
    dup_entries = [
        spdx3.DictionaryEntry(value="keyless"),
        spdx3.DictionaryEntry(key="b", value="2"),
    ]

    props._merge_dictionary_entries(
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

    props._merge_dictionary_entries(
        canonical, "ai_hyperparameter", canonical_entries, dup_entries
    )

    merged = canonical.ai_hyperparameter
    assert len(merged) == 1
    assert merged[0] is canonical_entries[0]


def _entry(value: str | None) -> spdx3.DictionaryEntry:
    entry = spdx3.DictionaryEntry(key="lr")
    if value is not None:
        entry.value = value
    return entry


@pytest.mark.parametrize(
    ("kept", "dropped", "result", "warns"),
    [
        ("0.1", "0.5", "0.1", True),
        ("0.1", "0.1", "0.1", False),
        ("0.1", None, "0.1", False),
        (None, "0.5", "0.5", False),
        (None, None, None, False),
        ("[1, 2]", "[1,2]", "[1, 2]", False),
    ],
    ids=["differs", "equal", "dropped-no-value", "kept-no-value", "none", "same-json"],
)
@pytest.mark.parametrize("prop", ["ai_hyperparameter", "ai_metric"])
def test_merge_dictionary_entries_on_a_key_collision(
    prop: str,
    kept: str | None,
    dropped: str | None,
    result: str | None,
    warns: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The canonical value wins; a value it lacks is filled in; a different
    one that is lost says so once, naming the key, the kept and the dropped
    value."""
    canonical = spdx3.ai_AIPackage(name="model")
    setattr(canonical, prop, [_entry(kept)])
    dup = [_entry(dropped), spdx3.DictionaryEntry(key="n", value="1")]
    with caplog.at_level(logging.WARNING, logger="pitloom.assemble.spdx3"):
        props._merge_dictionary_entries(canonical, prop, getattr(canonical, prop), dup)
    entries = {e.key: getattr(e, "value", None) for e in getattr(canonical, prop)}
    assert entries == {"lr": result, "n": "1"}
    messages = [m for m in caplog.messages if m.startswith("Merge: conflicting")]
    assert len(messages) == int(warns)
    if warns:
        assert f"{prop!r} key 'lr'" in messages[0]
        assert "keeping '0.1', dropping '0.5'" in messages[0]


def test_merge_dictionary_entries_first_of_two_canonical_duplicates_decides() -> None:
    """Canonical holds ``lr`` twice (no value, then ``0.1``): the first is the
    entry a duplicate fills, as the first of a repeated key wins elsewhere."""
    canonical = spdx3.ai_AIPackage(name="model")
    canonical.ai_hyperparameter = [_entry(None), _entry("0.1")]
    props._merge_dictionary_entries(
        canonical, "ai_hyperparameter", canonical.ai_hyperparameter, [_entry("0.5")]
    )
    values = [getattr(e, "value", None) for e in canonical.ai_hyperparameter]
    assert values == ["0.5", "0.1"]
