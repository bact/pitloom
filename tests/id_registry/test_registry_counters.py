# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Id counters (I8): a retired id is never minted again, for any key.

See also: test_registry_format.py (``id_counters`` in the file and its
``load()`` failures), test_persist_registry.py (the three-way replay),
test_registry_counters_cli.py (the order-matrix sequence through the CLI).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.id_registry import (
    FILE_TYPE,
    IdRegistry,
    RegistryEntry,
    persist_registry,
)
from pitloom.id_registry._counters import MAX_ID_NUMBER, RESERVE_CEILING, id_number
from tests.id_registry.shared import _write_sample_sbom
from tests.registry_helpers import make_registry

_NS = "https://example.org/x"
_DOC = "https://spdx.org/spdxdocs/demo-1"
_CI = spdx3.CreationInfo(
    specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
)


def _files(*pairs: tuple[str, str], sha256: str | None = None) -> spdx3.SHACLObjectSet:
    """An object set of ``software_File`` elements, ``(name, spdxId)``, each
    with *sha256* if given."""
    object_set = spdx3.SHACLObjectSet()
    for name, spdx_id in pairs:
        element = spdx3.software_File(spdxId=spdx_id, name=name, creationInfo=_CI)
        if sha256 is not None:
            element.verifiedUsing = [
                spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=sha256)
            ]
        object_set.add(element)
    return object_set


@pytest.mark.parametrize("saved", [False, True], ids=["memory", "saved"])
def test_a_retired_id_is_not_minted_again(tmp_path: Path, saved: bool) -> None:
    """The order-matrix repro: `id generate`, edit ``b.py``, `project` (its
    document id replaces ``b.py``'s entry), edit ``__init__.py``, `id
    generate`: ``__init__.py`` must not get ``b.py``'s first id."""
    path = tmp_path / "reg.json"
    registry = IdRegistry.new("x", path=path, namespace=_NS)
    registry.register(FILE_TYPE, "demo/__init__.py", sha256="1" * 64)
    retired = registry.register(FILE_TYPE, "demo/b.py", sha256="2" * 64)
    registry.harvest(_files(("demo/b.py", f"{_DOC}#File-2"), sha256="4" * 64))
    assert registry.id_count() == 2 and retired not in {
        e.spdx_id for e in registry.elements.values()
    }
    if saved:
        registry.save()
        registry = IdRegistry.load(path)

    minted = registry.register(FILE_TYPE, "demo/__init__.py", sha256="3" * 64)

    assert (retired, minted) == (f"{_NS}#File-2", f"{_NS}#File-3")


def test_counters_survive_save_and_load_and_only_grow(tmp_path: Path) -> None:
    path = tmp_path / "reg.json"
    registry = IdRegistry.new("x", path=path, namespace=_NS)
    for name in ("a", "b", "c"):
        registry.register(FILE_TYPE, name)
    registry.elements.clear()  # every id retired
    registry.save()
    first = path.read_bytes()

    loaded = IdRegistry.load(path)
    loaded.save()

    assert path.read_bytes() == first
    assert json.loads(first)["id_counters"] == {"File": 3}
    assert loaded.id_counters == registry.id_counters == {"File": 3}
    assert loaded.register(FILE_TYPE, "a") == f"{_NS}#File-4"


@pytest.mark.parametrize("higher", ["mine", "theirs"])
def test_rebase_merges_counters_by_maximum(tmp_path: Path, higher: str) -> None:
    """Two runs read one file; each mints, the later one saves through
    :func:`persist_registry`. The file keeps the larger counter, never
    the later run's."""
    path = tmp_path / "reg.json"
    IdRegistry.new("x", path=path, namespace=_NS).save()
    early, late = IdRegistry.load(path), IdRegistry.load(path)
    many, few = (late, early) if higher == "mine" else (early, late)
    for name in ("a", "b", "c"):
        many.register(FILE_TYPE, f"many/{name}")
    many.elements.clear()
    few.register(FILE_TYPE, "few")

    early.save()
    persist_registry(late, 1, True)

    assert json.loads(path.read_bytes())["id_counters"] == {"File": 3}
    assert IdRegistry.load(path).register(FILE_TYPE, "next") == f"{_NS}#File-4"


