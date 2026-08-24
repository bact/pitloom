# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for any-to-any / omni-modal models accepting and producing
multiple modalities.

See also: _hf_patches_base.py, _hf_patches_text_generation_pretrained.py,
_hf_patches_text_generation_instruct.py,
_hf_patches_text_generation_regional.py, _hf_patches_gated_metadata.py,
_hf_patches_gated_access.py, _hf_patches_speech_audio.py,
_hf_patches_multimodal.py, _hf_patches_embeddings.py, _hf_patches_vision.py,
_hf_patches_structured_text.py, _hf_patches_generative_3d.py. Sibling test
modules import these names directly from the matching topic module.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)


def _patch_nemotron() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "NemotronH_Nano_Omni_Reasoning_V3",
            "architectures": ["NemotronH_Nano_Omni_Reasoning_V3"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="any-to-any",
            tags=["nvidia", "pytorch", "multimodal"],
            library_name="transformers",
            datasets=["nvidia/Nemotron-Image-Training-v3"],
        ),
        hub_info={
            "author": "nvidia",
            "tags": ["dataset:nvidia/Nemotron-Image-Training-v3"],
        },
    )


_LLADA2_MOE_CONFIG: dict[str, Any] = {
    "model_type": "llada2_moe",
    "architectures": ["LLaDA2MoeModelLM"],
    "vocab_size": 151936,
    "hidden_size": 2048,
    "num_hidden_layers": 28,
    "num_attention_heads": 16,
    "torch_dtype": "bfloat16",
    "use_qkv_bias": True,  # non-standard
    "use_qk_norm": True,  # non-standard
}


_LLADA2_MOE_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["en", "zh"],
    library_name="transformers",
)


def _patch_llada2_moe() -> Any:
    return _patch_hf_calls(
        config=_LLADA2_MOE_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_LLADA2_MOE_CARD_DATA,
        hub_info={"author": "inclusionAI", "sha": "deadf00d"},
    )


_BAGEL_CONFIG: dict[str, Any] = {
    "model_type": "bagel",
    "architectures": ["BagelForConditionalGeneration"],
    "llm_config": {"hidden_size": 3584, "num_hidden_layers": 28},  # nested
    "vit_config": {"hidden_size": 1024, "num_hidden_layers": 24},  # nested
    "vae_config": {"in_channels": 8},  # nested
    "visual_gen": True,
    "visual_und": True,
}


_BAGEL_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["en"],
    library_name="bagel-mot",
)


def _patch_bagel() -> Any:
    return _patch_hf_calls(
        config=_BAGEL_CONFIG,
        tokenizer_config=None,
        card_data=_BAGEL_CARD_DATA,
        hub_info={"author": "ByteDance-Seed", "sha": "deadf00d"},
    )


_SENSENOVA_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["zh", "en"],
    library_name="transformers",
)


_SENSENOVA_CONFIG: dict[str, Any] = {
    "model_type": "neo_chat",
    "architectures": ["NEOChatModel"],
    "llm_config": {"hidden_size": 3584, "num_hidden_layers": 28},  # nested
    "downsample_ratio": 2,  # non-standard
    "template": "chat",  # non-standard
}


def _patch_sensenova() -> Any:
    return _patch_hf_calls(
        config=_SENSENOVA_CONFIG,
        tokenizer_config=None,
        card_data=_SENSENOVA_CARD_DATA,
        hub_info={"author": "sensenova", "sha": "deadf00d"},
    )


_MMADA_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="any-to-any",
    language=["en"],
    library_name="transformers",
)


_MMADA_CONFIG: dict[str, Any] = {
    "model_type": "llada",
    "architectures": ["LLaDAModelLM"],
    "vocab_size": 32000,
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "alibi": True,  # ALiBi positional bias (non-standard, not in _HYPER_KEYS)
    "alibi_bias_max": 8,  # non-standard
    "attention_layer_norm": True,  # non-standard
    # No max_position_embeddings (ALiBi models don't have a fixed limit)
}


def _patch_mmada() -> Any:
    return _patch_hf_calls(
        config=_MMADA_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_MMADA_CARD_DATA,
        hub_info={"author": "Gen-Verse", "sha": "deadf00d"},
    )


