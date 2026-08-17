# ruff: noqa: F403, F405
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import (
    enrich_model,
    generate,
    generate_model_sbom,
)
from pitloom.assemble.spdx3.document import (
    build,
    build_model,
)
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract.ai_model import read_ai_model

from .conftest import (
    _AI_MODEL_FIXTURES,
    _AI_MODEL_ROOT,
    _check_license_relationships,
    _make_wheel,
)


def test_build_package_files_have_sha256_verified_using() -> None:
    """Every file (not directory) software_File must carry a SHA-256
    verifiedUsing hash matching the corresponding ProjectFile.digest_sha256."""
    files = [
        ProjectFile(
            physical_path="src/pkg/__init__.py",
            distribution_path="pkg/__init__.py",
            digest_sha256="a" * 64,
        ),
        ProjectFile(
            physical_path="src/pkg/module.py",
            distribution_path="pkg/module.py",
            digest_sha256="b" * 64,
        ),
    ]
    project = ProjectMetadata(name="file-hash-project", version="1.0.0", files=files)
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc)
    graph = json.loads(exporter.to_json())["@graph"]

    file_elements = [e for e in graph if e.get("type") == "software_File"]
    by_name = {e["name"]: e for e in file_elements}

    # Directory node: no verifiedUsing hash.
    assert "verifiedUsing" not in by_name["pkg"]

    # File nodes: exactly one SHA-256 Hash matching the source digest.
    for pf in files:
        file_elem = by_name[pf.distribution_path]
        assert file_elem["software_fileKind"] == "file"
        (hash_obj,) = file_elem["verifiedUsing"]
        assert hash_obj["algorithm"] == "sha256"
        assert hash_obj["hashValue"] == pf.digest_sha256


def test_enrich_then_merge_matches_one_shot_enrich() -> None:
    """generate_model_sbom(enrich=True) in one shot must produce the same
    enrichment evidence as: generate a base SBOM with enrich=False, run
    enrich_model() separately, then merge_fragments() the two -- the
    design invariant behind exposing enrichment as its own CLI/API surface
    (see the plan's Surface 2(d))."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )

        # One-shot.
        one_shot = json.loads(generate_model_sbom(model_path, enrich=True))
        one_shot_ds = {
            e["name"]
            for e in one_shot["@graph"]
            if e.get("type") == "dataset_DatasetPackage"
        }
        one_shot_ann_fields = {
            c["field"]
            for e in one_shot["@graph"]
            if e.get("type") == "Annotation" and e.get("statement")
            for c in json.loads(e["statement"]).get("changes", [])
            if json.loads(e["statement"]).get("kind") == "enrichment"
        }

        # Two-step: base without enrichment, then a separate fragment, merged.
        base_json = generate_model_sbom(model_path, enrich=False)
        fragment_json = enrich_model(model_path)
        fragment_path = tmppath / "enrichment.spdx3.json"
        fragment_path.write_text(fragment_json)

        exporter = Spdx3JsonExporter()
        # Re-deserialize the base doc into the exporter's object set, then merge.
        with tempfile.NamedTemporaryFile(
            suffix=".spdx3.json", mode="w", delete=False, dir=tmpdir
        ) as base_file:
            base_file.write(base_json)
            base_file_path = Path(base_file.name)
        with base_file_path.open("rb") as f:
            spdx3.JSONLDDeserializer().read(f, exporter.object_set)

        merge_fragments(tmppath, [fragment_path.name], exporter)
        merged = json.loads(exporter.to_json())

        merged_ds = {
            e["name"]
            for e in merged["@graph"]
            if e.get("type") == "dataset_DatasetPackage"
        }
        merged_ann_fields = {
            c["field"]
            for e in merged["@graph"]
            if e.get("type") == "Annotation" and e.get("statement")
            for c in json.loads(e["statement"]).get("changes", [])
            if json.loads(e["statement"]).get("kind") == "enrichment"
        }

        assert merged_ds == one_shot_ds == {"tiny-imagenet"}
        assert (
            merged_ann_fields
            == one_shot_ann_fields
            == {
                "license",
                "datasets:tiny-imagenet",
            }
        )


@pytest.mark.parametrize(
    "fixture_path",
    _AI_MODEL_FIXTURES,
    ids=[f"{p.parent.name}/{p.name}" for p in _AI_MODEL_FIXTURES],
)
def test_fixture_license_export(fixture_path: Path) -> None:
    """Extract metadata from a fixture file and verify SPDX 3 license output.

    Skips when:
    - The fixture file is absent from the repository clone.
    - The required optional library is not installed.
    - The model format does not embed a license (``meta.license is None``).

    When a license is present, asserts that the assembled ``build_model()``
    output contains both ``hasDeclaredLicense`` and ``hasConcludedLicense``
    relationships pointing to a ``simplelicensing_SimpleLicensingText`` element
    whose ``simplelicensing_licenseText`` matches the extracted license string.
    """
    if not fixture_path.exists():
        pytest.skip(f"Fixture not found: {fixture_path}")

    try:
        meta = read_ai_model(fixture_path)
    except ImportError as exc:
        pytest.skip(str(exc))

    if meta.license is None:
        pytest.skip(f"No license metadata embedded in {fixture_path.name}")

    exporter = build_model(meta, CreationMetadata())
    data = json.loads(exporter.to_json(pretty=True))
    graph = data["@graph"]

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 1
    assert meta.license is not None  # type: ignore[comparison-overlap]
    _check_license_relationships(graph, ai_pkgs[0]["spdxId"], meta.license)


def test_generate_smart_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate() smart entrypoint auto-detects targets correctly."""
    monkeypatch.chdir(tmp_path)
    pyproject = '[project]\nname = "smart-pkg"\nversion = "0.1.0"\n'
    (tmp_path / "pyproject.toml").write_text(pyproject)

    # 1. Directory target
    proj_json = generate(tmp_path)
    assert "smart-pkg" in proj_json

    # 2. Wheel target
    wheel_path = _make_wheel(tmp_path, "smart-wheel", "1.0.0")
    wheel_json = generate(wheel_path)
    assert "smart-wheel" in wheel_json
