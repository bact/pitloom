# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Harvest tests for pitloom.id_registry: I1 (record, never classify), I4
(one key per id, strict) and R-keep.

See also: test_registry.py (the in-memory API), test_registry_import.py
(``import_sbom``), test_registry_harvest_content_gate.py (the content
gate, the harvest() return and I5), shared.py (fixtures shared by this
group), _registry_harvest_shared.py (helpers shared by both halves).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

import pitloom.id_registry._harvest as ids_mod
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    PACKAGE_TYPE,
    IdRegistry,
    RegistryEntry,
)
from pitloom.id_registry._harvest import _harvest_elements, _import_sbom_element
from tests.id_registry._registry_harvest_shared import (
    _NS,
    _SHA_A,
    _SHA_B,
    _compact,
    _element,
    _file,
    _object_set,
)
from tests.registry_helpers import entries_of, make_registry

# --- I1: harvest records, never classifies ------------------------------


def test_harvest_records_every_element_under_its_own_key() -> None:
    """Each element keeps its type. Only the two gated types, a File and
    an AIPackage, keep a hash: a hashed DatasetPackage or Package gets a
    sha-less entry, as a hash-less File does. The hashed model, with no
    recorded key, takes the key of its file."""
    registry = IdRegistry.new("proj")
    object_set = _object_set(
        _element(spdx3.ai_AIPackage, "tiny", f"{_NS}#AIPackage-1", _SHA_A.upper()),
        _element(spdx3.dataset_DatasetPackage, "data/t.txt", f"{_NS}#Ds-1", _SHA_B),
        _file("src", f"{_NS}#File-1"),
        _file("src/a.py", f"{_NS}#File-2", _SHA_A),
        _element(spdx3.software_Package, "Py_YAML", f"{_NS}#Package-1", _SHA_A),
    )

    assert registry.harvest(object_set) == (5, True)

    assert entries_of(registry) == {
        (AI_PACKAGE_TYPE, "src/a.py"): (f"{_NS}#AIPackage-1", _SHA_A),
        (DATASET_PACKAGE_TYPE, "data/t.txt"): (f"{_NS}#Ds-1", None),
        (FILE_TYPE, "src"): (f"{_NS}#File-1", None),
        (FILE_TYPE, "src/a.py"): (f"{_NS}#File-2", _SHA_A),
        (PACKAGE_TYPE, "py-yaml"): (f"{_NS}#Package-1", None),
    }


def test_harvested_id_wins_over_an_existing_entry() -> None:
    registry = make_registry({(FILE_TYPE, "a.py"): (f"{_NS}#File-9", _SHA_A)})
    keys = {f"{_NS}#File-1": (FILE_TYPE, "a.py")}  # the run's own lookup

    _import_sbom_element(registry, _file("a.py", f"{_NS}#File-1", _SHA_B), keys=keys)

    assert registry.get(FILE_TYPE, "a.py") == RegistryEntry(f"{_NS}#File-1", _SHA_B)


@pytest.mark.parametrize(
    ("compact_type", "kept"),
    [("object", False), (None, True)],
    ids=["object", "class-name-fallback"],
)
def test_harvest_skips_only_an_untyped_element(
    compact_type: str | None, kept: bool
) -> None:
    class Dummy:  # pylint: disable=too-few-public-methods
        """A named element with an id and the given compact type."""

        name = "test"
        spdxId = "http://test"  # pylint: disable=invalid-name

        def get_compact_type(self) -> str | None:
            return compact_type

    registry = IdRegistry.new("test")

    _import_sbom_element(registry, Dummy())

    assert bool(registry.elements) is kept
    assert registry.get("Dummy", "test") == (
        RegistryEntry("http://test") if kept else None
    )


# --- I4: one key per id; R-keep ---------------------------------------


@pytest.mark.parametrize(
    ("cls", "recorded", "kept"),
    [
        (spdx3.software_Package, False, "aaa"),
        (spdx3.dataset_DatasetPackage, False, "bbb"),
        (spdx3.software_Package, True, "bbb"),
    ],
    ids=["same-type-kept", "other-type-released", "recorded-moves"],
)
def test_harvest_moves_an_id_between_same_type_keys_only_when_recorded(
    caplog: pytest.LogCaptureFixture, cls: Any, recorded: bool, kept: str
) -> None:
    """An element with no recorded key never moves an id another key of its
    type holds (R-keep); one of another type is released; a recorded key
    takes the id from every other key (strict I4)."""
    shared = f"{_NS}#Package-1"
    registry = make_registry({(PACKAGE_TYPE, "aaa"): (shared, None)}, namespace=_NS)
    keys = {shared: (_compact(cls), "bbb")} if recorded else None
    caplog.set_level(logging.DEBUG, logger="pitloom.id_registry")

    _import_sbom_element(registry, _element(cls, "bbb", shared), keys=keys)

    assert entries_of(registry) == {
        (PACKAGE_TYPE if kept == "aaa" else _compact(cls), kept): (shared, None)
    }
    assert registry.id_counters == {"Package": 1}  # reserved, nothing minted
    skipped = [r.getMessage() for r in caplog.records if "held under" in r.message]
    assert len(skipped) == (kept == "aaa")


