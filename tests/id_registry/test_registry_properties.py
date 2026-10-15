# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Seeded random runs over the registry's public API: whatever ids an SBOM
hands over, a saved registry loads back; whatever runs share one file, no
id is saved under two keys and no counter goes down.

See also: test_registry_counters.py (each id shape, one case each),
test_persist_registry.py (each replay case, one case each).
"""

from __future__ import annotations

import json
import random
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
from pitloom.id_registry._counters import MAX_ID_NUMBER, RESERVE_CEILING
from pitloom.id_registry._persist import Table, replay_changes

_NS = "https://example.org/ns"
_AGENT = f"{_NS}#Agent-1"
_CI = spdx3.CreationInfo(
    specVersion="3.0.1",
    created=datetime(2026, 1, 1, tzinfo=timezone.utc),
    createdBy=[_AGENT],
)
# Prefixes a mint never writes next to ones it does.
_PREFIXES = ("File", "pkg/requests", "a?b", "a b", "a#b", "x%2fy", "x%2Fy", "", "é")
_NUMBERS = ("1", "7", "007", str(RESERVE_CEILING + 1), str(MAX_ID_NUMBER), "x")
_TYPES = (FILE_TYPE, "ai_AIPackage", "x_a/b", "y_c d")


def _random_ids(rng: random.Random, count: int) -> list[str]:
    return sorted(
        {f"{_NS}#{rng.choice(_PREFIXES)}-{rng.choice(_NUMBERS)}" for _ in range(count)}
    )


def _files(names_and_ids: list[tuple[str, str]]) -> spdx3.SHACLObjectSet:
    object_set = spdx3.SHACLObjectSet()
    for name, spdx_id in names_and_ids:
        object_set.add(spdx3.software_File(spdxId=spdx_id, name=name, creationInfo=_CI))
    return object_set


def _write_sbom(path: Path, object_set: spdx3.SHACLObjectSet) -> None:
    object_set.add(spdx3.SpdxDocument(spdxId=_NS, name="doc", creationInfo=_CI))
    object_set.add(spdx3.Agent(spdxId=_AGENT, name="agent", creationInfo=_CI))
    with open(path, "wb") as f:
        spdx3.JSONLDSerializer().write(object_set, f)


@pytest.mark.parametrize("seed", range(12))
def test_any_harvested_or_imported_id_saves_a_file_that_loads(
    tmp_path: Path, seed: int
) -> None:
    rng = random.Random(seed)
    registry = IdRegistry.new("x", path=tmp_path / "reg.json", namespace=_NS)
    for step in range(6):
        op = rng.choice(("harvest", "import", "register"))
        ids = _random_ids(rng, 4)
        named = [(f"n{step}-{i}", spdx_id) for i, spdx_id in enumerate(ids)]
        if op == "harvest":
            registry.harvest(_files(named))
        elif op == "import":
            _write_sbom(tmp_path / "in.json", _files(named))
            registry.import_sbom(tmp_path / "in.json")
        else:
            registry.register(rng.choice(_TYPES), f"r{step}")
        registry.save()

        loaded = IdRegistry.load(registry.path or tmp_path)

        assert (loaded.elements, loaded.id_counters) == (
            registry.elements,
            registry.id_counters,
        )


def _one_key_per_id(entries: list[str], where: str) -> None:
    assert len(entries) == len(set(entries)), where


def _edited(rng: random.Random, table: Table) -> Table:
    """*table* after one to four harvest-like edits: a key takes an id (the
    key that held it lets go) or is dropped."""
    out = dict(table)
    for _ in range(rng.randint(1, 4)):
        key = (FILE_TYPE, rng.choice("abcd"))
        spdx_id = f"{_NS}#File-{rng.randint(1, 4)}"
        for holder in [k for k, entry in out.items() if entry.spdx_id == spdx_id]:
            del out[holder]
        if rng.random() < 0.8:
            out[key] = RegistryEntry(spdx_id)
        else:
            out.pop(key, None)
    return out


def test_a_replay_never_puts_one_id_under_two_keys() -> None:
    """I4 over random three-way tables: each merged key holds *mine*'s or
    *theirs*' entry, and no two hold one id."""
    for seed in range(400):
        rng = random.Random(seed)
        base = _edited(rng, {})
        mine, theirs = _edited(rng, base), _edited(rng, base)

        merged, _ = replay_changes(base, mine, theirs)

        _one_key_per_id([e.spdx_id for e in merged.values()], f"seed {seed}")
        assert all(e in (mine.get(k), theirs.get(k)) for k, e in merged.items())


def _share_one_file(path: Path, seed: int) -> None:
    rng = random.Random(seed)
    IdRegistry.new("x", path=path, namespace=_NS).save()
    runs = [IdRegistry.load(path) for _ in range(3)]
    counters: dict[str, int] = {}
    for _ in range(40):
        index = rng.randrange(len(runs))
        run = runs[index]
        op = rng.choice(
            ("register", "harvest", "harvest", "persist", "persist", "load")
        )
        if op == "register":
            run.register(FILE_TYPE, rng.choice("abcde"))
        elif op == "harvest":
            pool = sorted({e.spdx_id for e in IdRegistry.load(path).elements.values()})
            pool += [f"{_NS}#File-{n}" for n in range(1, 6)]
            names = rng.sample("abcde", 2)
            run.harvest(_files([(name, rng.choice(pool)) for name in names]))
        elif op == "persist":
            persist_registry(run, 1, True)
            data = json.loads(path.read_bytes())
            entries = [e for names in data["elements"].values() for e in names.values()]
            _one_key_per_id([e["spdxId"] for e in entries], f"seed {seed}")
            saved = data["id_counters"]
            assert all(saved.get(k, 0) >= v for k, v in counters.items()), seed
            counters = saved
        else:
            runs[index] = IdRegistry.load(path)


def test_runs_sharing_one_file_never_save_an_id_twice(tmp_path: Path) -> None:
    """Three runs read one file at random times, mint, harvest ids another
    run saved, and save through :func:`persist_registry`: no id under two
    keys, no counter lowered (no src-layout alias here: names hold no
    ``/`` and no hash)."""
    for seed in range(60):
        _share_one_file(tmp_path / f"reg-{seed}.json", seed)
