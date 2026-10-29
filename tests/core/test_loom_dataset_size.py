# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for a loom dataset's byte size and the evidence of its digest
(:func:`pitloom._loom_dataset_keys.digest_evidence`): a single file states
its size, over the hash ceiling from ``stat()``, and says why its hash is
missing; a pointer and a directory state no size.

See also: tests/core/test_loom_dataset.py (datasets at large),
tests/core/test_dataset_hash.py (the digest and its size),
tests/core/test_evidence.py (the evidence segment).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom._loom_dataset_keys import DigestEvidence, digest_evidence
from pitloom._loom_dataset_meta import DatasetSources
from pitloom.core.dataset_hash import DatasetDigest
from pitloom.core.dataset_metadata import DatasetMetadata
from pitloom.core.provenance import parse_provenance_value
from tests._lfs import lfs_pointer_bytes
from tests._spdx3_validate import assert_spdx3_valid
from tests.hash_helpers import file_hashes_json

#: The hash ceiling of these runs, and the byte counts of the files.
_CAP = 1024
_BIG = 2000
_SMALL = b"one line\n"
_NOT_MEASURED = {"evidence": "not_measured", "reason": "over-cap"}
_UNREAD = "Evidence: not_measured | Reason: over-cap"
_MAX_SAFE = 2**53 - 1
_POSIX = os.name != "nt"

Graph = list[dict[str, Any]]


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An entered project: ``big.bin`` over the ceiling, ``t.txt`` within
    it, a pointer ``p.bin`` and ``corpus/``; no calling script; a pinned
    clock."""
    root = tmp_path / "proj"
    (root / "corpus").mkdir(parents=True)
    (root / "big.bin").write_bytes(b"b" * _BIG)
    (root / "t.txt").write_bytes(_SMALL)
    (root / "p.bin").write_bytes(lfs_pointer_bytes(b"p" * 4096))
    (root / "corpus" / "a.txt").write_bytes(b"a")
    monkeypatch.chdir(root)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    return root


def _run(output: Path, *names: str) -> Graph:
    with loom.run(output, max_dataset_hash_bytes=_CAP):
        for name in names:
            loom.add_dataset(name)
    graph: Graph = json.loads(output.read_text(encoding="utf-8"))["@graph"]
    return graph


def _package(graph: Graph, name: str) -> dict[str, Any]:
    (package,) = (
        e for e in graph if e["type"] == "dataset_DatasetPackage" and e["name"] == name
    )
    return package


def _fields(graph: Graph, name: str) -> dict[str, dict[str, str]]:
    """The provenance fields of *name*'s package Annotation."""
    subject = _package(graph, name)["spdxId"]
    (statement,) = (
        e["statement"]
        for e in graph
        if e["type"] == "Annotation" and e["subject"] == subject
    )
    fields: dict[str, dict[str, str]] = json.loads(statement)["fields"]
    return fields


def _size_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and "byte_size" in r.getMessage()
    ]


@pytest.mark.parametrize("name", ["big.bin", "setup.cfg"], ids=["file", "manifest"])
def test_over_the_cap_the_size_is_from_stat_and_the_hash_says_why(
    project: Path, name: str
) -> None:
    """No hash, the ``stat()`` size, and both entries in the Annotation and
    the comment, also for a file named like a manifest (a source ``minimal``
    detail drops unless it carries evidence); valid SPDX 3."""
    if name != "big.bin":
        (project / "big.bin").rename(project / name)
    graph = _run(project / "o.json", name)
    package = _package(graph, name)
    assert "verifiedUsing" not in package
    assert package["dataset_datasetSize"] == _BIG
    fields = _fields(graph, name)
    assert fields["verified_using"] == {"source": name, **_NOT_MEASURED}
    assert fields["byte_size"] == {"source": name, "evidence": "measured_stat"}
    assert f"verified_using: Source: {name} | {_UNREAD}" in package["comment"]
    assert f"byte_size: Source: {name} | Evidence: measured_stat" in package["comment"]
    assert_spdx3_valid(project / "o.json")


@pytest.mark.parametrize(
    ("size", "recorded"), [(_MAX_SAFE + 1, None), (_MAX_SAFE, _MAX_SAFE)], ids=str
)
def test_a_size_past_canonical_json_is_not_measured_with_one_warning(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    size: int,
    recorded: int | None,
) -> None:
    """Past 2^53-1: no size, ``not_measured`` and one ``WARNING:`` however
    often it is declared; 2^53-1 itself is recorded, silently."""
    monkeypatch.setattr("pitloom.core.dataset_hash._file_size", lambda _: size)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        graph = _run(project / "o.json", "big.bin", "big.bin")
    assert _package(graph, "big.bin").get("dataset_datasetSize") == recorded
    expected = {"evidence": "measured_stat"} if recorded is not None else _NOT_MEASURED
    assert _fields(graph, "big.bin")["byte_size"] == {"source": "big.bin", **expected}
    assert len(_size_warnings(caplog)) == int(recorded is None)


@pytest.mark.parametrize(
    ("name", "size"),
    [("t.txt", len(_SMALL)), ("p.bin", None), ("corpus", None)],
    ids=["read", "pointer", "directory"],
)
def test_within_the_cap_only_a_file_read_states_its_size(
    project: Path, name: str, size: int | None
) -> None:
    """A file read: its hash as before and the bytes read, with no
    ``byte_size`` entry. A pointer (its own size is not the content's) and
    a directory: no size; the pointer's provenance as before."""
    graph = _run(project / "o.json", name)
    package = _package(graph, name)
    assert package.get("dataset_datasetSize") == size
    fields = _fields(graph, name)
    assert "byte_size" not in fields
    if name == "t.txt":
        assert package["verifiedUsing"] == file_hashes_json(_SMALL)
        assert set(fields) == {"package"}
    elif name == "p.bin":
        assert fields["verified_using"] == {"source": name, "method": "lfs_pointer"}


