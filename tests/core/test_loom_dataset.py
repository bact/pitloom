# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for loom datasets as SPDX elements (:mod:`pitloom._loom_dataset`):
a file dataset ``contains`` its ``software_File``, keyed from the registry's
project root; a directory gets a Merkle root; a remote name, neither.

See also: tests/core/test_loom_registry.py (registry reuse at large),
tests/core/test_dataset_hash.py (hashing),
tests/id_registry/test_registry_key_for_path.py (the file key).
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
from pitloom._loom_active_run import _ActiveRun
from pitloom.core.dataset_hash import hash_dataset
from pitloom.id_registry import DATASET_PACKAGE_TYPE, FILE_TYPE, IdRegistry
from tests._network import assert_spdx3_validate_ok
from tests.registry_helpers import Entries, make_registry

from .conftest import _relationships

_NS = "https://spdx.org/spdxdocs/test-1"
_CONTENT = b"one line\n"
_SHA = hashlib.sha256(_CONTENT).hexdigest()

Graph = list[dict[str, Any]]


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with ``data/t.txt``, ``corpus/`` (two files) and ``sub/``,
    entered; the calling script is not captured unless a test sets it."""
    root = tmp_path / "proj"
    (root / "data").mkdir(parents=True)
    (root / "data" / "t.txt").write_bytes(_CONTENT)
    (root / "corpus" / "b").mkdir(parents=True)
    (root / "corpus" / "a.txt").write_bytes(b"a")
    (root / "corpus" / "b" / "c.txt").write_bytes(b"c")
    (root / "sub").mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    return root


def _run(
    output: Path, registry: IdRegistry | None, body: Callable[[_ActiveRun], None]
) -> Graph:
    with loom.run(output, id_registry=registry) as run:
        body(run)
    graph: Graph = json.loads(output.read_text(encoding="utf-8"))["@graph"]
    return graph


def _of(graph: Graph, type_name: str) -> list[dict[str, Any]]:
    return [e for e in graph if e["type"] == type_name]


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


def _contains(graph: Graph) -> list[tuple[str, list[str]]]:
    return [
        (r["from"], r["to"])
        for r in _relationships(graph)
        if r["relationshipType"] == "contains"
    ]


@pytest.mark.parametrize(
    ("cwd", "given", "package_warns"),
    [(".", "data/t.txt", False), ("sub", "../data/t.txt", True)],
    ids=["root", "subdir"],
)
def test_file_dataset_contains_its_keyed_file(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    cwd: str,
    given: str,
    package_warns: bool,
) -> None:
    """The package is named and looked up as given; its file by the path
    from the project root, so from any directory it keeps its registry id.
    Package and file each carry their own ``Hash``."""
    registry = make_registry(
        {
            (FILE_TYPE, "data/t.txt"): (f"{_NS}#File-7", _SHA),
            (DATASET_PACKAGE_TYPE, "data/t.txt"): (f"{_NS}#DatasetPackage-3", None),
        },
        project_root=project,
    )
    monkeypatch.chdir(project / cwd)
    shared: list[bool] = []

    def body(run: _ActiveRun) -> None:
        loom.add_dataset(given)
        package = run.datasets[0]
        held = run.elements.file(given, Path(given), _SHA)  # the cached one
        shared.append(package.verifiedUsing[0] is held.verifiedUsing[0])

    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        graph = _run(project / "out.json", registry, body)

    (package,) = _of(graph, "dataset_DatasetPackage")
    (held,) = _of(graph, "software_File")
    assert (held["spdxId"], held["name"]) == (f"{_NS}#File-7", "data/t.txt")
    assert package["name"] == given
    assert (package["spdxId"] == f"{_NS}#DatasetPackage-3") is not package_warns
    assert [h["hashValue"] for h in package["verifiedUsing"]] == [_SHA]
    assert [h["hashValue"] for h in held["verifiedUsing"]] == [_SHA]
    assert _contains(graph) == [(package["spdxId"], [held["spdxId"]])]
    assert shared == [False]
    assert len(_warnings(caplog)) == int(package_warns)
    if package_warns:
        assert "untracked entity" in _warnings(caplog)[0]


@pytest.mark.parametrize(
    ("entry_type", "needle"),
    [
        (FILE_TYPE, "no longer matches"),
        (DATASET_PACKAGE_TYPE, "untracked file"),
        (None, "untracked file"),
    ],
    ids=["file-other-hash", "package-only", "absent"],
)
def test_file_miss_warning(
    project: Path,
    caplog: pytest.LogCaptureFixture,
    entry_type: str | None,
    needle: str,
) -> None:
    """A file entry with another hash is "content changed"; the dataset's
    own package entry under that name does not count for its file."""
    sha = "0" * 64 if entry_type == FILE_TYPE else None
    entries: Entries = (
        {} if entry_type is None else {(entry_type, "data/t.txt"): (f"{_NS}#X-1", sha)}
    )
    registry = make_registry(entries, project_root=project)

    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        graph = _run(
            project / "out.json", registry, lambda _: loom.add_dataset("data/t.txt")
        )

    (held,) = _of(graph, "software_File")
    assert held["spdxId"] != f"{_NS}#X-1"
    (warning,) = [w for w in _warnings(caplog) if "entity" not in w]
    assert warning.startswith("loom: ")
    assert needle in warning


@pytest.mark.parametrize(
    ("members", "count"), [(["a.txt"], "1 file"), (None, "2 files")], ids=["1", "2"]
)
def test_directory_dataset_has_its_merkle_root_and_no_file(
    project: Path, members: list[str] | None, count: str
) -> None:
    """A directory: the package carries the Merkle root, with a comment
    saying what it is over; no file elements, no ``contains``; the same
    root on the next run."""
    if members is not None:
        (project / "corpus" / "b" / "c.txt").unlink()
        (project / "corpus" / "b").rmdir()
    expected = hash_dataset(Path("corpus"), max_bytes=1 << 20).hex_digest
    roots = []
    for attempt in ("first", "second"):
        graph = _run(
            project / f"{attempt}.json", None, lambda _: loom.add_dataset("corpus")
        )
        (package,) = _of(graph, "dataset_DatasetPackage")
        (root_hash,) = package["verifiedUsing"]
        assert root_hash["comment"] == (
            f"SHA-256 Merkle root over {count} (path and content) in dataset "
            "directory, not a hash of a single artifact"
        )
        assert not _of(graph, "software_File")
        assert not _contains(graph)
        roots.append(root_hash["hashValue"])
    assert roots == [expected, expected]


def test_registry_inside_a_directory_dataset_is_left_out_with_one_warning(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The declared registry file inside a directory dataset is left out of
    its root (the root a run without it would give), said once per run."""
    without = hash_dataset(Path("corpus"), max_bytes=1 << 20).hex_digest
    registry = make_registry(path=project / "corpus" / "loom-id-registry.json")

    def body(_: _ActiveRun) -> None:
        loom.add_input_dataset("corpus")
        loom.add_dataset("corpus")

    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        graph = _run(project / "out.json", registry, body)

    roots = {
        h["hashValue"]
        for p in _of(graph, "dataset_DatasetPackage")
        for h in p["verifiedUsing"]
    }
    assert roots == {without}
    left_out = [w for w in _warnings(caplog) if "left out of its Merkle root" in w]
    assert len(left_out) == 1


