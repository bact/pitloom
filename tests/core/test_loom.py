# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration and unit tests for the pitloom.loom module.

See also: tests/core/test_loom_registry.py for registry-consultation
(id reuse/hash-mismatch), creator-type, and script-file/generates tests.
"""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import loom

from .conftest import _relationships


def test_get_caller_info_exception_logs_and_returns_fallback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When inspect.stack() itself raises, _get_caller_info() catches it,
    logs at debug level, and returns the same "unknown source" fallback
    string as before logging was added."""
    with patch("pitloom.loom.inspect.stack", side_effect=RuntimeError("no frames")):
        with caplog.at_level(logging.DEBUG, logger="pitloom.loom"):
            # pylint: disable=protected-access
            result = loom._get_caller_info()

    assert result == "Source: unknown | Method: inspect_caller (tool: pitloom.loom)"
    assert any("caller info" in r.message for r in caplog.records)


def test_loom_run_as_context_manager() -> None:
    """Test using loom.run as a context manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_ctx.json"

        with loom.run(output_file):
            loom.set_model("test-model-1")
            loom.add_dataset("test-dataset-1", dataset_type="text")
            loom.add_dataset("test-dataset-2", dataset_type="image")

        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        assert "@context" in data
        graph = data["@graph"]

        # Verify model
        models = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert len(models) == 1
        assert models[0]["name"] == "test-model-1"
        assert "test_loom_run_as_context_manager" in models[0].get("comment", "")
        assert "test_loom.py" in models[0].get("comment", "")
        model_id = models[0].get("@id", models[0].get("spdxId"))

        # Verify datasets
        datasets = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert len(datasets) == 2
        dataset_names = {d["name"] for d in datasets}
        assert "test-dataset-1" in dataset_names
        assert "test-dataset-2" in dataset_names
        assert all("test_loom.py" in d.get("comment", "") for d in datasets)
        assert all(
            "test_loom_run_as_context_manager" in d.get("comment", "") for d in datasets
        )

        # Verify relationships: 2 trainedOn (one per dataset) plus 1 generates
        # (this test file -> the model, since a training dataset was declared).
        rels = _relationships(graph)
        trained_on = [r for r in rels if r.get("relationshipType") == "trainedOn"]
        assert len(trained_on) == 2
        for rel in trained_on:
            assert rel["from"] == model_id
            assert len(rel["to"]) == 1
            assert any(d.get("@id", d.get("spdxId")) == rel["to"][0] for d in datasets)

        generates = [r for r in rels if r.get("relationshipType") == "generates"]
        assert len(generates) == 1
        assert generates[0]["to"] == [model_id]
        assert len(rels) == 3


def test_loom_run_as_decorator() -> None:
    """Test using loom.run as a function decorator."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_dec.json"

        @loom.run(output_file)
        def dummy_train_function() -> None:
            loom.set_model("test-model-2")
            loom.add_dataset("test-dataset-3", dataset_type="audio")

        # Execute the decorated function
        dummy_train_function()

        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]

        models = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert len(models) == 1
        assert models[0]["name"] == "test-model-2"
        assert "dummy_train_function" in models[0].get("comment", "")
        assert "test_loom.py" in models[0].get("comment", "")

        datasets = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert len(datasets) == 1
        assert datasets[0]["name"] == "test-dataset-3"
        assert "dummy_train_function" in datasets[0].get("comment", "")
        assert "test_loom.py" in datasets[0].get("comment", "")


def test_loom_run_with_exception() -> None:
    """Test that a fragment is NOT generated if an exception occurs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_error.json"

        class DummyError(Exception):
            """Simulates a training failure."""

        try:
            with loom.run(output_file):
                loom.set_model("error-model")
                loom.add_dataset("error-dataset")
                raise DummyError("Something went wrong during training")
        except DummyError:
            pass

        # The JSON fragment should not have been created because the block failed
        assert not output_file.exists()


def test_loom_validation_dataset() -> None:
    """Test add_validation_dataset creates testedOn relationship."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_valid.json"

        with loom.run(output_file):
            loom.set_model("test-model-valid")
            loom.add_dataset("train.txt", dataset_type="text")
            loom.add_validation_dataset("valid.txt", dataset_type="text")

        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]

        datasets = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert len(datasets) == 2
        dataset_names = {d["name"] for d in datasets}
        assert "train.txt" in dataset_names
        assert "valid.txt" in dataset_names

        rels = _relationships(graph)
        rel_types = {r.get("relationshipType") for r in rels}
        assert "trainedOn" in rel_types
        assert "testedOn" in rel_types


