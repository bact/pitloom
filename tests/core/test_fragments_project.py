# ruff: noqa: F403, F405
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from pitloom.assemble import generate_project_sbom
from pitloom.core.creation import CreationMetadata, Creator

from .conftest import *


def test_generate_project_sbom_includes_ai_model_fragment_elements() -> None:
    """Full pipeline must include elements from listed fragments."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Set up project
        (tmppath / "pyproject.toml").write_text(_PYPROJECT_TEMPLATE)

        # Copy fixtures into the project dir (fragments paths are relative to it)
        for name in (_AI_MODEL_FRAGMENT, _TRAINING_RUN_FRAGMENT):
            shutil.copy(_FRAGMENTS_DIR / name, tmppath / name)

        sbom_json = generate_project_sbom(
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


def test_generate_project_sbom_includes_dataset_fragment_elements() -> None:
    """dataset_DatasetPackage from fragment must appear in output."""
    pyproject = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "dataset-e2e-app"
version = "0.1.0"

[tool.pitloom]
pretty = true

[tool.pitloom.fragment]
files = ["dataset-fragment.spdx3.json"]
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(pyproject)
        shutil.copy(_FRAGMENTS_DIR / _DATASET_FRAGMENT, tmppath / _DATASET_FRAGMENT)

        sbom_json = generate_project_sbom(
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