def test_registry_alone_in_a_directory_dataset_is_still_said(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A directory holding only the registry gets no root; the registry
    was still found there and left out: one warning."""
    registry = make_registry(path=project / "sub" / "loom-id-registry.json")
    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        graph = _run(project / "out.json", registry, lambda _: loom.add_dataset("sub"))
    assert not _of(graph, "dataset_DatasetPackage")[0].get("verifiedUsing")
    left_out = [w for w in _warnings(caplog) if "left out of its Merkle root" in w]
    assert len(left_out) == 1


@pytest.mark.parametrize("pinned", [True, False], ids=["pinned", "unpinned"])
def test_remote_dataset_is_looked_up_by_name(
    project: Path, caplog: pytest.LogCaptureFixture, pinned: bool
) -> None:
    """A name that is no local path: a package with no hash and no file;
    its registry id when pinned, else an "untracked entity" warning."""
    name = "hf://datasets/org/corpus"
    entries: Entries = (
        {(DATASET_PACKAGE_TYPE, name): (f"{_NS}#DatasetPackage-9", None)}
        if pinned
        else {}
    )
    registry = make_registry(entries, project_root=project)

    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        graph = _run(project / "out.json", registry, lambda _: loom.add_dataset(name))

    (package,) = _of(graph, "dataset_DatasetPackage")
    assert "verifiedUsing" not in package
    assert not _of(graph, "software_File")
    assert (package["spdxId"] == f"{_NS}#DatasetPackage-9") is pinned
    untracked = [w for w in _warnings(caplog) if "untracked entity" in w]
    assert len(untracked) == int(not pinned)


@pytest.mark.parametrize("with_registry", [True, False], ids=["registry", "none"])
def test_file_outside_the_root_is_minted_with_one_warning(
    project: Path, caplog: pytest.LogCaptureFixture, with_registry: bool
) -> None:
    """Outside the registry's project root: no key, so no file lookup (an
    entry under the caller's spelling is not consulted), a minted id and
    one warning however often the path is declared. With no registry, no
    warning."""
    outside = project.parent / "outside.txt"
    outside.write_bytes(_CONTENT)
    given = str(outside)
    registry = (
        make_registry(
            {(FILE_TYPE, given): (f"{_NS}#File-5", _SHA)}, project_root=project
        )
        if with_registry
        else None
    )

    def body(_: _ActiveRun) -> None:
        loom.add_input_dataset(given)
        loom.add_dataset(given)
        loom.add_validation_dataset(str(project / ".." / "outside.txt"))

    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        graph = _run(project / "out.json", registry, body)

    files = _of(graph, "software_File")
    assert [f["name"] for f in files] == [given, str(project / ".." / "outside.txt")]
    assert all(f["spdxId"] != f"{_NS}#File-5" for f in files)
    outside_warnings = [w for w in _warnings(caplog) if "is outside the ID" in w]
    assert len(outside_warnings) == int(with_registry)


def test_one_file_two_spellings_is_one_file(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Two spellings of one file: two packages (each named as given), one
    ``software_File`` both contain, one registry claim."""
    registry = make_registry(
        {(FILE_TYPE, "data/t.txt"): (f"{_NS}#File-7", _SHA)}, project_root=project
    )

    def body(_: _ActiveRun) -> None:
        loom.add_input_dataset("data/t.txt")
        loom.add_dataset("./sub/../data/t.txt")

    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        graph = _run(project / "out.json", registry, body)

    (held,) = _of(graph, "software_File")
    assert held["spdxId"] == f"{_NS}#File-7"
    packages = _of(graph, "dataset_DatasetPackage")
    assert sorted(p["name"] for p in packages) == ["./sub/../data/t.txt", "data/t.txt"]
    assert sorted(_contains(graph)) == sorted(
        (p["spdxId"], [held["spdxId"]]) for p in packages
    )
    assert not [w for w in _warnings(caplog) if "registered for both" in w]


def test_script_is_keyed_from_the_root_when_run_from_a_subdirectory(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The script's file, captured as ``../train.py`` from ``sub/``, keys as
    ``train.py`` and keeps its registry id."""
    script = project / "train.py"
    script.write_bytes(_CONTENT)
    monkeypatch.chdir(project / "sub")
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: "../train.py"
    )
    registry = make_registry(
        {(FILE_TYPE, "train.py"): (f"{_NS}#File-2", _SHA)}, project_root=project
    )
    graph = _run(project / "out.json", registry, lambda _: loom.set_model("m"))
    (script_file,) = _of(graph, "software_File")
    assert (script_file["spdxId"], script_file["name"]) == (
        f"{_NS}#File-2",
        "train.py",
    )


@pytest.mark.network
def test_dataset_elements_validate(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run with a file, a directory and a remote dataset, a model and a
    script: valid SPDX 3."""
    (project / "train.py").write_bytes(_CONTENT)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: "train.py"
    )
    output = project / "out.json"

    def body(_: _ActiveRun) -> None:
        loom.set_model("m")
        loom.add_dataset("data/t.txt")
        loom.add_input_dataset("corpus")
        loom.add_validation_dataset("hf://datasets/org/corpus")

    _run(output, make_registry(project_root=project), body)
    assert_spdx3_validate_ok(output)
