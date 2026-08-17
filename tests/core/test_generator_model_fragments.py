# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for enrich_model(): bare-fragment output, id-consistency with
generate_model_sbom()/generate_project_sbom(), registry-pinned ids, and
build_model() base-model lineage.

See also: tests/core/test_generator_model.py for registry-based id reuse
in the assembler/build_deployed(). tests/core/test_generator_model_enrichment.py
for license handling, external identifiers, and README enrichment
variants.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from pitloom.assemble import enrich_model, generate_model_sbom, generate_project_sbom
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.ids import IdRegistry

from .conftest import _AI_MODEL_ROOT, _write_smoke_project


def test_enrich_model_writes_bare_graph_fragment() -> None:
    """enrich_model() must always run enrichment regardless of
    [tool.pitloom] enrich (calling it is itself the opt-in), and its output
    must be a bare @graph fragment -- no SpdxDocument/software_Sbom/
    ai_AIPackage wrapper -- containing only what the enrichment run added."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )

        fragment_json = enrich_model(model_path)
        fragment = json.loads(fragment_json)

        assert set(fragment.keys()) == {"@context", "@graph"}
        types = {e.get("type") for e in fragment["@graph"]}
        assert "SpdxDocument" not in types
        assert "software_Sbom" not in types
        assert "ai_AIPackage" not in types

        ds_pkgs = [
            e for e in fragment["@graph"] if e.get("type") == "dataset_DatasetPackage"
        ]
        assert len(ds_pkgs) == 1
        assert ds_pkgs[0]["name"] == "tiny-imagenet"

        annotations = [e for e in fragment["@graph"] if e.get("type") == "Annotation"]
        enrichment_anns = [
            a
            for a in annotations
            if a.get("statement")
            and json.loads(a["statement"]).get("kind") == "enrichment"
        ]
        assert len(enrichment_anns) == 1
        changed_fields = {
            c["field"] for c in json.loads(enrichment_anns[0]["statement"])["changes"]
        }
        assert changed_fields == {"license", "datasets:tiny-imagenet"}


def test_enrich_model_no_readme_produces_empty_fragment() -> None:
    """No adjacent README: enrich_model() must not raise -- it writes a
    valid fragment with no enrichment content."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())

        fragment = json.loads(enrich_model(model_path))

        assert not [
            e for e in fragment["@graph"] if e.get("type") == "dataset_DatasetPackage"
        ]
        assert not [e for e in fragment["@graph"] if e.get("type") == "Annotation"]


def test_enrich_model_rejects_huggingface_source() -> None:
    """A Hugging Face source has no local enrichment to run -- HF model
    cards are already parsed natively -- so enrich_model() must reject it
    with a clear error rather than silently doing nothing."""
    with pytest.raises(ValueError, match="Hugging Face"):
        enrich_model("org/model-id")


def test_enrich_model_and_generate_model_sbom_reference_matching_ai_package_id() -> (
    None
):
    """Design invariant: a fragment from enrich_model() run against a local
    file must reference the exact same ai_AIPackage spdxId that
    generate_model_sbom(enrich=True) on the same file would assign -- both
    go through the same identity computation (_ai_model_identity), so the
    fragment's Annotation subject resolves to the base doc's real AI
    package once merged. The fragment's own newly-minted elements
    (CreationInfo, Tool, Annotation, DatasetPackage) deliberately live in a
    separate id namespace from the base doc -- see build_enrichment_fragment's
    docstring -- so only the referenced ai_AIPackage id is expected to
    match, not the fragment's full id set."""
    fixture = _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(fixture.read_bytes())
        (tmppath / "README.md").write_text(
            "---\nlicense: apache-2.0\ndatasets:\n  - tiny-imagenet\n---\n"
        )

        fragment = json.loads(enrich_model(model_path))
        full_doc = json.loads(generate_model_sbom(model_path, enrich=True))

        full_ai_pkg = next(
            e for e in full_doc["@graph"] if e.get("type") == "ai_AIPackage"
        )
        enrichment_ann = next(
            e
            for e in fragment["@graph"]
            if e.get("type") == "Annotation"
            and json.loads(e.get("statement", "{}")).get("kind") == "enrichment"
        )
        assert enrichment_ann["subject"] == full_ai_pkg["spdxId"]


def test_enrich_model_project_target_matches_project_level_ai_package_id() -> None:
    """A fragment from enrich_model(project_target=...) must reference the
    same ai_AIPackage id generate_project_sbom() assigns for that model --
    project-level and single-model identity schemes differ (project name/
    version/dependencies/Merkle root vs. the model's own name/version), so
    without project_target the fragment would reference a nonexistent id
    once merged into a project-level base document (the bug this test
    guards against)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = _write_smoke_project(tmppath)

        fragment = json.loads(enrich_model(model_path, project_target=tmppath))
        full_doc = json.loads(generate_project_sbom(tmppath, enrich=True))

        full_ai_pkg = next(
            e for e in full_doc["@graph"] if e.get("type") == "ai_AIPackage"
        )
        enrichment_ann = next(
            e
            for e in fragment["@graph"]
            if e.get("type") == "Annotation"
            and json.loads(e.get("statement", "{}")).get("kind") == "enrichment"
        )
        assert enrichment_ann["subject"] == full_ai_pkg["spdxId"]


def test_enrich_model_without_project_target_mismatches_project_level_id() -> None:
    """Negative-space guard: *without* project_target, the fragment's
    referenced id must NOT match the project-level ai_AIPackage id -- if
    this test starts failing (i.e. they start matching by coincidence),
    the project_target parameter has become unnecessary and the "why" in
    build_enrichment_fragment's docstring needs re-checking, not this
    test silently loosened."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = _write_smoke_project(tmppath)

        fragment = json.loads(enrich_model(model_path))
        full_doc = json.loads(generate_project_sbom(tmppath, enrich=True))

        full_ai_pkg = next(
            e for e in full_doc["@graph"] if e.get("type") == "ai_AIPackage"
        )
        enrichment_ann = next(
            e
            for e in fragment["@graph"]
            if e.get("type") == "Annotation"
            and json.loads(e.get("statement", "{}")).get("kind") == "enrichment"
        )
        assert enrichment_ann["subject"] != full_ai_pkg["spdxId"]


