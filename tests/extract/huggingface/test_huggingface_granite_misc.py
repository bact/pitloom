# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the IBM Granite model family (text generation, embedding, and
geospatial models), plus generic dataset-extraction priority tests that
aren't tied to any specific model.

See also: test_huggingface_vision_robotics.py, test_huggingface_speech_misc.py,
and test_huggingface_text_misc.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .conftest import (
    _make_card_data,
    _patch_granite_4_1_8b,
    _patch_granite_embed,
    _patch_granite_geo_flood,
    _patch_hf_calls,
)


def test_granite_4_1_8b_gqa_and_12_languages() -> None:
    with _patch_granite_4_1_8b():
        meta = read_huggingface("ibm-granite/granite-4.1-8b")
    assert meta.hyperparameters.get("num_key_value_heads") == 8
    langs = meta.extra_lists.get("hf.language", [])
    assert len(langs) == 12 and "ja" in langs and "ar" in langs


def test_granite_4_1_8b_base_model_finetune() -> None:
    with _patch_granite_4_1_8b():
        meta = read_huggingface("ibm-granite/granite-4.1-8b")
    assert meta.extra_data.get("hf.base_model") == "ibm-granite/granite-4.1-8b-base"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_granite_embed_modernbert_arch_and_library() -> None:
    with _patch_granite_embed():
        meta = read_huggingface("ibm-granite/granite-embedding-97m-multilingual-r2")
    assert meta.type_of_model == "modernbert"
    assert meta.extra_data.get("hf.library_name") == "sentence-transformers"


def test_granite_embed_feature_extraction_domain() -> None:
    with _patch_granite_embed():
        meta = read_huggingface("ibm-granite/granite-embedding-97m-multilingual-r2")
    assert "feature-extraction" in meta.usage.domains


def test_granite_geo_flood_image_segmentation_domain() -> None:
    with _patch_granite_geo_flood():
        meta = read_huggingface("ibm-granite/granite-geospatial-uki-flooddetection")
    assert "image-segmentation" in meta.usage.domains


def test_granite_geo_flood_dataset_refs_from_hf_dataset_repos() -> None:
    # Both flood dataset HF IDs captured as DatasetReference objects.
    with _patch_granite_geo_flood():
        meta = read_huggingface("ibm-granite/granite-geospatial-uki-flooddetection")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "ai-for-good-lab/ai4g-flood-dataset" in ds_names
    assert "blanchon/ETCI-2021-Flood-Detection" in ds_names


def test_granite_geo_flood_terratorch_library_and_base_model() -> None:
    with _patch_granite_geo_flood():
        meta = read_huggingface("ibm-granite/granite-geospatial-uki-flooddetection")
    assert meta.extra_data.get("hf.library_name") == "terratorch"
    assert meta.extra_data.get("hf.base_model") == "ibm-granite/granite-geospatial-uki"


def test_dataset_card_yaml_takes_priority_over_info_tags() -> None:
    # When card_data has datasets, model_info tags are ignored for datasets.
    card = _make_card_data(
        license="cc-by-sa-4.0",
        pipeline_tag="text-generation",
        datasets=["from-card-dataset"],
    )
    with _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=card,
        hub_info={"tags": ["dataset:from-info-tag"]},
    ):
        meta = read_huggingface("pythainlp/wangchanglm-7.5B-sft-enth")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "from-card-dataset" in ds_names
    assert "from-info-tag" not in ds_names


def test_dataset_info_tag_fallback_when_no_card_datasets() -> None:
    # When card has no datasets, model_info tags with dataset: prefix are used.
    card = _make_card_data(license="mit", pipeline_tag="text-generation")
    with _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=card,
        hub_info={"tags": ["dataset:fallback-dataset"]},
    ):
        meta = read_huggingface("pythainlp/wangchanglm-7.5B-sft-enth")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "fallback-dataset" in ds_names