def test_a_directory_over_the_cap_says_why_and_states_no_size(
    project: Path,
) -> None:
    """A directory over the ceiling: the hash ``not_measured``, no size."""
    (project / "corpus" / "b.bin").write_bytes(b"c" * _BIG)
    graph = _run(project / "o.json", "corpus")
    assert "dataset_datasetSize" not in _package(graph, "corpus")
    fields = _fields(graph, "corpus")
    assert fields["verified_using"] == {"source": "corpus", **_NOT_MEASURED}
    assert "byte_size" not in fields


def test_a_small_file_over_the_cap_says_why_it_has_no_size(project: Path) -> None:
    """Under 1,024 bytes it may be a Git LFS pointer, whose size is not the
    content's: no size, and ``byte_size`` is ``not_measured`` like the hash."""
    (project / "s.bin").write_bytes(b"s" * 300)
    with loom.run(project / "o.json", max_dataset_hash_bytes=100):
        loom.add_dataset("s.bin")
    graph: Graph = json.loads((project / "o.json").read_text("utf-8"))["@graph"]
    assert "dataset_datasetSize" not in _package(graph, "s.bin")
    fields = _fields(graph, "s.bin")
    assert fields["verified_using"] == {"source": "s.bin", **_NOT_MEASURED}
    assert fields["byte_size"] == {"source": "s.bin", **_NOT_MEASURED}
    assert_spdx3_valid(project / "o.json")


def test_a_repeat_declaration_keeps_the_first_size(project: Path) -> None:
    """The file grows between two declarations (still over the ceiling, so
    one package): the size the first one measured."""
    with loom.run(project / "o.json", max_dataset_hash_bytes=_CAP):
        loom.add_dataset("big.bin")
        (project / "big.bin").write_bytes(b"b" * (_BIG + 1))
        loom.add_input_dataset("big.bin")
    graph: Graph = json.loads((project / "o.json").read_text("utf-8"))["@graph"]
    assert _package(graph, "big.bin")["dataset_datasetSize"] == _BIG


@pytest.mark.parametrize(
    ("name", "size", "entry"),
    [
        ("big.bin", _BIG, {"source": "big.bin", "evidence": "measured_stat"}),
        ("t.txt", len(_SMALL), None),
        ("p.bin", 5, {"source": "card.md"}),
        ("huge", 5, {"source": "card.md"}),
    ],
    ids=["stat", "read", "pointer", "unwritable"],
)
def test_a_stated_size_loses_to_a_measured_one(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    size: int,
    entry: dict[str, str] | None,
) -> None:
    """A source stating 5 bytes (none in loom does yet): the measured size
    and its provenance replace it; with none measured (a pointer, a size
    past 2^53-1) it stands, with its own."""

    def merged(_: DatasetSources, named: str) -> DatasetMetadata:
        return DatasetMetadata(
            name=named, byte_size=5, provenance={"byte_size": "Source: card.md"}
        )

    monkeypatch.setattr(DatasetSources, "merged", merged)
    if name == "huge":
        (project / "big.bin").rename(project / name)
        monkeypatch.setattr("pitloom.core.dataset_hash._file_size", lambda _: 2**53)
    graph = _run(project / "o.json", name)
    assert _package(graph, name)["dataset_datasetSize"] == size
    assert _fields(graph, name).get("byte_size") == entry


def _stable(output: Path, names: tuple[str, ...]) -> dict[str, Any]:
    """Per package: its properties but the run's random ids, and its
    Annotation's statement."""
    graph = _run(output, *names)
    return {
        name: (
            {k: v for k, v in _package(graph, name).items() if k != "spdxId"},
            _fields(graph, name),
        )
        for name in names
    }


def test_two_runs_and_two_orders_record_the_same(project: Path) -> None:
    """The same properties and statements across runs and declaration
    orders."""
    names = ("big.bin", "t.txt")
    first = _stable(project / "a.json", names)
    assert first["big.bin"][0]["dataset_datasetSize"] == _BIG
    assert first == _stable(project / "b.json", names)
    assert first == _stable(project / "c.json", names[::-1])


def test_an_injected_label_cannot_forge_a_segment() -> None:
    """``|`` in the label cannot add a segment; ``;`` and a line break stay
    text (the comment encoder escapes them)."""
    found = DatasetDigest("file", size=_BIG, omitted="over-cap")
    evidence = digest_evidence(found, "a|Evidence: measured_read;b\nc")
    source = {"source": "a/Evidence: measured_read;b\nc"}
    assert evidence.hash_provenance is not None
    assert evidence.size_provenance is not None
    assert parse_provenance_value(evidence.hash_provenance) == {
        **source,
        **_NOT_MEASURED,
    }
    assert parse_provenance_value(evidence.size_provenance) == {
        **source,
        "evidence": "measured_stat",
    }


@pytest.mark.skipif(not _POSIX, reason="'|' and a line break in a file name")
def test_an_injected_file_name_is_escaped_in_the_comment(project: Path) -> None:
    """In the comment ``;`` and the line break are escaped, ``|`` replaced."""
    name = "a|b;c\nd"
    (project / "big.bin").rename(project / name)
    package = _package(_run(project / "o.json", name), name)
    assert f"Source: a/b\\u003bc\\u000ad | {_UNREAD}" in package["comment"]


def test_nothing_is_recorded_for_a_digest_with_no_hash_or_reason() -> None:
    """Unreadable or missing: no hash and no reason, so nothing."""
    assert digest_evidence(DatasetDigest("file", size=_BIG), "x") == DigestEvidence()
