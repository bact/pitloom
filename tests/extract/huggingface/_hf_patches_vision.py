# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for vision-perception models: keypoint detection, segmentation,
depth estimation, object detection, and image classification.

See also: _hf_patches_base.py, _hf_patches_text_generation_pretrained.py,
_hf_patches_text_generation_instruct.py,
_hf_patches_text_generation_regional.py, _hf_patches_gated_metadata.py,
_hf_patches_speech_audio.py, _hf_patches_multimodal.py,
_hf_patches_omni_modal.py, _hf_patches_embeddings.py,
_hf_patches_structured_text.py, _hf_patches_generative_3d.py. Sibling test
modules import helper names from ``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)


def _patch_depth_pro() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "depth_pro",
            "architectures": ["DepthProForDepthEstimation"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apple-amlr",
            pipeline_tag="depth-estimation",
            tags=["vision", "depth-estimation"],
        ),
        hub_info={"author": "apple"},
    )


def _patch_marigold() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="depth-estimation",
            tags=["depth estimation", "image analysis", "computer vision", "zero-shot"],
            language=["en"],
            library_name="diffusers",
        ),
        hub_info={"author": "prs-eth"},
    )


def _patch_vitpose() -> Any:
    return _patch_hf_calls(
        config={"model_type": "vitpose", "architectures": ["VitPoseForPoseEstimation"]},
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="keypoint-detection",
            tags=[],
        ),
        hub_info={"author": "usyd-community"},
    )


def _patch_rmbg14() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "SegformerForSemanticSegmentation",
            "architectures": ["BriaRMBG"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="image-segmentation",
            tags=[
                "remove background",
                "background-removal",
                "vision",
                "legal liability",
            ],
        ),
        hub_info={"author": "briaai"},
    )


def _patch_rmbg20() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated - config.json returns 401
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="image-segmentation",
            tags=["remove background", "background-removal", "vision"],
        ),
        hub_info={"author": "briaai"},
    )


def _patch_fibo_edit() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="image-to-image",
            tags=["art", "background-removal", "image-segmentation"],
            library_name="diffusers",
            base_model=["briaai/Fibo-Edit"],
        ),
        hub_info={
            "author": "briaai",
            "tags": [
                "arxiv:2511.06876",
                "base_model:briaai/Fibo-Edit",
                "base_model:finetune:briaai/Fibo-Edit",
            ],
        },
    )


def _patch_laion_clip() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="zero-shot-image-classification",
            tags=["clip"],
        ),
        hub_info={"author": "laion"},
    )


def _patch_streetclip() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "clip",
            "architectures": ["CLIPModel"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="cc-by-nc-4.0",
            pipeline_tag="zero-shot-image-classification",
            tags=[
                "geolocalization",
                "geolocation",
                "geographic",
                "clip",
                "multi-modal",
            ],
            language=["en"],
        ),
        hub_info={"author": "geolocal"},
    )


def _patch_granite_geo_flood() -> Any:
    return _patch_hf_calls(
        config=None,  # TerraTorch -- no standard transformers config.json
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="image-segmentation",
            tags=["geospatial", "flood-detection", "sentinel-2", "sentinel-1"],
            datasets=[
                "ai-for-good-lab/ai4g-flood-dataset",
                "blanchon/ETCI-2021-Flood-Detection",
            ],
            base_model=["ibm-granite/granite-geospatial-uki"],
            library_name="terratorch",
        ),
        hub_info={
            "author": "ibm-granite",
            "tags": [
                "base_model:ibm-granite/granite-geospatial-uki",
                "base_model:finetune:ibm-granite/granite-geospatial-uki",
            ],
        },
    )


def _patch_flood_image_detect() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "siglip",
            "architectures": ["SiglipForImageClassification"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="image-classification",
            tags=["siglip", "Flood-Detection", "climate"],
            language=["en"],
            base_model=["google/siglip2-base-patch16-512"],
        ),
        hub_info={
            "author": "prithivMLmods",
            "tags": [
                "arxiv:2502.14786",
                "base_model:google/siglip2-base-patch16-512",
                "base_model:finetune:google/siglip2-base-patch16-512",
            ],
        },
    )


_EXAONE_PATH_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="pathology-image-analysis",
    language=["en"],
    library_name="transformers",
)


