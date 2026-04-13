# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for SBOM fragment merging — verifies that informational fields
from SPDX 3 fragment files are not dropped during the stitch/merge step.

Fixtures live in tests/fixtures/fragments/:
  ai-model-fragment.spdx3.json       — ai_AIPackage with full AI metadata
  dataset-fragment.spdx3.json        — dataset_DatasetPackage with dataset metadata
  training-run-fragment.spdx3.json   — loom.shoot()-style combined fragment:
                                        ai_AIPackage + 2 datasets + trainedOn/testedOn

Implementation note
-------------------
The spdx-python-model library serialises anonymous (blank) node objects —
DictionaryEntry, ai_EnergyConsumption, ai_EnergyConsumptionDescription — as
separate @graph entries referenced by blank-node IDs like ``_:DictionaryEntry0``.
The ``_resolve`` / ``_entries`` helpers below dereference those IDs so that
tests can navigate nested structures without depending on blank-node internals.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_sbom
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.creation import CreationMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter

_FRAGMENTS_DIR = Path(__file__).parent / "fixtures" / "fragments"

_AI_MODEL_FRAGMENT = "ai-model-fragment.spdx3.json"
_DATASET_FRAGMENT = "dataset-fragment.spdx3.json"
_TRAINING_RUN_FRAGMENT = "training-run-fragment.spdx3.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _merge_and_parse(*fragment_names: str) -> tuple[list[dict], dict[str, dict]]:
    """Merge named fragments into a fresh exporter; return ``(graph, index)``.

    ``index`` maps every blank-node ``@id`` to its graph entry so that
    callers can resolve references like ``'_:DictionaryEntry0'`` to
    ``{'key': 'lr', 'value': '0.01', 'type': 'DictionaryEntry'}``.
    """
    exporter = Spdx3JsonExporter()
    merge_fragments(_FRAGMENTS_DIR, list(fragment_names), exporter)
    data = json.loads(exporter.to_json(pretty=True))
    graph: list[dict] = data.get("@graph", [])
    index: dict[str, dict] = {e["@id"]: e for e in graph if "@id" in e}
    return graph, index


def _by_type(graph: list[dict], type_name: str) -> list[dict]:
    return [e for e in graph if e.get("type") == type_name]


def _resolve(ref: Any, index: dict[str, dict]) -> Any:
    """Dereference a blank-node string; return non-blank values unchanged."""
    if isinstance(ref, str) and ref.startswith("_:"):
        return index.get(ref, ref)
    return ref


def _entries(element: dict, field: str, index: dict[str, dict]) -> list[dict]:
    """Return all resolved dict entries for a list field that uses blank refs."""
    result = []
    for ref in element.get(field, []):
        resolved = _resolve(ref, index)
        if isinstance(resolved, dict):
            result.append(resolved)
    return result


def _hyperparams(element: dict, index: dict[str, dict]) -> dict[str, str]:
    """Return ``{key: value}`` for all ai_hyperparameter entries."""
    return {e["key"]: e["value"] for e in _entries(element, "ai_hyperparameter", index)}


def _metrics(element: dict, index: dict[str, dict]) -> dict[str, str]:
    """Return ``{key: value}`` for all ai_metric entries."""
    return {e["key"]: e["value"] for e in _entries(element, "ai_metric", index)}


# ---------------------------------------------------------------------------
# AI model fragment — all AI-profile fields must survive the merge
# ---------------------------------------------------------------------------


