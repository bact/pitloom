# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Git LFS pointers in a loom run: a dataset, model or script that
is a pointer is recorded by its ``oid`` (ids and hashes the same after
``git lfs pull``), its ``Hash`` and provenance say so, and the run ends with
one ``WARNING:`` for all of them.

See also: tests/core/test_dataset_hash_lfs.py (the dataset hash),
tests/core/test_loom_dataset.py (datasets at large).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.core.lfs_pointer import LfsPointer, UnreadPointers
from pitloom.id_registry import AI_PACKAGE_TYPE, IdRegistry
from pitloom.logging_config import PITLOOM_DEBUG_ENV_VAR
from tests._lfs import lfs_pointer_bytes
from tests.hash_helpers import file_hashes_json
from tests.registry_helpers import make_registry

_CONTENT = {"data/x.parquet": b"x" * 300, "corpus/a.bin": b"a", "m.bin": b"w" * 9}
_POINTERS = {name: lfs_pointer_bytes(data) for name, data in _CONTENT.items()}
_PULL_HINT = "run 'git lfs pull' for the content"

Graph = list[dict[str, Any]]


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An entered checkout made with LFS off: every :data:`_CONTENT` file a
    pointer, ``corpus/b.txt`` an ordinary file; no calling script."""
    root = tmp_path / "proj"
    _write(root, {**_POINTERS, "corpus/b.txt": b"b\n"})
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    return root


def _write(root: Path, files: dict[str, bytes]) -> None:
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)


def _pull(root: Path) -> None:
    assert (root / "m.bin").read_bytes() != _CONTENT["m.bin"]
    _write(root, _CONTENT)


def _run(output: Path, body: Callable[[], None], registry: Path | None = None) -> Graph:
    with loom.run(output, id_registry=registry):
        body()
    graph: Graph = json.loads(output.read_text(encoding="utf-8"))["@graph"]
    return graph


def _named(graph: Graph, type_name: str, name: str) -> dict[str, Any]:
    (element,) = (e for e in graph if e["type"] == type_name and e["name"] == name)
    return element


def _oid_hash(name: str) -> list[dict[str, str]]:
    size = len(_CONTENT[name])
    return [
        {
            "type": "Hash",
            "algorithm": "sha256",
            "hashValue": hashlib.sha256(_CONTENT[name]).hexdigest(),
            "comment": f"Git LFS pointer oid; content not read; size {size} bytes",
        }
    ]


def _pointer_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and "Git LFS" in r.getMessage()
    ]


def test_a_file_dataset_records_the_oid(project: Path) -> None:
    """Package and file carry the oid alone, with the comment; the
    package's provenance names the method. Pulled: the same SHA-256."""
    name = "data/x.parquet"
    graph = _run(project / "o.json", lambda: loom.add_dataset(name))
    package = _named(graph, "dataset_DatasetPackage", name)
    assert package["verifiedUsing"] == _oid_hash(name)
    assert _named(graph, "software_File", name)["verifiedUsing"] == _oid_hash(name)
    assert f"Source: {name} | Method: lfs_pointer" in package["comment"]
    _pull(project)
    graph = _run(project / "p.json", lambda: loom.add_dataset(name))
    package = _named(graph, "dataset_DatasetPackage", name)
    assert package["verifiedUsing"] == file_hashes_json(_CONTENT[name])
    assert "Method: lfs_pointer" not in package.get("comment", "")


def test_a_directory_root_is_the_same_after_a_pull(project: Path) -> None:
    """The Merkle root over a pointer and an ordinary file equals the root
    after the pull; only its comment counts the pointer."""

    def _root(output: Path) -> dict[str, Any]:
        graph = _run(output, lambda: loom.add_dataset("corpus"))
        (hashed,) = _named(graph, "dataset_DatasetPackage", "corpus")["verifiedUsing"]
        return dict(hashed)

    before = _root(project / "o.json")
    _pull(project)
    after = _root(project / "p.json")
    assert before["hashValue"] == after["hashValue"]
    assert before["comment"] == (
        f"{after['comment']}; Git LFS pointer oid for 1 file; content not read"
    )


