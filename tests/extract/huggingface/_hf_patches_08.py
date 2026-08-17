# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for Hugging Face model metadata tests (part 8 of 10).

See also: conftest.py, which re-exports everything via ``from
._hf_patches_08 import *``. Sibling test modules import helper names
from ``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_01 import _make_card_data, _patch_hf_calls

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


_BLOOMZ_7B1_CONFIG: dict[str, Any] = {
    "model_type": "bloom",
    "architectures": ["BloomForCausalLM"],
    "vocab_size": 250880,
    "hidden_size": 4096,
    "n_layer": 30,  # BLOOM-specific: not captured
    "n_head": 32,  # BLOOM-specific: not captured
    "seq_length": 2048,  # added to _HYPER_KEYS -> captured as context length
    "attention_softmax_in_fp32": True,
    "masked_softmax_fusion": True,
    "bias_dropout_fusion": True,
}

_BLOOMZ_7B1_CARD_DATA = _make_card_data(
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
    base_model="bigscience/bloom-7b1",
    datasets=["bigscience/xP3"],
)


def _patch_bloomz_7b1() -> Any:
    return _patch_hf_calls(
        config=_BLOOMZ_7B1_CONFIG,
        tokenizer_config={"tokenizer_class": "BloomTokenizerFast"},
        card_data=_BLOOMZ_7B1_CARD_DATA,
        hub_info={
            "author": "bigscience",
            "sha": "deadf00d",
            "tags": ["base_model:finetune:bigscience/bloom-7b1"],
        },
    )


def _patch_cohere_aya_23() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data={},  # gated card -> empty dict
        hub_info={"author": "CohereLabs", "sha": "deadf00d"},
    )


_OCCIGLOT_CONFIG: dict[str, Any] = {
    "model_type": "mistral",
    "architectures": ["MistralForCausalLM"],
    "vocab_size": 32002,
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "max_position_embeddings": 32768,
    "sliding_window": 4096,
    "torch_dtype": "bfloat16",
}

_OCCIGLOT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "es", "de", "fr", "it"],
    library_name="transformers",
    base_model="occiglot/occiglot-7b-eu5",
)

_OCCIGLOT_TOKENIZER_SENTINEL: int = 1_000_000_000_000_000_019_884_624_838_656


def _patch_occiglot() -> Any:
    return _patch_hf_calls(
        config=_OCCIGLOT_CONFIG,
        tokenizer_config={
            "tokenizer_class": "LlamaTokenizer",
            "model_max_length": _OCCIGLOT_TOKENIZER_SENTINEL,
        },
        card_data=_OCCIGLOT_CARD_DATA,
        hub_info={
            "author": "occiglot",
            "sha": "deadf00d",
            "tags": ["base_model:finetune:occiglot/occiglot-7b-eu5"],
        },
    )


_PHARIA_CONTROL_CARD_DATA = _make_card_data(
    license="other",
    license_name="open-aleph-license",
    pipeline_tag="text-generation",
    language=["de", "en", "fr", "es", "it", "pt", "nl"],
    library_name="scaling",
)


def _patch_pharia_control() -> Any:
    return _patch_hf_calls(
        config=None,  # absent (404) -- custom scaling framework
        tokenizer_config=None,
        card_data=_PHARIA_CONTROL_CARD_DATA,
        hub_info={"author": "Aleph-Alpha", "sha": "deadf00d"},
    )


_PHARIA_ALIGNED_CARD_DATA = _make_card_data(
    license="other",
    license_name="open-aleph-license",
    pipeline_tag="text-generation",
    language=["de", "en", "fr", "es", "it", "pt", "nl"],
    library_name="scaling",
    base_model="Aleph-Alpha/Pharia-1-LLM-7B-control",
)


def _patch_pharia_aligned() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_PHARIA_ALIGNED_CARD_DATA,
        hub_info={
            "author": "Aleph-Alpha",
            "sha": "deadf00d",
            "tags": ["base_model:finetune:Aleph-Alpha/Pharia-1-LLM-7B-control"],
        },
    )


def _patch_wmt22_cometkiwi() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data={},  # gated -> empty
        hub_info={"author": "Unbabel", "sha": "deadf00d"},
    )


_EUROLLM_1B7_CONFIG: dict[str, Any] = {
    "model_type": "llama",
    "architectures": ["LlamaForCausalLM"],
    "vocab_size": 128000,
    "hidden_size": 2048,
    "num_hidden_layers": 24,
    "num_attention_heads": 16,
    "num_key_value_heads": 8,
    "max_position_embeddings": 4096,
    "torch_dtype": "bfloat16",
}

_EUROLLM_1B7_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag=None,
    language=[
        "en",
        "de",
        "es",
        "fr",
        "it",
        "pt",
        "pl",
        "nl",
        "tr",
        "sv",
        "cs",
        "el",
        "hu",
        "ro",
        "fi",
        "uk",
        "sl",
        "sk",
        "da",
        "lt",
        "lv",
        "et",
        "bg",
        "no",
        "ca",
        "hr",
        "ga",
        "mt",
        "gl",
        "zh",
        "ru",
        "ko",
        "ja",
        "ar",
    ],
    library_name="transformers",
)

_EUROLLM_TOKENIZER_SENTINEL: int = 1_000_000_000_000_000_019_884_624_838_656


def _patch_eurollm_1b7() -> Any:
    return _patch_hf_calls(
        config=_EUROLLM_1B7_CONFIG,
        tokenizer_config={
            "tokenizer_class": "LlamaTokenizer",
            "model_max_length": _EUROLLM_TOKENIZER_SENTINEL,
        },
        card_data=_EUROLLM_1B7_CARD_DATA,
        hub_info={"author": "utter-project", "sha": "deadf00d"},
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


_HY_MOTION_CONFIG: dict[str, Any] = {
    "Name": "HunyuanMotion",  # non-standard metadata field
    "motion_module_type": "vanilla",
    "num_transformer_blocks": 20,
}

_HY_MOTION_CARD_DATA = _make_card_data(
    license="other",
    license_name="tencent-hunyuan-community",
    pipeline_tag="text-to-3d",
    language=["zh", "en"],
    library_name="HY-Motion-1.0",
)


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
    "_BLOOMZ_7B1_CARD_DATA",
    "_BLOOMZ_7B1_CONFIG",
    "_BLOOM_CARD_DATA",
    "_BLOOM_CONFIG",
    "_EUROLLM_1B7_CARD_DATA",
    "_EUROLLM_1B7_CONFIG",
    "_EUROLLM_TOKENIZER_SENTINEL",
    "_HY_MOTION_CARD_DATA",
    "_HY_MOTION_CONFIG",
    "_OCCIGLOT_CARD_DATA",
    "_OCCIGLOT_CONFIG",
    "_OCCIGLOT_TOKENIZER_SENTINEL",
    "_PHARIA_ALIGNED_CARD_DATA",
    "_PHARIA_CONTROL_CARD_DATA",
    "_SHAP_E_CARD_DATA",
    "_STABLE_ZERO123_CARD_DATA",
    "_patch_apple_sharp",
    "_patch_blenderllm",
    "_patch_blenderllm_gguf",
    "_patch_bloom",
    "_patch_bloomz_7b1",
    "_patch_cohere_aya_23",
    "_patch_eurollm_1b7",
    "_patch_hy_motion",
    "_patch_occiglot",
    "_patch_pharia_aligned",
    "_patch_pharia_control",
    "_patch_shap_e",
    "_patch_stable_zero123",
    "_patch_wmt22_cometkiwi",
]
