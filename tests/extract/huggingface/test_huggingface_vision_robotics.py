# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for vision, robotics, and vision-language models: image feature
extraction, pathology tags, robotic control, and visual question
answering.

See also: test_huggingface_speech_misc.py, test_huggingface_text_misc.py,
and test_huggingface_granite_misc.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .conftest import (
    _patch_blip_vqa,
    _patch_deplot,
    _patch_groot,
    _patch_openvla,
    _patch_pi05,
    _patch_rad_dino,
    _patch_sealion_vl,
    _patch_timm_convnext,
    _patch_uni2,
    _patch_vilt_vqa,
)


def test_rad_dino_image_feature_extraction() -> None:
    with _patch_rad_dino():
        meta = read_huggingface("microsoft/rad-dino")
    assert "image-feature-extraction" in meta.usage.domains


def test_uni2_pathology_tags_in_extra_lists() -> None:
    with _patch_uni2():
        meta = read_huggingface("MahmoodLab/UNI2-h")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "histology" in tags
    assert "pathology" in tags


def test_timm_convnext_library_name() -> None:
    with _patch_timm_convnext():
        meta = read_huggingface("timm/convnext_large.dinov3_lvd1689m")
    assert meta.extra_data.get("hf.library_name") == "timm"


def test_groot_robotics_domain() -> None:
    with _patch_groot():
        meta = read_huggingface("nvidia/GR00T-N1.7-3B")
    assert "robotics" in meta.usage.domains


def test_openvla_robotics_and_multimodal_tags() -> None:
    with _patch_openvla():
        meta = read_huggingface("openvla/openvla-7b")
    assert "robotics" in meta.usage.domains
    assert "image-text-to-text" in meta.usage.domains


def test_openvla_architecture() -> None:
    with _patch_openvla():
        meta = read_huggingface("openvla/openvla-7b")
    assert meta.type_of_model == "openvla"


def test_pi05_lerobot_library() -> None:
    with _patch_pi05():
        meta = read_huggingface("lerobot/pi05_base")
    assert meta.extra_data.get("hf.library_name") == "lerobot"


def test_sealion_vl_gemma3_architecture_and_base_model() -> None:
    with _patch_sealion_vl():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-4B-VL")
    assert meta.type_of_model == "gemma3"
    assert meta.extra_data.get("hf.base_model") == "google/gemma-3-4b-it"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_sealion_vl_image_text_to_text_domain() -> None:
    with _patch_sealion_vl():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-4B-VL")
    assert "image-text-to-text" in meta.usage.domains


def test_vilt_vqa_domain() -> None:
    with _patch_vilt_vqa():
        meta = read_huggingface("dandelin/vilt-b32-finetuned-vqa")
    assert "visual-question-answering" in meta.usage.domains


def test_vilt_vqa_base_model_finetune() -> None:
    with _patch_vilt_vqa():
        meta = read_huggingface("dandelin/vilt-b32-finetuned-vqa")
    assert meta.extra_data.get("hf.base_model") == "dandelin/vilt-b32"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_vilt_vqa_arxiv() -> None:
    with _patch_vilt_vqa():
        meta = read_huggingface("dandelin/vilt-b32-finetuned-vqa")
    assert "2102.03334" in meta.extra_lists.get("hf.arxiv", [])


def test_deplot_vqa_domain() -> None:
    with _patch_deplot():
        meta = read_huggingface("google/deplot")
    assert "visual-question-answering" in meta.usage.domains


def test_deplot_image_text_tag_also_domain() -> None:
    # "image-text-to-text" in tags also captured as domain.
    with _patch_deplot():
        meta = read_huggingface("google/deplot")
    assert "image-text-to-text" in meta.usage.domains


def test_deplot_arxiv() -> None:
    with _patch_deplot():
        meta = read_huggingface("google/deplot")
    assert "2212.10505" in meta.extra_lists.get("hf.arxiv", [])


def test_blip_vqa_domain() -> None:
    with _patch_blip_vqa():
        meta = read_huggingface("Salesforce/blip-vqa-base")
    assert "visual-question-answering" in meta.usage.domains
