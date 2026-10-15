# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Harvest tests for pitloom.id_registry: I1 (record, never classify), I4
(one key per id, the src-layout alias), I5 (ambiguity) and the
``harvest()`` return.

See also: test_registry.py (the in-memory API), test_registry_import.py
(``import_sbom``), shared.py (fixtures shared by this group).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar
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
from pitloom.id_registry._harvest import _import_sbom_element
from tests.registry_helpers import entries_of, make_registry

_NS = "https://spdx.org/spdxdocs/proj-1"
_CI = spdx3.CreationInfo(
    specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
)
_SHA_A = "a" * 64
_SHA_B = "b" * 64
_E = TypeVar("_E", bound=spdx3.Element)


def _hash(value: str) -> list[spdx3.Hash]:
    return [spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=value)]


def _element(cls: type[_E], name: str, spdx_id: str, sha256: str | None = None) -> _E:
    obj = cls(spdxId=spdx_id, name=name, creationInfo=_CI)
    if sha256 is not None:
        obj.verifiedUsing = _hash(sha256)
    return obj


def _file(name: str, spdx_id: str, sha256: str | None = None) -> spdx3.software_File:
    return _element(spdx3.software_File, name, spdx_id, sha256)


def _object_set(*objects: Any) -> spdx3.SHACLObjectSet:
    object_set = spdx3.SHACLObjectSet()
    for obj in objects:
        object_set.add(obj)
    return object_set


# --- I1: harvest records, never classifies ------------------------------


def test_harvest_records_every_element_under_its_own_key() -> None:
    """Each element keeps its type. Only the two gated types, a File and
    an AIPackage, keep a hash: a hashed DatasetPackage or Package gets a
    sha-less entry, as a hash-less File does."""
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
        (AI_PACKAGE_TYPE, "tiny"): (f"{_NS}#AIPackage-1", _SHA_A),
        (DATASET_PACKAGE_TYPE, "data/t.txt"): (f"{_NS}#Ds-1", None),
        (FILE_TYPE, "src"): (f"{_NS}#File-1", None),
        (FILE_TYPE, "src/a.py"): (f"{_NS}#File-2", _SHA_A),
        (PACKAGE_TYPE, "py-yaml"): (f"{_NS}#Package-1", None),
    }


def test_harvested_id_wins_over_an_existing_entry() -> None:
    registry = make_registry({(FILE_TYPE, "a.py"): (f"{_NS}#File-9", _SHA_A)})

    _import_sbom_element(registry, _file("a.py", f"{_NS}#File-1", _SHA_B))

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


# --- I4: one key per id -------------------------------------------------


def test_harvest_drops_a_stale_key_sharing_the_id() -> None:
    """A second element under another key with the same id proves the first
    key stale: it is dropped, whatever its type."""
    registry = IdRegistry.new("proj")
    shared = f"{_NS}#Package-1"
    _import_sbom_element(registry, _element(spdx3.software_Package, "aaa", shared))
    _import_sbom_element(registry, _element(spdx3.software_Package, "bbb", shared))

    assert entries_of(registry) == {(PACKAGE_TYPE, "bbb"): (shared, None)}


#: The second element of an alias pair, each case breaking one conjunct
#: of the alias rule: same type, same non-empty sha256, path-suffix names.
_ALIAS_CASES: dict[str, tuple[Any, str, str | None, str | None, bool]] = {
    "alias": (spdx3.software_File, "pkg/train.py", _SHA_A, _SHA_A, True),
    "other-type": (spdx3.ai_AIPackage, "pkg/train.py", _SHA_A, _SHA_A, False),
    "other-sha": (spdx3.software_File, "pkg/train.py", _SHA_A, _SHA_B, False),
    "no-sha": (spdx3.software_File, "pkg/train.py", None, None, False),
    "not-suffix": (spdx3.software_File, "other/train.py", _SHA_A, _SHA_A, False),
}


@pytest.mark.parametrize("case", list(_ALIAS_CASES))
def test_alias_rule_keeps_a_second_key_only_when_all_three_hold(case: str) -> None:
    cls, name, first_sha, second_sha, both = _ALIAS_CASES[case]
    registry = IdRegistry.new("proj")
    shared = f"{_NS}#File-1"
    _import_sbom_element(registry, _file("src/pkg/train.py", shared, first_sha))

    _import_sbom_element(registry, _element(cls, name, shared, second_sha))

    second_key = (_compact(cls), name)
    assert entries_of(registry)[second_key] == (shared, second_sha)
    assert ((FILE_TYPE, "src/pkg/train.py") in registry.elements) is both
    assert registry.id_count() == 1


def _compact(cls: Any) -> str:
    return str(cls(spdxId="urn:x", name="x", creationInfo=_CI).get_compact_type())


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


