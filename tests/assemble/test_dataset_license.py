# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A dataset's licence becomes a ``hasDeclaredLicense`` (or, from a
third-party record, ``hasConcludedLicense``) relationship, as a model's does.

See also: tests/assemble/test_license_elements_surfaces.py (the model side).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.dataset_metadata import (
    DatasetMetadata,
    DatasetReference,
    FurtherLicences,
)
from tests._author_routes import CREATED
from tests._spdx3_validate import assert_spdx3_valid

Graph = list[dict[str, Any]]


def _graph(
    dataset_license: str | None,
    *,
    model_license: str | None = None,
    provenance: dict[str, str] | None = None,
    further: FurtherLicences | None = None,
) -> Graph:
    dataset = DatasetMetadata(
        name="corpus",
        license=dataset_license,
        further_licenses=further,
        provenance=provenance or {},
    )
    model = AiModelMetadata(
        name="m",
        license=model_license,
        datasets=[DatasetReference(role="trainedOn", metadata=dataset)],
    )
    graph: Graph = json.loads(build_model(model, CREATED).to_json())["@graph"]
    return graph


def _of(graph: Graph, type_name: str) -> list[dict[str, Any]]:
    return [e for e in graph if e["type"] == type_name]


def _licence_links(graph: Graph) -> list[tuple[str, str, str]]:
    """(kind of source element, relationship type, licence element name)."""
    by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
    return sorted(
        (
            by_id[r["from"]]["type"],
            r["relationshipType"],
            by_id[r["to"][0]].get("name", ""),
        )
        for r in _of(graph, "Relationship")
        if r["relationshipType"].endswith("License")
    )


@pytest.mark.parametrize(
    ("licence", "name"),
    [
        ("CC-BY-4.0", "CC-BY-4.0"),
        ("MIT OR Apache-2.0", "Apache-2.0 OR MIT"),
        # A URL and free text are kept as text, not guessed into an expression;
        # another spelling of an id is read as the id (separator).
        ("https://creativecommons.org/licenses/by/4.0/",
         "https://creativecommons.org/licenses/by/4.0/"),
        ("Custom terms 2026", "Custom terms 2026"),
        ("CC BY 4.0", "CC-BY-4.0"),
        # Invisible and bidi controls are written escaped.
        ("MIT\u202e", "MIT\\u202e"),
    ],
    ids=["id", "expression", "url", "free-text", "respelled", "bidi"],
)  # fmt: skip
def test_dataset_licence_is_declared(licence: str, name: str) -> None:
    graph = _graph(licence)
    assert _licence_links(graph) == [
        ("dataset_DatasetPackage", "hasDeclaredLicense", name)
    ]


@pytest.mark.parametrize("licence", [None, ""], ids=["none", "empty"])
def test_no_licence_makes_no_element_or_relationship(licence: str | None) -> None:
    graph = _graph(licence)
    assert _licence_links(graph) == []
    assert not [e for e in graph if "icens" in e["type"]]


def test_a_third_party_record_is_concluded() -> None:
    graph = _graph("MIT", provenance={"license": "Source: PyPI JSON API"})
    assert _licence_links(graph) == [
        ("dataset_DatasetPackage", "hasConcludedLicense", "MIT")
    ]


def test_dataset_and_model_with_one_licence_share_its_element() -> None:
    graph = _graph("Apache-2.0", model_license="Apache-2.0")
    assert len(_of(graph, "simplelicensing_LicenseExpression")) == 1
    assert _licence_links(graph) == [
        ("ai_AIPackage", "hasDeclaredLicense", "Apache-2.0"),
        ("dataset_DatasetPackage", "hasDeclaredLicense", "Apache-2.0"),
    ]


def test_a_dataset_licence_does_not_become_the_models() -> None:
    graph = _graph("CC-BY-4.0")
    assert [k for k, _, _ in _licence_links(graph)] == ["dataset_DatasetPackage"]


def test_the_sbom_with_dataset_licences_is_valid(tmp_path: Path) -> None:
    dataset = DatasetMetadata(name="corpus", license="CC-BY-4.0")
    model = AiModelMetadata(
        name="m",
        license="Apache-2.0",
        datasets=[DatasetReference(role="trainedOn", metadata=dataset)],
    )
    path = tmp_path / "sbom.json"
    path.write_text(build_model(model, CREATED).to_json(), encoding="utf-8")
    assert_spdx3_valid(path)


_FURTHER = FurtherLicences(("GFDL-1.3-or-later",), "Hugging Face dataset card")


def test_several_licences_are_each_declared_with_one_comment() -> None:
    graph = _graph("CC-BY-SA-3.0", further=_FURTHER)
    assert _licence_links(graph) == [
        ("dataset_DatasetPackage", "hasDeclaredLicense", "CC-BY-SA-3.0"),
        ("dataset_DatasetPackage", "hasDeclaredLicense", "GFDL-1.3-or-later"),
    ]
    (package,) = _of(graph, "dataset_DatasetPackage")
    assert package["comment"].startswith(
        "The Hugging Face dataset card lists several licences; it does not say "
        "whether they combine as AND or OR."
    )


def test_one_licence_has_no_several_licences_comment() -> None:
    (package,) = _of(_graph("CC-BY-SA-3.0"), "dataset_DatasetPackage")
    assert "several licences" not in package.get("comment", "")


def test_several_licences_sbom_is_valid_and_identical(tmp_path: Path) -> None:
    dataset = DatasetMetadata(
        name="corpus", license="CC-BY-SA-3.0", further_licenses=_FURTHER
    )
    model = AiModelMetadata(
        name="m", datasets=[DatasetReference(role="trainedOn", metadata=dataset)]
    )
    outputs = [build_model(model, CREATED).to_json() for _ in range(2)]
    assert outputs[0] == outputs[1]
    path = tmp_path / "sbom.json"
    path.write_text(outputs[0], encoding="utf-8")
    assert_spdx3_valid(path)
