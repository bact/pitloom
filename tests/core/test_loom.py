# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration and unit tests for the pitloom.loom module."""

import hashlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom import loom
from pitloom.__about__ import __version__
from pitloom.core.creation import CreationMetadata, Creator
from pitloom.ids import EntityEntry, FileEntry, IdRegistry

#: A ``LifecycleScopedRelationship`` (used for scoped ``generates`` edges) is
#: a ``Relationship`` subclass at the Python level, but serializes with its
#: own JSON-LD ``type`` -- match both.
_RELATIONSHIP_TYPES = ("Relationship", "LifecycleScopedRelationship")


def _relationships(graph: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in graph if e.get("type") in _RELATIONSHIP_TYPES]


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


def test_loom_output_dataset_unknown_input_name_warns_and_skips(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An ``input_datasets=`` name with no matching ``add_input_dataset()``
    call is dropped with a warning, not a crash -- likely a typo the
    developer should see."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_bad_lineage.json"

        with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
            with loom.run(output_file):
                loom.add_input_dataset("rawdata/pos.txt")
                loom.add_output_dataset(
                    "data/train.txt",
                    input_datasets=["rawdata/pos.txt", "rawdata/typo.txt"],
                )

        assert any("rawdata/typo.txt" in r.message for r in caplog.records)

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)
        graph = data["@graph"]
        has_input = [e for e in graph if e.get("relationshipType") == "hasInput"]
        assert len(has_input) == 1
        assert len(has_input[0]["to"]) == 1


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
    """loom.run(creation_metadata=CreationMetadata(creators=[Creator(...)])) records
    a Person in createdBy, on par with the CLI."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        creation = CreationMetadata(creators=[Creator(name="Alice", email="a@ex.com")])
        with loom.run(output_file, creation_metadata=creation):
            loom.set_model("test-model")

        agents, _ = _run_creation_info(output_file)
        assert [a["type"] for a in agents] == ["Person"]
        assert agents[0]["name"] == "Alice"


def test_loom_run_organization_creator() -> None:
    """type='organization' on a Creator records an Organization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        creation = CreationMetadata(
            creators=[Creator(name="Acme Corp", type="organization")]
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
    """A creator's type also allows a named SoftwareAgent or the generic Agent,
    not just Person/Organization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        creation = CreationMetadata(
            creators=[Creator(name="CI Bot", type=creator_type)]
        )
        with loom.run(output_file, creation_metadata=creation):
            loom.set_model("test-model")

        agents, _ = _run_creation_info(output_file)
        assert [a["type"] for a in agents] == [expected_element_type]
        assert agents[0]["name"] == "CI Bot"


def test_loom_run_invalid_creator_type_raises() -> None:
    """An unrecognised creator type raises ValueError rather than silently
    falling back to Person.

    Validation now happens eagerly in ``Creator.__post_init__`` (construction
    time) rather than later at fragment assembly, so the invalid type is
    rejected before ``loom.run`` is ever reached."""
    with pytest.raises(ValueError, match="Invalid creator type"):
        Creator(name="Bot", type="robot")


def test_loom_run_suppress_tool_and_fixed_datetime() -> None:
    """tools=[] omits createdUsing; creation_datetime is
    normalised into created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        creation = CreationMetadata(
            tools=[],
            creation_datetime="2026-01-15T10:00:00Z",
        )
        with loom.run(output_file, creation_metadata=creation):
            loom.set_model("test-model")

        _, ci = _run_creation_info(output_file)
        assert "createdUsing" not in ci
        assert ci["created"] == "2026-01-15T10:00:00Z"


# ---------------------------------------------------------------------------
# Registry consultation: verifiedUsing hashes, registered id reuse, hash
# mismatch warn+mint (see pitloom.ids.IdRegistry)
# ---------------------------------------------------------------------------

# An existing on-disk file, stable across the test run, used as a stand-in
# "dataset" so add_dataset()'s "name is an existing file" branch engages.
_EXISTING_FILE = "pyproject.toml"


def _sha256_of(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_loom_dataset_gets_verified_using_hash_when_file_exists() -> None:
    """A dataset name that is an existing file gets a SHA-256 verifiedUsing
    hash, even with no registry -- this is what lets merge's hash-fallback
    unification work without one."""
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
    """A dataset name that is not an existing file gets no verifiedUsing --
    unchanged legacy behaviour."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.set_model("test-model")
            loom.add_dataset("no-such-file-anywhere.txt")

        graph = json.loads(output_file.read_text())["@graph"]
        (ds,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert "verifiedUsing" not in ds


def test_loom_registry_id_reuse_for_dataset_and_model() -> None:
    """A dataset/model already registered gets the registry's spdxId, not a
    freshly minted one."""
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
    """A registry entry whose recorded hash no longer matches the file's
    current content is treated as unregistered: warn, then mint a fresh id
    rather than reusing the stale one."""
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


# ---------------------------------------------------------------------------
# Script File + generates relationships
# ---------------------------------------------------------------------------


def test_loom_training_run_emits_script_file_and_generates_edge() -> None:
    """A run that declares a model and a training dataset (add_dataset) gets
    a software_File for the calling script plus a generates edge to the
    model -- the heuristic default (generated=None)."""
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
            and e.get("name") == "tests/core/test_loom.py"
        ]
        assert len(script_files) == 1

        (model,) = [e for e in graph if e["type"] == "ai_AIPackage"]
        rels = _relationships(graph)
        generates = [r for r in rels if r.get("relationshipType") == "generates"]
        assert len(generates) == 1
        assert generates[0]["from"] == script_files[0]["spdxId"]
        assert generates[0]["to"] == [model["spdxId"]]


def test_loom_testedon_only_run_emits_hasdatafile_edge() -> None:
    """An evaluation-only run (model + validation dataset, no training
    dataset) gets no generates edge, but DOES get a hasDataFile edge and
    a script File."""
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
    """generated=True forces the generates edge even without a training
    dataset."""
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
    """generated=False suppresses the generates edge even with a training
    dataset declared, but emits hasDataFile."""
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
    """use_model is an explicit shortcut for set_model(generated=False),
    emitting hasDataFile even if a training dataset is accidentally declared."""
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
    """A preprocessing-style run (no model, only output datasets) gets a
    generates edge from the script to its output dataset(s)."""
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
    """When the caller cannot be resolved to an on-disk script (e.g. a REPL
    frame), no script File is emitted even for an otherwise-generates-worthy
    run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with patch("pitloom.loom._get_caller_script_path", return_value=None):
            with loom.run(output_file):
                loom.set_model("test-model")
                loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        assert not [e for e in graph if e["type"] == "software_File"]
        rels = _relationships(graph)
        assert not [r for r in rels if r.get("relationshipType") == "generates"]
