# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Branch-coverage tests for pitloom._loom_active_run's relationship-emission
and finalize() guard clauses -- the "build_relationship returned None",
"mkdir skipped", and "no hash for the script file" edge paths that the
behavioural tests in test_loom.py / test_loom_registry.py don't exercise.

See also:
- :mod:`tests.core.test_loom` for loom.run() basics and dataset lineage.
- :mod:`tests.core.test_loom_registry` for registry and script file /
  generates edge behaviour.
"""

from __future__ import annotations

import errno
import json
import logging
import os
from pathlib import Path

import pytest

from pitloom import loom
from pitloom.core.file_hash import FileDigests

from .conftest import _relationships


def test_finalize_skips_relationships_when_build_relationship_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When build_relationship() returns None (from_id is None), each of the
    trainedOn/testedOn/hasInput/generates loops must skip add_relationship
    and simply continue, rather than crash."""
    monkeypatch.setattr(
        "pitloom._loom_active_run.build_relationship", lambda **_kw: None
    )

    output_file = tmp_path / "frag_none_rels.json"
    with loom.run(output_file):
        loom.set_model("test-model")
        loom.add_dataset("train.txt")
        loom.add_validation_dataset("valid.txt")
        loom.add_input_dataset("raw.txt")
        loom.add_output_dataset("out.txt", input_datasets=["raw.txt"])

    assert output_file.exists()
    graph = json.loads(output_file.read_text())["@graph"]
    # Every relationship was suppressed by the stubbed build_relationship.
    assert not _relationships(graph)
    # The packages themselves are still emitted.
    assert [e for e in graph if e["type"] == "ai_AIPackage"]
    assert [e for e in graph if e["type"] == "dataset_DatasetPackage"]


def test_finalize_skips_has_data_file_relationship_when_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The hasDataFile branch (generated=False) also tolerates
    build_relationship() returning None."""
    monkeypatch.setattr(
        "pitloom._loom_active_run.build_relationship", lambda **_kw: None
    )

    output_file = tmp_path / "frag_none_hasdatafile.json"
    with loom.run(output_file):
        loom.set_model("test-model", generated=False)
        loom.add_dataset("train.txt")

    assert output_file.exists()
    graph = json.loads(output_file.read_text())["@graph"]
    assert not _relationships(graph)


@pytest.mark.parametrize(
    ("failure", "warns"),
    [("gone", False), ("raced", False), ("unreadable", True)],
    ids=["gone", "raced", "unreadable"],
)
def test_script_file_without_a_hash_when_it_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    failure: str,
    warns: bool,
) -> None:
    """The script deleted before the run ends, or between its check and its
    read: its ``software_File`` has no hash, silently; unreadable: no hash
    and the shared ``FILE=`` warning."""
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "train.py"
    script.write_text("print('hi')\n", encoding="utf-8")
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: "train.py"
    )
    if failure != "gone":
        error = PermissionError if failure == "unreadable" else FileNotFoundError
        code = errno.EACCES if failure == "unreadable" else errno.ENOENT

        def _fails(path: Path) -> FileDigests:
            raise error(code, os.strerror(code), str(path))

        monkeypatch.setattr("pitloom._loom_dataset.file_digests", _fails)

    output_file = tmp_path / "frag_no_script_hash.json"
    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        with loom.run(output_file):
            loom.set_model("test-model")
            loom.add_dataset("train.txt")
            if failure == "gone":
                script.unlink()

    graph = json.loads(output_file.read_text())["@graph"]
    (script_file,) = [e for e in graph if e["type"] == "software_File"]
    assert script_file["name"] == "train.py"
    assert "verifiedUsing" not in script_file
    unreadable = [r for r in caplog.records if "could not read" in r.getMessage()]
    assert len(unreadable) == int(warns)