def test_loom_model_hyperparameters() -> None:
    """Test set_model_hyperparameters records key-value pairs on the model,
    each with its own per-key provenance Annotation entry (not one shared
    note for the whole dict)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_hparams.json"

        with loom.run(output_file) as run:
            run.set_model("test-model-hparams")
            run.add_dataset("train.txt")
            # Simulate post-training hyperparameter capture
            run.set_model_hyperparameters({"lr": "0.1", "epoch": "5", "dim": "100"})

        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]
        models = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert len(models) == 1
        model_id = models[0]["spdxId"]
        hparams = models[0].get("ai_hyperparameter", [])
        assert len(hparams) == 3
        hparam_dict = {h["key"]: h["value"] for h in hparams}
        assert hparam_dict["lr"] == "0.1"
        assert hparam_dict["epoch"] == "5"
        assert hparam_dict["dim"] == "100"

        annotations = [
            e
            for e in graph
            if e["type"] == "Annotation" and e.get("subject") == model_id
        ]
        # One Annotation from set_model() (package note), one from the
        # post-hoc set_model_hyperparameters() update.
        assert len(annotations) == 2
        hparam_annotation = next(
            a
            for a in annotations
            if "hyperparameters.lr" in json.loads(a["statement"])["fields"]
        )
        fields = json.loads(hparam_annotation["statement"])["fields"]
        assert set(fields) == {
            "hyperparameters.lr",
            "hyperparameters.epoch",
            "hyperparameters.dim",
        }
        for key, location in (
            ("hyperparameters.lr", "lr"),
            ("hyperparameters.epoch", "epoch"),
            ("hyperparameters.dim", "dim"),
        ):
            assert fields[key]["location"] == location
            assert fields[key]["method"] == (
                "inspect_caller (tool: pitloom.loom, "
                "function: test_loom_model_hyperparameters)"
            )


def test_loom_set_model_hyperparameters_have_per_key_provenance() -> None:
    """set_model(hyperparameters=...) at creation time also gets per-key
    provenance, alongside the model's own package-source note."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_hparams_creation.json"

        with loom.run(output_file) as run:
            run.set_model(
                "test-model-hparams-creation",
                hyperparameters={"lr": "0.05", "batch_size": "32"},
            )
            run.add_dataset("train.txt")

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]
        models = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert len(models) == 1
        model_id = models[0]["spdxId"]

        annotations = [
            e
            for e in graph
            if e["type"] == "Annotation" and e.get("subject") == model_id
        ]
        assert len(annotations) == 1
        fields = json.loads(annotations[0]["statement"])["fields"]
        assert set(fields) == {
            "package",
            "hyperparameters.lr",
            "hyperparameters.batch_size",
        }
        assert fields["hyperparameters.lr"]["location"] == "lr"
        assert fields["hyperparameters.batch_size"]["location"] == "batch_size"


