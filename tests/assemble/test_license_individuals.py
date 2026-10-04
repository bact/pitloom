# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``NOASSERTION`` and ``NONE`` as the ``NoAssertionLicense``/``NoneLicense``
individuals, end to end: a document that uses them validates against the
SPDX 3 schema and SHACL model (network), and merges as a fragment.

See also: :mod:`tests.assemble.test_license_elements_surfaces` for every
surface, :mod:`tests.core.test_fragments_dangling_refs` for the merge rule.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble.spdx3.document import build, build_model
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.extract.remote.huggingface import read_huggingface
from tests._license_graph import (
    graph_of,
    license_elements,
    license_targets,
    onnx_model,
    provenance_fields,
    two_packages,
)
from tests._network import assert_spdx3_validate_ok
from tests.extract.remote.hf_patches._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)


def _document(declared: str, concluded: str | None, model: str) -> DocumentModel:
    """A project, an AI model and a file that state each licence given."""
    file = ProjectFile(
        physical_path="pkg/a.py",
        distribution_path="pkg/a.py",
        digest_sha256="a" * 64,
        spdx_license_identifier="MIT",
    )
    project = ProjectMetadata(
        name="p",
        version="1.0",
        license_name=declared,
        license_concluded=concluded,
        files=[file],
    )
    return DocumentModel(
        project=project,
        creation_metadata=CreationMetadata(),
        ai_models=[onnx_model(model)],
    )


@pytest.mark.network
@pytest.mark.parametrize(
    ("declared", "concluded", "model"),
    [
        ("unknown", None, "NOASSERTION"),
        ("NONE", "NOASSERTION", "none"),
        ("MIT", "NONE", "unknown"),
    ],
)
def test_a_document_using_the_individuals_validates(
    tmp_path: Path, declared: str, concluded: str | None, model: str
) -> None:
    sbom = tmp_path / "sbom.json"
    sbom.write_text(build(_document(declared, concluded, model)).to_json())
    assert_spdx3_validate_ok(sbom)


def test_a_built_document_with_individuals_merges_as_a_fragment(
    tmp_path: Path,
) -> None:
    """The output of a build, read back as a fragment, resolves its
    references to the individuals and keeps every licence relationship."""
    fragment = build(_document("unknown", "NONE", "NOASSERTION"))
    (tmp_path / "frag.spdx3.json").write_text(fragment.to_json())
    merged = build(
        DocumentModel(
            project=ProjectMetadata(name="base", version="1.0"),
            creation_metadata=CreationMetadata(),
        )
    )
    merge_fragments(tmp_path, [FragmentConfig(path="frag.spdx3.json")], merged)

    graph: list[dict[str, Any]] = json.loads(merged.to_json())["@graph"]
    assert sorted(license_targets(graph)) == sorted(
        license_targets(json.loads(fragment.to_json())["@graph"])
    )
    assert {"NOASSERTION", "NONE", "MIT"} <= set(license_targets(graph))
    document = next(e for e in graph if e["type"] == "SpdxDocument")
    assert "expandedLicensing" in document["profileConformance"]


@pytest.mark.parametrize(
    ("raw", "normalised"),
    [
        ("UNKNOWN", True),
        ("unknown", True),
        ("NOASSERTION", False),
        ("none", True),
        ("NONE", False),
    ],
)
def test_an_individual_carries_the_source_on_the_relationship(
    raw: str, normalised: bool
) -> None:
    """An individual cannot hold provenance, so the relationship does: the
    source, and what it literally said when that was not the SPDX spelling."""
    graph = two_packages([raw])
    (rel,) = [e for e in graph if e["type"] == "Relationship"]
    fields = provenance_fields(graph, rel["spdxId"])
    # A plain source of a transparent manifest is left out by the default
    # filter, as for any other value; a normalisation note is kept.
    assert bool(fields) is normalised
    assert all("normalized-from" in f for f in fields)
    assert ("Normalized-From" in rel.get("comment", "")) is normalised
    # No parse took place, so no parser is named.
    assert "Normalizer" not in rel.get("comment", "")


def test_an_individual_is_shared_by_every_package_stating_it() -> None:
    graph = two_packages(["NOASSERTION", "unknown", "NONE"])
    rels = [e for e in graph if e["type"] == "Relationship"]
    assert rels[0]["to"] == rels[1]["to"]
    assert len({r["to"][0] for r in rels}) == 2
    assert not license_elements(graph)
    # Each relationship keeps its own note: only the second was normalised.
    assert [bool(provenance_fields(graph, r["spdxId"])) for r in rels] == [
        False,
        True,
        False,
    ]


def test_a_relationship_description_names_the_individual() -> None:
    project = ProjectMetadata(name="p", version="1.0", license_name="unknown")
    exporter = build(
        DocumentModel(project=project, creation_metadata=CreationMetadata())
    )
    graph = json.loads(exporter.to_json(describe_relationship=True))["@graph"]
    (rel,) = [e for e in graph if e["type"] == "Relationship"]
    assert rel["description"].endswith("hasDeclaredLicense: NOASSERTION")
    assert "expandedlicensing" not in rel["description"]


@pytest.mark.parametrize(
    ("card_license", "targets"),
    [
        ("unknown", ["NOASSERTION"]),
        ("Unknown", ["NOASSERTION"]),
        ("mit", ["MIT"]),
        ("other", []),
        (None, []),
    ],
)
def test_a_hugging_face_card_license_by_outcome(
    card_license: str | None, targets: list[str]
) -> None:
    """The Hugging Face surface: ``unknown`` is a ``NOASSERTION``, ``other``
    and a missing field state nothing (mocked Hub, no licence files)."""
    with _patch_hf_calls(card_data=_make_card_data(license=card_license)):
        meta = read_huggingface("org/model")
    graph = graph_of(build_model(meta, CreationMetadata()))
    assert license_targets(graph) == targets
