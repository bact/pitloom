# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A digest conflict on an id skips only the by-id fold.

The same bytes held under another id still unify (SHA-256 criterion); only
an element with no other match is renamed apart, with one warning. A
promoted survivor keeps its non-reader status and recorded registry key,
and two fragments of one relative path under different base directories
are two sources.

See also: tests/assemble/test_fragments_unify_hash_conflict.py and
tests/assemble/test_fragments_unify_pinned_survivor.py.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble.spdx3._fragments_unify import _MergeIndex
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter
from tests._license_graph import fragment_graph, write_fragment
from tests.assemble.test_fragments_unify_pinned_survivor import (
    _FILE,
    _REG,
    _digest,
    _loc,
)
from tests.core.test_fragments_merge_id_types import _MAIN, _base

_X, _Y = f"{_MAIN}#X", f"{_MAIN}#Y"


def _file(spdx_id: str, name: str, digest: str) -> dict[str, Any]:
    return {
        "type": _FILE,
        "spdxId": spdx_id,
        "name": name,
        "verifiedUsing": _digest(digest),
    }


def _run(
    tmp: Path,
    base: list[dict[str, Any]],
    fragments: list[list[dict[str, Any]]],
    caplog: pytest.LogCaptureFixture,
    exporter: Spdx3JsonExporter | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    exporter = exporter or _base(base)
    configs = []
    for i, elements in enumerate(fragments):
        path = f"f{i}.spdx3.json"
        write_fragment(tmp / path, fragment_graph(elements, ns=_loc(i)))
        configs.append(FragmentConfig(path=path))
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        merge_fragments(tmp, configs, exporter)
    graph = json.loads(exporter.to_json(pretty=True))["@graph"]
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    return {e["spdxId"]: e for e in graph if "spdxId" in e}, warnings


def _files(merged: dict[str, dict[str, Any]]) -> dict[str, str]:
    """File id -> first digest character."""
    return {
        i: e["verifiedUsing"][0]["hashValue"][0]
        for i, e in merged.items()
        if e["type"] == _FILE
    }


@pytest.mark.parametrize("reverse", [False, True], ids=["fwd", "rev"])
def test_two_fragments_with_the_same_conflicting_bytes_share_one_new_element(
    reverse: bool, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fragments = [
        [_file(_X, "x", "b"), _file(f"{_loc(i)}#Other", f"o{i}", str(i))]
        for i in range(2)
    ]
    merged, warnings = _run(
        tmp_path,
        [_file(_X, "x", "a")],
        fragments[::-1] if reverse else fragments,
        caplog,
    )
    shared = {i: d for i, d in _files(merged).items() if d in "ab"}
    assert shared == {_X: "a", f"{_MAIN}#File-1": "b"}
    assert len(warnings) == 1
    assert "different SHA256 hash" in warnings[0]


def test_same_bytes_under_another_id_fold_instead_of_a_new_element(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fragment = [_file(_X, "y", "b")]
    base = [_file(_X, "x", "a"), _file(_Y, "y", "b")]
    merged, warnings = _run(tmp_path, base, [fragment], caplog)
    assert _files(merged) == {_X: "a", _Y: "b"}
    assert not [w for w in warnings if "SHA" in w or "shares spdxId" in w]


@pytest.mark.parametrize("own", [False, True], ids=["moved", "own-kept"])
def test_promoted_survivor_keeps_its_registry_records(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, own: bool
) -> None:
    """The promoted survivor stays a non-reader, and the key and registry
    hash (a Git LFS pointer's ``oid``) its old id recorded move to its new
    id, unless that id recorded its own."""
    old, pinned = f"{_loc(9)}#File-1", f"{_REG}#File-8"
    exporter = _base([_file(old, "p", "c")])
    exporter.registry_non_readers.add(old)
    exporter.registry_keys[old] = (_FILE, "src/p")
    exporter.registry_hashes[old] = "1" * 64
    if own:
        exporter.registry_keys[pinned] = (_FILE, "own")
        exporter.registry_hashes[pinned] = "2" * 64
    fragments = [
        [_file(pinned, "p", "c"), _file(f"{_REG}#Filler", "f", "d")],
        [_file(f"{_REG}#Filler2", "g", "e")],
    ]
    merged, _ = _run(tmp_path, [], fragments, caplog, exporter)
    assert pinned in merged and old not in merged
    assert exporter.registry_non_readers == {pinned}
    assert exporter.registry_keys == {pinned: (_FILE, "own" if own else "src/p")}
    assert exporter.registry_hashes == {pinned: ("2" if own else "1") * 64}


def test_same_relative_path_under_two_base_dirs_is_two_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources: list[str] = []
    real = _MergeIndex.note_source

    def spy(self: _MergeIndex, source: str, objects: Any) -> None:
        sources.append(source)
        real(self, source, objects)

    monkeypatch.setattr(_MergeIndex, "note_source", spy)
    for name in ("a", "b"):
        write_fragment(
            tmp_path / name / "f.json",
            fragment_graph([_file(f"{_REG}#F-{name}", name, name)], ns=_loc(0)),
        )
    merge_fragments(
        tmp_path,
        [FragmentConfig(path="f.json", base_dir=str(tmp_path / n)) for n in "ab"],
        _base([]),
    )
    assert len(set(sources)) == 3
