# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for image-classification, detection, and other vision models.

See also: test_huggingface_embeddings.py, test_huggingface_gated_access.py,
test_huggingface_gated_metadata.py, test_huggingface_granite_misc.py,
test_huggingface_multimodal.py, test_huggingface_omni_modal.py,
test_huggingface_speech_misc.py, test_huggingface_structured_text.py,
test_huggingface_text_generation_instruct.py,
test_huggingface_text_generation_pretrained.py, test_huggingface_text_misc.py,
test_huggingface_vision_robotics.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .hf_patches._hf_patches_vision import (
    _patch_depth_pro,
    _patch_exaone_path,
    _patch_fibo_edit,
    _patch_flood_image_detect,
    _patch_hrnetpose,
    _patch_laion_clip,
    _patch_lightglue,
    _patch_marigold,
    _patch_rmbg14,
    _patch_rmbg20,
    _patch_rtdetr_coco,
    _patch_rtdetr_coco_o365,
    _patch_streetclip,
    _patch_vitpose,
    _patch_windowseat,
)


def test_depth_pro_depth_estimation_domain() -> None:
    with _patch_depth_pro():
        meta = read_huggingface("apple/DepthPro-hf")
    assert "depth-estimation" in meta.usage.domains


def test_depth_pro_architecture() -> None:
    with _patch_depth_pro():
        meta = read_huggingface("apple/DepthPro-hf")
    assert meta.type_of_model == "depth_pro"
    assert meta.architecture == "DepthProForDepthEstimation"


def test_marigold_depth_estimation_domain() -> None:
    with _patch_marigold():
        meta = read_huggingface("prs-eth/marigold-depth-v1-0")
    assert "depth-estimation" in meta.usage.domains


def test_marigold_diffusers_library() -> None:
    with _patch_marigold():
        meta = read_huggingface("prs-eth/marigold-depth-v1-0")
    assert meta.extra_data.get("hf.library_name") == "diffusers"


def test_vitpose_keypoint_detection_domain() -> None:
    with _patch_vitpose():
        meta = read_huggingface("usyd-community/vitpose-plus-huge")
    assert "keypoint-detection" in meta.usage.domains


def test_vitpose_architecture() -> None:
    with _patch_vitpose():
        meta = read_huggingface("usyd-community/vitpose-plus-huge")
    assert meta.type_of_model == "vitpose"


def test_rmbg14_image_segmentation_domain() -> None:
    with _patch_rmbg14():
        meta = read_huggingface("briaai/RMBG-1.4")
    assert "image-segmentation" in meta.usage.domains


def test_rmbg14_custom_tags_in_extra_lists() -> None:
    with _patch_rmbg14():
        meta = read_huggingface("briaai/RMBG-1.4")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "remove background" in tags
    assert "legal liability" in tags


def test_rmbg20_gated_still_has_domain_from_card() -> None:
    # Pipeline tag is in card YAML, so domain is captured even without config.
    with _patch_rmbg20():
        meta = read_huggingface("briaai/RMBG-2.0")
    assert "image-segmentation" in meta.usage.domains
    assert meta.type_of_model is None


def test_fibo_edit_image_to_image_domain() -> None:
    with _patch_fibo_edit():
        meta = read_huggingface("briaai/Fibo-Edit-RMBG")
    assert "image-to-image" in meta.usage.domains


def test_fibo_edit_arxiv_extracted() -> None:
    with _patch_fibo_edit():
        meta = read_huggingface("briaai/Fibo-Edit-RMBG")
    assert "2511.06876" in meta.extra_lists.get("hf.arxiv", [])


def test_fibo_edit_base_model_relation() -> None:
    with _patch_fibo_edit():
        meta = read_huggingface("briaai/Fibo-Edit-RMBG")
    assert meta.extra_data.get("hf.base_model") == "briaai/Fibo-Edit"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_laion_clip_zero_shot_image_classification_domain() -> None:
    with _patch_laion_clip():
        meta = read_huggingface("laion/CLIP-convnext_base_w-laion2B-s13B-b82K-augreg")
    assert "zero-shot-image-classification" in meta.usage.domains


def test_laion_clip_no_config_no_architecture() -> None:
    with _patch_laion_clip():
        meta = read_huggingface("laion/CLIP-convnext_base_w-laion2B-s13B-b82K-augreg")
    assert meta.type_of_model is None


def test_streetclip_zero_shot_classification_domain() -> None:
    with _patch_streetclip():
        meta = read_huggingface("geolocal/StreetCLIP")
    assert "zero-shot-image-classification" in meta.usage.domains


def test_streetclip_clip_architecture() -> None:
    with _patch_streetclip():
        meta = read_huggingface("geolocal/StreetCLIP")
    assert meta.type_of_model == "clip"


def test_streetclip_geo_tags_in_extra_lists() -> None:
    with _patch_streetclip():
        meta = read_huggingface("geolocal/StreetCLIP")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "geolocalization" in tags


def test_flood_image_detect_domain_and_base_model() -> None:
    with _patch_flood_image_detect():
        meta = read_huggingface("prithivMLmods/Flood-Image-Detection")
    assert "image-classification" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "google/siglip2-base-patch16-512"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_exaone_path_no_architecture() -> None:
    # Config gated -> no type_of_model or architecture
    with _patch_exaone_path():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-Path-2.0-rev-EGFR")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_exaone_path_pipeline_tag_captured_as_domain() -> None:
    # pipeline_tag is always added to usage.domains regardless of _DOMAIN_TAGS.
    # _DOMAIN_TAGS only governs which card *tags* qualify as domains.
    with _patch_exaone_path():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-Path-2.0-rev-EGFR")
    assert "pathology-image-analysis" in meta.usage.domains


