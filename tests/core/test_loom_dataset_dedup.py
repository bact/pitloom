# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for one ``dataset_DatasetPackage`` per (name, content digest) per loom
run, and for ``loom.run()`` leaving no active run behind when it fails to
write.

See also:
- :mod:`tests.core.test_loom_registry` for registry consultation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.core.config import PitloomConfig
from pitloom.core.dataset_merge import merge_dataset_references
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.dataset_names import CARD_DATASETS_CAP, distinct_dataset_names
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


def _skip_if_case_insensitive(directory: Path) -> None:
    """Skip when *directory*'s file system ignores case, before any
    case-variant path is made there."""
    (directory / "Probe").mkdir()
    if (directory / "probe").exists():
        pytest.skip("case-insensitive file system")  # pragma: no cover


_SPELLINGS = [
    pytest.param(["Org/Data", "org/data"], 1, id="hub-id-case"),
    pytest.param(["ds  one", "ds one"], 1, id="whitespace"),
    pytest.param(["Org/Data", " org/data "], 1, id="hub-id-case-and-edge-space"),
    pytest.param(["Not An Id", "not an id"], 2, id="other-name-case-kept"),
    pytest.param(["org/data", "org/other"], 2, id="different-ids"),
    pytest.param(["Data.txt", "data.txt"], 2, id="file-never-folded"),
]


@pytest.mark.parametrize(("names", "count"), _SPELLINGS)
def test_spellings_of_one_dataset_are_one_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, names: list[str], count: int
) -> None:
    """The SDK names one dataset as a model card's ``datasets:`` does
    (:func:`~pitloom.core.dataset_names.dataset_key`): the package is named
    as first declared, and each declaring call keeps its relationship. A name
    that is an existing file is never folded."""
    monkeypatch.chdir(tmp_path)
    if "Data.txt" in names:
        _skip_if_case_insensitive(tmp_path)
    (tmp_path / "Data.txt").write_bytes(b"data\n")
    out = tmp_path / "frag.json"
    with loom.run(out):
        loom.set_model("m")
        loom.add_dataset(names[0])
        loom.add_validation_dataset(names[1])
    graph: list[dict[str, Any]] = json.loads(out.read_text())["@graph"]
    packages = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
    assert len(packages) == count
    assert packages[0]["name"] == names[0]
    roles = sorted(
        r["relationshipType"]
        for r in _relationships(graph)
        if r["relationshipType"] in {"trainedOn", "testedOn"}
    )
    assert roles == ["testedOn", "trainedOn"]
    if "Data.txt" not in names:  # a file is the one place the SDK folds less
        card = distinct_dataset_names(names, CARD_DATASETS_CAP, "test")
        assert count == len(card)


@pytest.mark.parametrize("kind", ["empty-dir", "over-ceiling"])
def test_an_existing_path_is_never_folded_even_when_not_hashed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    """An empty directory and a file over ``max-dataset-hash-bytes`` have no
    digest but are paths: ``Org/Data`` and ``org/data`` stay two packages."""
    monkeypatch.chdir(tmp_path)
    _skip_if_case_insensitive(tmp_path)
    for name in ("Org/Data", "org/data"):
        path = Path(name)
        if kind == "empty-dir":
            path.mkdir(parents=True)
        else:
            path.parent.mkdir(parents=True)
            path.write_bytes(b"x" * 64)
    out = tmp_path / "frag.json"
    config = PitloomConfig(max_dataset_hash_bytes=8)
    with loom.run(out, pitloom_config=config):
        loom.set_model("m")
        loom.add_dataset("Org/Data")
        loom.add_dataset("org/data")
    graph = json.loads(out.read_text())["@graph"]
    assert len([e for e in graph if e["type"] == "dataset_DatasetPackage"]) == 2


