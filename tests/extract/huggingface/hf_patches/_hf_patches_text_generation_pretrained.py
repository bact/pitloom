# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for base/pretrained causal-LM text-generation models.

See also: _hf_patches_base.py, _hf_patches_text_generation_instruct.py,
_hf_patches_text_generation_regional.py, _hf_patches_gated_metadata.py,
_hf_patches_gated_access.py, _hf_patches_speech_audio.py,
_hf_patches_multimodal.py, _hf_patches_omni_modal.py,
_hf_patches_embeddings.py, _hf_patches_vision.py,
_hf_patches_structured_text.py, _hf_patches_generative_3d.py. Sibling test
modules import these names directly from the matching topic module.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)

_STARCODER2_CONFIG: dict[str, Any] = {
    "model_type": "starcoder2",
    "architectures": ["Starcoder2ForCausalLM"],
    "hidden_size": 3072,
    "num_hidden_layers": 30,
    "num_attention_heads": 24,
    "vocab_size": 49152,
    "torch_dtype": "float32",
}


_STARCODER2_CARD_DATA = _make_card_data(
    license="bigcode-openrail-m",
    pipeline_tag="text-generation",
    tags=["code"],
    language=None,
    datasets=["bigcode/the-stack-v2-train"],
    library_name="transformers",
)


def _patch_starcoder2() -> Any:
    return _patch_hf_calls(
        config=_STARCODER2_CONFIG,
        card_data=_STARCODER2_CARD_DATA,
        hub_info={"author": "bigcode"},
    )


_LLAMA_CARD_DATA = _make_card_data(
    license="llama3.2",  # Custom Meta license - not vague, not standard SPDX
    pipeline_tag="text-generation",
    tags=["facebook", "meta", "pytorch", "llama", "llama-3"],
    language=["en", "de", "fr", "it", "pt", "hi", "es", "th"],
    library_name="transformers",
)


def _patch_llama() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated - config.json inaccessible
        tokenizer_config=None,
        card_data=_LLAMA_CARD_DATA,
        hub_info={"author": "meta-llama"},
    )


def _patch_granite_4_1_8b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "granite",
            "architectures": ["GraniteForCausalLM"],
            "vocab_size": 49152,
            "num_hidden_layers": 40,
            "hidden_size": 4096,
            "num_attention_heads": 32,
            "num_key_value_heads": 8,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["granite", "conversational"],
            language=[
                "en",
                "de",
                "es",
                "fr",
                "ja",
                "pt",
                "ar",
                "cs",
                "it",
                "ko",
                "nl",
                "zh",
            ],
            base_model=["ibm-granite/granite-4.1-8b-base"],
        ),
        hub_info={
            "author": "ibm-granite",
            "tags": [
                "base_model:ibm-granite/granite-4.1-8b-base",
                "base_model:finetune:ibm-granite/granite-4.1-8b-base",
            ],
        },
    )


def _patch_opt_2_7b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "opt",
            "architectures": ["OPTForCausalLM"],
            "vocab_size": 50272,
            "num_hidden_layers": 32,
            "hidden_size": 2560,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="text-generation",
            tags=[],
        ),
        hub_info={"author": "facebook"},
    )


def _patch_gpt_neo_2_7b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "gpt_neo",
            "architectures": ["GPTNeoForCausalLM"],
            "vocab_size": 50257,
            "num_hidden_layers": 32,
            "hidden_size": 2560,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=[],
            language=["en"],
        ),
        hub_info={"author": "EleutherAI"},
    )


def _patch_phi2() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "phi",
            "architectures": ["PhiForCausalLM"],
            "vocab_size": 51200,
            "num_hidden_layers": 32,
            "hidden_size": 2560,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="text-generation",
            tags=["nlp", "code"],
            language=["en"],
        ),
        hub_info={"author": "microsoft"},
    )


def _patch_llama_3_2_3b() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated
        tokenizer_config=None,
        card_data=_make_card_data(
            license="llama3.2",
            pipeline_tag="text-generation",
            tags=[],
            language=["en", "de", "fr", "it", "pt", "hi", "es", "th"],
        ),
        hub_info={"author": "meta-llama"},
    )


_QWEN3_235B_GENERATION_CONFIG: dict[str, Any] = {
    "temperature": 0.6,
    "top_p": 0.95,
}


_QWEN3_235B_CARD_DATA = _make_card_data(
    license="qwen",
    pipeline_tag="text-generation",
    language=["multilingual"],
    library_name="transformers",
)


_QWEN3_235B_CONFIG: dict[str, Any] = {
    "model_type": "qwen3_moe",
    "architectures": ["Qwen3MoeForCausalLM"],
    "vocab_size": 152064,
    "hidden_size": 7168,
    "num_hidden_layers": 94,
    "num_attention_heads": 64,
    "num_key_value_heads": 4,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}


