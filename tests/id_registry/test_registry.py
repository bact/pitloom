# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Core tests for pitloom.id_registry: the key rule, ``lookup``, ``get``,
``register``, ``has_name``, ``id_count`` and ``root_dir``.

See also: test_registry_format.py (load/save), test_registry_harvest.py,
test_registry_generate.py, test_registry_import.py, test_session.py,
tests/registry_helpers.py (``make_registry``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    DEFAULT_ID_REGISTRY_FILENAME,
    FILE_TYPE,
    PACKAGE_TYPE,
    IdRegistry,
    IdRegistrySession,
    RegistryEntry,
    resolve_registry,
    type_id_prefix,
)
from pitloom.id_registry._types import _element_key
from tests.id_registry.surfaces_base import _run_cli
from tests.registry_helpers import entries_of, make_registry

_NS = "https://spdx.org/spdxdocs/test-1"
_SHA_A = "a" * 64
_SHA_B = "b" * 64
_ABSENT = "absent"


def test_resolve_registry_error(tmp_path: Path) -> None:
    # A declared-but-broken registry raises, it is never silently ignored.
    invalid_file = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    invalid_file.write_text("{")  # Malformed JSON

    with pytest.raises(ValueError, match="ID registry file"):
        resolve_registry(invalid_file, None, tmp_path)

    missing_file = tmp_path / "missing.json"
    with pytest.raises(ValueError, match="ID registry file"):
        resolve_registry(missing_file, None, tmp_path)


# --- the key rule -----------------------------------------------------


def test_element_key_canonicalises_only_a_package_name() -> None:
    """Keyword call, and a swap-killer: a type and a name that differ only
    by PEP 503 canonicalisation give different keys if swapped."""
    assert _element_key(type_name=PACKAGE_TYPE, name="Py_YAML") == (
        PACKAGE_TYPE,
        "py-yaml",
    )
    assert _element_key(type_name=FILE_TYPE, name="Py_YAML") == (FILE_TYPE, "Py_YAML")
    assert _element_key(type_name="Software_Package", name=PACKAGE_TYPE) == (
        "Software_Package",
        PACKAGE_TYPE,
    )


def test_element_key_rejects_a_positional_call() -> None:
    with pytest.raises(TypeError):
        # pylint: disable-next=too-many-function-args,missing-kwoa
        _element_key(PACKAGE_TYPE, "x")  # type: ignore[call-arg]


def test_registry_entry_lowercases_and_rejects_an_empty_sha256() -> None:
    assert RegistryEntry("x", "ABC").sha256 == "abc"
    assert RegistryEntry("x").sha256 is None
    with pytest.raises(ValueError, match="sha256"):
        RegistryEntry("x", "")


@pytest.mark.parametrize(
    ("type_name", "prefix"),
    [
        (FILE_TYPE, "File"),
        (PACKAGE_TYPE, "Package"),
        (AI_PACKAGE_TYPE, "AIPackage"),
        (DATASET_PACKAGE_TYPE, "DatasetPackage"),
        ("Agent", "Agent"),
    ],
)
def test_type_id_prefix(type_name: str, prefix: str) -> None:
    assert type_id_prefix(type_name) == prefix


# --- lookup and get ----------------------------------------------------


def test_lookup_is_typed_and_a_file_and_a_dataset_at_one_path_differ() -> None:
    """A File and a DatasetPackage at one path get two ids (D2), and a
    lookup of one type never returns the other's."""
    registry = IdRegistry.new("demo")
    file_id = registry.register(FILE_TYPE, "data/t.txt", sha256=_SHA_A)
    dataset_id = registry.register(DATASET_PACKAGE_TYPE, "data/t.txt")

    assert file_id != dataset_id
    assert file_id.endswith("#File-1")
    assert dataset_id.endswith("#DatasetPackage-1")
    assert registry.lookup(FILE_TYPE, ["data/t.txt"]) == file_id
    assert registry.lookup(DATASET_PACKAGE_TYPE, ["data/t.txt"]) == dataset_id
    assert registry.lookup(AI_PACKAGE_TYPE, ["data/t.txt"]) is None