@pytest.mark.parametrize("order", [("Org/Data", "org/data"), ("org/data", "Org/Data")])
def test_a_pin_under_the_later_spelling_is_warned_not_silent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    order: tuple[str, str],
) -> None:
    """The first spelling's id is used whichever it is; a different id pinned
    under the later one is named in a ``WARNING:``."""
    monkeypatch.chdir(tmp_path)
    ids = {"Org/Data": f"{_NS}#DatasetPackage-1", "org/data": f"{_NS}#DatasetPackage-2"}
    registry = make_registry(
        {
            (DATASET_PACKAGE_TYPE, name): (spdx_id, None)
            for name, spdx_id in ids.items()
        },
        namespace=_NS,
    )
    out = tmp_path / "frag.json"
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(out, id_registry=registry):
            loom.set_model("m")
            for name in order:
                loom.add_dataset(name)
    graph = json.loads(out.read_text())["@graph"]
    (package,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
    assert (package["name"], package["spdxId"]) == (order[0], ids[order[0]])
    (warning,) = [r.getMessage() for r in caplog.records if "is pinned to" in r.message]
    assert ids[order[1]] in warning and order[0] in warning


def test_spellings_share_one_registered_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Both spellings resolve to the package registered under the first."""
    monkeypatch.chdir(tmp_path)
    registry = make_registry(
        {(DATASET_PACKAGE_TYPE, "Org/Data"): (f"{_NS}#DatasetPackage-3", None)},
        namespace=_NS,
    )
    out = tmp_path / "frag.json"
    with loom.run(out, id_registry=registry):
        loom.set_model("m")
        loom.add_dataset("Org/Data")
        loom.add_validation_dataset("org/data")
    graph = json.loads(out.read_text())["@graph"]
    (package,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
    assert package["spdxId"] == f"{_NS}#DatasetPackage-3"


def _said(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if "name one dataset" in r.message]


def test_a_folded_spelling_is_said_once_by_every_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The SDK, a card's ``datasets:`` and two merged references say the
    same ``INFO:`` for ``Org/Data``/``org/data``, the SDK once however often
    the pair is declared; an identical spelling says nothing."""
    monkeypatch.chdir(tmp_path)
    expected = (
        "dataset Org/Data and org/data name one dataset; the first spelling is kept"
    )
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with loom.run(tmp_path / "frag.json"):
            loom.set_model("m")
            for name in ("Org/Data", "org/data", "org/data", "Org/Data"):
                loom.add_dataset(name)
        sdk = _said(caplog)
        caplog.clear()
        distinct_dataset_names(
            ["Org/Data", "org/data", "Org/Data"], CARD_DATASETS_CAP, "t"
        )
        card = _said(caplog)
        caplog.clear()
        merge_dataset_references(
            [
                DatasetReference(r, DatasetMetadata(name=n))
                for r, n in (
                    ("trainedOn", "Org/Data"),
                    ("testedOn", "org/data"),
                    ("trainedOn", "Org/Data"),
                )
            ]
        )
        merged = _said(caplog)
    assert sdk == card == merged == [expected]


def test_a_dangling_link_is_a_path_and_never_folded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without a registry too, a link to nothing is a path: ``Org`` and
    ``org`` stay two packages."""
    if not hasattr(os, "symlink"):  # pragma: no cover
        pytest.skip("no symlinks")
    monkeypatch.chdir(tmp_path)
    _skip_if_case_insensitive(tmp_path)
    try:
        os.symlink("nowhere", "Org")
    except OSError:  # pragma: no cover
        pytest.skip("symlinks need a privilege")
    out = tmp_path / "frag.json"
    with loom.run(out):
        loom.set_model("m")
        loom.add_dataset("Org")
        loom.add_dataset("org")
    graph = json.loads(out.read_text())["@graph"]
    assert len([e for e in graph if e["type"] == "dataset_DatasetPackage"]) == 2


def test_a_repeated_later_spelling_is_said_once_on_the_card_route(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A card listing ``org/data`` a thousand times says it once."""
    with caplog.at_level(logging.INFO, logger="pitloom"):
        names = distinct_dataset_names(
            ["Org/Data", *["org/data"] * 1000, "ORG/DATA"], CARD_DATASETS_CAP, "t"
        )
    assert names == ["Org/Data"]
    assert len(_said(caplog)) == 2


def test_the_pin_warning_cannot_forge_a_tagged_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Newlines in either spelling are escaped in the warning: it stays one
    line, so no second line starts with a level tag."""
    monkeypatch.chdir(tmp_path)
    registry = make_registry(
        {(DATASET_PACKAGE_TYPE, "ds WARNING: fake"): (f"{_NS}#DatasetPackage-9", None)},
        namespace=_NS,
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(tmp_path / "frag.json", id_registry=registry):
            loom.set_model("m")
            loom.add_dataset("ds\nWARNING: fake")
            loom.add_dataset("ds WARNING: fake")
    (warning,) = [r.getMessage() for r in caplog.records if "is pinned to" in r.message]
    assert "\n" not in warning
