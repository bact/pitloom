# ruff: noqa: F403, F405
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom import loom
from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3.fragments import FragmentMergeError, merge_fragments
from pitloom.core.creation import CreationMetadata, Creator
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.ids import IdRegistry

from .conftest import (
    _AI_MODEL_FRAGMENT,
    _DATASET_FRAGMENT,
    _PYPROJECT_TEMPLATE,
    _TRAINING_RUN_FRAGMENT,
    _by_type,
    _hyperparams,
    _merge_and_parse,
    _relationships,
)


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

    sbom_json = generate_project_sbom(
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


def test_unification_annotation_records_sha256_merge() -> None:
    """When a fragment element unifies with a base element by SHA-256 content
    equality, the merge records a Core Annotation on the survivor naming the
    criterion, the dropped id, and the origin fragment -- provenance the merge
    would otherwise silently discard."""
    # pylint: disable=import-outside-toplevel

    import hashlib

    # pylint: disable=import-outside-toplevel
    from pitloom.assemble.spdx3.document import build

    # pylint: disable=import-outside-toplevel
    from pitloom.core.document import DocumentModel

    # pylint: disable=import-outside-toplevel
    from pitloom.core.project import (
        ProjectFile,
        ProjectMetadata,
    )

    model_bytes = b"MODELDATA" * 100
    sha = hashlib.sha256(model_bytes).hexdigest()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        project_file = ProjectFile(
            physical_path="pkg/model.bin",
            distribution_path="pkg/model.bin",
            digest_sha256=sha,
        )
        doc = DocumentModel(
            project=ProjectMetadata(name="demo", version="1.0.0", files=[project_file]),
            creation_metadata=CreationMetadata(
                creation_datetime="2026-01-01T00:00:00+00:00"
            ),
        )
        exporter = build(doc)

        fragment = {
            "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
            "@graph": [
                {
                    "type": "CreationInfo",
                    "@id": "_:ci",
                    "specVersion": "3.0.1",
                    "created": "2026-01-01T00:00:00Z",
                    "createdBy": ["urn:agent"],
                },
                {
                    "type": "Agent",
                    "spdxId": "urn:agent",
                    "name": "x",
                    "creationInfo": "_:ci",
                },
                {
                    "type": "software_File",
                    "spdxId": "https://frag/doc#File-99",
                    "name": "model.bin",
                    "creationInfo": "_:ci",
                    "verifiedUsing": [
                        {"type": "Hash", "algorithm": "sha256", "hashValue": sha}
                    ],
                },
            ],
        }
        (tmp_path / "frag.spdx3.json").write_text(json.dumps(fragment))

        merge_fragments(tmp_path, ["frag.spdx3.json"], exporter)
        graph = json.loads(exporter.to_json())["@graph"]

        unification = [
            a
            for a in graph
            if a.get("type") == "Annotation"
            and "provenance/unification/1" in a.get("statement", "")
        ]
        assert len(unification) == 1
        statement = json.loads(unification[0]["statement"])
        assert statement["criterion"] == "sha256"
        assert statement["unified"] == ["https://frag/doc#File-99"]
        assert statement["fragments"] == ["frag.spdx3.json"]


def test_merge_fragments_populates_spdx_document_imports(tmp_path: Path) -> None:
    """merge_fragments() must populate main_doc.import_ with ExternalMap
    entries naming each merged fragment's SpdxDocument spdxId and location hint.
    """
    frag_namespace = "https://spdx.org/spdxdocs/fragment-import-test"
    envelope_fragment = {
        "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
        "@graph": [
            {
                "type": "CreationInfo",
                "@id": "_:creationinfo0",
                "specVersion": "3.0.1",
                "created": "2026-01-01T00:00:00Z",
                "createdBy": [f"{frag_namespace}#Agent-1"],
            },
            {
                "type": "SoftwareAgent",
                "spdxId": f"{frag_namespace}#Agent-1",
                "creationInfo": "_:creationinfo0",
                "name": "Pitloom",
            },
            {
                "type": "SpdxDocument",
                "spdxId": frag_namespace,
                "creationInfo": "_:creationinfo0",
                "rootElement": [f"{frag_namespace}#Sbom-1"],
            },
            {
                "type": "software_Sbom",
                "spdxId": f"{frag_namespace}#Sbom-1",
                "creationInfo": "_:creationinfo0",
                "rootElement": [f"{frag_namespace}#AIPackage-1"],
            },
            {
                "type": "ai_AIPackage",
                "spdxId": f"{frag_namespace}#AIPackage-1",
                "creationInfo": "_:creationinfo0",
                "name": "imported-model",
            },
        ],
    }
    frag_path = tmp_path / "frag-import.spdx3.json"
    frag_path.write_text(json.dumps(envelope_fragment))

    ci = spdx3.CreationInfo(
        _id="_:ci",
        specVersion="3.0.1",
        created=datetime.now(timezone.utc),
        createdBy=["https://spdx.org/agent1"],
    )
    main_doc = spdx3.SpdxDocument(
        spdxId="https://spdx.org/spdxdocs/main-doc",
        name="main-doc",
        creationInfo=ci,
    )
    exporter = Spdx3JsonExporter()
    exporter.add_document(main_doc)

    merge_fragments(tmp_path, ["frag-import.spdx3.json"], exporter)

    graph = json.loads(exporter.to_json(pretty=True)).get("@graph", [])
    docs = [e for e in graph if e.get("type") == "SpdxDocument"]
    assert len(docs) == 1
    doc = docs[0]

    imports = doc.get("import", [])
    frag_imports = [
        m
        for m in imports
        if m.get("type") == "ExternalMap" and m.get("externalSpdxId") == frag_namespace
    ]
    assert len(frag_imports) == 1
    assert frag_imports[0].get("locationHint") == "frag-import.spdx3.json"


def test_merge_fragments_raises_on_dangling_reference(tmp_path: Path) -> None:
    """A fragment whose Relationship references an id absent from the base
    SBOM (the doc_uuid-staleness scenario) must fail the merge, not just
    warn -- merge_fragments() must not silently produce a broken graph."""
    frag_namespace = "https://spdx.org/spdxdocs/dangling-frag-test"
    fragment = {
        "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
        "@graph": [
            {
                "type": "CreationInfo",
                "@id": "_:creationinfo0",
                "specVersion": "3.0.1",
                "created": "2026-01-01T00:00:00Z",
                "createdBy": [f"{frag_namespace}#Agent-1"],
            },
            {
                "type": "SoftwareAgent",
                "spdxId": f"{frag_namespace}#Agent-1",
                "creationInfo": "_:creationinfo0",
                "name": "Pitloom",
            },
            {
                "type": "Relationship",
                "spdxId": f"{frag_namespace}#Relationship-1",
                "creationInfo": "_:creationinfo0",
                "from": "https://spdx.org/spdxdocs/main-doc#stale-package",
                "to": ["https://spdx.org/spdxdocs/main-doc#also-stale"],
                "relationshipType": "dependsOn",
            },
        ],
    }
    frag_path = tmp_path / "dangling-frag.spdx3.json"
    frag_path.write_text(json.dumps(fragment))

    ci = spdx3.CreationInfo(
        _id="_:ci",
        specVersion="3.0.1",
        created=datetime.now(timezone.utc),
        createdBy=["https://spdx.org/agent1"],
    )
    main_doc = spdx3.SpdxDocument(
        spdxId="https://spdx.org/spdxdocs/main-doc",
        name="main-doc",
        creationInfo=ci,
    )
    exporter = Spdx3JsonExporter()
    exporter.add_document(main_doc)

    with pytest.raises(FragmentMergeError, match="dangling reference"):
        merge_fragments(tmp_path, ["dangling-frag.spdx3.json"], exporter)


def test_merge_fragments_empty_fragment_list_skips_dangling_check(
    tmp_path: Path,
) -> None:
    """An empty fragment list (or one where nothing could be ingested) must
    not run the dangling-reference check at all -- a pre-existing, unrelated
    dangling Relationship in the base document alone must not fail a merge
    that never actually merged anything."""
    ci = spdx3.CreationInfo(
        _id="_:ci",
        specVersion="3.0.1",
        created=datetime.now(timezone.utc),
        createdBy=["https://spdx.org/agent1"],
    )
    rel = spdx3.Relationship(
        spdxId="https://spdx.org/spdxdocs/main-doc#Relationship-1",
        from_="https://spdx.org/spdxdocs/main-doc#missing",
        to=["https://spdx.org/spdxdocs/main-doc#also-missing"],
        relationshipType=spdx3.RelationshipType.dependsOn,
        creationInfo=ci,
    )
    exporter = Spdx3JsonExporter()
    exporter.add_relationship(rel)

    merge_fragments(tmp_path, [], exporter)
