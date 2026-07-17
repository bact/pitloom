# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""End-to-end AI-pipeline SBOM test: registry -> loom fragments -> real wheel.

Simulates the full sentimentdemo-style workflow without any ML dependency:

1. ``IdRegistry.generate`` pins stable ids for the project's source and data
   files (plus a registered ``ai_AIPackage`` entity for the model).
2. Two ``loom.run`` sessions -- a preprocess run (input/output datasets) and
   a training run (model + trainedOn/testedOn) -- write fragments that
   consult the registry.
3. A real wheel is built with Hatchling; the Pitloom build hook assembles
   the project SBOM, reuses registry ids for the wheel's own files, and
   merges the fragments.

The resulting SBOM inside the wheel must be one *connected* graph:

    Package --contains--> train.py File --generates--> AIPackage
        --trainedOn--> processed DatasetPackage --hasInput--> raw DatasetPackage
"""

# pylint: disable=missing-function-docstring,redefined-outer-name

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

pytest.importorskip(
    "hatchling", reason="hatchling is required for wheel integration tests"
)

# pylint: disable=wrong-import-position
from hatchling.builders.wheel import WheelBuilder  # noqa: E402

from pitloom import loom  # noqa: E402
from pitloom.ids import IdRegistry  # noqa: E402

# pylint: enable=wrong-import-position

_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pipedemo"
version = "0.1.0"
description = "AI pipeline SBOM end-to-end test app"

[tool.hatch.build.targets.wheel]
packages = ["src/pipedemo"]

[tool.hatch.build.hooks.pitloom]
enabled = true

[tool.pitloom]
sbom-basename = "pipedemo"

[tool.pitloom.fragments]
files = [
    "fragments/01_preprocess.spdx3.json",
    "fragments/02_train.spdx3.json",
]
"""