def test_a_run_that_mints_saves_its_counter_even_when_refused(
    tmp_path: Path,
) -> None:
    """Another run saved ``File-1`` first, so this run's ``b`` is not
    recorded (``another run saved ... first``), and a harvest replaced its
    ``File-2``: no entry of the file holds ``File-2``, the counter does."""
    path = tmp_path / "reg.json"
    IdRegistry.new("x", path=path, namespace=_NS).save()
    other, mine = IdRegistry.load(path), IdRegistry.load(path)
    other.register(FILE_TYPE, "a")
    other.save()
    mine.register(FILE_TYPE, "b")
    mine.register(FILE_TYPE, "c")
    mine.harvest(_files(("c", f"{_DOC}#File-9")))

    persist_registry(mine, 1, True)

    saved = IdRegistry.load(path)
    assert saved.id_counters == {"File": 2}
    assert saved.register(FILE_TYPE, "d") == f"{_NS}#File-3"


@pytest.mark.parametrize(
    ("spdx_id", "counters"),
    [
        (f"{_NS}#File-7", {"File": 7}),
        (f"{_DOC}#File-7", {}),
        (f"{_NS}#File-007", {}),
        (f"{_NS}#File-١", {}),
        (f"{_NS}#File-x", {}),
        (f"{_NS}#AIPackage-whisper-tiny", {}),
        (f"{_NS}#AIPackage-whisper-tiny-1", {"AIPackage-whisper-tiny": 1}),
        (f"{_NS}#File-{RESERVE_CEILING}", {"File": RESERVE_CEILING}),
        (f"{_NS}#File-{RESERVE_CEILING + 1}", {}),
        (f"{_NS}#File-{MAX_ID_NUMBER}", {}),
        (f"{_NS}#File-{MAX_ID_NUMBER + 1}", {}),
        (f"{_NS}#File-1{'0' * 4400}", {}),
        (f"{_NS}#-3", {}),
        (f"{_NS}#pkg/requests-1", {}),
        (f"{_NS}#a?b-1", {}),
        (f"{_NS}#a b-1", {}),
        (f"{_NS}#a#b-1", {}),
        (f"{_NS}#pkg%2frequests-1", {}),
        (f"{_NS}#pkg%2Frequests-1", {"pkg%2Frequests": 1}),
    ],
    ids=[
        "ns",
        "other-ns",
        "leading-zero",
        "non-ascii-digit",
        "no-number",
        "name-suffix",
        "name-then-number",
        "ceiling",
        "over-ceiling",
        "max",
        "over-max",
        "long",
        "no-prefix",
        "slash-prefix",
        "query-prefix",
        "space-prefix",
        "hash-prefix",
        "lower-escape-prefix",
        "upper-escape-prefix",
    ],
)
def test_harvest_reserves_an_id_of_the_registry_namespace(
    tmp_path: Path, spdx_id: str, counters: dict[str, int]
) -> None:
    """A stored id in the registry's namespace raises its prefix's counter
    up to :data:`RESERVE_CEILING`; any other id (another namespace, not a
    mint's shape, a prefix no mint writes, a foreign number above the
    ceiling) leaves them, and the registry saves a file that loads back."""
    registry = IdRegistry(namespace=_NS)

    new_ids, changed = registry.harvest(_files(("a.py", spdx_id)))
    registry.save(tmp_path / "reg.json")

    assert (new_ids, changed) == (1, True)
    assert registry.id_counters == counters
    assert IdRegistry.load(tmp_path / "reg.json").id_counters == counters


