# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the registry key and content gate of a loom dataset package
(:mod:`pitloom._loom_dataset`): a dataset below the registry root is keyed by
its path, whatever the spelling, and gated by its digest, a hash-less pin
holding for any content; anything else keeps its name.

See also: tests/core/test_loom_dataset.py (the elements),
tests/cli/test_cli_id_entity_key.py (``id generate -e``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import json
import logging
import os
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.cli.id import _run_id_command
from pitloom.cli.parser import _build_parser
from pitloom.core.config import PitloomConfig
from pitloom.core.dataset_hash import hash_dataset
from pitloom.id_registry import DATASET_PACKAGE_TYPE, FILE_TYPE, IdRegistry, keys
from tests.registry_helpers import Entries, make_registry

from .conftest import _relationships

_NS = "https://spdx.org/spdxdocs/test-1"
_PIN = f"{_NS}#DatasetPackage-3"
_CONTENT = b"one line\n"
_SHA = hashlib.sha256(_CONTENT).hexdigest()
_NFC = unicodedata.normalize("NFC", "data/café.txt")
_NFD = unicodedata.normalize("NFD", _NFC)

Graph = list[dict[str, Any]]


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An entered project: ``data/t.txt``, ``data/<NFD name>`` (same
    bytes), ``corpus/a.txt`` and ``scripts/``; no script captured."""
    root = tmp_path / "proj"
    for folder in ("data", "corpus", "scripts"):
        (root / folder).mkdir(parents=True)
    (root / "data" / "t.txt").write_bytes(_CONTENT)
    (root / _NFD).write_bytes(_CONTENT)
    (root / "corpus" / "a.txt").write_bytes(b"a")
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    return root


def _run(
    project: Path,
    entries: Entries,
    body: Callable[[], None],
    config: PitloomConfig | None = None,
) -> Graph:
    registry = make_registry(entries, project_root=project)
    output = project / "out.json"
    with loom.run(output, id_registry=registry, pitloom_config=config):
        body()
    graph: Graph = json.loads(output.read_text(encoding="utf-8"))["@graph"]
    return graph


def _of(graph: Graph, type_name: str) -> list[dict[str, Any]]:
    return [e for e in graph if e["type"] == type_name]


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


def _infos(caplog: pytest.LogCaptureFixture) -> list[str]:
    """The ``ID registry: dataset`` INFO lines, without that prefix."""
    prefix = "ID registry: dataset "
    return [
        r.getMessage()[len(prefix) :]
        for r in caplog.records
        if r.levelno == logging.INFO and r.getMessage().startswith(prefix)
    ]


def _declare(*spellings: tuple[str, str]) -> Callable[[], None]:
    """Declare each ``(cwd, name)`` as a training dataset from *cwd*."""

    def body() -> None:
        for cwd, name in spellings:
            os.chdir(cwd)
            loom.add_dataset(name)

    return body


def _case_variant(project: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """``data/T.TXT``: a hard link where the file system tells case apart,
    hidden from the listing, so only its identity names ``t.txt``."""
    try:
        os.link(project / "data" / "t.txt", project / "data" / "T.TXT")
    except FileExistsError:  # case-insensitive: already the same file
        pass
    except OSError:
        pytest.skip("hard links unavailable on this file system")
    real = os.listdir
    monkeypatch.setattr(
        keys, "_listdir", lambda d: [n for n in real(d) if n != "T.TXT"]
    )
    return "data/T.TXT"


@pytest.mark.parametrize(
    ("key", "cwd", "second"),
    [
        ("data/t.txt", ".", "./data/t.txt"),
        ("data/t.txt", "scripts", "../data/t.txt"),
        ("data/t.txt", ".", "absolute"),
        ("data/t.txt", ".", "case"),
        (_NFC, ".", f"./{_NFD}"),
    ],
    ids=["dot", "parent", "absolute", "case", "nfd"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_spellings_of_one_dataset_are_one_package(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    key: str,
    cwd: str,
    second: str,
) -> None:
    """Two spellings of one file: one package, named as first declared,
    with the id pinned under its path key; one file, one ``contains``."""
    first = _NFD if key == _NFC else key
    if second == "absolute":
        second = str(project / first)
    elif second == "case":
        second = _case_variant(project, monkeypatch)
    entries: Entries = {
        (DATASET_PACKAGE_TYPE, key): (_PIN, _SHA),
        (FILE_TYPE, key): (f"{_NS}#File-7", _SHA),
    }
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        graph = _run(project, entries, _declare((str(project), first), (cwd, second)))

    (package,) = _of(graph, "dataset_DatasetPackage")
    (held,) = _of(graph, "software_File")
    assert (package["spdxId"], package["name"]) == (_PIN, first)
    assert (held["spdxId"], held["name"]) == (f"{_NS}#File-7", key)
    contains = [r for r in _relationships(graph) if r["relationshipType"] == "contains"]
    assert [(r["from"], r["to"]) for r in contains] == [(_PIN, [held["spdxId"]])]
    assert not _warnings(caplog)


@pytest.mark.parametrize(
    ("pinned", "content", "hit", "needle"),
    [
        (None, b"changed\n", True, None),
        (_SHA, _CONTENT, True, None),
        (_SHA, b"changed\n", False, "no longer matches"),
        ("absent", _CONTENT, False, "untracked entity"),
    ],
    ids=["hashless-any", "equal", "changed", "absent"],
)
def test_package_lookup_is_gated_by_its_digest(
    project: Path,
    caplog: pytest.LogCaptureFixture,
    pinned: str | None,
    content: bytes,
    hit: bool,
    needle: str | None,
) -> None:
    """A hash-less pin holds for any content, said once per package; a
    hashed one only for equal content; a miss mints and says why, naming
    the path key."""
    (project / "data" / "t.txt").write_bytes(content)
    entries: Entries = (
        {}
        if pinned == "absent"
        else {(DATASET_PACKAGE_TYPE, "data/t.txt"): (_PIN, pinned)}
    )
    with caplog.at_level(logging.INFO, logger="pitloom.loom"):
        graph = _run(
            project, entries, _declare((".", "./data/t.txt"), (".", "data/t.txt"))
        )

    (package,) = _of(graph, "dataset_DatasetPackage")
    assert (package["spdxId"] == _PIN) is hit
    hashless = ["data/t.txt matched a pin without SHA-256; content not checked"]
    assert _infos(caplog) == (hashless if pinned is None else [])
    assert package["name"] == "./data/t.txt"
    missed = [w for w in _warnings(caplog) if "entity" in w or "matches" in w]
    assert len(missed) == int(not hit)
    if needle is not None:
        assert needle in missed[0]
        assert "'data/t.txt'" in missed[0]


@pytest.mark.parametrize("added", [False, True], ids=["same", "file-added"])
def test_directory_dataset_is_gated_by_its_merkle_root(
    project: Path, added: bool
) -> None:
    """A directory pinned with its Merkle root keeps its id while its files
    stay; one more file is a new root, so a new package id."""
    root = hash_dataset(Path("corpus"), max_bytes=1 << 20).hex_digest
    if added:
        (project / "corpus" / "b.txt").write_bytes(b"b")
    entries: Entries = {(DATASET_PACKAGE_TYPE, "corpus"): (_PIN, root)}
    graph = _run(project, entries, _declare((".", "./corpus/")))

    (package,) = _of(graph, "dataset_DatasetPackage")
    assert (package["spdxId"] == _PIN) is not added


def test_unhashed_dataset_is_looked_up_ungated_by_its_path_key(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Over the hash ceiling: no digest, so the path key is looked up
    ungated: the ceiling warns (per declaration, each one hashed), and one
    INFO per package."""
    entries: Entries = {(DATASET_PACKAGE_TYPE, "data/t.txt"): (_PIN, "0" * 64)}
    with caplog.at_level(logging.INFO, logger="pitloom"):
        graph = _run(
            project,
            entries,
            _declare((".", "./data/t.txt"), (".", "data/t.txt")),
            PitloomConfig(max_dataset_hash_bytes=4),
        )

    (package,) = _of(graph, "dataset_DatasetPackage")
    assert package["spdxId"] == _PIN
    assert "verifiedUsing" not in package
    assert all("max-dataset-hash-bytes" in w for w in _warnings(caplog))
    assert _infos(caplog) == ["data/t.txt looked up ungated: not hashed"]


@pytest.mark.parametrize(
    "name",
    [
        "imdb",
        "stanfordnlp/imdb",
        "https://example.org/d.csv",
        "data/missing.txt",
        "outside",
    ],
    ids=["bare", "hub", "url", "missing", "outside"],
)
def test_pathless_dataset_keeps_its_name(
    project: Path, caplog: pytest.LogCaptureFixture, name: str
) -> None:
    """No local path below the root (an output not written yet included):
    looked up by the name as given, a hash-less pin holding; one INFO per
    package saying why. Only a file outside the root gets a file (and its
    warning, as before)."""
    reason = "not found"
    if name == "outside":
        (project.parent / "outside.txt").write_bytes(_CONTENT)
        name, reason = str(project.parent / "outside.txt"), "outside the project root"
    entries: Entries = {(DATASET_PACKAGE_TYPE, name): (_PIN, None)}

    def body() -> None:
        loom.add_input_dataset(name)
        loom.add_output_dataset(name)

    with caplog.at_level(logging.INFO, logger="pitloom"):
        graph = _run(project, entries, body)

    (package,) = _of(graph, "dataset_DatasetPackage")
    assert (package["spdxId"], package["name"]) == (_PIN, name)
    assert len(_of(graph, "software_File")) == len(_warnings(caplog))
    assert len(_warnings(caplog)) == int(reason != "not found")
    assert _infos(caplog) == [f"{name} keyed by its name: {reason}"]


def test_an_output_names_its_input_by_any_spelling(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An input declared under two spellings is one package; an output
    naming either spelling as its source gets it."""

    def body() -> None:
        loom.add_input_dataset("data/t.txt")
        loom.add_input_dataset("./data/t.txt")
        loom.add_output_dataset("out", input_datasets=["./data/t.txt"])

    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        graph = _run(project, {}, body)

    packages = {p["name"]: p["spdxId"] for p in _of(graph, "dataset_DatasetPackage")}
    assert sorted(packages) == ["data/t.txt", "out"]
    (rel,) = [r for r in _relationships(graph) if r["relationshipType"] == "hasInput"]
    assert (rel["from"], rel["to"]) == (packages["out"], [packages["data/t.txt"]])
    assert not [w for w in _warnings(caplog) if "input_datasets" in w]


@pytest.mark.parametrize("name", ["data/t.txt", "corpus"], ids=["file", "dir"])
def test_id_generate_pin_hits_the_loom_package(project: Path, name: str) -> None:
    """Drift guard: ``id generate -e`` stores the digest the loom package
    carries, so the pin hits and the two hashes are equal."""
    registry_path = project / "reg.json"
    args = _build_parser().parse_args(
        ["id", "generate", "--project-dir", str(project), "-o", str(registry_path)]
        + ["-e", f"./{name}:{DATASET_PACKAGE_TYPE}", "data"]
    )
    assert _run_id_command(args) == 0
    pin = IdRegistry.load(registry_path).get(DATASET_PACKAGE_TYPE, name)
    assert pin is not None and pin.sha256 is not None

    output = project / "out.json"
    with loom.run(output, id_registry=str(registry_path)):
        loom.add_dataset(name)
    graph: Graph = json.loads(output.read_text(encoding="utf-8"))["@graph"]

    (package,) = _of(graph, "dataset_DatasetPackage")
    assert package["spdxId"] == pin.spdx_id
    assert [h["hashValue"] for h in package["verifiedUsing"]] == [pin.sha256]


def test_dataset_file_found_through_the_layout_alias_says_so_once(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A ``src/`` file hits the key a wheel gave its installed path; the run
    says so once, at its end, counting only the hit file."""
    (project / "src" / "pkg").mkdir(parents=True)
    (project / "src" / "pkg" / "t.txt").write_bytes(_CONTENT)
    entries: Entries = {(FILE_TYPE, "pkg/t.txt"): (f"{_NS}#File-9", _SHA)}

    with caplog.at_level(logging.INFO):
        graph = _run(project, entries, _declare((".", "src/pkg/t.txt")))

    (held,) = _of(graph, "software_File")
    assert (held["spdxId"], held["name"]) == (f"{_NS}#File-9", "src/pkg/t.txt")
    (info,) = [r.getMessage() for r in caplog.records if "layout alias" in r.message]
    assert info == (
        "ID registry: 1 element(s) matched a registry key through the "
        "src/lib layout alias"
    )
