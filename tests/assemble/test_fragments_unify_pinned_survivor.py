# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""When fragments carry the same bytes, the survivor is the registry-pinned id.

A minted id's namespace belongs to its one fragment; a pinned id's is shared
by every fragment that uses the registry. Merge ranks an id by the number of
sources (base document and fragments) holding an id in its namespace, counted
over all fragments before the first merge, so the survivor does not depend on
fragment order. A tie keeps the earlier element, and
every reference to the other id follows the survivor.

See also: tests/core/test_fragments_merge_id_types.py (type clash) and
tests/assemble/test_fragments_unify_hash_conflict.py (digest conflict).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import FragmentConfig
from tests._license_graph import fragment_graph, write_fragment
from tests.core.test_fragments_merge_id_types import _base

_REG = "https://spdx.org/spdxdocs/reg"
_FILE = "software_File"
_DATASET = "dataset_DatasetPackage"


def _loc(n: int) -> str:
    return f"https://spdx.org/spdxdocs/loc-{n}"


def _digest(value: str) -> list[dict[str, str]]:
    return [{"type": "Hash", "algorithm": "sha256", "hashValue": value * 64}]


def _entry(spec: str) -> tuple[str, str]:
    """``"<id>"`` or ``"<id>|<type>"`` -> (id, type)."""
    spdx_id, _, type_name = spec.partition("|")
    return spdx_id, type_name or _FILE


def _fragment(index: int, specs: list[str]) -> list[dict[str, Any]]:
    """Fragment *index*: each spec is a file of the shared bytes ``a``; a
    filler (different bytes) in the pinned namespace makes it shared; a
    relationship from the filler references every spec."""
    entries = [_entry(s) for s in specs]
    elements: list[dict[str, Any]] = [
        {
            "type": type_name,
            "spdxId": spdx_id,
            "name": f"n{index}",
            "verifiedUsing": _digest("a"),
            **({"dataset_datasetType": ["text"]} if type_name == _DATASET else {}),
        }
        for spdx_id, type_name in entries
    ]
    filler = f"{_REG}#Filler-{index}"
    elements.append(
        {
            "type": _FILE,
            "spdxId": filler,
            "name": f"filler{index}",
            "verifiedUsing": _digest(str(index)),
        }
    )
    elements.append(
        {
            "type": "Relationship",
            "spdxId": f"{_loc(index)}#R",
            "from": filler,
            "to": [spdx_id for spdx_id, _ in entries],
            "relationshipType": "contains",
        }
    )
    return elements


def _merge_all(
    tmp: Path, fragments: list[list[str]], reverse: bool
) -> dict[str, dict[str, Any]]:
    """Merge the *fragments* (reversed when *reverse*) into a base holding a
    pinned-namespace file; return the merged elements by id."""
    base = _base(
        [
            {
                "type": _FILE,
                "spdxId": f"{_REG}#Base",
                "name": "base",
                "verifiedUsing": _digest("f"),
            }
        ]
    )
    configs = []
    order = list(enumerate(fragments))
    for i, specs in reversed(order) if reverse else order:
        path = f"f{i}.spdx3.json"
        write_fragment(tmp / path, fragment_graph(_fragment(i, specs), ns=_loc(i)))
        configs.append(FragmentConfig(path=path))
    merge_fragments(tmp, configs, base)
    graph = json.loads(base.to_json(pretty=True))["@graph"]
    return {e["spdxId"]: e for e in graph if "spdxId" in e}


def _shared_files(
    merged: dict[str, dict[str, Any]], types: tuple[str, ...]
) -> set[str]:
    """Ids of the elements carrying the shared bytes."""
    return {
        i
        for i, e in merged.items()
        if e["type"] in types
        and e.get("verifiedUsing", [{}])[0].get("hashValue") == "a" * 64
    }


_P1, _P2 = f"{_REG}#File-8", f"{_REG}#File-9"
_L1, _L2, _L3 = f"{_loc(0)}#File-1", f"{_loc(1)}#File-1", f"{_loc(2)}#File-1"


@pytest.mark.parametrize(
    ("fragments", "expected"),
    [
        ([[_L1], [_P1]], _P1),
        ([[_P1], [_L2]], _P1),
        ([[_L1], [_P1], [_L3]], _P1),
        ([[_L1], [_L2], [_P1]], _P1),
    ],
    ids=["pinned-later", "pinned-first", "three-way-middle", "three-way-last"],
)
@pytest.mark.parametrize("reverse", [False, True], ids=["fwd", "rev"])
def test_pinned_id_survives_in_any_order(
    fragments: list[list[str]],
    expected: str,
    reverse: bool,
    tmp_path: Path,
) -> None:
    merged = _merge_all(tmp_path, fragments, reverse)
    assert _shared_files(merged, (_FILE,)) == {expected}
    # Every relationship that named a loser now names the survivor.
    targets = {
        t
        for e in merged.values()
        if e["type"] == "Relationship"
        for t in e["to"]
        if "#File-" in t
    }
    assert targets == {expected}


@pytest.mark.parametrize(
    ("fragments", "first", "last"),
    [
        ([[_L1], [_L2]], _L1, _L2),
        ([[_P1], [_P2]], _P1, _P2),
    ],
    ids=["none-pinned", "both-pinned"],
)
@pytest.mark.parametrize("reverse", [False, True], ids=["fwd", "rev"])
def test_a_tie_keeps_the_earlier_element(
    fragments: list[list[str]],
    first: str,
    last: str,
    reverse: bool,
    tmp_path: Path,
) -> None:
    """Equal rank: the earlier fragment's id, as before the ranking."""
    merged = _merge_all(tmp_path, fragments, reverse)
    assert _shared_files(merged, (_FILE,)) == {last if reverse else first}


def test_no_fold_across_types(tmp_path: Path) -> None:
    merged = _merge_all(tmp_path, [[_L1], [f"{_P1}|{_DATASET}"]], False)
    assert _shared_files(merged, (_FILE, _DATASET)) == {_L1, _P1}
