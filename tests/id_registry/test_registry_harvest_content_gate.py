# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Harvest tests for pitloom.id_registry: the content gate (a recorded hash
is never erased), the harvest() return and I5 (ambiguity).

See also: test_registry_harvest.py (I1 and I4), _registry_harvest_shared.py
(helpers shared by both halves).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

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
from tests.id_registry._registry_harvest_shared import (
    _NS,
    _SHA_A,
    _SHA_B,
    _compact,
    _element,
    _file,
    _object_set,
)
from tests.registry_helpers import make_registry

_DROPPED = "content gate dropped for software_File 'a.py'"
_KEPT = "content gate kept for software_File 'a.py'"


@pytest.mark.parametrize(
    ("incoming", "new_id", "imported", "want", "info"),
    [
        (None, False, False, ("old", _SHA_A), None),
        (_SHA_A, False, False, ("old", _SHA_A), None),
        (None, True, False, ("old", _SHA_A), _KEPT),
        (None, False, True, ("old", _SHA_A), None),
        (_SHA_B, True, True, ("new", _SHA_B), None),
        (None, True, True, ("new", None), _DROPPED),
    ],
    ids=["keep", "same", "new-id", "import-keep", "import-new", "import"],
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


def test_harvest_drops_a_hash_an_ungated_entry_carried() -> None:
    """No lookup gates a package: a hash recorded for one (a file edited by
    hand) is dropped, so two surfaces' hashes cannot flip it."""
    element = _element(spdx3.software_Package, "dep", f"{_NS}#X-1", _SHA_B)
    key = (PACKAGE_TYPE, "dep")
    registry = make_registry({key: (f"{_NS}#X-1", _SHA_A)})

    assert registry.harvest(_object_set(element)) == (0, True)
    assert registry.elements[key] == RegistryEntry(f"{_NS}#X-1")


_DATASET = "dataset_DatasetPackage 'd'"


@pytest.mark.parametrize(
    ("incoming", "new_id", "imported", "want", "info"),
    [
        (None, False, False, ("old", _SHA_A), None),
        (_SHA_B, False, False, ("old", _SHA_A), None),
        (None, True, False, ("old", _SHA_A), "kept"),
        (None, False, True, ("old", _SHA_A), None),
        (None, True, True, ("new", None), "dropped"),
        (_SHA_B, False, True, ("old", _SHA_B), None),
        (_SHA_B, True, True, ("new", _SHA_B), None),
    ],
    ids=["keep", "hash-ignored", "new-id", "import-keep", "import-new"]
    + ["import-hashed", "import-hashed-new"],
)
def test_dataset_pin_hash_kept_and_never_recorded(
    caplog: pytest.LogCaptureFixture,
    incoming: str | None,
    new_id: bool,
    imported: bool,
    want: tuple[str, str | None],
    info: str | None,
) -> None:
    """A run's harvest never records a dataset package's hash: an element
    of its id keeps the held one, whatever hash it carries; another id is
    not written (one INFO). ``id import`` records the element's own hash;
    an unhashed one keeps the held hash for its id, else is written with
    none and one INFO."""
    ids = {"old": f"{_NS}#DatasetPackage-1", "new": f"{_NS}#DatasetPackage-2"}
    key = (DATASET_PACKAGE_TYPE, "d")
    registry = make_registry({key: (ids["old"], _SHA_A)})
    element = _element(
        spdx3.dataset_DatasetPackage, "d", ids["new" if new_id else "old"], incoming
    )
    caplog.set_level(logging.INFO, logger="pitloom.id_registry")

    # pylint: disable-next=protected-access
    ids_mod._harvest_elements(registry, [element], imported=imported)

    assert registry.elements[key] == RegistryEntry(ids[want[0]], want[1])
    messages = [r.getMessage() for r in caplog.records]
    assert messages == (
        [
            f"ID registry: content gate {info} for {_DATASET}: "
            + (
                f"imported id {ids['new']} replaces {ids['old']}"
                if imported
                else f"harvested id {ids['new']} not recorded over {ids['old']}"
            )
        ]
        if info
        else []
    )


# --- the harvest() return ------------------------------------------------


def test_harvest_counts_distinct_new_ids_not_keys() -> None:
    """A known id under another name of its type is kept where it is
    (R-keep); its recorded key takes it over (a promotion) and adds no id;
    a key given a new id replaces its entry and adds none."""
    registry = IdRegistry.new("proj")
    shared = f"{_NS}#File-1"
    tail = _object_set(_file("p/a.py", shared, _SHA_A))

    first = registry.harvest(_object_set(_file("src/p/a.py", shared, _SHA_A)))
    kept = registry.harvest(tail)
    counters = dict(registry.id_counters)
    promoted = registry.harvest(tail, keys={shared: (FILE_TYPE, "p/a.py")})
    assert list(registry.elements) == [(FILE_TYPE, "p/a.py")]
    assert registry.id_counters == counters
    again = registry.harvest(tail)
    moved = registry.harvest(
        _object_set(_file("p/a.py", f"{_NS}#File-2", _SHA_B)),
        keys={f"{_NS}#File-2": (FILE_TYPE, "p/a.py")},
    )

    assert first == (1, True)
    assert kept == (0, False)
    assert promoted == (0, True)
    assert again == (0, False)
    assert moved == (0, True)


def test_harvest_pair_in_one_pass_is_one_new_id() -> None:
    """Two elements of one id: the first written keeps it."""
    registry = IdRegistry.new("proj")
    shared = f"{_NS}#File-1"

    result = registry.harvest(
        _object_set(
            _file("src/p/a.py", shared, _SHA_A), _file("p/a.py", shared, _SHA_A)
        )
    )

    assert result == (1, True)
    assert len(registry.elements) == 1


def test_harvest_reports_a_changed_hash_as_a_change() -> None:
    registry = make_registry({(FILE_TYPE, "a.py"): (f"{_NS}#File-1", _SHA_A)})

    result = registry.harvest(
        _object_set(_file("a.py", f"{_NS}#File-1", _SHA_B)),
        keys={f"{_NS}#File-1": (FILE_TYPE, "a.py")},
    )

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

    # Both recorded under *key*: a model's name key alone is never written.
    keys = {f"{_NS}#X-1": key, f"{_NS}#X-2": key}
    result = registry.harvest(_object_set(*objects), keys=keys)

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