#: name -> (held key -> id, the pass's (name, id) files, expected key -> id).
_PASS_CASES: dict[str, tuple[dict[str, str], list[tuple[str, str]], dict[str, str]]] = {
    # a.py's id moves, so __init__.py's id is not held: imported, any order.
    "freed": (
        {"__init__.py": "File-1", "a.py": "File-2"},
        [("__init__.py", "File-2"), ("a.py", "File-3")],
        {"__init__.py": "File-2", "a.py": "File-3"},
    ),
    # h is written by an element R-keep skips (its id held under g): kept.
    "chain": (
        {"h": "File-1", "g": "File-2"},
        [("k", "File-1"), ("h", "File-2")],
        {"h": "File-1", "g": "File-2"},
    ),
}


@pytest.mark.parametrize("backwards", [False, True], ids=["forward", "backwards"])
@pytest.mark.parametrize("imported", [True, False], ids=["import", "harvest"])
@pytest.mark.parametrize("case", list(_PASS_CASES))
def test_r_keep_is_decided_before_the_pass(
    case: str, imported: bool, backwards: bool
) -> None:
    """R-keep is decided once, before any write: the result is the same in
    either element order, and a second pass changes nothing."""
    held, files, expected = _PASS_CASES[case]
    registry = make_registry(
        {(FILE_TYPE, k): (f"{_NS}#{v}", None) for k, v in held.items()}
    )
    objects = [_file(name, f"{_NS}#{spdx_id}") for name, spdx_id in files]
    order = objects[::-1] if backwards else objects

    _harvest_elements(registry, order, imported=imported)
    first = entries_of(registry)
    _harvest_elements(registry, order, imported=imported)

    assert entries_of(registry) == first
    assert first == {(FILE_TYPE, k): (f"{_NS}#{v}", None) for k, v in expected.items()}


#: Cases the dropped src-layout alias rule told apart: with a recorded
#: key, every other key holding the id is dropped, whatever its type, hash
#: or path; with none, only another type's key is.
_RELEASE_CASES: dict[str, tuple[Any, str, str | None, str | None]] = {
    "alias": (spdx3.software_File, "pkg/train.py", _SHA_A, _SHA_A),
    "other-type": (spdx3.ai_AIPackage, "pkg/train.py", _SHA_A, _SHA_A),
    "other-sha": (spdx3.software_File, "pkg/train.py", _SHA_A, _SHA_B),
    "no-sha": (spdx3.software_File, "pkg/train.py", None, None),
    "not-suffix": (spdx3.software_File, "other/train.py", _SHA_A, _SHA_A),
}


@pytest.mark.parametrize("recorded", [True, False], ids=["recorded", "name"])
@pytest.mark.parametrize("case", list(_RELEASE_CASES))
def test_strict_one_key_per_id(case: str, recorded: bool) -> None:
    cls, name, first_sha, second_sha = _RELEASE_CASES[case]
    registry = IdRegistry.new("proj")
    shared = f"{_NS}#File-1"
    _import_sbom_element(registry, _file("src/pkg/train.py", shared, first_sha))
    keys = {shared: (_compact(cls), name)} if recorded else None

    _import_sbom_element(registry, _element(cls, "x", shared, second_sha), keys=keys)

    first, second = (FILE_TYPE, "src/pkg/train.py"), (_compact(cls), name)
    if not recorded:  # written under its own name "x"
        second = (_compact(cls), "x")
    moved = recorded or cls is not spdx3.software_File
    assert entries_of(registry) == (
        {second: (shared, second_sha)} if moved else {first: (shared, first_sha)}
    )


def test_harvest_file_repointed_then_old_id_claimed_keeps_both() -> None:
    """A key moved to a new id no longer holds its old id: a later element
    claiming the old id must not release the moved key."""
    registry = make_registry(
        {(FILE_TYPE, "a.py"): (f"{_NS}#File-2", _SHA_A)}, namespace=_NS
    )

    registry.harvest(
        _object_set(
            _file("a.py", f"{_NS}#File-1", _SHA_A),
            _file("b.py", f"{_NS}#File-2", _SHA_B),
        )
    )

    assert registry.lookup(FILE_TYPE, ["a.py"]) == f"{_NS}#File-1"
    assert registry.lookup(FILE_TYPE, ["b.py"]) == f"{_NS}#File-2"


def test_release_stale_keys_visits_only_keys_sharing_the_id() -> None:
    """Only keys already sharing the harvested id are dropped: 2,000
    unrelated same-content files with their own ids are never touched."""
    registry = IdRegistry.new("proj")
    collided = f"{registry.namespace}#File-1"
    for i in range(2000):
        registry.elements[(FILE_TYPE, f"pkg{i}/mod.py")] = RegistryEntry(
            f"{registry.namespace}#File-unique-{i}", _SHA_A
        )
    registry.elements[(FILE_TYPE, "colliding_a")] = RegistryEntry(collided, _SHA_A)
    registry.elements[(FILE_TYPE, "colliding_b")] = RegistryEntry(collided, _SHA_A)
    keys = {collided: (FILE_TYPE, "colliding_c")}

    with patch.object(
        ids_mod._SpdxIdIndex,  # pylint: disable=protected-access
        "drop",
        autospec=True,
        # pylint: disable-next=protected-access
        side_effect=ids_mod._SpdxIdIndex.drop,
    ) as spy:
        _import_sbom_element(registry, _file("x", collided, _SHA_A), keys=keys)

    assert sorted(call.args[3] for call in spy.call_args_list) == [
        (FILE_TYPE, "colliding_a"),
        (FILE_TYPE, "colliding_b"),
    ]
    assert registry.lookup(FILE_TYPE, ["colliding_a", "colliding_b"]) is None
    assert registry.lookup(FILE_TYPE, ["colliding_c"]) == collided
    assert len(registry.elements) == 2001
