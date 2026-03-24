# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration and unit tests for the loom.bom module."""

import json
import tempfile
from pathlib import Path

from loom import bom


def test_bom_track_as_context_manager() -> None:
    """Test using bom.track as a context manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_ctx.json"

        with bom.track(output_file):
            bom.set_model("test-model-1")
            bom.add_dataset("test-dataset-1", dataset_type="text")
            bom.add_dataset("test-dataset-2", dataset_type="image")

        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        assert "@context" in data
        graph = data["@graph"]

        # Verify model
        models = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert len(models) == 1
        assert models[0]["name"] == "test-model-1"
        assert "test_bom_track_as_context_manager" in models[0].get("comment", "")
        assert "test_bom.py" in models[0].get("comment", "")
        model_id = models[0].get("@id", models[0].get("spdxId"))

        # Verify datasets
        datasets = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert len(datasets) == 2
        dataset_names = {d["name"] for d in datasets}
        assert "test-dataset-1" in dataset_names
        assert "test-dataset-2" in dataset_names
        assert all("test_bom.py" in d.get("comment", "") for d in datasets)
        assert all(
            "test_bom_track_as_context_manager" in d.get("comment", "")
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


def test_bom_track_as_decorator() -> None:
    """Test using bom.track as a function decorator."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_dec.json"

        @bom.track(output_file)
        def dummy_train_function() -> None:
            bom.set_model("test-model-2")
            bom.add_dataset("test-dataset-3", dataset_type="audio")

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
        assert "test_bom.py" in models[0].get("comment", "")

        datasets = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert len(datasets) == 1
        assert datasets[0]["name"] == "test-dataset-3"
        assert "dummy_train_function" in datasets[0].get("comment", "")
        assert "test_bom.py" in datasets[0].get("comment", "")


def test_bom_track_with_exception() -> None:
    """Test that a fragment is NOT generated if an exception occurs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_error.json"

        class DummyError(Exception):
            """Simulates a training failure."""

        try:
            with bom.track(output_file):
                bom.set_model("error-model")
                bom.add_dataset("error-dataset")
                raise DummyError("Something went wrong during training")
        except DummyError:
            pass

        # The JSON fragment should not have been created because the block failed
        assert not output_file.exists()