@pytest.mark.parametrize(
    ("stored", "given", "hit"),
    [
        (_SHA_A, _SHA_A, True),
        (_SHA_A, _SHA_A.upper(), True),
        (_SHA_A.upper(), _SHA_A, True),
        (_SHA_A, _SHA_B, False),
        (None, _SHA_A, False),  # a sha-less entry never satisfies a gate
        (None, None, True),
        (_SHA_A, None, True),  # ungated ignores the entry's hash
    ],
    ids=["equal", "given-upper", "stored-upper", "differs", "no-sha", "ungated", "u+s"],
)
def test_lookup_gate(stored: str | None, given: str | None, hit: bool) -> None:
    registry = make_registry({(FILE_TYPE, "a.py"): (f"{_NS}#File-1", stored)})

    found = registry.lookup(FILE_TYPE, ["a.py"], sha256=given)

    assert found == (f"{_NS}#File-1" if hit else None)


@pytest.mark.parametrize(
    ("stored", "hit"), [(None, True), (_SHA_A, False)], ids=["no-sha", "sha"]
)
def test_lookup_miss_hashed_skips_an_entry_recording_a_hash(
    stored: str | None, hit: bool
) -> None:
    """Content-less input cannot vouch for a hashed entry; a hash-less one
    still hits."""
    registry = make_registry({(AI_PACKAGE_TYPE, "m"): (f"{_NS}#AIPackage-1", stored)})

    found = registry.lookup(AI_PACKAGE_TYPE, ["m"], miss_hashed=True)

    assert found == (f"{_NS}#AIPackage-1" if hit else None)


def test_lookup_first_gated_hit_wins_in_candidate_order() -> None:
    """I3: the first candidate whose gate passes wins; a candidate whose
    hash differs is skipped, not a stop."""
    registry = make_registry(
        {
            (FILE_TYPE, "src/p/a.py"): (f"{_NS}#File-1", _SHA_B),
            (FILE_TYPE, "p/a.py"): (f"{_NS}#File-2", _SHA_A),
            (FILE_TYPE, "x/a.py"): (f"{_NS}#File-3", _SHA_A),
        }
    )
    names = ["src/p/a.py", "p/a.py", "x/a.py"]

    assert registry.lookup(FILE_TYPE, names, sha256=_SHA_A) == f"{_NS}#File-2"
    assert registry.lookup(FILE_TYPE, names[::-1], sha256=_SHA_A) == f"{_NS}#File-3"
    assert registry.lookup(FILE_TYPE, names) == f"{_NS}#File-1"


@pytest.mark.parametrize(
    "registry", [None, IdRegistry.new("x")], ids=["none", "registry"]
)
def test_lookup_rejects_a_bare_string(registry: IdRegistry | None) -> None:
    with pytest.raises(TypeError, match="not one str"):
        IdRegistrySession(registry).lookup_id("c", FILE_TYPE, "a.py")
    with pytest.raises(TypeError, match="not one str"):
        IdRegistry.new("x").lookup(FILE_TYPE, "a.py")


def test_get_and_lookup_canonicalise_a_package_name() -> None:
    registry = IdRegistry.new("x")
    pinned = registry.register(PACKAGE_TYPE, "PyYAML")

    assert registry.lookup(PACKAGE_TYPE, ["pyyaml"]) == pinned
    assert registry.get(PACKAGE_TYPE, "PYYAML") == RegistryEntry(pinned)
    assert registry.get(FILE_TYPE, "PyYAML") is None


# --- register (D12), row by row ----------------------------------------


