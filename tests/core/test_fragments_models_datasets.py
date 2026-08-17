# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for AI model, dataset, and training run fragment merging."""

# ruff: noqa: F403, F405
from __future__ import annotations

from .conftest import (
    _AI_MODEL_FRAGMENT,
    _DATASET_FRAGMENT,
    _TRAINING_RUN_FRAGMENT,
    _by_type,
    _entries,
    _hyperparams,
    _merge_and_parse,
    _metrics,
    _relationships,
    _resolve,
)


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

        energy = _resolve(pkg.get("ai_energyConsumption"), index)
        assert isinstance(energy, dict), "ai_energyConsumption was dropped during merge"

        training = _entries(energy, "ai_trainingEnergyConsumption", index)
        assert len(training) == 1
        assert training[0].get("ai_energyQuantity") == "0.5"
        assert training[0].get("ai_energyUnit") == "kilowattHour"

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
        rels = _relationships(graph)
        trained_on = [r for r in rels if r.get("relationshipType") == "trainedOn"]
        assert len(trained_on) == 1, "trainedOn relationship was dropped during merge"

    def test_tested_on_relationship_present(self) -> None:
        graph, _ = _merge_and_parse(_TRAINING_RUN_FRAGMENT)
        rels = _relationships(graph)
        tested_on = [r for r in rels if r.get("relationshipType") == "testedOn"]
        assert len(tested_on) == 1, "testedOn relationship was dropped during merge"

    def test_trained_on_provenance_links_correct(self) -> None:
        """trainedOn must point from the AI model to the training dataset."""
        graph, _ = _merge_and_parse(_TRAINING_RUN_FRAGMENT)
        rels = _relationships(graph)
        trained_on = next(r for r in rels if r.get("relationshipType") == "trainedOn")
        assert "linear-regressor-01" in trained_on["from"]
        assert any("tabular-train-01" in t for t in trained_on["to"])

    def test_tested_on_provenance_links_correct(self) -> None:
        """testedOn must point from the AI model to the test dataset."""
        graph, _ = _merge_and_parse(_TRAINING_RUN_FRAGMENT)
        rels = _relationships(graph)
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
