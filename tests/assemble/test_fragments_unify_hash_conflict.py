# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Same-id elements with conflicting digests are not folded.

Folding them would leave one element with two SHA-256 values: the content
differs, so they are two artefacts. The fragment's element is kept apart
under a new id with one ``WARNING:``, the mechanism a type clash already
uses (D11); the earlier element keeps the id. Case-only and
cross-algorithm differences, and an element with no digest, still fold.

See also: tests/core/test_fragments_merge_id_types.py (type clash).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import _fragments_hashes as hashes
from pitloom.export.spdx3_json import sha256_hash
from tests.core.test_fragments_merge_id_types import (
    _DATASET,
    _FILE,
    _MAIN,
    _SHARED,
    _by_id,
    _element,
    _merge,
)

_A, _B = "a" * 64, "b" * 64


def _hashes(*pairs: tuple[str, str]) -> list[dict[str, Any]]:
    return [{"type": "Hash", "algorithm": alg, "hashValue": val} for alg, val in pairs]


def _with(type_name: str, *pairs: tuple[str, str], name: str = "data") -> Any:
    element = _element(type_name, _SHARED)
    element["name"] = name
    if pairs:
        element["verifiedUsing"] = _hashes(*pairs)
    return element


_SHA = "sha256"


@pytest.mark.parametrize(
    ("type_name", "base_name", "frag_name"),
    [
        (_FILE, "data", "data"),
        (_FILE, "a.txt", "b.txt"),
        (_DATASET, "data", "data"),
    ],
    ids=["file-same-name", "file-diff-name", "dataset"],
)
def test_conflicting_sha256_keeps_both_with_one_warning(
    type_name: str,
    base_name: str,
    frag_name: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    base = [_with(type_name, (_SHA, _A), name=base_name)]
    fragment = [_with(type_name, (_SHA, _B), name=frag_name)]
    merged, warnings = _merge(tmp_path, base, fragment, caplog)
    new_id = f"{_MAIN}#{type_name.partition('_')[2]}-1"
    by_id = _by_id(merged)
    assert [h["hashValue"] for h in by_id[_SHARED]["verifiedUsing"]] == [_A]
    assert [h["hashValue"] for h in by_id[new_id]["verifiedUsing"]] == [_B]
    assert warnings == [
        f"Merge: {type_name} {frag_name!r} shares spdxId {_SHARED} with a "
        f"{type_name} of a different SHA256 hash; keeping both, it gets new "
        f"id {new_id}."
    ]


@pytest.mark.parametrize(
    ("base_hashes", "frag_hashes"),
    [
        ([(_SHA, _A)], [(_SHA, _A.upper())]),
        ([(_SHA, _A)], [("sha512", "c" * 128)]),
        ([(_SHA, _A)], []),
        ([], [(_SHA, _A)]),
        ([(_SHA, _A), (_SHA, _B)], [(_SHA, _B)]),
    ],
    ids=["case", "other-algorithm", "frag-absent", "base-absent", "overlap"],
)
def test_non_conflicting_digests_still_fold(
    base_hashes: list[tuple[str, str]],
    frag_hashes: list[tuple[str, str]],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    base = [_with(_FILE, *base_hashes)]
    fragment = [_with(_FILE, *frag_hashes)]
    merged, warnings = _merge(tmp_path, base, fragment, caplog)
    assert warnings == []
    assert [k for k, e in _by_id(merged).items() if e["type"] == _FILE] == [_SHARED]


def test_second_conflicting_fragment_element_gets_the_next_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base = [_with(_FILE, (_SHA, _A))]
    fragment = [
        _with(_FILE, (_SHA, _B)),
        {**_with(_FILE, (_SHA, "c" * 64), name="o"), "spdxId": _SHARED + "-x"},
    ]
    merged, warnings = _merge(tmp_path, base, fragment, caplog)
    assert len(warnings) == 1
    assert f"{_MAIN}#File-1" in _by_id(merged)


def test_hash_conflict_is_deterministic_and_algorithm_ordered() -> None:
    def file(*pairs: tuple[str, str]) -> spdx3.software_File:
        obj = spdx3.software_File(name="f")
        obj.verifiedUsing = [
            spdx3.Hash(algorithm=getattr(spdx3.HashAlgorithm, alg), hashValue=v)
            for alg, v in pairs
        ]
        return obj

    one = file(("sha512", "1"), (_SHA, _A))
    two = file(("sha512", "2"), (_SHA, _B))
    assert hashes.hash_conflict(one, two) == _SHA
    assert hashes.hash_conflict(two, one) == _SHA
    assert hashes.hash_conflict(one, spdx3.Agent(name="a")) is None
    empty = file((_SHA, ""))
    assert hashes.hash_conflict(one, empty) is None
    assert sha256_hash(_A).hashValue == _A