#: (entry's sha256 or _ABSENT, given sha256, id number, stored sha256, INFO)
_REGISTER_ROWS: dict[str, tuple[str | None, str | None, int, str | None, bool]] = {
    "none-none": (_ABSENT, None, 1, None, False),
    "none-sha": (_ABSENT, _SHA_A, 1, _SHA_A, False),
    "nosha-none": (None, None, 7, None, False),
    "sha-none-kept": (_SHA_A, None, 7, _SHA_A, False),
    "equal": (_SHA_A, _SHA_A.upper(), 7, _SHA_A, False),
    "differs": (_SHA_A, _SHA_B, 8, _SHA_B, True),
    "nosha-gets-sha": (None, _SHA_B, 8, _SHA_B, True),
}


@pytest.mark.parametrize("row", list(_REGISTER_ROWS))
def test_register_table(row: str, caplog: pytest.LogCaptureFixture) -> None:
    entry_sha, given, number, stored, info = _REGISTER_ROWS[row]
    old_id = f"{_NS}#AIPackage-7"
    entries = (
        {} if entry_sha == _ABSENT else {(AI_PACKAGE_TYPE, "m"): (old_id, entry_sha)}
    )
    registry = make_registry(entries)

    with caplog.at_level("INFO", logger="pitloom.id_registry"):
        spdx_id = registry.register(AI_PACKAGE_TYPE, "m", sha256=given)

    assert spdx_id == f"{_NS}#AIPackage-{number}"
    assert registry.get(AI_PACKAGE_TYPE, "m") == RegistryEntry(spdx_id, stored)
    changed = [
        r.getMessage()
        for r in caplog.records
        if "ID registry: content changed" in r.getMessage()
    ]
    assert len(changed) == int(info)
    assert all(old_id in message for message in changed)


@pytest.mark.parametrize(
    ("entry_sha", "number", "info"),
    [
        (None, 7, "dataset d pin now gated by its SHA-256"),
        (_SHA_A, 8, f"content changed for d; minting a new spdxId (old: {_NS}#"),
    ],
    ids=["pin-adopts", "changed"],
)
def test_register_gives_a_hashless_dataset_pin_its_digest(
    caplog: pytest.LogCaptureFixture, entry_sha: str | None, number: int, info: str
) -> None:
    """A dataset pin made before its data existed keeps its id when ``-e``
    first sees the data (gated from then on, one INFO); a pin recording
    other content is a new id, as for every type."""
    held = {(DATASET_PACKAGE_TYPE, "d"): (f"{_NS}#DatasetPackage-7", entry_sha)}
    registry = make_registry(held, namespace=_NS)

    with caplog.at_level("INFO", logger="pitloom.id_registry"):
        spdx_id = registry.register(DATASET_PACKAGE_TYPE, "d", sha256=_SHA_B)

    assert spdx_id == f"{_NS}#DatasetPackage-{number}"
    assert registry.get(DATASET_PACKAGE_TYPE, "d") == RegistryEntry(spdx_id, _SHA_B)
    said = [m for m in caplog.messages if m.startswith("ID registry: ")]
    assert len(said) == 1 and said[0].startswith(f"ID registry: {info}")


def test_id_generate_e_pin_keeps_its_id_once_the_data_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sentimentdemo stage 0, run twice: ``-e`` of a dataset not yet
    written pins it hash-less; once it exists, the same ``-e`` keeps the
    id and records the digest."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_bytes(b"")
    argv = ["id", "generate", "src", "-e", "data/t.txt:dataset_DatasetPackage"]
    reg = tmp_path / DEFAULT_ID_REGISTRY_FILENAME

    def pinned() -> RegistryEntry | None:
        assert _run_cli(monkeypatch, [*argv, "-o", str(reg)]) == 0
        return IdRegistry.load(reg).get(DATASET_PACKAGE_TYPE, "data/t.txt")

    first = pinned()
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "t.txt").write_bytes(b"rows\n")
    second = pinned()

    assert first is not None and first.sha256 is None
    assert second is not None and second.spdx_id == first.spdx_id
    assert second.sha256 == hashlib.sha256(b"rows\n").hexdigest()
    assert pinned() == second