def test_a_foreign_id_above_the_ceiling_never_disables_minting() -> None:
    """A held id above :data:`RESERVE_CEILING` reserves nothing, yet a mint
    reaching it skips it: mints go on, never handing out a held id."""
    registry = IdRegistry(namespace=_NS)
    registry.harvest(_files(("a.py", f"{_NS}#File-{MAX_ID_NUMBER}")))
    assert registry.register(FILE_TYPE, "b.py") == f"{_NS}#File-1"

    registry.harvest(_files(("c.py", f"{_NS}#File-{RESERVE_CEILING + 1}")))
    registry.id_counters["File"] = RESERVE_CEILING

    assert registry.register(FILE_TYPE, "d.py") == f"{_NS}#File-{RESERVE_CEILING + 2}"


def test_register_refuses_a_type_with_no_id_prefix() -> None:
    """``""`` gives no prefix: an id ``ns#-1`` and a counter the file
    cannot hold. Refused, with nothing changed."""
    registry = IdRegistry(namespace=_NS)

    with pytest.raises(ValueError, match="^ID registry: no id prefix"):
        registry.register("", "x")

    assert (registry.elements, registry.id_counters) == ({}, {})


def _with_counters(path: Path, counters: dict[str, int]) -> None:
    data = json.loads(path.read_bytes())
    data["id_counters"] = counters
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("how", ["mint", "harvest", "import", "load"])
def test_a_held_id_counts_even_without_a_counter(tmp_path: Path, how: str) -> None:
    """An id set into the table directly, or held by a file whose counter
    is lower, is reserved before a mint, or a harvest or import that
    replaces its entry."""
    held = (FILE_TYPE, "src/pkg/train.py")
    registry = make_registry({held: (f"{_NS}#File-6", None)}, namespace=_NS)
    registry.id_counters.clear()
    if how == "load":
        registry.save(tmp_path / "reg.json")
        _with_counters(tmp_path / "reg.json", {"File": 2})
        registry = IdRegistry.load(tmp_path / "reg.json")
    if how in ("harvest", "load"):
        registry.harvest(_files((held[1], f"{_DOC}#File-1")))
    if how == "import":
        _write_sample_sbom(tmp_path / "sbom.json")
        registry.import_sbom(tmp_path / "sbom.json")
    assert how == "mint" or registry.get(*held) != RegistryEntry(f"{_NS}#File-6")

    assert registry.register(FILE_TYPE, "b") == f"{_NS}#File-7"


def test_counters_never_read_below_a_held_id(tmp_path: Path) -> None:
    """Loading, or re-reading a file another run left with a lower counter
    than its entries, reads the counter as the held id's number; the
    re-read registry then differs from its file, so it is saved."""
    path = tmp_path / "reg.json"
    make_registry({(FILE_TYPE, "a"): (f"{_NS}#File-6", None)}, namespace=_NS, path=path)
    _with_counters(path, {})
    never_read = IdRegistry(namespace=_NS, path=path)

    assert IdRegistry.load(path).id_counters == {"File": 6}
    assert never_read.rebase().pending
    assert never_read.id_counters == {"File": 6}


def test_mint_refuses_past_the_largest_number() -> None:
    registry = IdRegistry(namespace=_NS, id_counters={"File": MAX_ID_NUMBER})

    with pytest.raises(ValueError, match="^ID registry: no File id left to mint"):
        registry.register(FILE_TYPE, "a")

    assert not registry.elements


def test_id_number_needs_the_namespace_then_a_hash() -> None:
    """A namespace that is a prefix of another is not that namespace."""
    assert id_number(_NS, f"{_NS}2#File-1") is None
    assert id_number(_NS, f"{_NS}#File-1") == ("File", 1)


@pytest.mark.parametrize(
    "counters",
    [{"a/b": 1}, {"File": 0}, {"File": MAX_ID_NUMBER + 1}],
    ids=["prefix", "zero", "over-max"],
)
def test_save_refuses_a_counter_the_loader_rejects(
    tmp_path: Path, counters: dict[str, int]
) -> None:
    """A counter set through the library API is checked as ``load()``
    checks it: no save writes a file that does not load back."""
    registry = IdRegistry(namespace=_NS, id_counters=counters)

    with pytest.raises(ValueError, match="^ID registry file .*'id_counters' "):
        registry.save(tmp_path / "reg.json")

    assert not (tmp_path / "reg.json").exists()
