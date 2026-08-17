# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for registry unification and hash-fallback unification in fragment merging.

See also:
- :mod:`tests.core.test_fragments_models_datasets` for AI model, dataset,
  and training runs.
"""

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

from .conftest import (
    _by_type,
    _fixed_creation,
    _make_unify_project,
    _relationships,
    _run_unify_pipeline,
)


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
