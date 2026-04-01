# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for DatasetMetadata and DatasetReference dataclasses."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference

# ---------------------------------------------------------------------------
# DatasetMetadata
# ---------------------------------------------------------------------------


def test_dataset_metadata_required_field() -> None:
    meta = DatasetMetadata(name="My Dataset")
    assert meta.name == "My Dataset"


def test_dataset_metadata_defaults() -> None:
    meta = DatasetMetadata(name="x")
    assert meta.version is None
    assert meta.description is None
    assert meta.download_url is None
    assert meta.license is None
    assert not meta.keywords
    assert meta.creator is None
    assert not meta.dataset_types
    assert meta.dataset_size is None
    assert meta.data_collection_process is None
    assert not meta.data_preprocessing
    assert not meta.known_bias
    assert meta.intended_use is None
    assert meta.has_sensitive_personal_information is None
    assert not meta.anonymization_methods
    assert meta.croissant_url is None
    assert not meta.provenance


def test_dataset_metadata_full_construction() -> None:
    meta = DatasetMetadata(
        name="Full Dataset",
        version="1.0",
        description="A complete dataset.",
        download_url="https://example.com/data",
        license="Apache-2.0",
        keywords=["NLP", "text"],
        creator="Test Author",
        dataset_types=["text", "numeric"],
        dataset_size=10000,
        data_collection_process="Web scraping.",
        data_preprocessing=["tokenization"],
        known_bias=["selection bias"],
        intended_use="Sentiment analysis.",
        has_sensitive_personal_information="no",
        anonymization_methods=["k-anonymity"],
        croissant_url="https://example.com/croissant.json",
        provenance={"name": "Source: test"},
    )
    assert meta.name == "Full Dataset"
    assert meta.version == "1.0"
    assert meta.dataset_types == ["text", "numeric"]
    assert meta.dataset_size == 10000
    assert meta.has_sensitive_personal_information == "no"
    assert meta.croissant_url == "https://example.com/croissant.json"


def test_dataset_metadata_mutable_lists_are_independent() -> None:
    meta1 = DatasetMetadata(name="a")
    meta2 = DatasetMetadata(name="b")
    meta1.keywords.append("x")
    assert not meta2.keywords


# ---------------------------------------------------------------------------
# DatasetReference
# ---------------------------------------------------------------------------


def test_dataset_reference_construction() -> None:
    meta = DatasetMetadata(name="Train Set")
    ref = DatasetReference(role="trainedOn", metadata=meta)
    assert ref.role == "trainedOn"
    assert ref.metadata.name == "Train Set"


def test_dataset_reference_roles() -> None:
    roles = ["trainedOn", "testedOn", "finetunedOn", "validatedOn", "pretrainedOn"]
    for role in roles:
        ref = DatasetReference(role=role, metadata=DatasetMetadata(name="d"))
        assert ref.role == role


# ---------------------------------------------------------------------------
# Integration with AiModelMetadata
# ---------------------------------------------------------------------------


def test_ai_model_metadata_datasets_field() -> None:
    model = AiModelMetadata(name="MyModel")
    assert not model.datasets

    ref = DatasetReference(role="trainedOn", metadata=DatasetMetadata(name="Wiki"))
    model.datasets.append(ref)
    assert len(model.datasets) == 1
    assert model.datasets[0].role == "trainedOn"
    assert model.datasets[0].metadata.name == "Wiki"