def test_register_never_erases_a_sha() -> None:
    registry = IdRegistry.new("x")
    first = registry.register(FILE_TYPE, "a.py", sha256=_SHA_A)

    for _ in range(2):
        assert registry.register(FILE_TYPE, "a.py") == first

    assert registry.get(FILE_TYPE, "a.py") == RegistryEntry(first, _SHA_A)


def test_register_encodes_a_user_given_type_prefix() -> None:
    """``loom id generate -e NAME:TYPE`` takes any TYPE; its id prefix is
    encoded, and the next mint for that type still finds the previous one."""
    registry = IdRegistry.new("test")

    first = registry.register("My Type#1", "a")
    second = registry.register("My Type#1", "b")

    assert first == f"{registry.namespace}#My%20Type%231-1"
    assert second == f"{registry.namespace}#My%20Type%231-2"


def test_register_same_name_different_types_gets_two_ids(tmp_path: Path) -> None:
    """A directory and a package sharing one name are two entries, before
    and after a save/load round trip."""
    registry = IdRegistry.new("demo-proj")
    dir_id = registry.register(FILE_TYPE, "demo")
    pkg_id = registry.register(PACKAGE_TYPE, "demo")

    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    registry.save(path)
    reloaded = IdRegistry.load(path)

    assert dir_id != pkg_id
    assert reloaded.lookup(FILE_TYPE, ["demo"]) == dir_id
    assert reloaded.lookup(PACKAGE_TYPE, ["demo"]) == pkg_id
    assert entries_of(reloaded) == entries_of(registry)


# --- has_name, id_count, root_dir --------------------------------------


def test_has_name_matches_any_type_and_a_canonical_package_name() -> None:
    registry = make_registry(
        {
            (PACKAGE_TYPE, "My_Model"): (f"{_NS}#Package-1", None),
            (FILE_TYPE, "data/t.txt"): (f"{_NS}#File-1", _SHA_A),
        }
    )

    assert registry.has_name("My_Model")
    assert registry.has_name("my-model")
    assert registry.has_name("data/t.txt")
    assert not registry.has_name("other")


def test_id_count_counts_distinct_ids_not_keys() -> None:
    registry = make_registry(
        {
            (FILE_TYPE, "src/p/a.py"): (f"{_NS}#File-1", _SHA_A),
            (FILE_TYPE, "p/a.py"): (f"{_NS}#File-1", _SHA_A),
            (PACKAGE_TYPE, "p"): (f"{_NS}#Package-1", None),
        }
    )

    assert len(registry.elements) == 3
    assert registry.id_count() == 2
    assert IdRegistry.new("x").id_count() == 0


def test_root_dir_cascade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "proj"
    (project / "build").mkdir(parents=True)
    monkeypatch.chdir(project)
    real = Path(os.path.realpath(project))

    assert IdRegistry.new("x").root_dir() == real
    in_build = IdRegistry.new("x", path=Path("build") / "reg.json")
    assert in_build.root_dir() == real / "build"
    rooted = IdRegistry.new(
        "x", path=Path("build") / "reg.json", project_root=Path(".")
    )
    assert rooted.root_dir() == real
    assert rooted.project_root == real
    rooted.project_root = Path(".")  # an assignment skips __init__'s realpath
    assert rooted.root_dir() == real


@pytest.mark.parametrize("which", ["name", "type"])
def test_register_refuses_a_lone_surrogate_and_stores_nothing(
    tmp_path: Path, which: str
) -> None:
    """A name that is not UTF-8 text could never be saved: refused at the
    boundary, escaped in the message, the registry left saveable."""
    registry = IdRegistry.new("x", tmp_path / "s.json", namespace=_NS)
    bad = "\udcff.txt"
    args = (FILE_TYPE, bad) if which == "name" else (bad, "a.txt")

    with pytest.raises(ValueError, match="lone surrogate") as excinfo:
        registry.register(*args)

    assert "\\udcff" in str(excinfo.value)
    assert f"ID registry: {'name' if which == 'name' else 'type name'} " in str(
        excinfo.value
    )
    assert not registry.elements
    registry.save()
