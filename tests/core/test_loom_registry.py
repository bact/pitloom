# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.loom registry consultation and script-file + generates edges.

See also:
- :mod:`tests.core.test_loom` for loom.run() basics and dataset lineage.
- :mod:`tests.core.test_loom_creators` for creators and tools handling.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import loom
from pitloom.ids import EntityEntry, FileEntry, IdRegistry

from .conftest import _relationships

# An existing on-disk file, stable across the test run, used as a stand-in
# "dataset" so add_dataset()'s "name is an existing file" branch engages.
_EXISTING_FILE = "pyproject.toml"


def _sha256_of(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
        (hash_obj,) = ds["verifiedUsing"]
        assert hash_obj["algorithm"] == "sha256"
        assert hash_obj["hashValue"] == _sha256_of(_EXISTING_FILE)


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
    """A dataset/model already registered gets the registry's spdxId."""
    namespace = "https://spdx.org/spdxdocs/test-proj-fixed"
    registry = IdRegistry(
        namespace=namespace,
        files={
            _EXISTING_FILE: FileEntry(
                spdx_id=f"{namespace}#File-1", sha256=_sha256_of(_EXISTING_FILE)
            )
        },
        entities={
            "registered-model": EntityEntry(
                type="ai_AIPackage", spdx_id=f"{namespace}#AIPackage-1"
            )
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file, registry=registry):
            loom.set_model("registered-model")
            loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        (model,) = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert model["spdxId"] == f"{namespace}#AIPackage-1"
        (ds,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert ds["spdxId"] == f"{namespace}#File-1"


def test_loom_registry_hash_mismatch_warns_and_mints_new_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A registry entry with non-matching recorded hash is treated as unregistered."""
    namespace = "https://spdx.org/spdxdocs/test-proj-fixed"
    registry = IdRegistry(
        namespace=namespace,
        files={
            _EXISTING_FILE: FileEntry(
                spdx_id=f"{namespace}#File-1",
                sha256="0" * 64,  # deliberately wrong
            )
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
            with loom.run(output_file, registry=registry):
                loom.set_model("test-model")
                loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        (ds,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert ds["spdxId"] != f"{namespace}#File-1"
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


def test_loom_repl_caller_gets_no_script_file() -> None:
    """When caller cannot be resolved to a script file, no script File is emitted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with patch(
            "pitloom._loom_active_run._get_caller_script_path", return_value=None
        ):
            with loom.run(output_file):
                loom.set_model("test-model")
                loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        assert not [e for e in graph if e["type"] == "software_File"]
        rels = _relationships(graph)
        assert not [r for r in rels if r.get("relationshipType") == "generates"]
