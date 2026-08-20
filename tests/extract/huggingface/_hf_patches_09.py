# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for Hugging Face model metadata tests (part 9 of 10).

See also: conftest.py, which re-exports everything via ``from
._hf_patches_09 import *``. Sibling test modules import helper names
from ``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_01 import _make_card_data, _patch_hf_calls

_FIRERED_VAD_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="voice-activity-detection",
    language=None,
    library_name=None,
)


def _patch_firered_vad() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_FIRERED_VAD_CARD_DATA,
        hub_info={"author": "FireRedTeam", "sha": "deadf00d"},
    )


_GTE_RERANKER_CONFIG: dict[str, Any] = {
    "model_type": "new",
    "architectures": ["NewForSequenceClassification"],
    "vocab_size": 250002,
    "hidden_size": 768,
    "num_hidden_layers": 12,
    "torch_dtype": "bfloat16",
}

_GTE_RERANKER_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-ranking",
    language=["multilingual"],
    library_name="sentence-transformers",
)


def _patch_gte_reranker() -> Any:
    return _patch_hf_calls(
        config=_GTE_RERANKER_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_GTE_RERANKER_CARD_DATA,
        hub_info={"author": "Alibaba-NLP", "sha": "deadf00d"},
    )


_OPENELM_270M_CONFIG: dict[str, Any] = {
    "model_type": "openelm",
    "architectures": ["OpenELMForCausalLM"],
    "vocab_size": 32000,
    "hidden_size": 1280,
    "num_hidden_layers": 16,
    "num_attention_heads": 10,
    "head_dim": 64,
    "max_position_embeddings": 2048,
    "torch_dtype": "float16",
    "activation_fn_name": "swiglu",  # non-standard
    "ffn_dim_divisor": 256,  # non-standard
}

_OPENELM_270M_CARD_DATA = _make_card_data(
    license="apple-amlr",
    pipeline_tag="text-generation",
    language=["en"],
    library_name="transformers",
)


def _patch_openelm_270m() -> Any:
    return _patch_hf_calls(
        config=_OPENELM_270M_CONFIG,
        tokenizer_config={"tokenizer_class": "LlamaTokenizer"},
        card_data=_OPENELM_270M_CARD_DATA,
        hub_info={"author": "apple", "sha": "deadf00d"},
    )


_MINIMAX_M2_CONFIG: dict[str, Any] = {
    "model_type": "minimax_m2",
    "architectures": ["MiniMaxM2ForCausalLM"],
    "vocab_size": 200064,
    "hidden_size": 7168,
    "num_hidden_layers": 80,
    "num_attention_heads": 64,
    "num_key_value_heads": 8,
    "max_position_embeddings": 1000000,
    "torch_dtype": "bfloat16",
    "attn_type_list": ["mhsa", "local"] * 40,  # non-standard: mixed attention
    "mtp_transformer_layers": 3,  # non-standard: multi-token prediction
    "num_experts_per_tok": 2,  # non-standard: MoE routing
}

_MINIMAX_M2_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="text-generation",
    language=["en", "zh"],
    library_name="transformers",
)


def _patch_minimax_m2() -> Any:
    return _patch_hf_calls(
        config=_MINIMAX_M2_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_MINIMAX_M2_CARD_DATA,
        hub_info={"author": "MiniMaxAI", "sha": "deadf00d"},
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


_SENSENOVA_CONFIG: dict[str, Any] = {
    "model_type": "neo_chat",
    "architectures": ["NEOChatModel"],
    "llm_config": {"hidden_size": 3584, "num_hidden_layers": 28},  # nested
    "downsample_ratio": 2,  # non-standard
    "template": "chat",  # non-standard
}

_SENSENOVA_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["zh", "en"],
    library_name="transformers",
)


def _patch_sensenova() -> Any:
    return _patch_hf_calls(
        config=_SENSENOVA_CONFIG,
        tokenizer_config=None,
        card_data=_SENSENOVA_CARD_DATA,
        hub_info={"author": "sensenova", "sha": "deadf00d"},
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

_MMADA_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="any-to-any",
    language=["en"],
    library_name="transformers",
)


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


_STANZA_FI_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag=None,
    language=["fi"],
    library_name="stanza",
)


def _patch_stanza_fi() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_STANZA_FI_CARD_DATA,
        hub_info={"author": "stanfordnlp", "sha": "deadf00d"},
    )