def test_enrich_model_project_target_merges_correctly_end_to_end() -> None:
    """The actual regression test for the bug: a fragment generated with
    project_target, registered under [tool.pitloom.fragment], and merged
    via a real generate_project_sbom() re-run must produce a
    dataset_DatasetPackage and enrichment Annotation genuinely attached to
    the project's real ai_AIPackage -- not just matching id strings in
    isolation (see the two tests above), but surviving an actual
    merge_fragments() pass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = _write_smoke_project(tmppath)

        fragment_path = tmppath / "model.enrich.spdx3.json"
        enrich_model(model_path, project_target=tmppath, output_path=fragment_path)
        with (tmppath / "pyproject.toml").open("a") as f:
            f.write('\n[tool.pitloom.fragment]\nfiles = ["model.enrich.spdx3.json"]\n')

        merged = json.loads(generate_project_sbom(tmppath))
        graph = merged["@graph"]

        ai_pkg = next(e for e in graph if e.get("type") == "ai_AIPackage")
        ds_pkgs = [e for e in graph if e.get("type") == "dataset_DatasetPackage"]
        assert len(ds_pkgs) == 1
        assert ds_pkgs[0]["name"] == "tiny-imagenet"

        rels = [e for e in graph if e.get("type") == "Relationship"]
        trained_on = [
            r
            for r in rels
            if r.get("relationshipType") == "trainedOn"
            and r.get("from") == ai_pkg["spdxId"]
            and ds_pkgs[0]["spdxId"] in r.get("to", [])
        ]
        assert len(trained_on) == 1

        annotations = [e for e in graph if e.get("type") == "Annotation"]
        enrichment_anns = [
            a
            for a in annotations
            if a.get("subject") == ai_pkg["spdxId"]
            and json.loads(a.get("statement", "{}")).get("kind") == "enrichment"
        ]
        assert len(enrichment_anns) == 1


def test_enrich_model_registry_pinned_id_matches_base_doc() -> None:
    """A registry-pinned ai_AIPackage id must be referenced by the
    fragment too, not the freshly computed one -- otherwise a project
    using a stable registry (--registry) gets the same dangling-reference
    bug as the project_target case, even for a single-model base doc."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        model_path = tmppath / "model.safetensors"
        model_path.write_bytes(
            (
                _AI_MODEL_ROOT / "safetensors" / "phi-tiny-random.safetensors"
            ).read_bytes()
        )
        (tmppath / "README.md").write_text("---\ndatasets:\n  - tiny-imagenet\n---\n")

        registry_path = tmppath / "loom-ids.json"
        registry = IdRegistry.new("pinned-demo", path=registry_path)
        pinned_id = registry.register_entity("model", "ai_AIPackage")
        registry.save()

        full_doc = json.loads(
            generate_model_sbom(model_path, enrich=True, registry=registry_path)
        )
        fragment = json.loads(enrich_model(model_path, registry=registry_path))

        full_ai_pkg = next(
            e for e in full_doc["@graph"] if e.get("type") == "ai_AIPackage"
        )
        assert full_ai_pkg["spdxId"] == pinned_id

        enrichment_ann = next(
            e
            for e in fragment["@graph"]
            if e.get("type") == "Annotation"
            and json.loads(e.get("statement", "{}")).get("kind") == "enrichment"
        )
        assert enrichment_ann["subject"] == pinned_id


def test_build_model_base_model_lineage() -> None:
    """build_model() must emit a stub base model ai_AIPackage and a descendantOf
    Relationship when base_model and base_model_relation are present
    (base-model lineage).
    """
    meta = AiModelMetadata(
        name="my-finetuned-model",
        base_model="Qwen/Qwen2.5-Math-1.5B",
        base_model_relation="finetune",
    )
    exporter = build_model(meta, CreationMetadata())
    graph = json.loads(exporter.to_json(pretty=True)).get("@graph", [])

    ai_pkgs = [e for e in graph if e.get("type") == "ai_AIPackage"]
    assert len(ai_pkgs) == 2
    derived_pkg = next(p for p in ai_pkgs if p["name"] == "my-finetuned-model")
    base_pkg = next(p for p in ai_pkgs if p["name"] == "Qwen2.5-Math-1.5B")

    ext_refs = base_pkg.get("externalRef", [])
    assert any(
        r.get("externalRefType") == "altWebPage"
        and "https://huggingface.co/Qwen/Qwen2.5-Math-1.5B" in r.get("locator", [])
        for r in ext_refs
    )

    rels = [e for e in graph if e.get("type") == "Relationship"]
    lineage_rels = [
        r
        for r in rels
        if r.get("relationshipType") == "descendantOf"
        and r.get("from") == derived_pkg["spdxId"]
        and base_pkg["spdxId"] in r.get("to", [])
    ]
    assert len(lineage_rels) == 1
    assert lineage_rels[0].get("comment") == "base_model_relation:finetune"
