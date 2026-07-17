# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for SBOM fragment merging -- verifies that informational fields
from SPDX 3 fragment files are not dropped during the stitch/merge step.

Fixtures live in tests/fixtures/fragments/:
  ai-model-fragment.spdx3.json       -- ai_AIPackage with full AI metadata
  dataset-fragment.spdx3.json        -- dataset_DatasetPackage with dataset metadata
  training-run-fragment.spdx3.json   -- loom.run()-style combined fragment:
                                        ai_AIPackage + 2 datasets + trainedOn/testedOn

Implementation note
-------------------
The spdx-python-model library serialises anonymous (blank) node objects --
DictionaryEntry, ai_EnergyConsumption, ai_EnergyConsumptionDescription -- as
separate @graph entries referenced by blank-node IDs like ``_:DictionaryEntry0``.
The ``_resolve`` / ``_entries`` helpers below dereference those IDs so that
tests can navigate nested structures without depending on blank-node internals.
"""

# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom import loom
from pitloom.assemble import generate_sbom
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.creation import CreationMetadata, Creator
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.ids import IdRegistry

_FRAGMENTS_DIR = Path(__file__).parent / "fixtures" / "fragments"

_AI_MODEL_FRAGMENT = "ai-model-fragment.spdx3.json"
_DATASET_FRAGMENT = "dataset-fragment.spdx3.json"
_TRAINING_RUN_FRAGMENT = "training-run-fragment.spdx3.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _merge_and_parse(
    *fragment_names: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Merge named fragments into a fresh exporter; return ``(graph, index)``.

    ``index`` maps every blank-node ``@id`` to its graph entry so that
    callers can resolve references like ``'_:DictionaryEntry0'`` to
    ``{'key': 'lr', 'value': '0.01', 'type': 'DictionaryEntry'}``.
    """
    exporter = Spdx3JsonExporter()
    merge_fragments(_FRAGMENTS_DIR, list(fragment_names), exporter)
    data = json.loads(exporter.to_json(pretty=True))
    graph: list[dict[str, Any]] = data.get("@graph", [])
    index: dict[str, dict[str, Any]] = {e["@id"]: e for e in graph if "@id" in e}
    return graph, index


def _by_type(graph: list[dict[str, Any]], type_name: str) -> list[dict[str, Any]]:
    return [e for e in graph if e.get("type") == type_name]


#: A ``LifecycleScopedRelationship`` (used for scoped ``generates``/
#: ``hasDataFile`` edges) is a ``Relationship`` subclass at the Python level,
#: but serializes with its own JSON-LD ``type`` -- match both.
_RELATIONSHIP_TYPES = ("Relationship", "LifecycleScopedRelationship")


def _relationships(graph: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in graph if e.get("type") in _RELATIONSHIP_TYPES]


def _resolve(ref: Any, index: dict[str, dict[str, Any]]) -> Any:
    """Dereference a blank-node string; return non-blank values unchanged."""
    if isinstance(ref, str) and ref.startswith("_:"):
        return index.get(ref, ref)
    return ref