def test_loom_model_type() -> None:
    """Test set_model with model_type sets ai_typeOfModel."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_modeltype.json"

        with loom.run(output_file):
            loom.set_model("test-model-type", model_type="supervised")
            loom.add_dataset("train.txt")

        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]
        models = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert len(models) == 1
        assert "supervised" in models[0].get("ai_typeOfModel", [])


def test_loom_dataset_lineage() -> None:
    """Test add_input/output_dataset creates hasInput relationship for lineage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_lineage.json"

        with loom.run(output_file):
            loom.add_input_dataset("rawdata/neg.txt", dataset_type="text")
            loom.add_input_dataset("rawdata/pos.txt", dataset_type="text")
            loom.add_output_dataset(
                "data/train.txt",
                dataset_type="text",
                data_preprocessing=["tokenization", "normalization"],
            )

        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]

        datasets = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert len(datasets) == 3
        dataset_names = {d["name"] for d in datasets}
        assert "rawdata/neg.txt" in dataset_names
        assert "rawdata/pos.txt" in dataset_names
        assert "data/train.txt" in dataset_names

        output_ds = next(d for d in datasets if d["name"] == "data/train.txt")
        assert "tokenization" in output_ds.get("dataset_dataPreprocessing", [])
        assert "normalization" in output_ds.get("dataset_dataPreprocessing", [])

        # hasInput (lineage) plus generates (this test file -> the output
        # dataset, since no model was set but an output dataset was declared).
        rels = _relationships(graph)
        assert len(rels) == 2
        has_input = [r for r in rels if r.get("relationshipType") == "hasInput"]
        assert len(has_input) == 1
        rel = has_input[0]
        output_id = output_ds.get("@id", output_ds.get("spdxId"))
        assert rel["from"] == output_id
        assert len(rel["to"]) == 2

        generates = [r for r in rels if r.get("relationshipType") == "generates"]
        assert len(generates) == 1
        assert generates[0]["to"] == [output_id]


def test_loom_generates_relationships_are_lifecycle_scoped_build() -> None:
    """``generates`` edges (script -> model/output datasets) are emitted as
    ``LifecycleScopedRelationship`` with ``scope: build`` -- the producing
    script is a build-time step, not something that runs in the shipped
    artifact."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_scope.json"

        with loom.run(output_file):
            loom.set_model("scoped-model")
            loom.add_dataset("train.txt")

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]
        generates = [
            e
            for e in graph
            if e.get("type") == "LifecycleScopedRelationship"
            and e.get("relationshipType") == "generates"
        ]
        assert len(generates) == 1
        assert generates[0]["scope"] == "build"
        # Plain "Relationship"-typed elements must not include a generates
        # edge -- it was reclassified, not duplicated.
        assert not any(
            e.get("type") == "Relationship" and e.get("relationshipType") == "generates"
            for e in graph
        )


def test_loom_output_dataset_input_datasets_scopes_lineage() -> None:
    """A single accumulating run covering multiple independent preprocessing
    stages (e.g. train/valid/test splits) keeps each output's ``hasInput``
    lineage scoped to only the inputs named via ``input_datasets=`` --
    instead of every input the run has seen, avoiding cross-contamination
    between splits."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_grouped_lineage.json"

        with loom.run(output_file):
            loom.add_input_dataset("rawdata/train/pos.txt")
            loom.add_input_dataset("rawdata/train/neg.txt")
            loom.add_output_dataset(
                "data/train.txt",
                input_datasets=["rawdata/train/pos.txt", "rawdata/train/neg.txt"],
            )

            loom.add_input_dataset("rawdata/valid/pos.txt")
            loom.add_input_dataset("rawdata/valid/neg.txt")
            loom.add_output_dataset(
                "data/valid.txt",
                input_datasets=["rawdata/valid/pos.txt", "rawdata/valid/neg.txt"],
            )

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]
        datasets = {
            d["name"]: d for d in graph if d["type"] == "dataset_DatasetPackage"
        }
        assert len(datasets) == 6

        has_input = [
            e
            for e in graph
            if e.get("type") in ("Relationship", "LifecycleScopedRelationship")
            and e.get("relationshipType") == "hasInput"
        ]
        assert len(has_input) == 2

        train_rel = next(
            r for r in has_input if r["from"] == datasets["data/train.txt"]["spdxId"]
        )
        assert set(train_rel["to"]) == {
            datasets["rawdata/train/pos.txt"]["spdxId"],
            datasets["rawdata/train/neg.txt"]["spdxId"],
        }

        valid_rel = next(
            r for r in has_input if r["from"] == datasets["data/valid.txt"]["spdxId"]
        )
        assert set(valid_rel["to"]) == {
            datasets["rawdata/valid/pos.txt"]["spdxId"],
            datasets["rawdata/valid/neg.txt"]["spdxId"],
        }