_STANZA_DE_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag=None,
    language=["de"],
    library_name="stanza",
)


def _patch_stanza_de() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_STANZA_DE_CARD_DATA,
        hub_info={"author": "stanfordnlp", "sha": "deadf00d"},
    )


_OPENVINO_MIXTRAL_CONFIG: dict[str, Any] = {
    "model_type": "mixtral",
    "architectures": ["MixtralForCausalLM"],
    "vocab_size": 32000,
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "max_position_embeddings": 32768,
    "torch_dtype": "int8",  # quantized dtype captured
    "num_experts_per_tok": 2,  # non-standard (MoE)
    "router_aux_loss_coef": 0.001,  # non-standard (MoE routing)
}

_OPENVINO_MIXTRAL_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "de", "fr", "es", "it"],
    library_name="openvino",
    base_model="mistralai/Mixtral-8x7B-Instruct-v0.1",
)


def _patch_openvino_mixtral() -> Any:
    return _patch_hf_calls(
        config=_OPENVINO_MIXTRAL_CONFIG,
        tokenizer_config=None,
        card_data=_OPENVINO_MIXTRAL_CARD_DATA,
        hub_info={
            "author": "OpenVINO",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:mistralai/Mixtral-8x7B-Instruct-v0.1"],
        },
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

_MLX_GEMMA4_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["multilingual"],
    library_name="mlx",
    base_model="google/gemma-4-e2b-it",
)


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


_SAILOR2_20B_CONFIG: dict[str, Any] = {
    "model_type": "qwen2",
    "architectures": ["Qwen2ForCausalLM"],
    "vocab_size": 151936,
    "hidden_size": 5120,
    "num_hidden_layers": 48,
    "num_attention_heads": 40,
    "num_key_value_heads": 8,
    "max_position_embeddings": 32768,
    "torch_dtype": "bfloat16",
}

_SAILOR2_20B_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "zh", "th", "id", "vi", "ms", "my", "km", "lo", "tl"],
    library_name="transformers",
)


def _patch_sailor2_20b() -> Any:
    return _patch_hf_calls(
        config=_SAILOR2_20B_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_SAILOR2_20B_CARD_DATA,
        hub_info={"author": "sail", "sha": "deadf00d"},
    )


__all__ = [
    "_AION_CARD_DATA",
    "_AION_CONFIG",
    "_BAGEL_CARD_DATA",
    "_BAGEL_CONFIG",
    "_FIRERED_VAD_CARD_DATA",
    "_GTE_RERANKER_CARD_DATA",
    "_GTE_RERANKER_CONFIG",
    "_LIGHTGLUE_CARD_DATA",
    "_LIGHTGLUE_CONFIG",
    "_LLADA2_MOE_CARD_DATA",
    "_LLADA2_MOE_CONFIG",
    "_MIMO_AUDIO_CARD_DATA",
    "_MIMO_AUDIO_CONFIG",
    "_MINIMAX_M2_CARD_DATA",
    "_MINIMAX_M2_CONFIG",
    "_MLX_GEMMA4_CARD_DATA",
    "_MLX_GEMMA4_CONFIG",
    "_MMADA_CARD_DATA",
    "_MMADA_CONFIG",
    "_ONNX_GEMMA4_CARD_DATA",
    "_ONNX_GEMMA4_CONFIG",
    "_OPENELM_270M_CARD_DATA",
    "_OPENELM_270M_CONFIG",
    "_OPENVINO_MIXTRAL_CARD_DATA",
    "_OPENVINO_MIXTRAL_CONFIG",
    "_SAILOR2_20B_CARD_DATA",
    "_SAILOR2_20B_CONFIG",
    "_SENSENOVA_CARD_DATA",
    "_SENSENOVA_CONFIG",
    "_STANZA_DE_CARD_DATA",
    "_STANZA_FI_CARD_DATA",
    "_patch_aion",
    "_patch_bagel",
    "_patch_firered_vad",
    "_patch_gte_reranker",
    "_patch_lightglue",
    "_patch_llada2_moe",
    "_patch_mimo_audio",
    "_patch_minimax_m2",
    "_patch_mlx_gemma4",
    "_patch_mmada",
    "_patch_onnx_gemma4",
    "_patch_openelm_270m",
    "_patch_openvino_mixtral",
    "_patch_sailor2_20b",
    "_patch_sensenova",
    "_patch_stanza_de",
    "_patch_stanza_fi",
]
