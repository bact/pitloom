# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``_build_dataset_package``: core fields, dataset-profile
fields, the Croissant ExternalRef, and provenance handoff to the caller.

See also: test_spdx3_dataset_relationships.py -- the sibling covering
relationship types and dataset-profile conformance.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.dataset import (
    _build_dataset_package,
    add_datasets_for_model,
)
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.dataset_metadata import DatasetReference
from pitloom.core.models import _clear_doc_counters, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract.dataset.croissant import read_croissant
from tests._author_routes import CREATED
from tests._spdx3_validate import assert_spdx3_valid

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


_MAX_SIZE = 2**53 - 1
_BYTES = "Source: caller | Field: byte_size"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (10000, 10000),
        (0, 0),
        (_MAX_SIZE, _MAX_SIZE),
        (None, None),
        (-1, None),
        (True, None),
        (_MAX_SIZE + 1, None),
        (1.5, None),
    ],
    ids=["size", "zero", "largest", "absent", "negative", "bool", "over", "fraction"],
)
def test_byte_size_reaches_dataset_size_when_it_is_a_count(
    value: object, expected: int | None, caplog: pytest.LogCaptureFixture
) -> None:
    """A library caller's ``byte_size`` is ``dataset_datasetSize`` (bytes);
    a value that is no count gives none, with one ``WARNING:``, and the
    provenance the caller gave it goes too."""
    _clear_doc_counters(_DOC_UUID)
    exporter = _make_exporter()
    meta = _make_meta(byte_size=value, provenance={"byte_size": _BYTES})
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        add_datasets_for_model(
            generate_spdx_id("AIPackage", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID),
            [DatasetReference(role="trainedOn", metadata=meta)],
            _make_ci(),
            _DOC_NAME,
            _DOC_UUID,
            exporter,
            ai_model=AiModelMetadata(),
        )
    graph = json.loads(exporter.to_json())["@graph"]
    package = next(e for e in graph if e.get("type") == "dataset_DatasetPackage")
    assert package.get("dataset_datasetSize") == expected
    noted = [e for e in graph if e.get("type") == "Annotation"]
    stated = any("byte_size" in a["statement"] for a in noted)
    assert stated is (expected is not None)
    assert len(caplog.records) == (value is not None and expected is None)


@pytest.mark.parametrize("name", ["full.json", "prefixed.json"])
def test_a_croissant_count_gives_a_valid_deterministic_sbom_without_size(
    tmp_path: Path, name: str
) -> None:
    """The fixtures state ``totalItems``: the SBOM has no size, is valid
    SPDX 3 and is the same bytes when built again."""
    meta = read_croissant(Path(__file__).parents[1] / "fixtures" / "croissant" / name)
    model = AiModelMetadata(
        name="m", datasets=[DatasetReference(role="trainedOn", metadata=meta)]
    )
    first, second = (build_model(model, CREATED).to_json() for _ in range(2))
    assert first == second
    assert "datasetSize" not in first
    sbom = tmp_path / "m.spdx3.json"
    sbom.write_text(first, encoding="utf-8")
    assert_spdx3_valid(sbom)


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
    Core Annotation and (default ``"both"`` format) a comment."""
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
    add_datasets_for_model(
        ai_spdx_id,
        datasets,
        ci,
        _DOC_NAME,
        _DOC_UUID,
        exporter,
        ai_model=AiModelMetadata(),
    )

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