def _entries(
    element: dict[str, Any], field: str, index: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return all resolved dict entries for a list field that uses blank refs."""
    result = []
    for ref in element.get(field, []):
        resolved = _resolve(ref, index)
        if isinstance(resolved, dict):
            result.append(resolved)
    return result


def _hyperparams(
    element: dict[str, Any], index: dict[str, dict[str, Any]]
) -> dict[str, str]:
    """Return ``{key: value}`` for all ai_hyperparameter entries."""
    return {e["key"]: e["value"] for e in _entries(element, "ai_hyperparameter", index)}


def _metrics(
    element: dict[str, Any], index: dict[str, dict[str, Any]]
) -> dict[str, str]:
    """Return ``{key: value}`` for all ai_metric entries."""
    return {e["key"]: e["value"] for e in _entries(element, "ai_metric", index)}


# ---------------------------------------------------------------------------
# AI model fragment -- all AI-profile fields must survive the merge
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
# Dataset fragment -- all dataset-profile fields must survive the merge
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
# Training-run fragment -- relationships and combined elements preserved
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


# ---------------------------------------------------------------------------
# Multiple fragments merged together -- no element from any fragment dropped
# ---------------------------------------------------------------------------


class TestMultipleFragmentsMerge:
    def test_ai_packages_from_all_fragments_present(self) -> None:
        """Both ai_AIPackage elements (one per AI fragment) must appear."""
        graph, _ = _merge_and_parse(
            _AI_MODEL_FRAGMENT, _DATASET_FRAGMENT, _TRAINING_RUN_FRAGMENT
        )
        ai_pkgs = _by_type(graph, "ai_AIPackage")
        assert len(ai_pkgs) == 2, (
            f"Expected 2 ai_AIPackage elements, got {len(ai_pkgs)}"
        )

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
        """trainedOn + testedOn relationships from training-run fragment must
        survive."""
        graph, _ = _merge_and_parse(
            _AI_MODEL_FRAGMENT, _DATASET_FRAGMENT, _TRAINING_RUN_FRAGMENT
        )
        rels = _relationships(graph)
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
# End-to-end via generate_sbom -- fragment elements survive full pipeline
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
            creation_metadata=CreationMetadata(creators=[Creator(name="Test")]),
        )
        data = json.loads(sbom_json)
        graph: list[dict[str, Any]] = data.get("@graph", [])
        index: dict[str, dict[str, Any]] = {e["@id"]: e for e in graph if "@id" in e}

        # ai_AIPackage elements from both fragments must be in the final SBOM
        ai_pkgs = _by_type(graph, "ai_AIPackage")
        assert len(ai_pkgs) == 2, f"Expected 2 ai_AIPackage, got {len(ai_pkgs)}"

        names = {p["name"] for p in ai_pkgs}
        assert "resnet-tiny-classifier" in names
        assert "linear-regressor" in names

        # Provenance relationships must also survive
        rels = _relationships(graph)
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
            creation_metadata=CreationMetadata(creators=[Creator(name="Test")]),
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
    # Object set must be empty -- nothing merged
    data = json.loads(exporter.to_json())
    graph = data.get("@graph", [])
    assert len(graph) == 0

    # Warning must have been emitted
    assert any("nonexistent-fragment" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Cross-fragment unification (registry ids, hash fallback, envelopes)
# ---------------------------------------------------------------------------

_UNIFY_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "fragdemo"
version = "0.1.0"
description = "Fragment unification test app"

[tool.hatch.build.targets.wheel]
packages = ["src/fragdemo"]

[tool.pitloom.fragments]
files = [
    "fragments/01_preprocess.spdx3.json",
    "fragments/02_train.spdx3.json",
]
"""


def _fixed_creation() -> CreationMetadata:
    return CreationMetadata(
        creators=[Creator(name="Test")],
        creation_datetime="2026-01-01T00:00:00+00:00",
        build_datetime="2026-01-01T00:00:00+00:00",
    )


def _make_unify_project(tmppath: Path) -> None:
    """Lay out the src/data tree used by the unification tests."""
    (tmppath / "pyproject.toml").write_text(_UNIFY_PYPROJECT)
    pkg = tmppath / "src" / "fragdemo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "preprocess.py").write_text("# preprocess script\n")
    (pkg / "train.py").write_text("# training script\n")
    data = tmppath / "data"
    data.mkdir()
    (data / "raw.txt").write_text("raw data\n")
    (data / "train.txt").write_text("processed training data\n")


def _run_unify_pipeline(tmppath: Path) -> None:
    """Simulate the two-stage loom pipeline with a shared ID registry."""
    registry = IdRegistry.new("fragdemo")
    registry.generate([Path("src"), Path("data")], tmppath)
    registry.register_entity("demo-model", "ai_AIPackage")
    registry.save(tmppath / "loom-ids.json")

    with patch(
        "pitloom.loom._get_caller_script_path",
        return_value="src/fragdemo/preprocess.py",
    ):
        with loom.run(tmppath / "fragments" / "01_preprocess.spdx3.json") as run:
            run.add_input_dataset("data/raw.txt")
            run.add_output_dataset("data/train.txt")

    with patch(
        "pitloom.loom._get_caller_script_path",
        return_value="src/fragdemo/train.py",
    ):
        with loom.run(tmppath / "fragments" / "02_train.spdx3.json") as run:
            run.set_model("demo-model", model_type="supervised")
            run.add_dataset("data/train.txt")
            run.add_validation_dataset("data/raw.txt")


class TestRegistryUnification:
    """The full workflow: `ids generate` -> loom runs -> generate_sbom."""

    @pytest.fixture()
    def merged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], IdRegistry]:
        _make_unify_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        _run_unify_pipeline(tmp_path)

        sbom_json = generate_sbom(tmp_path, creation_metadata=_fixed_creation())
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
        first = generate_sbom(tmp_path, creation_metadata=creation)
        second = generate_sbom(tmp_path, creation_metadata=creation)
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