_MIMO_AUDIO_CONFIG: dict[str, Any] = {
    "model_type": "qwen2",
    "architectures": ["MiMoAudioModel"],  # custom arch despite qwen2 model_type
    "vocab_size": 152064,
    "hidden_size": 3584,
    "num_hidden_layers": 28,
    "num_attention_heads": 28,
    "num_key_value_heads": 4,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
    "audio_channels": 128,  # non-standard
    "delay_pattern": "valley",  # non-standard
}


_MIMO_AUDIO_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="any-to-any",
    language=["en", "zh"],
    library_name="transformers",
)


def _patch_mimo_audio() -> Any:
    return _patch_hf_calls(
        config=_MIMO_AUDIO_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_MIMO_AUDIO_CARD_DATA,
        hub_info={"author": "XiaomiMiMo", "sha": "deadf00d"},
    )


_AION_CONFIG: dict[str, Any] = {
    "decoder_depth": 8,
    "encoder_depth": 8,
    "domains_in": ["fluids", "climate", "seismology"],
    "domains_out": ["fluids", "climate", "seismology"],
    "patch_size": 16,
}


_AION_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="any-to-any",
    language=None,
    library_name="aion",
)


def _patch_aion() -> Any:
    return _patch_hf_calls(
        config=_AION_CONFIG,
        tokenizer_config=None,
        card_data=_AION_CARD_DATA,
        hub_info={"author": "polymathic-ai", "sha": "deadf00d"},
    )


_MLX_GEMMA4_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["multilingual"],
    library_name="mlx",
    base_model="google/gemma-4-e2b-it",
)


_MLX_GEMMA4_CONFIG: dict[str, Any] = {
    "model_type": "gemma4",
    "architectures": ["Gemma4ForConditionalGeneration"],
    "vocab_size": 262144,
    "hidden_size": 2560,
    "num_hidden_layers": 34,
    "num_attention_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}


def _patch_mlx_gemma4() -> Any:
    return _patch_hf_calls(
        config=_MLX_GEMMA4_CONFIG,
        tokenizer_config=None,
        card_data=_MLX_GEMMA4_CARD_DATA,
        hub_info={
            "author": "mlx-community",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:google/gemma-4-e2b-it"],
        },
    )


_ONNX_GEMMA4_CONFIG: dict[str, Any] = {
    "model_type": "gemma4",
    "architectures": ["Gemma4ForConditionalGeneration"],
    "vocab_size": 262144,
    "hidden_size": 2560,
    "num_hidden_layers": 34,
    "num_attention_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}


_ONNX_GEMMA4_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["multilingual"],
    library_name="transformers.js",
    base_model="google/gemma-4-E2B-it",
)


def _patch_onnx_gemma4() -> Any:
    return _patch_hf_calls(
        config=_ONNX_GEMMA4_CONFIG,
        tokenizer_config=None,
        card_data=_ONNX_GEMMA4_CARD_DATA,
        hub_info={
            "author": "onnx-community",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:google/gemma-4-E2B-it"],
        },
    )


__all__ = [
    "_AION_CARD_DATA",
    "_AION_CONFIG",
    "_BAGEL_CARD_DATA",
    "_BAGEL_CONFIG",
    "_LLADA2_MOE_CARD_DATA",
    "_LLADA2_MOE_CONFIG",
    "_MIMO_AUDIO_CARD_DATA",
    "_MIMO_AUDIO_CONFIG",
    "_MLX_GEMMA4_CARD_DATA",
    "_MLX_GEMMA4_CONFIG",
    "_MMADA_CARD_DATA",
    "_MMADA_CONFIG",
    "_ONNX_GEMMA4_CARD_DATA",
    "_ONNX_GEMMA4_CONFIG",
    "_SENSENOVA_CARD_DATA",
    "_SENSENOVA_CONFIG",
    "_patch_aion",
    "_patch_bagel",
    "_patch_llada2_moe",
    "_patch_mimo_audio",
    "_patch_mlx_gemma4",
    "_patch_mmada",
    "_patch_nemotron",
    "_patch_onnx_gemma4",
    "_patch_sensenova",
]
