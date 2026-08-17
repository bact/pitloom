# ruff: noqa: F403, F405
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.ids import IdRegistry

from .conftest import *


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


class TestRegistryUnification:
    """The full workflow: `ids generate` -> loom runs -> generate_project_sbom."""

    @pytest.fixture()
    def merged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], IdRegistry]:
        _make_unify_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        _run_unify_pipeline(tmp_path)

        sbom_json = generate_project_sbom(tmp_path, creation_metadata=_fixed_creation())
        graph = json.loads(sbom_json).get("@graph", [])
        index = {e["spdxId"]: e for e in graph if "spdxId" in e}
        registry = IdRegistry.load(tmp_path / "loom-ids.json")
        return graph, index, registry

    def test_single_ai_package_under_registry_id(
        self, merged: tuple[list[dict[str, Any]], dict[str, dict[str, Any]], IdRegistry]
    ) -> None:
        graph, _, registry = merged
        ai_pkgs = _by_type(graph, "ai_AIPackage")
        assert len(ai_pkgs) == 1
        assert ai_pkgs[0]["spdxId"] == registry.entities["demo-model"].spdx_id

    def test_dataset_appears_once_and_lineage_chain_connects(
        self, merged: tuple[list[dict[str, Any]], dict[str, dict[str, Any]], IdRegistry]
    ) -> None:
        graph, _, registry = merged
        datasets = _by_type(graph, "dataset_DatasetPackage")
        by_name: dict[str, list[dict[str, Any]]] = {}
        for ds in datasets:
            by_name.setdefault(ds["name"], []).append(ds)
        assert len(by_name["data/train.txt"]) == 1
        assert len(by_name["data/raw.txt"]) == 1

        train_id = registry.files["data/train.txt"].spdx_id
        raw_id = registry.files["data/raw.txt"].spdx_id
        assert by_name["data/train.txt"][0]["spdxId"] == train_id
        assert by_name["data/raw.txt"][0]["spdxId"] == raw_id

        rels = _relationships(graph)
        model_id = registry.entities["demo-model"].spdx_id
        assert any(
            r["relationshipType"] == "hasInput"
            and r["from"] == train_id
            and raw_id in r["to"]
            for r in rels
        )
        assert any(
            r["relationshipType"] == "trainedOn"
            and r["from"] == model_id
            and train_id in r["to"]
            for r in rels
        )
        assert any(
            r["relationshipType"] == "testedOn"
            and r["from"] == model_id
            and raw_id in r["to"]
            for r in rels
        )

    def test_script_files_unified_with_wheel_files(
        self, merged: tuple[list[dict[str, Any]], dict[str, dict[str, Any]], IdRegistry]
    ) -> None:
        """The fragment's script File and the wheel's own File for the same
        script must be one element, and the generates edges hang off it."""
        graph, _, registry = merged
        train_script_id = registry.files["src/fragdemo/train.py"].spdx_id
        preprocess_script_id = registry.files["src/fragdemo/preprocess.py"].spdx_id

        files = _by_type(graph, "software_File")
        assert [f["spdxId"] for f in files].count(train_script_id) == 1
        assert [f["spdxId"] for f in files].count(preprocess_script_id) == 1

        rels = _relationships(graph)
        model_id = registry.entities["demo-model"].spdx_id
        train_txt_id = registry.files["data/train.txt"].spdx_id
        assert any(
            r["relationshipType"] == "generates"
            and r["from"] == train_script_id
            and model_id in r["to"]
            for r in rels
        )
        assert any(
            r["relationshipType"] == "generates"
            and r["from"] == preprocess_script_id
            and train_txt_id in r["to"]
            for r in rels
        )

    def test_profile_conformance_gains_ai_and_dataset(
        self, merged: tuple[list[dict[str, Any]], dict[str, dict[str, Any]], IdRegistry]
    ) -> None:
        graph, _, _ = merged
        docs = _by_type(graph, "SpdxDocument")
        assert len(docs) == 1
        conformance = docs[0]["profileConformance"]
        assert "ai" in conformance
        assert "dataset" in conformance

    def test_second_sbom_rooted_at_model(
        self, merged: tuple[list[dict[str, Any]], dict[str, dict[str, Any]], IdRegistry]
    ) -> None:
        graph, _, registry = merged
        docs = _by_type(graph, "SpdxDocument")
        sboms = _by_type(graph, "software_Sbom")
        assert len(sboms) == 2
        assert set(docs[0]["rootElement"]) == {s["spdxId"] for s in sboms}
        model_id = registry.entities["demo-model"].spdx_id
        assert any(s["rootElement"] == [model_id] for s in sboms)

    def test_single_pitloom_agent_and_tool(
        self, merged: tuple[list[dict[str, Any]], dict[str, dict[str, Any]], IdRegistry]
    ) -> None:
        """Each fragment mints its own 'Pitloom' agent/tool; structurally
        identical copies must collapse to one."""
        graph, _, _ = merged
        agents = [e for e in _by_type(graph, "SoftwareAgent") if e["name"] == "Pitloom"]
        tools = [e for e in _by_type(graph, "Tool") if e["name"] == "Pitloom"]
        assert len(agents) == 1
        assert len(tools) == 1

    def test_merge_is_deterministic(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_unify_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        _run_unify_pipeline(tmp_path)
        creation = _fixed_creation()
        first = generate_project_sbom(tmp_path, creation_metadata=creation)
        second = generate_project_sbom(tmp_path, creation_metadata=creation)
        assert first == second


class TestHashFallbackUnification:
    """Without any registry, identical content (SHA-256) still unifies;
    same name with different content never does."""

    @staticmethod
    def _two_runs(
        tmp_path: Path, mutate_between_runs: bool
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        data = tmp_path / "data"
        data.mkdir()
        (data / "train.txt").write_text("training data\n")

        with loom.run(tmp_path / "f1.spdx3.json") as run:
            run.add_output_dataset("data/train.txt")

        if mutate_between_runs:
            (data / "train.txt").write_text("training data CHANGED\n")

        with loom.run(tmp_path / "f2.spdx3.json") as run:
            run.set_model("m", generated=False)
            run.add_dataset("data/train.txt")

        exporter = Spdx3JsonExporter()
        merge_fragments(tmp_path, ["f1.spdx3.json", "f2.spdx3.json"], exporter)
        graph = json.loads(exporter.to_json(pretty=True)).get("@graph", [])
        index = {e["spdxId"]: e for e in graph if "spdxId" in e}
        return graph, index

    def test_same_content_unifies_without_registry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        graph, _ = self._two_runs(tmp_path, mutate_between_runs=False)
        datasets = [
            d
            for d in _by_type(graph, "dataset_DatasetPackage")
            if d["name"] == "data/train.txt"
        ]
        assert len(datasets) == 1
        # The trainedOn edge from fragment 2 must point at the surviving id.
        rels = _relationships(graph)
        trained = [r for r in rels if r["relationshipType"] == "trainedOn"]
        assert trained and trained[0]["to"] == [datasets[0]["spdxId"]]

    def test_different_content_stays_separate(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with caplog.at_level(
            logging.WARNING, logger="pitloom.assemble.spdx3.fragments"
        ):
            graph, _ = self._two_runs(tmp_path, mutate_between_runs=True)
        datasets = [
            d
            for d in _by_type(graph, "dataset_DatasetPackage")
            if d["name"] == "data/train.txt"
        ]
        assert len(datasets) == 2
        assert any("two different SHA-256" in r.message for r in caplog.records)