class TestAiModelFragment:
    def test_ai_package_present(self) -> None:
        graph, _ = _merge_and_parse(_AI_MODEL_FRAGMENT)
        ai_pkgs = _by_type(graph, "ai_AIPackage")
        assert len(ai_pkgs) == 1, "Expected exactly one ai_AIPackage in merged output"

    def test_name_and_version_preserved(self) -> None:
        graph, _ = _merge_and_parse(_AI_MODEL_FRAGMENT)
        pkg = _by_type(graph, "ai_AIPackage")[0]
        assert pkg["name"] == "resnet-tiny-classifier"
        assert pkg["software_packageVersion"] == "1.0.0"

    def test_type_of_model_preserved(self) -> None:
        graph, _ = _merge_and_parse(_AI_MODEL_FRAGMENT)
        pkg = _by_type(graph, "ai_AIPackage")[0]
        type_of_model = pkg.get("ai_typeOfModel", [])
        assert "classification" in type_of_model
        assert "convolutional" in type_of_model

    def test_hyperparameters_all_preserved(self) -> None:
        graph, index = _merge_and_parse(_AI_MODEL_FRAGMENT)
        pkg = _by_type(graph, "ai_AIPackage")[0]
        hp = _hyperparams(pkg, index)
        assert hp.get("learning_rate") == "0.001"
        assert hp.get("batch_size") == "32"
        assert hp.get("epochs") == "50"
        assert len(hp) == 3, f"Expected 3 hyperparameters, got {len(hp)}: {hp}"

    def test_metrics_all_preserved(self) -> None:
        graph, index = _merge_and_parse(_AI_MODEL_FRAGMENT)
        pkg = _by_type(graph, "ai_AIPackage")[0]
        m = _metrics(pkg, index)
        assert m.get("accuracy") == "0.9234"
        assert m.get("f1") == "0.9187"
        assert len(m) == 2, f"Expected 2 metrics, got {len(m)}: {m}"

    def test_domain_preserved(self) -> None:
        graph, _ = _merge_and_parse(_AI_MODEL_FRAGMENT)
        pkg = _by_type(graph, "ai_AIPackage")[0]
        domain = pkg.get("ai_domain", [])
        assert "image classification" in domain
        assert "computer vision" in domain

    def test_autonomy_type_preserved(self) -> None:
        graph, _ = _merge_and_parse(_AI_MODEL_FRAGMENT)
        pkg = _by_type(graph, "ai_AIPackage")[0]
        assert pkg.get("ai_autonomyType") == "yes"

    def test_energy_consumption_preserved(self) -> None:
        graph, index = _merge_and_parse(_AI_MODEL_FRAGMENT)
        pkg = _by_type(graph, "ai_AIPackage")[0]

        # ai_energyConsumption is serialised as a blank-node reference
        energy = _resolve(pkg.get("ai_energyConsumption"), index)
        assert isinstance(energy, dict), "ai_energyConsumption was dropped during merge"

        # Training energy entry
        training = _entries(energy, "ai_trainingEnergyConsumption", index)
        assert len(training) == 1
        assert training[0].get("ai_energyQuantity") == "0.5"
        assert training[0].get("ai_energyUnit") == "kilowattHour"

        # Inference energy entry
        inference = _entries(energy, "ai_inferenceEnergyConsumption", index)
        assert len(inference) == 1
        assert inference[0].get("ai_energyQuantity") == "0.001"

    def test_sensitive_personal_info_preserved(self) -> None:
        graph, _ = _merge_and_parse(_AI_MODEL_FRAGMENT)
        pkg = _by_type(graph, "ai_AIPackage")[0]
        assert pkg.get("ai_useSensitivePersonalInformation") == "no"

    def test_description_preserved(self) -> None:
        graph, _ = _merge_and_parse(_AI_MODEL_FRAGMENT)
        pkg = _by_type(graph, "ai_AIPackage")[0]
        assert "image classification" in pkg.get("description", "")

    def test_primary_purpose_preserved(self) -> None:
        graph, _ = _merge_and_parse(_AI_MODEL_FRAGMENT)
        pkg = _by_type(graph, "ai_AIPackage")[0]
        assert pkg.get("software_primaryPurpose") == "model"


# ---------------------------------------------------------------------------
# Dataset fragment — all dataset-profile fields must survive the merge
# ---------------------------------------------------------------------------