def _patch_exaone_path() -> Any:
    return _patch_hf_calls(
        config=None,  # gated -> 401
        tokenizer_config=None,
        card_data=_EXAONE_PATH_CARD_DATA,
        hub_info={"author": "LGAI-EXAONE", "sha": "deadf00d"},
    )


_WINDOWSEAT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="image-to-image",
    language=None,
    library_name="peft",
)


def _patch_windowseat() -> Any:
    return _patch_hf_calls(
        config=None,  # absent -> 404
        tokenizer_config=None,
        card_data=_WINDOWSEAT_CARD_DATA,
        hub_info={"author": "windowseat-ai", "sha": "deadf00d"},
    )


_LIGHTGLUE_CONFIG: dict[str, Any] = {
    "model_type": "lightglue",
    "architectures": ["LightGlueForKeypointMatching"],
    "descriptor_dim": 256,  # non-standard
    "filter_threshold": 0.1,  # non-standard
    "depth_confidence": 0.95,  # non-standard
    "keypoint_detector_config": {"name": "superpoint", "descriptor_dim": 256},
}


_LIGHTGLUE_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="keypoint-detection",
    language=None,
    library_name="transformers",
)


def _patch_lightglue() -> Any:
    return _patch_hf_calls(
        config=_LIGHTGLUE_CONFIG,
        tokenizer_config=None,
        card_data=_LIGHTGLUE_CARD_DATA,
        hub_info={"author": "ETH-CVG", "sha": "deadf00d"},
    )


_HRNETPOSE_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="keypoint-detection",
    language=None,
    library_name="pytorch",
)


def _patch_hrnetpose() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_HRNETPOSE_CARD_DATA,
        hub_info={"author": "qualcomm", "sha": "deadf00d"},
    )


_RTDETR_COCO_O365_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="object-detection",
    language=["en"],
    library_name="transformers",
    datasets=["coco"],
)


_RTDETR_COCO_O365_CONFIG: dict[str, Any] = {
    "model_type": "rt_detr",
    "architectures": ["RTDetrForObjectDetection"],
    "torch_dtype": "float32",
    # Detection-specific keys -- none in _HYPER_KEYS
    "d_model": 256,
    "decoder_attention_heads": 8,
    "encoder_attention_heads": 8,
    "decoder_layers": 6,
    "encoder_layers": 1,
    "num_queries": 300,
    "is_encoder_decoder": True,
}


def _patch_rtdetr_coco_o365() -> Any:
    return _patch_hf_calls(
        config=_RTDETR_COCO_O365_CONFIG,
        tokenizer_config=None,
        card_data=_RTDETR_COCO_O365_CARD_DATA,
        hub_info={
            "author": "PekingU",
            "sha": "deadf00d",
            "tags": ["arxiv:2304.08069", "dataset:coco"],
        },
    )


_RTDETR_COCO_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="object-detection",
    language=["en"],
    library_name="transformers",
    datasets=["coco"],
)


def _patch_rtdetr_coco() -> Any:
    return _patch_hf_calls(
        config=_RTDETR_COCO_O365_CONFIG,  # same config schema
        tokenizer_config=None,
        card_data=_RTDETR_COCO_CARD_DATA,
        hub_info={
            "author": "PekingU",
            "sha": "deadf00d",
            "tags": ["arxiv:2304.08069", "dataset:coco"],
        },
    )


__all__ = [
    "_EXAONE_PATH_CARD_DATA",
    "_HRNETPOSE_CARD_DATA",
    "_LIGHTGLUE_CARD_DATA",
    "_LIGHTGLUE_CONFIG",
    "_RTDETR_COCO_CARD_DATA",
    "_RTDETR_COCO_O365_CARD_DATA",
    "_RTDETR_COCO_O365_CONFIG",
    "_WINDOWSEAT_CARD_DATA",
    "_patch_depth_pro",
    "_patch_exaone_path",
    "_patch_fibo_edit",
    "_patch_flood_image_detect",
    "_patch_granite_geo_flood",
    "_patch_hrnetpose",
    "_patch_laion_clip",
    "_patch_lightglue",
    "_patch_marigold",
    "_patch_rmbg14",
    "_patch_rmbg20",
    "_patch_rtdetr_coco",
    "_patch_rtdetr_coco_o365",
    "_patch_streetclip",
    "_patch_vitpose",
    "_patch_windowseat",
]
