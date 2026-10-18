# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.loom registry consultation and script-file + generates edges.

See also:
- :mod:`tests.core.test_loom` for loom.run() basics and dataset lineage.
- :mod:`tests.core.test_loom_creators` for creators and tools handling.

See also: test_loom_registry_set_model.py (repeated set_model calls).
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import pytest

from pitloom import loom
from pitloom.id_registry import DATASET_PACKAGE_TYPE, FILE_TYPE
from tests.core._loom_registry_shared import (
    _EXISTING_FILE,
    _sha256_of,
)
from tests.hash_helpers import file_hashes_json
from tests.registry_helpers import make_registry

from .conftest import _relationships


def test_loom_dataset_gets_verified_using_hash_when_file_exists() -> None:
    """A dataset name that is an existing file gets a SHA-256 verifiedUsing hash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.set_model("test-model")
            loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        datasets = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        (ds,) = [d for d in datasets if d["name"] == _EXISTING_FILE]
        assert ds["verifiedUsing"] == file_hashes_json(
            Path(_EXISTING_FILE).read_bytes()
        )


def test_loom_dataset_without_existing_file_has_no_hash() -> None:
    """A dataset name that is not an existing file gets no verifiedUsing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.set_model("test-model")
            loom.add_dataset("no-such-file-anywhere.txt")

        graph = json.loads(output_file.read_text())["@graph"]
        (ds,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert "verifiedUsing" not in ds


def test_loom_registry_id_reuse_for_dataset_and_model() -> None:
    """A dataset, its file and the model already registered get the
    registry's spdxIds, each under its own type."""
    namespace = "https://spdx.org/spdxdocs/test-proj-fixed"
    registry = make_registry(
        {
            (FILE_TYPE, _EXISTING_FILE): (
                f"{namespace}#File-1",
                _sha256_of(_EXISTING_FILE),
            ),
            (DATASET_PACKAGE_TYPE, _EXISTING_FILE): (
                f"{namespace}#DatasetPackage-1",
                None,
            ),
            ("ai_AIPackage", "registered-model"): (f"{namespace}#AIPackage-1", None),
        },
        namespace=namespace,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file, id_registry=registry):
            loom.set_model("registered-model")
            loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        (model,) = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert model["spdxId"] == f"{namespace}#AIPackage-1"
        (ds,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert ds["spdxId"] == f"{namespace}#DatasetPackage-1"
        (data_file,) = [
            e
            for e in graph
            if e["type"] == "software_File" and e["name"] == _EXISTING_FILE
        ]
        assert data_file["spdxId"] == f"{namespace}#File-1"


def test_loom_registry_hash_mismatch_warns_and_mints_new_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A registry entry with non-matching recorded hash is treated as unregistered."""
    namespace = "https://spdx.org/spdxdocs/test-proj-fixed"
    registry = make_registry(
        {(FILE_TYPE, _EXISTING_FILE): (f"{namespace}#File-1", "0" * 64)},  # wrong
        namespace=namespace,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
            with loom.run(output_file, id_registry=registry):
                loom.set_model("test-model")
                loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        files = [e for e in graph if e.get("name") == _EXISTING_FILE]
        assert {e["type"] for e in files} == {"software_File", "dataset_DatasetPackage"}
        assert f"{namespace}#File-1" not in {e["spdxId"] for e in files}
        assert any("no longer matches" in r.message for r in caplog.records)


def test_loom_training_run_emits_script_file_and_generates_edge() -> None:
    """A training run gets a software_File for calling script and generates edge."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.set_model("test-model")
            loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        script_files = [
            e
            for e in graph
            if e["type"] == "software_File"
            and e.get("name") == "tests/core/test_loom_registry.py"
        ]
        assert len(script_files) == 1

        (model,) = [e for e in graph if e["type"] == "ai_AIPackage"]
        rels = _relationships(graph)
        generates = [r for r in rels if r.get("relationshipType") == "generates"]
        assert len(generates) == 1
        assert generates[0]["from"] == script_files[0]["spdxId"]
        assert generates[0]["to"] == [model["spdxId"]]


def test_loom_testedon_only_run_emits_hasdatafile_edge() -> None:
    """An evaluation-only run gets a hasDataFile edge and a script File."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.set_model("test-model")
            loom.add_validation_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        assert [e for e in graph if e["type"] == "software_File"]
        rels = _relationships(graph)
        assert not [r for r in rels if r.get("relationshipType") == "generates"]
        assert [r for r in rels if r.get("relationshipType") == "hasDataFile"]


def test_loom_generated_true_override_forces_edge() -> None:
    """generated=True forces the generates edge even without a training dataset."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.set_model("test-model", generated=True)
            loom.add_validation_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        rels = _relationships(graph)
        assert [r for r in rels if r.get("relationshipType") == "generates"]
        assert [e for e in graph if e["type"] == "software_File"]


def test_loom_generated_false_override_emits_hasdatafile_edge() -> None:
    """generated=False suppresses generates edge, emits hasDataFile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.set_model("test-model", generated=False)
            loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        rels = _relationships(graph)
        assert not [r for r in rels if r.get("relationshipType") == "generates"]
        assert [r for r in rels if r.get("relationshipType") == "hasDataFile"]
        assert [e for e in graph if e["type"] == "software_File"]


def test_loom_use_model_emits_hasdatafile_edge() -> None:
    """use_model is an explicit shortcut for set_model(generated=False)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.use_model("test-model")
            loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        rels = _relationships(graph)
        assert not [r for r in rels if r.get("relationshipType") == "generates"]
        assert [r for r in rels if r.get("relationshipType") == "hasDataFile"]
        assert [e for e in graph if e["type"] == "software_File"]


def test_loom_output_dataset_only_run_gets_generates_edge_to_outputs() -> None:
    """A preprocessing run gets a generates edge to its output dataset(s)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.add_output_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        (ds,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        rels = _relationships(graph)
        (generates,) = [r for r in rels if r.get("relationshipType") == "generates"]
        assert generates["to"] == [ds["spdxId"]]