def test_exaone_path_only_pipeline_tag_domain() -> None:
    # Only the pipeline_tag domain is present; no other domain tags in card.
    with _patch_exaone_path():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-Path-2.0-rev-EGFR")
    assert meta.usage.domains == ["pathology-image-analysis"]


def test_windowseat_no_architecture() -> None:
    # No config.json -> type_of_model and architecture are None
    with _patch_windowseat():
        meta = read_huggingface("windowseat-ai/windowseat-reflection")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_windowseat_peft_library_name() -> None:
    # PEFT adapter: library_name="peft" -> extra_data["hf.library_name"]
    with _patch_windowseat():
        meta = read_huggingface("windowseat-ai/windowseat-reflection")
    assert (meta.extra_data or {}).get("hf.library_name") == "peft"


def test_windowseat_image_to_image_domain() -> None:
    with _patch_windowseat():
        meta = read_huggingface("windowseat-ai/windowseat-reflection")
    assert "image-to-image" in meta.usage.domains


def test_lightglue_type_of_model() -> None:
    with _patch_lightglue():
        meta = read_huggingface("ETH-CVG/lightglue_superpoint")
    assert meta.type_of_model == "lightglue"


def test_lightglue_architecture() -> None:
    with _patch_lightglue():
        meta = read_huggingface("ETH-CVG/lightglue_superpoint")
    assert meta.architecture == "LightGlueForKeypointMatching"


def test_lightglue_empty_hyperparameters() -> None:
    # descriptor_dim, filter_threshold, depth_confidence not in _HYPER_KEYS
    with _patch_lightglue():
        meta = read_huggingface("ETH-CVG/lightglue_superpoint")
    assert not meta.hyperparameters


def test_hrnetpose_keypoint_detection_domain() -> None:
    with _patch_hrnetpose():
        meta = read_huggingface("qualcomm/HRNetPose")
    assert "keypoint-detection" in meta.usage.domains


def test_hrnetpose_pytorch_library() -> None:
    # Qualcomm uses library_name=pytorch for native PyTorch format
    with _patch_hrnetpose():
        meta = read_huggingface("qualcomm/HRNetPose")
    assert (meta.extra_data or {}).get("hf.library_name") == "pytorch"


def test_hrnetpose_no_architecture() -> None:
    with _patch_hrnetpose():
        meta = read_huggingface("qualcomm/HRNetPose")
    assert meta.type_of_model is None


def test_rtdetr_coco_o365_type_of_model() -> None:
    with _patch_rtdetr_coco_o365():
        meta = read_huggingface("PekingU/rtdetr_r50vd_coco_o365")
    assert meta.type_of_model == "rt_detr"


def test_rtdetr_coco_o365_architecture() -> None:
    with _patch_rtdetr_coco_o365():
        meta = read_huggingface("PekingU/rtdetr_r50vd_coco_o365")
    assert meta.architecture == "RTDetrForObjectDetection"


def test_rtdetr_coco_o365_object_detection_domain() -> None:
    # object-detection is in _DOMAIN_TAGS -- captured as domain
    with _patch_rtdetr_coco_o365():
        meta = read_huggingface("PekingU/rtdetr_r50vd_coco_o365")
    assert "object-detection" in meta.usage.domains


def test_rtdetr_coco_o365_only_torch_dtype_in_hyperparameters() -> None:
    # Detection config has no LM keys; only torch_dtype matches _HYPER_KEYS
    with _patch_rtdetr_coco_o365():
        meta = read_huggingface("PekingU/rtdetr_r50vd_coco_o365")
    assert meta.hyperparameters.get("torch_dtype") == "float32"
    assert "hidden_size" not in meta.hyperparameters
    assert "vocab_size" not in meta.hyperparameters


def test_rtdetr_coco_o365_arxiv() -> None:
    with _patch_rtdetr_coco_o365():
        meta = read_huggingface("PekingU/rtdetr_r50vd_coco_o365")
    arxivs = (meta.extra_lists or {}).get("hf.arxiv", [])
    assert "2304.08069" in arxivs


def test_rtdetr_coco_o365_coco_dataset() -> None:
    with _patch_rtdetr_coco_o365():
        meta = read_huggingface("PekingU/rtdetr_r50vd_coco_o365")
    assert meta.datasets
    names = [d.metadata.name for d in meta.datasets if d.metadata and d.metadata.name]
    assert "coco" in names


def test_rtdetr_coco_type_of_model() -> None:
    with _patch_rtdetr_coco():
        meta = read_huggingface("PekingU/rtdetr_r50vd")
    assert meta.type_of_model == "rt_detr"


def test_rtdetr_coco_object_detection_domain() -> None:
    with _patch_rtdetr_coco():
        meta = read_huggingface("PekingU/rtdetr_r50vd")
    assert "object-detection" in meta.usage.domains


def test_rtdetr_coco_no_lm_hyperparameters() -> None:
    # Detection model: d_model, decoder_layers, etc. are NOT in _HYPER_KEYS
    with _patch_rtdetr_coco():
        meta = read_huggingface("PekingU/rtdetr_r50vd")
    assert "hidden_size" not in meta.hyperparameters
    assert "vocab_size" not in meta.hyperparameters