@pytest.mark.parametrize("registry", [False, True])
def test_a_model_keeps_its_id_after_a_pull(project: Path, registry: bool) -> None:
    """``use_model(path=)`` on a pointer is keyed and gated by the oid, so
    the registered id holds after the pull (lineage does not split)."""
    reg = None
    if registry:
        reg = project / "reg.json"
        make_registry(path=reg)

    def _model(output: Path) -> dict[str, Any]:
        graph = _run(output, lambda: loom.use_model("m", path="m.bin"), reg)
        return _named(graph, "ai_AIPackage", "m")

    before = _model(project / "o.json")
    assert before["verifiedUsing"] == _oid_hash("m.bin")
    assert "Source: m.bin | Method: lfs_pointer" in before["comment"]
    _pull(project)
    after = _model(project / "p.json")
    assert after["verifiedUsing"] == file_hashes_json(_CONTENT["m.bin"])
    if reg is not None:
        assert before["spdxId"] == after["spdxId"]
        (entry,) = IdRegistry.load(reg).elements.items()
        assert entry[0][0] == AI_PACKAGE_TYPE
        assert entry[1].sha256 == hashlib.sha256(_CONTENT["m.bin"]).hexdigest()


def _everything() -> None:
    loom.add_dataset("data/x.parquet")
    loom.add_input_dataset("data/../data/x.parquet")  # one file, two spellings
    loom.add_validation_dataset("corpus")
    loom.use_model("m", path="m.bin")


@pytest.mark.parametrize(
    ("body", "expected", "count"),
    [
        (_everything, "corpus/a.bin: Git LFS pointer, content not read (3 files)", 3),
        (lambda: loom.add_dataset("corpus/b.txt"), None, 0),
        (
            lambda: loom.use_model("m", path="m.bin"),
            "m.bin: Git LFS pointer, content not read",
            1,
        ),
    ],
    ids=["three-calls", "normal-run", "model"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_one_warning_per_run_and_a_debug_line_per_file(
    project: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    body: Callable[[], None],
    expected: str | None,
    count: int,
) -> None:
    """Every pointer the run recorded counted once, in one summary written
    at the run's end naming the first path as given; one ``DEBUG`` line per
    file; none without pointers."""
    monkeypatch.setenv(PITLOOM_DEBUG_ENV_VAR, "1")
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        _run(project / "o.json", body)
    debug = [
        r
        for r in caplog.records
        if r.levelno == logging.DEBUG and "Git LFS pointer" in r.getMessage()
    ]
    assert len(debug) == count
    summary = [] if expected is None else [f"FILE={expected}; {_PULL_HINT}"]
    assert _pointer_warnings(caplog) == summary


def test_a_raising_run_warns_of_nothing(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A run whose block raises records nothing, so it warns of nothing,
    and the next run counts only its own pointers."""
    with caplog.at_level(logging.WARNING), pytest.raises(KeyError):
        with loom.run(project / "o.json"):
            loom.add_dataset("data/x.parquet")
            raise KeyError("stop")
    assert not _pointer_warnings(caplog)
    _run(project / "p.json", lambda: loom.add_dataset("corpus"))
    assert _pointer_warnings(caplog) == [
        f"FILE=corpus/a.bin: Git LFS pointer, content not read; {_PULL_HINT}"
    ]


def test_a_pointer_script_records_its_oid(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The calling script's ``software_File``, the dataset ceiling aside."""
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path",
        lambda: str(project / "m.bin"),
    )
    graph = _run(project / "o.json", lambda: loom.set_model("m"))
    assert _named(graph, "software_File", "m.bin")["verifiedUsing"] == _oid_hash(
        "m.bin"
    )


def test_the_summary_is_said_once_per_file_and_once_in_all(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Two spellings of one file are one file; a second ``warn()`` finds
    nothing left to say."""
    noted = UnreadPointers()
    pointer = LfsPointer("ab" * 32, 1)
    for path in ("m.bin", str(project / "m.bin"), "data/x.parquet"):
        noted.note(path, pointer)
    with caplog.at_level(logging.WARNING):
        noted.warn()
        noted.warn()
    assert _pointer_warnings(caplog) == [
        "FILE=data/x.parquet: Git LFS pointer, content not read (2 files); "
        + _PULL_HINT
    ]