class TestDatasetFragment:
    def test_dataset_package_present(self) -> None:
        graph, _ = _merge_and_parse(_DATASET_FRAGMENT)
        ds_pkgs = _by_type(graph, "dataset_DatasetPackage")
        assert len(ds_pkgs) == 1, "Expected exactly one dataset_DatasetPackage"

    def test_name_preserved(self) -> None:
        graph, _ = _merge_and_parse(_DATASET_FRAGMENT)
        pkg = _by_type(graph, "dataset_DatasetPackage")[0]
        assert pkg["name"] == "tiny-image-dataset"

    def test_dataset_type_preserved(self) -> None:
        graph, _ = _merge_and_parse(_DATASET_FRAGMENT)
        pkg = _by_type(graph, "dataset_DatasetPackage")[0]
        assert pkg.get("dataset_datasetType") == ["image"]

    def test_dataset_size_preserved(self) -> None:
        graph, _ = _merge_and_parse(_DATASET_FRAGMENT)
        pkg = _by_type(graph, "dataset_DatasetPackage")[0]
        assert pkg.get("dataset_datasetSize") == 50000

    def test_dataset_availability_preserved(self) -> None:
        graph, _ = _merge_and_parse(_DATASET_FRAGMENT)
        pkg = _by_type(graph, "dataset_DatasetPackage")[0]
        assert pkg.get("dataset_datasetAvailability") == "directDownload"

    def test_description_preserved(self) -> None:
        graph, _ = _merge_and_parse(_DATASET_FRAGMENT)
        pkg = _by_type(graph, "dataset_DatasetPackage")[0]
        assert "image dataset" in pkg.get("description", "")

    def test_download_location_preserved(self) -> None:
        graph, _ = _merge_and_parse(_DATASET_FRAGMENT)
        pkg = _by_type(graph, "dataset_DatasetPackage")[0]
        assert "example.org/datasets/tiny-image" in pkg.get(
            "software_downloadLocation", ""
        )


# ---------------------------------------------------------------------------
# Training-run fragment — relationships and combined elements preserved
# ---------------------------------------------------------------------------


class TestTrainingRunFragment:
    def test_ai_package_present(self) -> None:
        graph, _ = _merge_and_parse(_TRAINING_RUN_FRAGMENT)
        ai_pkgs = _by_type(graph, "ai_AIPackage")
        assert len(ai_pkgs) == 1

    def test_two_dataset_packages_present(self) -> None:
        graph, _ = _merge_and_parse(_TRAINING_RUN_FRAGMENT)
        ds_pkgs = _by_type(graph, "dataset_DatasetPackage")
        assert len(ds_pkgs) == 2, f"Expected 2 datasets, got {len(ds_pkgs)}"

    def test_dataset_names_preserved(self) -> None:
        graph, _ = _merge_and_parse(_TRAINING_RUN_FRAGMENT)
        names = {e["name"] for e in _by_type(graph, "dataset_DatasetPackage")}
        assert "tabular-train-dataset" in names
        assert "tabular-test-dataset" in names

    def test_trained_on_relationship_present(self) -> None:
        graph, _ = _merge_and_parse(_TRAINING_RUN_FRAGMENT)
        rels = _by_type(graph, "Relationship")
        trained_on = [r for r in rels if r.get("relationshipType") == "trainedOn"]
        assert len(trained_on) == 1, "trainedOn relationship was dropped during merge"

    def test_tested_on_relationship_present(self) -> None:
        graph, _ = _merge_and_parse(_TRAINING_RUN_FRAGMENT)
        rels = _by_type(graph, "Relationship")
        tested_on = [r for r in rels if r.get("relationshipType") == "testedOn"]
        assert len(tested_on) == 1, "testedOn relationship was dropped during merge"

    def test_trained_on_provenance_links_correct(self) -> None:
        """trainedOn must point from the AI model to the training dataset."""
        graph, _ = _merge_and_parse(_TRAINING_RUN_FRAGMENT)
        rels = _by_type(graph, "Relationship")
        trained_on = next(r for r in rels if r.get("relationshipType") == "trainedOn")
        assert "linear-regressor-01" in trained_on["from"]
        assert any("tabular-train-01" in t for t in trained_on["to"])

    def test_tested_on_provenance_links_correct(self) -> None:
        """testedOn must point from the AI model to the test dataset."""
        graph, _ = _merge_and_parse(_TRAINING_RUN_FRAGMENT)
        rels = _by_type(graph, "Relationship")
        tested_on = next(r for r in rels if r.get("relationshipType") == "testedOn")
        assert "linear-regressor-01" in tested_on["from"]
        assert any("tabular-test-01" in t for t in tested_on["to"])

    def test_ai_hyperparameters_preserved(self) -> None:
        graph, index = _merge_and_parse(_TRAINING_RUN_FRAGMENT)
        pkg = _by_type(graph, "ai_AIPackage")[0]
        hp = _hyperparams(pkg, index)
        assert hp.get("lr") == "0.01"
        assert hp.get("momentum") == "0.9"

    def test_ai_metrics_preserved(self) -> None:
        graph, index = _merge_and_parse(_TRAINING_RUN_FRAGMENT)
        pkg = _by_type(graph, "ai_AIPackage")[0]
        m = _metrics(pkg, index)
        assert m.get("val_loss") == "0.0423"
        assert m.get("val_accuracy") == "0.9876"

    def test_dataset_sizes_preserved(self) -> None:
        graph, _ = _merge_and_parse(_TRAINING_RUN_FRAGMENT)
        sizes = {
            e["name"]: e.get("dataset_datasetSize")
            for e in _by_type(graph, "dataset_DatasetPackage")
        }
        assert sizes["tabular-train-dataset"] == 10000
        assert sizes["tabular-test-dataset"] == 2000


