# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``_build_dataset_package``: core fields, dataset-profile
fields, the Croissant ExternalRef, and provenance handoff to the caller.

See also: test_spdx3_dataset_relationships.py -- this module's sibling,
split from the original test_spdx3_dataset.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.dataset import (
    _build_dataset_package,
    add_datasets_for_model,
)
from pitloom.core.dataset_metadata import DatasetReference
from pitloom.core.models import _clear_doc_counters, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter

from .conftest import _DOC_NAME, _DOC_UUID, _make_ci, _make_meta


def _make_exporter() -> Spdx3JsonExporter:
    return Spdx3JsonExporter()


# ---------------------------------------------------------------------------
# _build_dataset_package -- core fields
# ---------------------------------------------------------------------------


def test_build_dataset_package_name() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(_make_meta(), _make_ci(), _DOC_NAME, _DOC_UUID)
    assert pkg.name == "Test Dataset"


def test_build_dataset_package_version() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(version="2.0"), _make_ci(), _DOC_NAME, _DOC_UUID
    )
    assert pkg.software_packageVersion == "2.0"


def test_build_dataset_package_description() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(description="A test dataset."), _make_ci(), _DOC_NAME, _DOC_UUID
    )
    assert pkg.description == "A test dataset."


def test_build_dataset_package_download_url() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(download_url="https://example.com/data"),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.software_downloadLocation == "https://example.com/data"


# ---------------------------------------------------------------------------
# _build_dataset_package -- dataset-profile fields
# ---------------------------------------------------------------------------


def test_build_dataset_package_dataset_types() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(dataset_types=["text", "numeric"]), _make_ci(), _DOC_NAME, _DOC_UUID
    )
    assert len(pkg.dataset_datasetType) == 2


def test_build_dataset_package_unknown_type_skipped() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(dataset_types=["text", "unknownXYZ"]),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    # Only "text" is valid; "unknownXYZ" is silently skipped.
    assert len(pkg.dataset_datasetType) == 1


def test_build_dataset_package_dataset_size() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(dataset_size=10000), _make_ci(), _DOC_NAME, _DOC_UUID
    )
    assert pkg.dataset_datasetSize == 10000


def test_build_dataset_package_data_collection_process() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(data_collection_process="Web crawl."),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.dataset_dataCollectionProcess == "Web crawl."


def test_build_dataset_package_preprocessing() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(data_preprocessing=["tokenization", "lowercasing"]),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert "tokenization" in pkg.dataset_dataPreprocessing
    assert "lowercasing" in pkg.dataset_dataPreprocessing


def test_build_dataset_package_known_bias() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(known_bias=["selection bias"]), _make_ci(), _DOC_NAME, _DOC_UUID
    )
    assert "selection bias" in pkg.dataset_knownBias


def test_build_dataset_package_intended_use() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(intended_use="Sentiment analysis."),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.dataset_intendedUse == "Sentiment analysis."


def test_build_dataset_package_sensitivity_no() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(has_sensitive_personal_information="no"),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.dataset_hasSensitivePersonalInformation == spdx3.PresenceType.no


def test_build_dataset_package_sensitivity_yes() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(has_sensitive_personal_information="yes"),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.dataset_hasSensitivePersonalInformation == spdx3.PresenceType.yes


def test_build_dataset_package_sensitivity_no_assertion() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(has_sensitive_personal_information="noAssertion"),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.dataset_hasSensitivePersonalInformation == spdx3.PresenceType.noAssertion


def test_build_dataset_package_invalid_sensitivity_omitted() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(has_sensitive_personal_information="maybe"),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.dataset_hasSensitivePersonalInformation is None


def test_build_dataset_package_anonymization() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(anonymization_methods=["k-anonymity"]),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert "k-anonymity" in pkg.dataset_anonymizationMethodUsed


# ---------------------------------------------------------------------------
# _build_dataset_package -- Croissant ExternalRef
# ---------------------------------------------------------------------------


def test_build_dataset_package_croissant_url_as_external_ref() -> None:
    _clear_doc_counters(_DOC_UUID)
    url = "https://huggingface.co/datasets/example/croissant.json"
    pkg = _build_dataset_package(
        _make_meta(croissant_url=url), _make_ci(), _DOC_NAME, _DOC_UUID
    )
    assert len(pkg.externalRef) == 1
    ref = pkg.externalRef[0]
    assert isinstance(ref, spdx3.ExternalRef)
    assert url in ref.locator
    assert ref.externalRefType == spdx3.ExternalRefType.other
    assert ref.comment == "Croissant metadata"


def test_build_dataset_package_no_croissant_url_no_external_ref() -> None:
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(_make_meta(), _make_ci(), _DOC_NAME, _DOC_UUID)
    assert not pkg.externalRef


# ---------------------------------------------------------------------------
# _build_dataset_package -- provenance
# ---------------------------------------------------------------------------


def test_build_dataset_package_leaves_provenance_to_caller() -> None:
    """``_build_dataset_package`` itself sets no comment -- provenance is
    emitted separately by :func:`add_datasets_for_model` via
    :func:`~pitloom.assemble.spdx3.provenance.emit_provenance` (see
    :func:`test_add_datasets_provenance_annotation_and_comment`)."""
    _clear_doc_counters(_DOC_UUID)
    pkg = _build_dataset_package(
        _make_meta(provenance={"name": "Source: test.json | Field: name"}),
        _make_ci(),
        _DOC_NAME,
        _DOC_UUID,
    )
    assert pkg.comment is None


def test_add_datasets_provenance_annotation_and_comment() -> None:
    """``add_datasets_for_model`` records the dataset's provenance as both a
    Core Annotation and (default ``"both"`` format) the legacy comment."""
    _clear_doc_counters(_DOC_UUID)
    exporter = _make_exporter()
    ci = _make_ci()
    ai_spdx_id = generate_spdx_id("AIPackage", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID)

    datasets = [
        DatasetReference(
            role="trainedOn",
            metadata=_make_meta(provenance={"name": "Source: test.json | Field: name"}),
        )
    ]
    add_datasets_for_model(ai_spdx_id, datasets, ci, _DOC_NAME, _DOC_UUID, exporter)

    data = json.loads(exporter.to_json())
    graph = data["@graph"]
    dataset_pkg = next(e for e in graph if e.get("type") == "dataset_DatasetPackage")
    assert "Metadata provenance" in dataset_pkg["comment"]
    assert "name" in dataset_pkg["comment"]

    annotations = [e for e in graph if e.get("type") == "Annotation"]
    dataset_annotations = [
        a for a in annotations if a.get("subject") == dataset_pkg["spdxId"]
    ]
    assert len(dataset_annotations) == 1
    assert dataset_annotations[0]["contentType"] == "application/json"
    statement = json.loads(dataset_annotations[0]["statement"])
    assert statement["schema"] == "https://pitloom.dev/provenance/fields/1"
    assert statement["fields"]["name"]["source"] == "test.json"