def test_release_stale_keys_checks_id_before_computing_path_alias() -> None:
    """Only keys already sharing the harvested id get the alias check: 2,000
    unrelated same-content files with their own ids are never compared."""
    registry = IdRegistry.new("proj")
    collided = f"{registry.namespace}#File-1"
    for i in range(2000):
        registry.elements[(FILE_TYPE, f"pkg{i}/mod.py")] = RegistryEntry(
            f"{registry.namespace}#File-unique-{i}", _SHA_A
        )
    registry.elements[(FILE_TYPE, "colliding_a")] = RegistryEntry(collided, _SHA_A)
    registry.elements[(FILE_TYPE, "colliding_b")] = RegistryEntry(collided, _SHA_A)

    with patch.object(
        ids_mod,
        "_is_files_path_alias",
        # pylint: disable-next=protected-access
        wraps=ids_mod._is_files_path_alias,
    ) as spy:
        _import_sbom_element(registry, _file("colliding_c", collided, _SHA_A))

    assert spy.call_count == 2
    assert registry.lookup(FILE_TYPE, ["colliding_a", "colliding_b"]) is None
    assert registry.lookup(FILE_TYPE, ["colliding_c"]) == collided


_DROPPED = "content gate dropped for software_File 'a.py'"
_KEPT = "content gate kept for software_File 'a.py'"


@pytest.mark.parametrize(
    ("incoming", "new_id", "imported", "want", "info"),
    [
        (None, False, False, ("old", _SHA_A), None),
        (_SHA_B, False, False, ("old", _SHA_B), None),
        (_SHA_A, False, False, ("old", _SHA_A), None),
        (None, True, False, ("old", _SHA_A), _KEPT),
        (None, False, True, ("old", _SHA_A), None),
        (_SHA_B, True, True, ("new", _SHA_B), None),
        (None, True, True, ("new", None), _DROPPED),
    ],
    ids=["keep", "replace", "same", "new-id", "import-keep", "import-new", "import"],
)
def test_harvest_never_erases_a_recorded_sha_and_import_says_so(
    caplog: pytest.LogCaptureFixture,
    incoming: str | None,
    new_id: bool,
    imported: bool,
    want: tuple[str, str | None],
    info: str | None,
) -> None:
    """A hashed element replaces the entry's hash; an unhashed one with its
    id keeps it. An unhashed one with another id: a run's harvest leaves the
    entry as is, ``id import`` writes it with no hash; each says so in one
    INFO."""
    ids = {"old": f"{_NS}#File-1", "new": f"{_NS}#File-2"}
    registry = make_registry({(FILE_TYPE, "a.py"): (ids["old"], _SHA_A)})
    assert registry.get(FILE_TYPE, "a.py") == RegistryEntry(ids["old"], _SHA_A)
    element = _file("a.py", ids["new" if new_id else "old"], incoming)
    caplog.set_level(logging.DEBUG, logger="pitloom.id_registry")

    # pylint: disable-next=protected-access
    ids_mod._harvest_elements(registry, [element], imported=imported)

    assert registry.get(FILE_TYPE, "a.py") == RegistryEntry(ids[want[0]], want[1])
    detail = (
        f"imported id {ids['new']} replaces {ids['old']}"
        if imported
        else f"harvested id {ids['new']} not recorded over {ids['old']}"
    )
    gate = [r for r in caplog.records if "content gate" in r.getMessage()]
    assert [(r.levelno, r.getMessage()) for r in gate] == (
        [(logging.INFO, f"ID registry: {info}: {detail}")] if info else []
    )


def test_harvest_returns_unchanged_when_it_keeps_a_gated_entry() -> None:
    """The auto-harvest of an unhashed element under another id changes
    nothing, so the run saves nothing."""
    registry = make_registry({(FILE_TYPE, "a.py"): (f"{_NS}#File-1", _SHA_A)})

    assert registry.harvest(_object_set(_file("a.py", f"{_NS}#File-2"))) == (0, False)


@pytest.mark.parametrize(
    ("cls", "recorded"),
    [(spdx3.software_File, _SHA_A), (spdx3.software_Package, None)],
    ids=["file", "package"],
)
def test_alternating_hashed_and_unhashed_runs_leave_the_file_unchanged(
    tmp_path: Path, cls: type[spdx3.Element], recorded: str | None
) -> None:
    path = tmp_path / "registry.json"
    spdx_id = f"{_NS}#X-1"

    def run(sha256: str | None) -> bytes:
        registry = (
            IdRegistry.load(path)
            if path.exists()
            else IdRegistry(namespace=_NS, project_root=tmp_path)
        )
        element = _element(cls, "dep", spdx_id, sha256)
        if registry.harvest(_object_set(element))[1]:
            registry.save(path)
        return path.read_bytes()

    first, second, third = run(_SHA_A), run(None), run(_SHA_A)

    assert IdRegistry.load(path).get(_compact(cls), "dep") == (
        RegistryEntry(spdx_id, recorded)
    )
    assert first == second == third