# ---------------------------------------------------------------------------
# Multiple fragments merged together — no element from any fragment dropped
# ---------------------------------------------------------------------------


class TestMultipleFragmentsMerge:
    def test_ai_packages_from_all_fragments_present(self) -> None:
        """Both ai_AIPackage elements (one per AI fragment) must appear."""
        graph, _ = _merge_and_parse(
            _AI_MODEL_FRAGMENT, _DATASET_FRAGMENT, _TRAINING_RUN_FRAGMENT
        )
        ai_pkgs = _by_type(graph, "ai_AIPackage")
        assert len(ai_pkgs) == 2, f"Expected 2 ai_AIPackage elements, got {len(ai_pkgs)}"

    def test_all_dataset_packages_from_all_fragments_present(self) -> None:
        """All 3 dataset_DatasetPackage elements (1 + 2) must appear."""
        graph, _ = _merge_and_parse(
            _AI_MODEL_FRAGMENT, _DATASET_FRAGMENT, _TRAINING_RUN_FRAGMENT
        )
        ds_pkgs = _by_type(graph, "dataset_DatasetPackage")
        assert len(ds_pkgs) == 3, (
            f"Expected 3 dataset_DatasetPackage elements, got {len(ds_pkgs)}"
        )

    def test_all_relationships_from_all_fragments_present(self) -> None:
        """trainedOn + testedOn relationships from training-run fragment must survive."""
        graph, _ = _merge_and_parse(
            _AI_MODEL_FRAGMENT, _DATASET_FRAGMENT, _TRAINING_RUN_FRAGMENT
        )
        rels = _by_type(graph, "Relationship")
        rel_types = {r.get("relationshipType") for r in rels}
        assert "trainedOn" in rel_types
        assert "testedOn" in rel_types

    def test_ai_package_names_distinct_across_fragments(self) -> None:
        """Each fragment contributes a uniquely-named AI package."""
        graph, _ = _merge_and_parse(
            _AI_MODEL_FRAGMENT, _DATASET_FRAGMENT, _TRAINING_RUN_FRAGMENT
        )
        names = {e["name"] for e in _by_type(graph, "ai_AIPackage")}
        assert "resnet-tiny-classifier" in names
        assert "linear-regressor" in names

    def test_all_dataset_names_distinct_across_fragments(self) -> None:
        graph, _ = _merge_and_parse(
            _AI_MODEL_FRAGMENT, _DATASET_FRAGMENT, _TRAINING_RUN_FRAGMENT
        )
        names = {e["name"] for e in _by_type(graph, "dataset_DatasetPackage")}
        assert "tiny-image-dataset" in names
        assert "tabular-train-dataset" in names
        assert "tabular-test-dataset" in names

    def test_ai_fields_not_cross_contaminated(self) -> None:
        """Each AI package must have only its own hyperparameters, not the other's."""
        graph, index = _merge_and_parse(
            _AI_MODEL_FRAGMENT, _DATASET_FRAGMENT, _TRAINING_RUN_FRAGMENT
        )
        ai_pkgs = _by_type(graph, "ai_AIPackage")
        resnet = next(p for p in ai_pkgs if p["name"] == "resnet-tiny-classifier")
        linear = next(p for p in ai_pkgs if p["name"] == "linear-regressor")

        resnet_hp = _hyperparams(resnet, index)
        linear_hp = _hyperparams(linear, index)

        # Each model has only its own keys
        assert "learning_rate" in resnet_hp
        assert "lr" not in resnet_hp
        assert "lr" in linear_hp
        assert "learning_rate" not in linear_hp


