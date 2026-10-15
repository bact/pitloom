# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A loom run's minted fallback ids never take an id the registry holds,
nor one another's, when the registry already numbers ``File-1``,
``File-2``, ``DatasetPackage-1`` for other paths: a fallback id lives in
its own per-run namespace, so only its ``#File-N`` suffix can repeat.

See also: tests/core/test_loom_dataset.py (dataset elements at large).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.id_registry import DATASET_PACKAGE_TYPE, FILE_TYPE
from tests.registry_helpers import make_registry

from .conftest import _relationships

_NS = "https://spdx.org/spdxdocs/test-1"
_PINNED = b"pinned\n"
_SCRIPT = b"print()\n"


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize("script_pinned", [False, True], ids=["new", "pinned"])
def test_minted_ids_are_distinct_from_registry_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script_pinned: bool
) -> None:
    """``data/new.txt`` (file and package) and, unpinned, the script are
    minted; ``data/a.txt`` and ``data/b.txt`` hit. Every element carries a
    registry id only when the registry pins it for that element's own key,
    no two elements share an id, and each ``contains`` and ``generates``
    edge points at the element of the expected name."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    for name in ("a", "b"):
        (tmp_path / "data" / f"{name}.txt").write_bytes(name.encode() + _PINNED)
    (tmp_path / "data" / "new.txt").write_bytes(b"new\n")
    (tmp_path / "train.py").write_bytes(_SCRIPT)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: "train.py"
    )
    pinned: dict[tuple[str, str], tuple[str, str | None]] = {
        (FILE_TYPE, "data/a.txt"): (f"{_NS}#File-1", _sha(b"a" + _PINNED)),
        (FILE_TYPE, "data/b.txt"): (f"{_NS}#File-2", _sha(b"b" + _PINNED)),
        (DATASET_PACKAGE_TYPE, "data/a.txt"): (f"{_NS}#DatasetPackage-1", None),
        (DATASET_PACKAGE_TYPE, "data/b.txt"): (f"{_NS}#DatasetPackage-2", None),
    }
    if script_pinned:
        pinned[(FILE_TYPE, "train.py")] = (f"{_NS}#File-3", _sha(_SCRIPT))
    registry = make_registry(pinned, project_root=tmp_path)
    output = tmp_path / "out.json"

    with loom.run(output, id_registry=registry):
        loom.add_input_dataset("data/a.txt")
        loom.add_input_dataset("data/b.txt")
        loom.add_output_dataset("data/new.txt")

    document = json.loads(output.read_text(encoding="utf-8"))
    graph: list[dict[str, Any]] = document["@graph"]
    ids = [e["spdxId"] for e in graph if "spdxId" in e]
    assert len(ids) == len(set(ids))
    owner = {spdx_id: key for key, (spdx_id, _) in pinned.items()}
    named = {
        e["spdxId"]: (e["type"], e["name"])
        for e in graph
        if e["type"] in (FILE_TYPE, DATASET_PACKAGE_TYPE)
    }
    assert len(named) == 7
    assert {i: k for i, k in named.items() if i in owner} == owner
    minted = [k for i, k in named.items() if i not in owner]
    # the reported shape: a minted id repeats a registry id's suffix
    suffixes = {i.rsplit("#", 1)[1] for i in named}
    assert len(suffixes) < len(named)
    assert sorted(minted) == sorted(
        [(FILE_TYPE, "data/new.txt"), (DATASET_PACKAGE_TYPE, "data/new.txt")]
        + ([] if script_pinned else [(FILE_TYPE, "train.py")])
    )
    edges = sorted(
        (r["relationshipType"], named[r["from"]], [named[t] for t in r["to"]])
        for r in _relationships(graph)
        if r["relationshipType"] in ("contains", "generates")
    )
    new_package = (DATASET_PACKAGE_TYPE, "data/new.txt")
    assert edges == [
        ("contains", (DATASET_PACKAGE_TYPE, p), [(FILE_TYPE, p)])
        for p in ("data/a.txt", "data/b.txt", "data/new.txt")
    ] + [("generates", (FILE_TYPE, "train.py"), [new_package])]