@pytest.fixture(scope="module")
def sbom_graph(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[list[dict[str, Any]], IdRegistry]:
    """Run the whole pipeline, build the wheel, return (graph, registry)."""
    project = tmp_path_factory.mktemp("pipedemo")

    (project / "pyproject.toml").write_text(_PYPROJECT)
    pkg = project / "src" / "pipedemo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "preprocess.py").write_text("# preprocess script\n")
    (pkg / "train.py").write_text("# training script\n")
    data = project / "data"
    data.mkdir()
    (data / "raw.txt").write_text("raw data\n")
    (data / "train.txt").write_text("processed training data\n")
    (data / "test.txt").write_text("processed test data\n")

    registry = IdRegistry.new("pipedemo")
    registry.generate([Path("src"), Path("data")], project)
    registry.register_entity("pipedemo-model", "ai_AIPackage")
    registry.save(project / "loom-ids.json")

    # loom resolves dataset paths and the registry relative to the cwd.
    old_cwd = os.getcwd()
    os.chdir(project)
    try:
        with patch(
            "pitloom.loom._get_caller_script_path",
            return_value="src/pipedemo/preprocess.py",
        ):
            with loom.run(project / "fragments" / "01_preprocess.spdx3.json") as run:
                run.add_input_dataset("data/raw.txt")
                run.add_output_dataset("data/train.txt")
                run.add_output_dataset("data/test.txt")

        with patch(
            "pitloom.loom._get_caller_script_path",
            return_value="src/pipedemo/train.py",
        ):
            with loom.run(project / "fragments" / "02_train.spdx3.json") as run:
                run.set_model("pipedemo-model", model_type="supervised")
                run.add_dataset("data/train.txt")
                run.add_validation_dataset("data/test.txt")
    finally:
        os.chdir(old_cwd)

    out_dir = tmp_path_factory.mktemp("wheel_out")
    builder = WheelBuilder(str(project))
    wheel_path = Path(
        next(builder.build(directory=str(out_dir), versions=["standard"]))
    )

    with zipfile.ZipFile(wheel_path) as zf:
        (sbom_entry,) = [n for n in zf.namelist() if "/sboms/" in n]
        assert sbom_entry.endswith(".dist-info/sboms/pipedemo.spdx3.json")
        graph = json.loads(zf.read(sbom_entry))["@graph"]

    return graph, IdRegistry.load(project / "loom-ids.json")


def _by_type(graph: list[dict[str, Any]], type_name: str) -> list[dict[str, Any]]:
    return [e for e in graph if e.get("type") == type_name]


#: A ``LifecycleScopedRelationship`` (used for scoped ``generates``/
#: ``hasDataFile`` edges) is a ``Relationship`` subclass at the Python level,
#: but serializes with its own JSON-LD ``type`` -- match both.
_RELATIONSHIP_TYPES = ("Relationship", "LifecycleScopedRelationship")


def _rels(graph: list[dict[str, Any]], rel_type: str) -> list[dict[str, Any]]:
    return [
        r
        for r in graph
        if r.get("type") in _RELATIONSHIP_TYPES
        and r.get("relationshipType") == rel_type
    ]


def test_connected_pipeline_chain(
    sbom_graph: tuple[list[dict[str, Any]], IdRegistry],
) -> None:
    """Package -> contains -> train.py -> generates -> model -> trainedOn ->
    train.txt -> hasInput -> raw.txt, all through registry-stable ids."""
    graph, registry = sbom_graph
    train_py_id = registry.files["src/pipedemo/train.py"].spdx_id
    model_id = registry.entities["pipedemo-model"].spdx_id
    train_txt_id = registry.files["data/train.txt"].spdx_id
    raw_id = registry.files["data/raw.txt"].spdx_id

    (main_pkg,) = _by_type(graph, "software_Package")
    # Containment is hierarchical (Package contains the package directory,
    # which contains the scripts) -- walk `contains` transitively.
    contains_rels = _rels(graph, "contains")
    contained: set[str] = set()
    frontier = {main_pkg["spdxId"]}
    while frontier:
        source = frontier.pop()
        for rel in contains_rels:
            if rel["from"] == source:
                new = set(rel["to"]) - contained
                contained |= new
                frontier |= new
    # The wheel's train.py File is the *same element* the fragment refers to.
    assert train_py_id in contained

    assert any(
        r["from"] == train_py_id and model_id in r["to"]
        for r in _rels(graph, "generates")
    )
    assert any(
        r["from"] == model_id and train_txt_id in r["to"]
        for r in _rels(graph, "trainedOn")
    )
    assert any(
        r["from"] == train_txt_id and raw_id in r["to"]
        for r in _rels(graph, "hasInput")
    )
    assert any(r["from"] == model_id for r in _rels(graph, "testedOn"))


def test_preprocess_generates_both_outputs(
    sbom_graph: tuple[list[dict[str, Any]], IdRegistry],
) -> None:
    graph, registry = sbom_graph
    preprocess_id = registry.files["src/pipedemo/preprocess.py"].spdx_id
    train_txt_id = registry.files["data/train.txt"].spdx_id
    test_txt_id = registry.files["data/test.txt"].spdx_id
    assert any(
        r["from"] == preprocess_id and set(r["to"]) == {train_txt_id, test_txt_id}
        for r in _rels(graph, "generates")
    )


def test_single_model_and_unified_datasets(
    sbom_graph: tuple[list[dict[str, Any]], IdRegistry],
) -> None:
    graph, _ = sbom_graph
    assert len(_by_type(graph, "ai_AIPackage")) == 1
    dataset_names = [d["name"] for d in _by_type(graph, "dataset_DatasetPackage")]
    assert sorted(dataset_names) == ["data/raw.txt", "data/test.txt", "data/train.txt"]


def test_document_envelope_and_profiles(
    sbom_graph: tuple[list[dict[str, Any]], IdRegistry],
) -> None:
    graph, registry = sbom_graph
    (doc,) = _by_type(graph, "SpdxDocument")
    assert "ai" in doc["profileConformance"]
    assert "dataset" in doc["profileConformance"]

    sboms = _by_type(graph, "software_Sbom")
    assert len(sboms) == 2
    assert set(doc["rootElement"]) == {s["spdxId"] for s in sboms}
    model_id = registry.entities["pipedemo-model"].spdx_id
    assert any(s["rootElement"] == [model_id] for s in sboms)


def test_pinned_creation_datetime_gives_byte_identical_sboms(
    tmp_path: Path,
) -> None:
    """With [tool.pitloom.creation] creation-datetime pinned (and no
    SOURCE_DATE_EPOCH), rebuilding unchanged sources produces byte-identical
    SBOMs."""
    project = tmp_path / "proj"
    pkg = project / "src" / "pindemo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (project / "pyproject.toml").write_text(
        """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pindemo"
version = "0.1.0"

[tool.hatch.build.targets.wheel]
packages = ["src/pindemo"]

[tool.hatch.build.hooks.pitloom]
enabled = true

[tool.pitloom.creation]
creation-datetime = "2026-01-01T00:00:00+00:00"
"""
    )

    def _build_and_read(out_name: str) -> bytes:
        out_dir = tmp_path / out_name
        builder = WheelBuilder(str(project))
        wheel = Path(next(builder.build(directory=str(out_dir), versions=["standard"])))
        with zipfile.ZipFile(wheel) as zf:
            (sbom_entry,) = [n for n in zf.namelist() if "/sboms/" in n]
            return zf.read(sbom_entry)

    assert _build_and_read("out1") == _build_and_read("out2")
