# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for the tests under tests/core/.

Fragment-merge helpers verify that informational fields from SPDX 3
fragment files are not dropped during the stitch/merge step.

Fixtures live in tests/fixtures/fragments/:

- ai-model-fragment.spdx3.json -- ai_AIPackage with full AI metadata
- dataset-fragment.spdx3.json -- dataset_DatasetPackage with dataset metadata
- training-run-fragment.spdx3.json -- loom.run()-style combined fragment:
  ai_AIPackage + 2 datasets + trainedOn/testedOn

The spdx-python-model library serialises anonymous (blank) node objects --
DictionaryEntry, ai_EnergyConsumption, ai_EnergyConsumptionDescription -- as
separate @graph entries referenced by blank-node IDs like ``_:DictionaryEntry0``.
The ``_resolve`` / ``_entries`` helpers below dereference those IDs so that
tests can navigate nested structures without depending on blank-node internals.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from pitloom import loom
from pitloom.assemble.spdx3.document import build
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.config import FragmentConfig
from pitloom.core.creation import CreationMetadata, Creator
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.id_registry import DEFAULT_ID_REGISTRY_FILENAME, IdRegistry
from tests._license_graph import license_value

_FRAGMENTS_DIR = Path(__file__).parent.parent / "fixtures" / "fragments"

_AI_MODEL_FRAGMENT = "ai-model-fragment.spdx3.json"

_DATASET_FRAGMENT = "dataset-fragment.spdx3.json"

_TRAINING_RUN_FRAGMENT = "training-run-fragment.spdx3.json"


