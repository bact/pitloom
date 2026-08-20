# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.loom hyperparameters provenance, dataset lineage, and scopes.

See also:
- :mod:`tests.core.test_loom` for loom.run() basics and validation datasets.
- :mod:`tests.core.test_loom_creators` for creators, tools, and comments.
- :mod:`tests.core.test_loom_registry` for registry and script file / generates edges.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pitloom import loom

from .conftest import _relationships


def test_loom_model_hyperparameters() -> None:
    """Test set_model_hyperparameters records key-value pairs on the model."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_hparams.json"

        with loom.run(output_file) as run:
            run.set_model("test-model-hparams")
            run.add_dataset("train.txt")
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
    """set_model(hyperparameters=...) at creation time also gets per-key provenance."""
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
    """generates edges are emitted as LifecycleScopedRelationship with scope: build."""
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
        assert not any(
            e.get("type") == "Relationship" and e.get("relationshipType") == "generates"
            for e in graph
        )


def test_loom_output_dataset_input_datasets_scopes_lineage() -> None:
    """Scoped input_datasets avoids cross-contamination between splits."""
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
