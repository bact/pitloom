# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration and unit tests for the pitloom.loom module."""

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.__about__ import __version__
from pitloom.core.creation import CreationMetadata


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

        # Verify relationships
        rels = [e for e in graph if e["type"] == "Relationship"]
        assert len(rels) == 2
        for rel in rels:
            assert rel.get("relationshipType", rel.get("spdxId")) == "trainedOn"
            assert rel["from"] == model_id
            assert len(rel["to"]) == 1
            assert any(d.get("@id", d.get("spdxId")) == rel["to"][0] for d in datasets)


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

        rels = [e for e in graph if e["type"] == "Relationship"]
        rel_types = {r.get("relationshipType") for r in rels}
        assert "trainedOn" in rel_types
        assert "testedOn" in rel_types


def test_loom_model_hyperparameters() -> None:
    """Test set_model_hyperparameters records key-value pairs on the model."""
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

        rels = [e for e in graph if e["type"] == "Relationship"]
        assert len(rels) == 1
        rel = rels[0]
        assert rel.get("relationshipType") == "hasInput"
        output_id = output_ds.get("@id", output_ds.get("spdxId"))
        assert rel["from"] == output_id
        assert len(rel["to"]) == 2


def test_loom_run_default_comment() -> None:
    """A fragment's CreationInfo.comment defaults to a loom-SDK provenance note."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_comment.json"

        with loom.run(output_file):
            loom.set_model("test-model")

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        creation_infos = [e for e in data["@graph"] if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert creation_infos[0]["comment"] == (
            f"Generated via Pitloom loom SDK v{__version__} (script/notebook capture)"
        )


def test_loom_run_custom_comment() -> None:
    """An explicit creation_comment overrides the default loom-SDK provenance note."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_custom_comment.json"

        creation = CreationMetadata(
            creation_comment="Generated during nightly training job"
        )
        with loom.run(output_file, creation_metadata=creation):
            loom.set_model("test-model")

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        creation_infos = [e for e in data["@graph"] if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert creation_infos[0]["comment"] == "Generated during nightly training job"


def test_loom_run_creator_is_software_agent_and_tool() -> None:
    """A fragment's createdBy is the SoftwareAgent "Pitloom" (not a Person) and
    createdUsing is the Tool "Pitloom" with a versioned summary."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_agent.json"

        with loom.run(output_file):
            loom.set_model("test-model")

        with open(output_file, encoding="utf-8") as f:
            graph = json.load(f)["@graph"]

        by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        ci = creation_infos[0]

        agents = [by_id[ref] for ref in ci["createdBy"]]
        assert [a["type"] for a in agents] == ["SoftwareAgent"]
        assert agents[0]["name"] == "Pitloom"
        assert not [e for e in graph if e["type"] == "Person"]

        tools = [by_id[ref] for ref in ci["createdUsing"]]
        assert [t["type"] for t in tools] == ["Tool"]
        assert tools[0]["name"] == "Pitloom"
        assert tools[0]["summary"] == f"Pitloom {__version__}"


def _run_creation_info(
    output_file: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (createdBy agents, CreationInfo) from a written fragment."""
    with open(output_file, encoding="utf-8") as f:
        graph = json.load(f)["@graph"]
    by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
    ci = next(e for e in graph if e["type"] == "CreationInfo")
    return [by_id[ref] for ref in ci["createdBy"]], ci


def test_loom_run_named_person_creator() -> None:
    """loom.run(creation_metadata=CreationMetadata(creator_name=...)) records a Person
    in createdBy, on par with the CLI."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        creation = CreationMetadata(creator_name="Alice", creator_email="a@ex.com")
        with loom.run(output_file, creation_metadata=creation):
            loom.set_model("test-model")

        agents, _ = _run_creation_info(output_file)
        assert [a["type"] for a in agents] == ["Person"]
        assert agents[0]["name"] == "Alice"


def test_loom_run_organization_creator() -> None:
    """creator_type='organization' on the CreationMetadata records an
    Organization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        creation = CreationMetadata(
            creator_name="Acme Corp", creator_type="organization"
        )
        with loom.run(output_file, creation_metadata=creation):
            loom.set_model("test-model")

        agents, _ = _run_creation_info(output_file)
        assert [a["type"] for a in agents] == ["Organization"]
        assert agents[0]["name"] == "Acme Corp"


@pytest.mark.parametrize(
    ("creator_type", "expected_element_type"),
    [
        ("software-agent", "SoftwareAgent"),
        ("agent", "Agent"),
    ],
)
def test_loom_run_software_agent_and_generic_agent_creator(
    creator_type: str, expected_element_type: str
) -> None:
    """creator_type also allows a named SoftwareAgent or the generic Agent,
    not just Person/Organization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        creation = CreationMetadata(creator_name="CI Bot", creator_type=creator_type)
        with loom.run(output_file, creation_metadata=creation):
            loom.set_model("test-model")

        agents, _ = _run_creation_info(output_file)
        assert [a["type"] for a in agents] == [expected_element_type]
        assert agents[0]["name"] == "CI Bot"


def test_loom_run_invalid_creator_type_raises() -> None:
    """An unrecognised creator_type raises ValueError rather than silently
    falling back to Person."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        creation = CreationMetadata(creator_name="Bot", creator_type="robot")
        with pytest.raises(ValueError, match="Invalid creator_type"):
            with loom.run(output_file, creation_metadata=creation):
                loom.set_model("test-model")


def test_loom_run_suppress_tool_and_fixed_datetime() -> None:
    """creation_tool=None omits createdUsing; creation_datetime is
    normalised into created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        creation = CreationMetadata(
            creation_tool=None,
            creation_datetime="2026-01-15T10:00:00Z",
        )
        with loom.run(output_file, creation_metadata=creation):
            loom.set_model("test-model")

        _, ci = _run_creation_info(output_file)
        assert "createdUsing" not in ci
        assert ci["created"] == "2026-01-15T10:00:00Z"