def test_duplicate_relationships_deduplicated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two fragments asserting the same edge (after unification) must yield
    exactly one Relationship in the merged graph."""
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    (data / "train.txt").write_text("training data\n")

    registry = IdRegistry.new("dedup")
    registry.generate([Path("data")], tmp_path)
    registry.register_entity("m", "ai_AIPackage")
    registry.save(tmp_path / "loom-ids.json")

    for fragment_name in ("f1.spdx3.json", "f2.spdx3.json"):
        with loom.run(tmp_path / fragment_name) as run:
            run.set_model("m", generated=False)
            run.add_dataset("data/train.txt")

    exporter = Spdx3JsonExporter()
    merge_fragments(tmp_path, ["f1.spdx3.json", "f2.spdx3.json"], exporter)
    graph = json.loads(exporter.to_json(pretty=True)).get("@graph", [])
    trained = [r for r in _relationships(graph) if r["relationshipType"] == "trainedOn"]
    assert len(trained) == 1


def test_fragment_envelope_is_dropped(tmp_path: Path) -> None:
    """A fragment carrying its own SpdxDocument/software_Sbom envelope (e.g.
    from `loom model`) must not add a second envelope to the merged SBOM."""
    namespace = "https://spdx.org/spdxdocs/envelope-test"
    envelope_fragment = {
        "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
        "@graph": [
            {
                "type": "CreationInfo",
                "@id": "_:creationinfo0",
                "specVersion": "3.0.1",
                "created": "2026-01-01T00:00:00Z",
                "createdBy": [f"{namespace}#Agent-1"],
            },
            {
                "type": "SoftwareAgent",
                "spdxId": f"{namespace}#Agent-1",
                "creationInfo": "_:creationinfo0",
                "name": "Pitloom",
            },
            {
                "type": "SpdxDocument",
                "spdxId": namespace,
                "creationInfo": "_:creationinfo0",
                "rootElement": [f"{namespace}#Sbom-1"],
            },
            {
                "type": "software_Sbom",
                "spdxId": f"{namespace}#Sbom-1",
                "creationInfo": "_:creationinfo0",
                "rootElement": [f"{namespace}#AIPackage-1"],
            },
            {
                "type": "ai_AIPackage",
                "spdxId": f"{namespace}#AIPackage-1",
                "creationInfo": "_:creationinfo0",
                "name": "enveloped-model",
            },
        ],
    }
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_TEMPLATE.replace(
            'files = [\n    "ai-model-fragment.spdx3.json",\n'
            '    "training-run-fragment.spdx3.json",\n]',
            'files = ["envelope-fragment.spdx3.json"]',
        )
    )
    (tmp_path / "envelope-fragment.spdx3.json").write_text(
        json.dumps(envelope_fragment)
    )

    sbom_json = generate_sbom(
        tmp_path, creation_metadata=CreationMetadata(creators=[Creator(name="Test")])
    )
    graph = json.loads(sbom_json).get("@graph", [])

    docs = _by_type(graph, "SpdxDocument")
    assert len(docs) == 1
    assert docs[0]["spdxId"] != namespace

    # The fragment's AIPackage itself must survive (only its envelope dies),
    # and the model Sbom added post-merge is rooted at it.
    ai_pkgs = _by_type(graph, "ai_AIPackage")
    assert [p["name"] for p in ai_pkgs] == ["enveloped-model"]
    sboms = _by_type(graph, "software_Sbom")
    assert len(sboms) == 2
    assert any(s["rootElement"] == [ai_pkgs[0]["spdxId"]] for s in sboms)
