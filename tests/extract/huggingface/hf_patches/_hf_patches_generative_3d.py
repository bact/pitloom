# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for generative 3D, image, and robotics models: text-to-3D, image-
to-3D, text-to-image, and robotic control.

See also: _hf_patches_base.py, _hf_patches_text_generation_pretrained.py,
_hf_patches_text_generation_instruct.py,
_hf_patches_text_generation_regional.py, _hf_patches_gated_metadata.py,
_hf_patches_gated_access.py, _hf_patches_speech_audio.py,
_hf_patches_multimodal.py, _hf_patches_omni_modal.py,
_hf_patches_embeddings.py, _hf_patches_vision.py,
_hf_patches_structured_text.py. Sibling test modules import these names
directly from the matching topic module.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)


def _patch_groot() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "Gr00tN1d7",
            "architectures": ["Gr00tN1d7"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag="robotics",
            tags=["robotics"],
        ),
        hub_info={"author": "nvidia"},
    )


def _patch_openvla() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "openvla",
            "architectures": ["OpenVLAForActionPrediction"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="robotics",
            tags=["vla", "image-text-to-text", "multimodal", "pretraining"],
            language=["en"],
        ),
        hub_info={"author": "openvla"},
    )


def _patch_pi05() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="gemma",
            pipeline_tag="robotics",
            tags=["vision-language-action", "imitation-learning", "lerobot"],
            language=["en"],
            library_name="lerobot",
        ),
        hub_info={"author": "lerobot"},
    )


def _patch_ernie_image_turbo() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-to-image",
            tags=["diffusion", "distilled"],
            language=["en", "zh"],
            library_name="diffusers",
        ),
        hub_info={"author": "baidu"},
    )


_STABLE_ZERO123_CARD_DATA = _make_card_data(
    license="other",
    license_name="sai-nc-community",
    pipeline_tag="text-to-3d",
    language=None,
    library_name="diffusers",
)


def _patch_stable_zero123() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_STABLE_ZERO123_CARD_DATA,
        hub_info={"author": "stabilityai", "sha": "deadf00d"},
    )


_SHAP_E_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="text-to-3d",
    language=None,
    library_name=None,
)


def _patch_shap_e() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_SHAP_E_CARD_DATA,
        hub_info={"author": "openai", "sha": "deadf00d"},
    )


_BLENDERLLM_CONFIG: dict[str, Any] = {
    "model_type": "qwen2",
    "architectures": ["Qwen2ForCausalLM"],
    "vocab_size": 152064,
    "hidden_size": 3584,
    "num_hidden_layers": 28,
    "num_attention_heads": 28,
    "num_key_value_heads": 4,
    "max_position_embeddings": 32768,
    "torch_dtype": "bfloat16",
}


_BLENDERLLM_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-to-3d",
    language=["en"],
    library_name="transformers",
)


def _patch_blenderllm() -> Any:
    return _patch_hf_calls(
        config=_BLENDERLLM_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_BLENDERLLM_CARD_DATA,
        hub_info={"author": "FreedomIntelligence", "sha": "deadf00d"},
    )


_BLENDERLLM_GGUF_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-to-3d",
    language=None,
    library_name="gguf",
    base_model="FreedomIntelligence/BlenderLLM",
)


def _patch_blenderllm_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_BLENDERLLM_GGUF_CARD_DATA,
        hub_info={
            "author": "hellork",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:FreedomIntelligence/BlenderLLM"],
        },
    )


_HY_MOTION_CARD_DATA = _make_card_data(
    license="other",
    license_name="tencent-hunyuan-community",
    pipeline_tag="text-to-3d",
    language=["zh", "en"],
    library_name="HY-Motion-1.0",
)


_HY_MOTION_CONFIG: dict[str, Any] = {
    "Name": "HunyuanMotion",  # non-standard metadata field
    "motion_module_type": "vanilla",
    "num_transformer_blocks": 20,
}


def _patch_hy_motion() -> Any:
    return _patch_hf_calls(
        config=_HY_MOTION_CONFIG,
        tokenizer_config=None,
        card_data=_HY_MOTION_CARD_DATA,
        hub_info={"author": "tencent", "sha": "deadf00d"},
    )


_APPLE_SHARP_CARD_DATA = _make_card_data(
    license="apple-amlr",
    pipeline_tag="image-to-3d",
    language=None,
    library_name="ml-sharp",
)


def _patch_apple_sharp() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_APPLE_SHARP_CARD_DATA,
        hub_info={"author": "apple", "sha": "deadf00d"},
    )


__all__ = [
    "_APPLE_SHARP_CARD_DATA",
    "_BLENDERLLM_CARD_DATA",
    "_BLENDERLLM_CONFIG",
    "_BLENDERLLM_GGUF_CARD_DATA",
    "_HY_MOTION_CARD_DATA",
    "_HY_MOTION_CONFIG",
    "_SHAP_E_CARD_DATA",
    "_STABLE_ZERO123_CARD_DATA",
    "_patch_apple_sharp",
    "_patch_blenderllm",
    "_patch_blenderllm_gguf",
    "_patch_ernie_image_turbo",
    "_patch_groot",
    "_patch_hy_motion",
    "_patch_openvla",
    "_patch_pi05",
    "_patch_shap_e",
    "_patch_stable_zero123",
]
