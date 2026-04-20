# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration and unit tests for the pitloom.loom module."""

import json
import tempfile
from pathlib import Path

from pitloom import loom


def test_loom_shoot_as_context_manager() -> None:
    """Test using loom.shoot as a context manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_ctx.json"

        with loom.shoot(output_file):
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
        assert "test_loom_shoot_as_context_manager" in models[0].get("comment", "")
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
            "test_loom_shoot_as_context_manager" in d.get("comment", "")
            for d in datasets
        )

        # Verify relationships
        rels = [e for e in graph if e["type"] == "Relationship"]
        assert len(rels) == 2
        for rel in rels:
            assert rel.get("relationshipType", rel.get("spdxId")) == "trainedOn"
            assert rel["from"] == model_id
            assert len(rel["to"]) == 1
            assert any(d.get("@id", d.get("spdxId")) == rel["to"][0] for d in datasets)


def test_loom_shoot_as_decorator() -> None:
    """Test using loom.shoot as a function decorator."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_dec.json"

        @loom.shoot(output_file)
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


def test_loom_shoot_with_exception() -> None:
    """Test that a fragment is NOT generated if an exception occurs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_error.json"

        class DummyError(Exception):
            """Simulates a training failure."""

        try:
            with loom.shoot(output_file):
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

        with loom.shoot(output_file):
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

        rels = [e for e in graph if e["type"] == "Relationship"]
        rel_types = {r.get("relationshipType") for r in rels}
        assert "trainedOn" in rel_types
        assert "testedOn" in rel_types


def test_loom_model_hyperparameters() -> None:
    """Test set_model_hyperparameters records key-value pairs on the model."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_hparams.json"

        with loom.shoot(output_file) as shot:
            shot.set_model("test-model-hparams")
            shot.add_dataset("train.txt")
            # Simulate post-training hyperparameter capture
            shot.set_model_hyperparameters({"lr": "0.1", "epoch": "5", "dim": "100"})

        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]
        models = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert len(models) == 1
        hparams = models[0].get("ai_hyperparameter", [])
        assert len(hparams) == 3
        hparam_dict = {h["key"]: h["value"] for h in hparams}
        assert hparam_dict["lr"] == "0.1"
        assert hparam_dict["epoch"] == "5"
        assert hparam_dict["dim"] == "100"


def test_loom_model_type() -> None:
    """Test set_model with model_type sets ai_typeOfModel."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_modeltype.json"

        with loom.shoot(output_file):
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
    """Test add_input/output_dataset creates hasInput relationship for dataset lineage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_lineage.json"

        with loom.shoot(output_file):
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

        rels = [e for e in graph if e["type"] == "Relationship"]
        assert len(rels) == 1
        rel = rels[0]
        assert rel.get("relationshipType") == "hasInput"
        output_id = output_ds.get("@id", output_ds.get("spdxId"))
        assert rel["from"] == output_id
        assert len(rel["to"]) == 2
