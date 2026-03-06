# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Croissant dataset metadata extraction."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from loom.extractors.croissant import (
    CroissantDatasetMetadata,
    _extract_agent_names,
    _map_metadata,
    enrich_dataset_package,
    extract_croissant_metadata,
    load_croissant_from_url,
)

# ---------------------------------------------------------------------------
# Minimal valid Croissant JSON-LD fixture
# ---------------------------------------------------------------------------

_MINIMAL_CROISSANT = {
    "@context": {
        "@language": "en",
        "@vocab": "https://schema.org/",
        "sc": "https://schema.org/",
        "cr": "http://mlcommons.org/croissant/",
        "citeAs": "cr:citeAs",
        "conformsTo": "dct:conformsTo",
        "dct": "http://purl.org/dc/terms/",
        "field": "cr:field",
        "dataType": "cr:dataType",
        "source": "cr:source",
        "extract": "cr:extract",
        "recordSet": "cr:recordSet",
        "includes": "cr:includes",
    },
    "@type": "sc:Dataset",
    "name": "Test Dataset",
    "description": "A test dataset for AI training.",
    "url": "https://example.com/dataset",
    "license": "https://creativecommons.org/licenses/by/4.0/",
    "version": "1.0.0",
    "keywords": ["machine learning", "test"],
    "conformsTo": "http://mlcommons.org/croissant/1.0",
}

_FULL_CROISSANT = {
    **_MINIMAL_CROISSANT,
    "citeAs": "@article{test2025, title={Test Dataset}}",
    "datePublished": "2024-01-15",
    "dateCreated": "2023-06-01",
    "dateModified": "2024-02-20",
    "inLanguage": "en",
    "creator": {"@type": "sc:Organization", "name": "Test Org"},
}


# ---------------------------------------------------------------------------
# extract_croissant_metadata — dict input
# ---------------------------------------------------------------------------


def test_extract_from_dict_basic():
    """Basic fields are extracted from a Croissant dict."""
    meta = extract_croissant_metadata(_MINIMAL_CROISSANT)

    assert meta.name == "Test Dataset"
    assert meta.description == "A test dataset for AI training."
    assert meta.url == "https://example.com/dataset"
    assert meta.version == "1.0.0"
    assert "https://creativecommons.org/licenses/by/4.0/" in meta.license
    assert "machine learning" in meta.keywords
    assert "test" in meta.keywords


def test_extract_from_dict_provenance():
    """Provenance entries are populated for extracted fields."""
    meta = extract_croissant_metadata(_MINIMAL_CROISSANT)

    assert "name" in meta.provenance
    assert "url" in meta.provenance
    assert "license" in meta.provenance
    assert "Croissant" in meta.provenance["name"]


def test_extract_from_file(tmp_path: Path):
    """Metadata is extracted from a local Croissant JSON file."""
    croissant_file = tmp_path / "dataset.json"
    croissant_file.write_text(json.dumps(_MINIMAL_CROISSANT), encoding="utf-8")

    meta = extract_croissant_metadata(croissant_file)
    assert meta.name == "Test Dataset"
    assert meta.url == "https://example.com/dataset"


def test_extract_from_file_string_path(tmp_path: Path):
    """Metadata is extracted from a local Croissant JSON path given as str."""
    croissant_file = tmp_path / "dataset.json"
    croissant_file.write_text(json.dumps(_MINIMAL_CROISSANT), encoding="utf-8")

    meta = extract_croissant_metadata(str(croissant_file))
    assert meta.name == "Test Dataset"


def test_extract_file_not_found():
    """FileNotFoundError is raised for non-existent paths."""
    with pytest.raises(FileNotFoundError):
        extract_croissant_metadata(Path("/nonexistent/dataset.json"))


def test_extract_invalid_document():
    """ValueError is raised for an invalid Croissant document."""
    bad_doc = {"@context": {"@vocab": "https://schema.org/"}, "name": "Bad"}
    with pytest.raises(ValueError):
        extract_croissant_metadata(bad_doc)