# ---------------------------------------------------------------------------
# End-to-end via generate_sbom — fragment elements survive full pipeline
# ---------------------------------------------------------------------------


_PYPROJECT_TEMPLATE = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "fragment-e2e-app"
version = "0.1.0"
description = "End-to-end fragment test app"

[tool.pitloom]
pretty = true

[tool.pitloom.fragments]
files = [
    "ai-model-fragment.spdx3.json",
    "training-run-fragment.spdx3.json",
]
"""


def test_generate_sbom_includes_ai_model_fragment_elements() -> None:
    """Full generate_sbom pipeline must include elements from listed fragments."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Set up project
        (tmppath / "pyproject.toml").write_text(_PYPROJECT_TEMPLATE)

        # Copy fixtures into the project dir (fragments paths are relative to it)
        for name in (_AI_MODEL_FRAGMENT, _TRAINING_RUN_FRAGMENT):
            shutil.copy(_FRAGMENTS_DIR / name, tmppath / name)

        sbom_json = generate_sbom(
            tmppath,
            creation_info=CreationMetadata(creator_name="Test"),
        )
        data = json.loads(sbom_json)
        graph: list[dict] = data.get("@graph", [])
        index: dict[str, dict] = {e["@id"]: e for e in graph if "@id" in e}

        # ai_AIPackage elements from both fragments must be in the final SBOM
        ai_pkgs = _by_type(graph, "ai_AIPackage")
        assert len(ai_pkgs) == 2, f"Expected 2 ai_AIPackage, got {len(ai_pkgs)}"

        names = {p["name"] for p in ai_pkgs}
        assert "resnet-tiny-classifier" in names
        assert "linear-regressor" in names

        # Provenance relationships must also survive
        rels = _by_type(graph, "Relationship")
        rel_types = {r.get("relationshipType") for r in rels}
        assert "trainedOn" in rel_types
        assert "testedOn" in rel_types

        # AI metadata must not be stripped from the fragment elements
        resnet = next(p for p in ai_pkgs if p["name"] == "resnet-tiny-classifier")
        hp = _hyperparams(resnet, index)
        assert hp.get("learning_rate") == "0.001"
        assert hp.get("batch_size") == "32"
        assert hp.get("epochs") == "50"

        linear = next(p for p in ai_pkgs if p["name"] == "linear-regressor")
        m = _metrics(linear, index)
        assert m.get("val_loss") == "0.0423"
        assert m.get("val_accuracy") == "0.9876"


def test_generate_sbom_includes_dataset_fragment_elements() -> None:
    """dataset_DatasetPackage from fragment must appear in generate_sbom output."""
    pyproject = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "dataset-e2e-app"
version = "0.1.0"

[tool.pitloom]
pretty = true

[tool.pitloom.fragments]
files = ["dataset-fragment.spdx3.json"]
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject)
        shutil.copy(_FRAGMENTS_DIR / _DATASET_FRAGMENT, tmppath / _DATASET_FRAGMENT)

        sbom_json = generate_sbom(
            tmppath,
            creation_info=CreationMetadata(creator_name="Test"),
        )
        graph = json.loads(sbom_json).get("@graph", [])

        ds_pkgs = _by_type(graph, "dataset_DatasetPackage")
        assert len(ds_pkgs) == 1
        pkg = ds_pkgs[0]
        assert pkg["name"] == "tiny-image-dataset"
        assert pkg.get("dataset_datasetType") == ["image"]
        assert pkg.get("dataset_datasetSize") == 50000
        assert pkg.get("dataset_datasetAvailability") == "directDownload"


# ---------------------------------------------------------------------------
# Graceful handling of missing fragment
# ---------------------------------------------------------------------------


def test_missing_fragment_does_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    """A fragment file that does not exist must be skipped with a warning."""
    exporter = Spdx3JsonExporter()
    with caplog.at_level(logging.WARNING, logger="pitloom.assemble.spdx3.fragments"):
        merge_fragments(
            _FRAGMENTS_DIR,
            ["nonexistent-fragment.spdx3.json"],
            exporter,
        )
    # Object set must be empty — nothing merged
    data = json.loads(exporter.to_json())
    graph = data.get("@graph", [])
    assert len(graph) == 0

    # Warning must have been emitted
    assert any("nonexistent-fragment" in r.message for r in caplog.records)
