# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for one ``dataset_DatasetPackage`` per name per loom run, and for
``loom.run()`` leaving no active run behind when it fails to write.

See also:
- :mod:`tests.core.test_loom_registry` for registry consultation.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.id_registry import DATASET_PACKAGE_TYPE, FILE_TYPE
from tests.registry_helpers import make_registry

from .conftest import _relationships

_NS = "https://spdx.org/spdxdocs/test-proj-fixed"


def _declare_twice(first: str, second: str) -> None:
    """Declare ``f.txt`` through two ``loom`` calls (names as in ``_CALLS``)."""
    for call in (first, second):
        if call == "input":
            loom.add_input_dataset("f.txt")
        elif call == "output":
            loom.add_output_dataset("f.txt")
        elif call == "train":
            loom.add_dataset("f.txt")
        else:
            loom.add_validation_dataset("f.txt")


@pytest.mark.parametrize(
    ("first", "second", "wanted"),
    [
        ("input", "train", {"trainedOn"}),
        ("input", "output", set()),
        ("train", "train", {"trainedOn"}),
        ("train", "validate", {"trainedOn", "testedOn"}),
    ],
    ids=["input-train", "input-output", "train-train", "train-validate"],
)
def test_same_dataset_name_twice_is_one_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    first: str,
    second: str,
    wanted: set[str],
) -> None:
    """The same name and content declared twice in one run is one registered
    package and one file, with the roles of both declarations on it; no
    collision warning, no relationship repeated or from a package to itself.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "f.txt").write_bytes(b"data\n")
    digest = hashlib.sha256(b"data\n").hexdigest()
    registry = make_registry(
        {
            (FILE_TYPE, "f.txt"): (f"{_NS}#File-1", digest),
            (DATASET_PACKAGE_TYPE, "f.txt"): (f"{_NS}#DatasetPackage-1", None),
        },
        namespace=_NS,
    )
    out = tmp_path / "frag.json"
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(out, id_registry=registry):
            loom.set_model("m")
            _declare_twice(first, second)

    assert not [r for r in caplog.records if "registered for both" in r.message]
    graph: list[dict[str, Any]] = json.loads(out.read_text())["@graph"]
    (package,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
    assert package["spdxId"] == f"{_NS}#DatasetPackage-1"
    files = [e for e in graph if e["type"] == "software_File"]
    (data_file,) = [e for e in files if e["name"] == "f.txt"]
    assert data_file["spdxId"] == f"{_NS}#File-1"
    rels = _relationships(graph)
    keys = [(r["relationshipType"], r["from"], tuple(r["to"])) for r in rels]
    assert len(keys) == len(set(keys))
    assert all(
        r["from"] != package["spdxId"] or package["spdxId"] not in r["to"] for r in rels
    )
    kinds = {r["relationshipType"] for r in rels if package["spdxId"] in r["to"]}
    assert {"trainedOn", "testedOn"} & kinds == wanted


def test_same_name_other_dataset_type_keeps_both_kinds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A second ``dataset_type`` for the same package is added, in
    declaration order, not dropped."""
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "frag.json"
    with loom.run(out):
        loom.add_input_dataset("x", dataset_type="text")
        loom.add_dataset("x", dataset_type="image")
        loom.add_dataset("x", dataset_type="image")
    graph = json.loads(out.read_text())["@graph"]
    (package,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
    assert package["dataset_datasetType"] == ["text", "image"]


@pytest.mark.parametrize(
    ("first", "second", "count"),
    [(["a"], ["b"], 2), (["a"], ["a"], 1), (None, ["a"], 2), (["a"], None, 2)],
    ids=["union", "same", "all-first", "all-second"],
)
def test_output_dataset_merges_declared_sources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    first: list[str] | None,
    second: list[str] | None,
    count: int,
) -> None:
    """One output declared twice: the sources are the union, without
    repeats; ``None`` (every input) wins over a list."""
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "frag.json"
    with loom.run(out):
        loom.add_input_dataset("a")
        loom.add_input_dataset("b")
        loom.add_output_dataset("o", input_datasets=first)
        loom.add_output_dataset("o", input_datasets=second)
    graph = json.loads(out.read_text())["@graph"]
    (rel,) = [r for r in _relationships(graph) if r["relationshipType"] == "hasInput"]
    assert len(rel["to"]) == count


def _no_active_run_raises() -> None:
    with pytest.raises(RuntimeError, match="No active loom.run"):
        loom.add_dataset("x")


def test_failed_finalize_leaves_no_active_run(tmp_path: Path) -> None:
    """A fragment that cannot be written still ends the run: a later call
    outside any run raises instead of recording into the dead one."""
    target = tmp_path / "is_a_dir"
    target.mkdir()
    with pytest.raises(OSError):
        with loom.run(target):
            loom.add_dataset("x")
    _no_active_run_raises()


def test_nested_run_restores_outer_after_failed_inner(tmp_path: Path) -> None:
    """A failing inner run hands back the outer one."""
    target = tmp_path / "is_a_dir"
    target.mkdir()
    out = tmp_path / "outer.json"
    with loom.run(out):
        with pytest.raises(OSError):
            with loom.run(target):
                pass
        loom.add_dataset("outer-data")
    assert "outer-data" in out.read_text()
    _no_active_run_raises()


def test_recursive_decorated_run_leaves_no_active_run(tmp_path: Path) -> None:
    """A ``@loom.run`` function calling itself restores, at each exit, the
    run that was active at the matching entry."""

    @loom.run(tmp_path / "frag.json")
    def train(depth: int) -> None:
        if depth:
            train(depth - 1)

    train(2)
    _no_active_run_raises()