# ---------------------------------------------------------------------------
# extract_croissant_metadata — ImportError when mlcroissant missing
# ---------------------------------------------------------------------------


def test_extract_raises_import_error_without_mlcroissant():
    """ImportError is raised when mlcroissant is not installed."""
    with patch.dict("sys.modules", {"mlcroissant": None}):
        with pytest.raises(ImportError, match="mlcroissant"):
            extract_croissant_metadata(_MINIMAL_CROISSANT)


# ---------------------------------------------------------------------------
# load_croissant_from_url
# ---------------------------------------------------------------------------


def test_load_from_url_success():
    """load_croissant_from_url returns parsed JSON on success."""
    payload = json.dumps({"name": "Remote Dataset"}).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = payload
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = load_croissant_from_url("https://example.com/croissant.json")

    assert result == {"name": "Remote Dataset"}


def test_load_from_url_network_error():
    """ValueError is raised on network failure."""
    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        with pytest.raises(ValueError, match="Failed to fetch"):
            load_croissant_from_url("https://example.com/croissant.json")


def test_load_from_url_invalid_json():
    """ValueError is raised when the response is not valid JSON."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"not json {"
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(ValueError, match="not valid JSON"):
            load_croissant_from_url("https://example.com/croissant.json")


# ---------------------------------------------------------------------------
# _extract_agent_names
# ---------------------------------------------------------------------------


def test_extract_agent_names_empty():
    assert _extract_agent_names(None) == []
    assert _extract_agent_names([]) == []


def test_extract_agent_names_with_objects():
    agent1 = MagicMock()
    agent1.name = "Alice"
    agent2 = MagicMock()
    agent2.name = "Bob Inc."
    result = _extract_agent_names([agent1, agent2])
    assert result == ["Alice", "Bob Inc."]


def test_extract_agent_names_missing_name():
    agent = MagicMock(spec=[])  # no 'name' attribute
    assert _extract_agent_names([agent]) == []


# ---------------------------------------------------------------------------
# _map_metadata — RAI fields
# ---------------------------------------------------------------------------


def _make_metadata_mock(**kwargs: object) -> MagicMock:
    """Build a mock of a mlcroissant Metadata object."""
    defaults = {
        "name": None,
        "description": None,
        "url": None,
        "version": None,
        "license": None,
        "keywords": None,
        "in_language": None,
        "date_published": None,
        "date_created": None,
        "date_modified": None,
        "cite_as": None,
        "creators": [],
        "publisher": [],
        "data_collection": None,
        "data_collection_type": None,
        "data_preprocessing_protocol": None,
        "data_annotation_protocol": None,
        "data_biases": None,
        "data_use_cases": None,
        "data_limitations": None,
        "data_social_impact": None,
        "personal_sensitive_information": None,
    }
    defaults.update(kwargs)
    mock = MagicMock(spec=list(defaults.keys()))
    for attr, val in defaults.items():
        setattr(mock, attr, val)
    return mock


def test_map_metadata_rai_fields():
    """RAI fields from the Croissant RAI spec are mapped correctly."""
    mock_meta = _make_metadata_mock(
        name="RAI Dataset",
        data_collection="Surveys and interviews",
        data_biases=["selection bias", "reporting bias"],
        data_use_cases=["sentiment analysis"],
        data_limitations=["English only"],
        data_social_impact="May affect hiring decisions",
        personal_sensitive_information=["names", "emails"],
    )

    result = _map_metadata(mock_meta, "test-source")

    assert result.data_collection == "Surveys and interviews"
    assert "selection bias" in result.data_biases
    assert "sentiment analysis" in result.data_use_cases
    assert "English only" in result.data_limitations
    assert result.data_social_impact == "May affect hiring decisions"
    assert "names" in result.personal_sensitive_information
    assert "data_biases" in result.provenance


def test_map_metadata_dates():
    """Date fields are converted to ISO-8601 date strings."""
    from datetime import datetime, timezone

    mock_meta = _make_metadata_mock(
        name="Dated Dataset",
        date_published=datetime(2024, 1, 15, tzinfo=timezone.utc),
        date_created=datetime(2023, 6, 1, tzinfo=timezone.utc),
        date_modified=datetime(2024, 2, 20, tzinfo=timezone.utc),
    )

    result = _map_metadata(mock_meta, "test-source")
    assert result.date_published == "2024-01-15"
    assert result.date_created == "2023-06-01"
    assert result.date_modified == "2024-02-20"


def test_map_metadata_license_creative_work():
    """License as CreativeWork object is resolved to its URL."""
    cw = MagicMock()
    cw.url = "https://creativecommons.org/licenses/by/4.0/"

    mock_meta = _make_metadata_mock(
        name="Licensed Dataset",
        license=[cw],
    )

    result = _map_metadata(mock_meta, "test-source")
    assert "https://creativecommons.org/licenses/by/4.0/" in result.license


# ---------------------------------------------------------------------------
# enrich_dataset_package
# ---------------------------------------------------------------------------


def test_enrich_dataset_package_basic():
    """enrich_dataset_package populates empty SPDX fields from Croissant metadata."""
    from spdx_python_model import v3_0_1 as spdx3

    from loom.core.models import generate_spdx_id

    creation_info = spdx3.CreationInfo(specVersion="3.0.1")
    pkg = spdx3.dataset_DatasetPackage(
        spdxId=generate_spdx_id("DatasetPackage", "my-dataset"),
        name="my-dataset",
        creationInfo=creation_info,
    )

    meta = CroissantDatasetMetadata(
        name="My Dataset",
        description="A great dataset",
        url="https://example.com/dataset",
        version="2.0",
        data_biases=["sampling bias"],
        data_use_cases=["text classification"],
        provenance={"name": "Source: test | Format: Croissant | Field: name"},
    )

    enrich_dataset_package(pkg, meta)

    assert pkg.description == "A great dataset"
    assert pkg.software_downloadLocation == "https://example.com/dataset"
    assert pkg.software_homePage == "https://example.com/dataset"
    assert pkg.software_packageVersion == "2.0"
    assert "sampling bias" in pkg.dataset_knownBias
    assert "text classification" in pkg.dataset_intendedUse
    assert pkg.comment is not None
    assert "Croissant metadata provenance" in pkg.comment


def test_enrich_dataset_package_does_not_overwrite():
    """enrich_dataset_package does not overwrite existing SPDX fields."""
    from spdx_python_model import v3_0_1 as spdx3

    from loom.core.models import generate_spdx_id

    creation_info = spdx3.CreationInfo(specVersion="3.0.1")
    pkg = spdx3.dataset_DatasetPackage(
        spdxId=generate_spdx_id("DatasetPackage", "existing-dataset"),
        name="existing-dataset",
        creationInfo=creation_info,
    )
    pkg.description = "Existing description"
    pkg.software_downloadLocation = "https://existing.example.com"
    pkg.software_packageVersion = "3.0"

    meta = CroissantDatasetMetadata(
        name="Other Name",
        description="Croissant description",
        url="https://croissant.example.com",
        version="9.9",
        provenance={},
    )

    enrich_dataset_package(pkg, meta)

    # Original values should be preserved
    assert pkg.description == "Existing description"
    assert pkg.software_downloadLocation == "https://existing.example.com"
    assert pkg.software_packageVersion == "3.0"


def test_enrich_dataset_package_appends_comment():
    """enrich_dataset_package appends to an existing comment."""
    from spdx_python_model import v3_0_1 as spdx3

    from loom.core.models import generate_spdx_id

    creation_info = spdx3.CreationInfo(specVersion="3.0.1")
    pkg = spdx3.dataset_DatasetPackage(
        spdxId=generate_spdx_id("DatasetPackage", "comment-test"),
        name="comment-test",
        creationInfo=creation_info,
        comment="Original comment",
    )

    meta = CroissantDatasetMetadata(
        name="Dataset",
        provenance={"name": "Source: test | Format: Croissant | Field: name"},
    )

    enrich_dataset_package(pkg, meta)

    assert "Original comment" in pkg.comment
    assert "Croissant metadata provenance" in pkg.comment


# ---------------------------------------------------------------------------
# _apply_metadata_sources in bom module (integration)
# ---------------------------------------------------------------------------


def test_bom_add_dataset_with_croissant_metadata_source(tmp_path: Path):
    """metadata_sources={"croissant": ...} enriches the SPDX dataset package."""
    import loom.bom as bom

    croissant_file = tmp_path / "dataset.json"
    croissant_file.write_text(json.dumps(_MINIMAL_CROISSANT), encoding="utf-8")

    output_file = tmp_path / "fragment.spdx.json"
    with bom.track(output_file=str(output_file)):
        bom.set_model("my-model")
        bom.add_dataset(
            "Test Dataset",
            dataset_type="text",
            metadata_sources={"croissant": str(croissant_file)},
        )

    assert output_file.exists()
    data = json.loads(output_file.read_text())
    graph = data.get("@graph", [])
    dataset_nodes = [n for n in graph if n.get("type") == "dataset_DatasetPackage"]
    assert len(dataset_nodes) > 0
    # Description enriched from the Croissant document must appear in the output
    assert "A test dataset for AI training" in output_file.read_text()


def test_bom_add_dataset_no_metadata_sources(tmp_path: Path):
    """add_dataset without metadata_sources works as before (no enrichment)."""
    import loom.bom as bom

    output_file = tmp_path / "fragment.spdx.json"
    with bom.track(output_file=str(output_file)):
        bom.set_model("my-model")
        bom.add_dataset("Plain Dataset", dataset_type="text")

    assert output_file.exists()
    assert "@graph" in json.loads(output_file.read_text())


def test_bom_add_dataset_unknown_source_type_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """An unknown source type in metadata_sources logs a warning and is skipped."""
    import logging

    import loom.bom as bom

    output_file = tmp_path / "fragment.spdx.json"
    with caplog.at_level(logging.WARNING, logger="loom.bom"):
        with bom.track(output_file=str(output_file)):
            bom.set_model("my-model")
            bom.add_dataset(
                "Test Dataset",
                metadata_sources={"unknown_format": "/some/path.json"},
            )

    assert output_file.exists()
    assert any("unknown_format" in r.message for r in caplog.records)


def test_bom_add_dataset_bad_croissant_path_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """A bad Croissant path in metadata_sources logs a warning; run still succeeds."""
    import logging

    import loom.bom as bom

    output_file = tmp_path / "fragment.spdx.json"
    with caplog.at_level(logging.WARNING, logger="loom.bom"):
        with bom.track(output_file=str(output_file)):
            bom.set_model("my-model")
            bom.add_dataset(
                "Bad Dataset",
                metadata_sources={"croissant": "/nonexistent/croissant.json"},
            )

    assert output_file.exists()


def test_bom_add_dataset_multiple_metadata_sources(tmp_path: Path):
    """Multiple entries in metadata_sources are each processed independently."""

    import loom.bom as bom

    croissant_file = tmp_path / "dataset.json"
    croissant_file.write_text(json.dumps(_MINIMAL_CROISSANT), encoding="utf-8")

    output_file = tmp_path / "fragment.spdx.json"
    with bom.track(output_file=str(output_file)):
        bom.set_model("my-model")
        # Provide two sources: one valid Croissant, one unknown type
        bom.add_dataset(
            "Multi-source Dataset",
            metadata_sources={
                "croissant": str(croissant_file),
                "future_format": "/some/future.json",
            },
        )

    assert output_file.exists()
    # Croissant enrichment must have been applied
    assert "A test dataset for AI training" in output_file.read_text()