@pytest.mark.parametrize(
    "cls",
    [spdx3.software_Package, spdx3.dataset_DatasetPackage],
    ids=["package", "dataset"],
)
def test_harvest_drops_a_hash_an_ungated_entry_carried(
    cls: type[spdx3.Element],
) -> None:
    """No lookup gates these types: a hash recorded for one (a file edited
    by hand) is dropped, so two surfaces' hashes cannot flip it."""
    element = _element(cls, "dep", f"{_NS}#X-1", _SHA_B)
    key = (_compact(cls), "dep")
    registry = make_registry({key: (f"{_NS}#X-1", _SHA_A)})

    assert registry.harvest(_object_set(element)) == (0, True)
    assert registry.elements[key] == RegistryEntry(f"{_NS}#X-1")


# --- the harvest() return ------------------------------------------------


def test_harvest_counts_distinct_new_ids_not_keys() -> None:
    """A src-layout alias adds a key, not an id; a key given a new id
    replaces its entry and adds none."""
    registry = IdRegistry.new("proj")
    shared = f"{_NS}#File-1"

    first = registry.harvest(_object_set(_file("src/p/a.py", shared, _SHA_A)))
    alias = registry.harvest(_object_set(_file("p/a.py", shared, _SHA_A)))
    assert (len(registry.elements), registry.id_count()) == (2, 1)
    again = registry.harvest(_object_set(_file("p/a.py", shared, _SHA_A)))
    moved = registry.harvest(_object_set(_file("p/a.py", f"{_NS}#File-2", _SHA_B)))

    assert first == (1, True)
    assert alias == (0, True)
    assert again == (0, False)
    assert moved == (0, True)


def test_harvest_pair_in_one_pass_is_one_new_id() -> None:
    registry = IdRegistry.new("proj")
    shared = f"{_NS}#File-1"

    result = registry.harvest(
        _object_set(
            _file("src/p/a.py", shared, _SHA_A), _file("p/a.py", shared, _SHA_A)
        )
    )

    assert result == (1, True)
    assert len(registry.elements) == 2


def test_harvest_reports_a_changed_hash_as_a_change() -> None:
    registry = make_registry({(FILE_TYPE, "a.py"): (f"{_NS}#File-1", _SHA_A)})

    result = registry.harvest(_object_set(_file("a.py", f"{_NS}#File-1", _SHA_B)))

    assert result == (0, True)
    assert registry.get(FILE_TYPE, "a.py") == RegistryEntry(f"{_NS}#File-1", _SHA_B)


# --- I5: ambiguity covers every key --------------------------------------


@pytest.mark.parametrize(
    ("cls", "names", "key"),
    [
        (spdx3.software_File, ("a.py", "a.py"), (FILE_TYPE, "a.py")),
        (spdx3.software_Package, ("Foo", "foo"), (PACKAGE_TYPE, "foo")),
        (spdx3.ai_AIPackage, ("m", "m"), (AI_PACKAGE_TYPE, "m")),
    ],
    ids=["file-path", "package", "ai-package"],
)
def test_ambiguous_key_skips_both_and_keeps_the_existing_entry(
    cls: Any, names: tuple[str, str], key: tuple[str, str]
) -> None:
    pinned = f"{_NS}#Pinned-1"
    registry = make_registry({key: (pinned, _SHA_A)})
    objects = [
        _element(cls, names[0], f"{_NS}#X-1", _SHA_A),
        _element(cls, names[1], f"{_NS}#X-2", _SHA_B),
        _file("other.py", f"{_NS}#X-3", _SHA_A),
    ]

    result = registry.harvest(_object_set(*objects))

    assert registry.elements[key] == RegistryEntry(pinned, _SHA_A)
    assert registry.get(FILE_TYPE, "other.py") == RegistryEntry(f"{_NS}#X-3", _SHA_A)
    assert result == (1, True)


@pytest.mark.parametrize("field", ["name", "spdxId"])
def test_harvest_skips_an_element_with_a_lone_surrogate_with_a_warning(
    caplog: pytest.LogCaptureFixture, field: str
) -> None:
    """One unencodable name or id from an SBOM is skipped; the rest of the
    harvest goes on."""
    bad = "\udcff"
    name, spdx_id = (bad, f"{_NS}#X-1") if field == "name" else ("a", f"{_NS}#{bad}")
    registry = make_registry()

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        registry.harvest(
            _object_set(_file(name, spdx_id), _file("ok.py", f"{_NS}#X-2"))
        )

    (warning,) = [r.getMessage() for r in caplog.records]
    assert warning.startswith("ID registry: ") and "lone surrogate" in warning
    assert bad not in warning
    assert list(registry.elements) == [(FILE_TYPE, "ok.py")]


def test_harvest_reserves_the_id_of_a_skipped_element() -> None:
    """A skipped (unencodable) name still holds its id: never minted."""
    registry = make_registry(namespace=_NS)

    registry.harvest(_object_set(_file("a\ud800b.txt", f"{_NS}#File-9")))

    assert not registry.elements
    assert registry.register(FILE_TYPE, "n") == f"{_NS}#File-10"