def _merge_and_parse(
    *fragment_names: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Merge named fragments into a fresh exporter; return ``(graph, index)``.

    ``index`` maps every blank-node ``@id`` to its graph entry so that
    callers can resolve references like ``'_:DictionaryEntry0'`` to
    ``{'key': 'lr', 'value': '0.01', 'type': 'DictionaryEntry'}``.
    """
    exporter = Spdx3JsonExporter()
    merge_fragments(
        _FRAGMENTS_DIR,
        [FragmentConfig(path=name) for name in fragment_names],
        exporter,
    )
    data = json.loads(exporter.to_json(pretty=True))
    graph: list[dict[str, Any]] = data.get("@graph", [])
    index: dict[str, dict[str, Any]] = {e["@id"]: e for e in graph if "@id" in e}
    return (graph, index)


def _by_type(graph: list[dict[str, Any]], type_name: str) -> list[dict[str, Any]]:
    return [e for e in graph if e.get("type") == type_name]


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

[tool.pitloom.fragment]
files = [
    "ai-model-fragment.spdx3.json",
    "training-run-fragment.spdx3.json",
]
"""

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

[tool.pitloom.fragment]
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
    registry_path = tmppath / DEFAULT_ID_REGISTRY_FILENAME
    registry.save(registry_path)
    with patch(
        "pitloom._loom_active_run._get_caller_script_path",
        return_value="src/fragdemo/preprocess.py",
    ):
        with loom.run(
            tmppath / "fragments" / "01_preprocess.spdx3.json",
            id_registry=registry_path,
        ) as run:
            run.add_input_dataset("data/raw.txt")
            run.add_output_dataset("data/train.txt")
    with patch(
        "pitloom._loom_active_run._get_caller_script_path",
        return_value="src/fragdemo/train.py",
    ):
        with loom.run(
            tmppath / "fragments" / "02_train.spdx3.json", id_registry=registry_path
        ) as run:
            run.set_model("demo-model", model_type="supervised")
            run.add_dataset("data/train.txt")
            run.add_validation_dataset("data/raw.txt")


# Integration tests for SBOM generation.


def _build_graph_for_files(files: list[ProjectFile]) -> list[dict[str, object]]:
    """Build a minimal document from *files* and return its ``@graph``.

    ``created`` is pinned so two calls compare equal across a second boundary.
    """
    project = ProjectMetadata(name="file-headers-project", version="1.0.0", files=files)
    creation = CreationMetadata(creation_datetime="2026-01-01T00:00:00+00:00")
    doc = DocumentModel(project=project, creation_metadata=creation)
    exporter = build(doc)
    graph: list[dict[str, object]] = json.loads(exporter.to_json())["@graph"]
    return graph


def _find_file_element(
    graph: list[dict[str, object]], distribution_path: str
) -> dict[str, object]:
    return next(
        e
        for e in graph
        if e.get("type") == "software_File" and e.get("name") == distribution_path
    )


def _annotation_fields_for(
    graph: list[dict[str, object]], subject_spdx_id: object
) -> dict[str, dict[str, str]] | None:
    """Return the decoded ``fields`` map of the ``provenance/fields/1``
    Annotation on *subject_spdx_id*, or ``None`` if there isn't one."""
    for element in graph:
        if element.get("type") != "Annotation":
            continue
        if element.get("subject") != subject_spdx_id:
            continue
        raw_statement = element["statement"]
        assert isinstance(raw_statement, str)
        statement = json.loads(raw_statement)
        if statement.get("kind") == "fields":
            return cast("dict[str, dict[str, str]]", statement["fields"])
    return None


def _creation_agents(graph: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the elements referenced by the single CreationInfo.createdBy."""
    creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
    assert len(creation_infos) == 1
    by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
    return [by_id[ref] for ref in creation_infos[0]["createdBy"]]


_AI_LICENSE_CASES: list[tuple[str, str, str]] = [
    ("Kokoro-82M", "apache-2.0", "hexgrad/Kokoro-82M"),
    ("DeepSeek-R1", "mit", "deepseek-ai/DeepSeek-R1"),
    ("blip-vqa-base", "bsd-3-clause", "Salesforce/blip-vqa-base"),
    (
        "speaker-diarization-community-1",
        "cc-by-4.0",
        "pyannote/speaker-diarization-community-1",
    ),
    ("seamless-m4t-v2-large", "cc-by-nc-4.0", "facebook/seamless-m4t-v2-large"),
    (
        "wangchanglm-7.5B-sft-enth",
        "cc-by-sa-4.0",
        "pythainlp/wangchanglm-7.5B-sft-enth",
    ),
    ("starcoder2-3b", "bigcode-openrail-m", "bigcode/starcoder2-3b"),
    ("Llama-3.2-1B", "llama3.2", "meta-llama/Llama-3.2-1B"),
    ("Hermes-3-Llama-3.2-3B", "llama3", "NousResearch/Hermes-3-Llama-3.2-3B"),
    ("Gemma-SEA-LION-v4-27B-IT", "gemma", "aisingapore/Gemma-SEA-LION-v4-27B-IT"),
    (
        "Deberta_Human_Value_Detector",
        "openrail++",
        "tum-nlp/Deberta_Human_Value_Detector",
    ),
    ("DepthPro-hf", "apple-amlr", "apple/DepthPro-hf"),
]


#: Literal expectations: lower-case id -> its SPDX spelling (an expression);
#: any other id (``llama3``, ``openrail++``) stays text as written.
_SPDX_CASE: dict[str, str] = {
    "apache-2.0": "Apache-2.0",
    "mit": "MIT",
    "bsd-3-clause": "BSD-3-Clause",
    "cc-by-4.0": "CC-BY-4.0",
    "cc-by-nc-4.0": "CC-BY-NC-4.0",
    "cc-by-sa-4.0": "CC-BY-SA-4.0",
    "cc0-1.0": "CC0-1.0",
}


def _check_license_relationships(
    graph: list[dict[str, Any]], ai_pkg_id: str, license_id: str
) -> None:
    """Assert hasDeclaredLicense or hasConcludedLicense relationship exists."""
    rels = [e for e in graph if e.get("type") == "Relationship"]
    declared = [
        r
        for r in rels
        if r.get("relationshipType") == "hasDeclaredLicense"
        and r.get("from") == ai_pkg_id
    ]
    concluded = [
        r
        for r in rels
        if r.get("relationshipType") == "hasConcludedLicense"
        and r.get("from") == ai_pkg_id
    ]
    assert len(declared) + len(concluded) == 1, (
        "expected exactly one license relationship, got "
        f"{len(declared)} declared and {len(concluded)} concluded"
    )
    license_rel = declared[0] if declared else concluded[0]
    license_spdx_id = license_rel["to"][0]
    license_elems = [
        e
        for e in graph
        if e.get("type")
        in ("simplelicensing_LicenseExpression", "simplelicensing_SimpleLicensingText")
        and e.get("spdxId") == license_spdx_id
    ]
    assert len(license_elems) == 1
    # A valid id is recorded in its SPDX case ("mit" -> "MIT") as an
    # expression; anything else stays text as written.
    spdx_case = _SPDX_CASE.get(license_id.lower())
    assert license_elems[0]["type"] == (
        "simplelicensing_LicenseExpression"
        if spdx_case
        else "simplelicensing_SimpleLicensingText"
    )
    assert license_value(license_elems[0]) == (spdx_case or license_id)
    spdx_docs = [e for e in graph if e.get("type") == "SpdxDocument"]
    assert "simpleLicensing" in spdx_docs[0]["profileConformance"]


_BUILD_MODEL_LICENSE_CASES: list[tuple[str, str, AiModelFormat, str]] = [
    (
        "Gemma-SEA-LION-v4-4B-VL-GGUF",
        "gemma",
        AiModelFormat.GGUF,
        "aisingapore/Gemma-SEA-LION-v4-4B-VL-GGUF",
    ),
    ("DeepSeek-R1", "mit", AiModelFormat.SAFETENSORS, "deepseek-ai/DeepSeek-R1"),
]


def _write_smoke_project(tmppath: Path, *, enrich_local: bool = False) -> Path:
    """Write a minimal Hatchling project with one AI model + README under
    ``src/smoke_project/`` at *tmppath*; returns the model file's path.
    Shared by the project-target enrichment tests below."""
    pkg_dir = tmppath / "src" / "smoke_project"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("")
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    model_path = pkg_dir / "model.safetensors"
    model_path.write_bytes(fixture.read_bytes())
    (pkg_dir / "README.md").write_text(
        "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
    )
    enrich_toml = "[tool.pitloom]\nenrich = true\n" if enrich_local else ""
    (tmppath / "pyproject.toml").write_text(
        "[build-system]\n"
        'requires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        "[project]\n"
        'name = "smoke-project"\n'
        'version = "0.1.0"\n\n'
        "[tool.hatch.build.targets.wheel]\n"
        'packages = ["src/smoke_project"]\n\n' + enrich_toml
    )
    return model_path


_FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures"

_AI_MODEL_ROOT = _FIXTURE_ROOT / "aimodels"

_AI_MODEL_DIRS = [
    "fasttext",
    "gguf",
    "hdf5",
    "keras",
    "numpy",
    "onnx",
    "pytorch",
    "pytorch_pt2",
    "safetensors",
]

_AI_MODEL_FIXTURES: list[Path] = [
    p
    for d in _AI_MODEL_DIRS
    for p in sorted((_AI_MODEL_ROOT / d).glob("*"))
    if p.is_file() and p.suffix != ""
]


def _make_wheel(tmp_path: Path, name: str, version: str) -> Path:
    """Build a minimal .whl with just a METADATA file."""
    wheel_path = tmp_path / f"{name}-{version}-py3-none-any.whl"
    metadata_body = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(f"{name}-{version}.dist-info/METADATA", metadata_body)
        zf.writestr(f"{name}/__init__.py", "")
    return wheel_path


def _license_relationships(
    graph: list[dict[str, Any]], subject_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rels = [e for e in graph if e.get("type") == "Relationship"]
    declared = [
        r
        for r in rels
        if r.get("relationshipType") == "hasDeclaredLicense"
        and r.get("from") == subject_id
    ]
    concluded = [
        r
        for r in rels
        if r.get("relationshipType") == "hasConcludedLicense"
        and r.get("from") == subject_id
    ]
    return (declared, concluded)


__all__ = [
    "AiModelFormat",
    "Any",
    "CreationMetadata",
    "Creator",
    "DocumentModel",
    "IdRegistry",
    "Path",
    "ProjectFile",
    "ProjectMetadata",
    "Spdx3JsonExporter",
    "_AI_LICENSE_CASES",
    "_AI_MODEL_DIRS",
    "_AI_MODEL_FIXTURES",
    "_AI_MODEL_FRAGMENT",
    "_AI_MODEL_ROOT",
    "_BUILD_MODEL_LICENSE_CASES",
    "_DATASET_FRAGMENT",
    "_FIXTURE_ROOT",
    "_FRAGMENTS_DIR",
    "_PYPROJECT_TEMPLATE",
    "_RELATIONSHIP_TYPES",
    "_TRAINING_RUN_FRAGMENT",
    "_UNIFY_PYPROJECT",
    "_annotation_fields_for",
    "_build_graph_for_files",
    "_by_type",
    "_check_license_relationships",
    "_creation_agents",
    "_entries",
    "_find_file_element",
    "_fixed_creation",
    "_hyperparams",
    "_license_relationships",
    "_make_unify_project",
    "_make_wheel",
    "_merge_and_parse",
    "_metrics",
    "_relationships",
    "_resolve",
    "_run_unify_pipeline",
    "_write_smoke_project",
    "annotations",
    "build",
    "json",
    "loom",
    "merge_fragments",
    "patch",
    "zipfile",
]