def _patch_qwen3_235b() -> Any:
    return _patch_hf_calls(
        config=_QWEN3_235B_CONFIG,
        tokenizer_config={
            "tokenizer_class": "Qwen2Tokenizer",
            "model_max_length": 32768,
        },
        generation_config=_QWEN3_235B_GENERATION_CONFIG,
        card_data=_QWEN3_235B_CARD_DATA,
        hub_info={"author": "Qwen", "sha": "abc123ef"},
    )


_QWEN35_27B_CONFIG: dict[str, Any] = {
    "model_type": "qwen3",
    "architectures": ["Qwen3ForCausalLM"],
    "vocab_size": 152064,
    "hidden_size": 5120,
    "num_hidden_layers": 64,
    "num_attention_heads": 40,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}


_QWEN35_27B_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["multilingual"],
    library_name="transformers",
)


def _patch_qwen35_27b() -> Any:
    return _patch_hf_calls(
        config=_QWEN35_27B_CONFIG,
        tokenizer_config={
            "tokenizer_class": "Qwen2Tokenizer",
            "model_max_length": 131072,
        },
        card_data=_QWEN35_27B_CARD_DATA,
        hub_info={"author": "Qwen", "sha": "deadf00d"},
    )


_BLOOM_CONFIG: dict[str, Any] = {
    "model_type": "bloom",
    "architectures": ["BloomForCausalLM"],
    "vocab_size": 250880,
    "hidden_size": 14336,
    "n_layer": 70,  # BLOOM-specific: extractor does NOT capture (not in _HYPER_KEYS)
    "n_head": 112,  # BLOOM-specific: extractor does NOT capture (not in _HYPER_KEYS)
    "attention_softmax_in_fp32": True,
    "masked_softmax_fusion": True,
    # No max_position_embeddings (ALiBi)
    # No torch_dtype in config
}


_BLOOM_CARD_DATA = _make_card_data(
    license="bigscience-bloom-rail-1.0",
    pipeline_tag="text-generation",
    language=[
        "ak",
        "ar",
        "as",
        "bm",
        "bn",
        "ca",
        "code",
        "en",
        "es",
        "eu",
        "fon",
        "fr",
        "gu",
        "hi",
        "id",
        "ig",
        "ki",
        "kn",
        "lg",
        "ln",
        "ml",
        "mr",
        "ne",
        "nso",
        "ny",
        "or",
        "pa",
        "pt",
        "rn",
        "rw",
        "sn",
        "st",
        "sw",
        "ta",
        "te",
        "tn",
        "ts",
        "tum",
        "tw",
        "ur",
        "ve",
        "vi",
        "wo",
        "xh",
        "yo",
        "zh",
        "zu",
    ],
    library_name="transformers",
)


def _patch_bloom() -> Any:
    return _patch_hf_calls(
        config=_BLOOM_CONFIG,
        tokenizer_config={"tokenizer_class": "BloomTokenizerFast"},
        card_data=_BLOOM_CARD_DATA,
        hub_info={"author": "bigscience", "sha": "deadf00d"},
    )


_OPENELM_270M_CARD_DATA = _make_card_data(
    license="apple-amlr",
    pipeline_tag="text-generation",
    language=["en"],
    library_name="transformers",
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


def _patch_openelm_270m() -> Any:
    return _patch_hf_calls(
        config=_OPENELM_270M_CONFIG,
        tokenizer_config={"tokenizer_class": "LlamaTokenizer"},
        card_data=_OPENELM_270M_CARD_DATA,
        hub_info={"author": "apple", "sha": "deadf00d"},
    )


__all__ = [
    "_BLOOM_CARD_DATA",
    "_BLOOM_CONFIG",
    "_LLAMA_CARD_DATA",
    "_OPENELM_270M_CARD_DATA",
    "_OPENELM_270M_CONFIG",
    "_QWEN35_27B_CARD_DATA",
    "_QWEN35_27B_CONFIG",
    "_QWEN3_235B_CARD_DATA",
    "_QWEN3_235B_CONFIG",
    "_QWEN3_235B_GENERATION_CONFIG",
    "_STARCODER2_CARD_DATA",
    "_STARCODER2_CONFIG",
    "_patch_bloom",
    "_patch_gpt_neo_2_7b",
    "_patch_granite_4_1_8b",
    "_patch_llama",
    "_patch_llama_3_2_3b",
    "_patch_openelm_270m",
    "_patch_opt_2_7b",
    "_patch_phi2",
    "_patch_qwen35_27b",
    "_patch_qwen3_235b",
    "_patch_starcoder2",
]
