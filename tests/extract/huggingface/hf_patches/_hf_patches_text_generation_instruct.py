# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for instruction- or chat-tuned causal-LM text-generation models.

See also: _hf_patches_base.py, _hf_patches_text_generation_pretrained.py,
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


def _patch_crow_9b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "qwen3_5",
            "architectures": ["Qwen3_5ForCausalLM"],
            "vocab_size": 151936,
            "num_hidden_layers": 40,
            "hidden_size": 3584,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["agent", "conversational"],
            language=[
                "en",
                "zh",
                "fr",
                "de",
                "es",
                "pt",
                "it",
                "ja",
                "ko",
                "ru",
                "ar",
                "hi",
                "nl",
                "pl",
                "sv",
                "da",
                "no",
                "fi",
                "cs",
                "hu",
                "ro",
                "tr",
                "vi",
                "id",
                "th",
                "uk",
            ],
            base_model=["Qwen/Qwen3.5-9B-Base"],
        ),
        hub_info={
            "author": "Crownelius",
            "tags": [
                "base_model:Qwen/Qwen3.5-9B-Base",
                "base_model:merge:Qwen/Qwen3.5-9B-Base",
            ],
        },
    )


def _patch_qwen3_reap() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "qwen3_moe",
            "architectures": ["Qwen3MoeForCausalLM"],
            "num_hidden_layers": 94,
            "hidden_size": 4096,
            "num_experts": 384,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["mixture-of-experts", "code", "expert-merging"],
            base_model=["Qwen/Qwen3-Coder-Next"],
        ),
        hub_info={
            "author": "SamsungSAILMontreal",
            "tags": [
                "base_model:Qwen/Qwen3-Coder-Next",
                "base_model:merge:Qwen/Qwen3-Coder-Next",
            ],
        },
    )


def _patch_opt_iml() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "opt",
            "architectures": ["OPTForCausalLM"],
            "vocab_size": 50272,
            "num_hidden_layers": 24,
            "hidden_size": 2048,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="text-generation",
            tags=["opt"],
        ),
        hub_info={
            "author": "facebook",
            "tags": ["arxiv:2212.12017"],
        },
    )


def _patch_stablelm_zephyr() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "stablelm_epoch",
            "architectures": ["StableLMEpochForCausalLM"],
            "vocab_size": 100352,
            "num_hidden_layers": 24,
            "hidden_size": 2048,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["conversational"],
            language=[
                "en",
                "de",
                "es",
                "fr",
                "it",
                "nl",
                "pt",
                "pl",
                "ru",
                "zh",
                "ja",
                "ko",
            ],
        ),
        hub_info={"author": "stabilityai"},
    )


def _patch_tinyllama_chat() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "llama",
            "architectures": ["LlamaForCausalLM"],
            "vocab_size": 32000,
            "num_hidden_layers": 22,
            "hidden_size": 2048,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["conversational"],
            language=["en"],
        ),
        hub_info={"author": "TinyLlama"},
    )


def _patch_llama_3_2_3b_instruct() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated
        tokenizer_config=None,
        card_data=_make_card_data(
            license="llama3.2",
            pipeline_tag="text-generation",
            tags=["conversational"],
            language=["en", "de", "fr", "it", "pt", "hi", "es", "th"],
            base_model=["meta-llama/Llama-3.2-3B"],
        ),
        hub_info={
            "author": "meta-llama",
            "tags": [
                "base_model:meta-llama/Llama-3.2-3B",
                "base_model:finetune:meta-llama/Llama-3.2-3B",
            ],
        },
    )


def _patch_hermes_3_llama_3b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "llama",
            "architectures": ["LlamaForCausalLM"],
            "vocab_size": 128256,
            "num_hidden_layers": 28,
            "hidden_size": 3072,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="llama3",
            pipeline_tag="text-generation",
            tags=["chatml", "instruct", "function-calling"],
            language=["en"],
            base_model=["meta-llama/Llama-3.2-3B"],
        ),
        hub_info={
            "author": "NousResearch",
            "tags": [
                "base_model:meta-llama/Llama-3.2-3B",
                "base_model:finetune:meta-llama/Llama-3.2-3B",
            ],
        },
    )


_GLM45_AIR_REAP_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "ko", "zh"],
    library_name="transformers",
    base_model="THUDM/GLM-4.5-Air",
)


_GLM45_AIR_REAP_CONFIG: dict[str, Any] = {
    "model_type": "glm4_moe",
    "architectures": ["Glm4MoeForCausalLM"],
    "vocab_size": 151552,
    "hidden_size": 4096,
    "num_hidden_layers": 62,
    "num_attention_heads": 32,
    "num_key_value_heads": 2,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}


def _patch_glm45_air_reap() -> Any:
    return _patch_hf_calls(
        config=_GLM45_AIR_REAP_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_GLM45_AIR_REAP_CARD_DATA,
        hub_info={
            "author": "THUDM",
            "sha": "deadf00d",
            "tags": ["base_model:merge:THUDM/GLM-4.5-Air"],
        },
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


_OCCIGLOT_TOKENIZER_SENTINEL: int = 1_000_000_000_000_000_019_884_624_838_656


_OCCIGLOT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "es", "de", "fr", "it"],
    library_name="transformers",
    base_model="occiglot/occiglot-7b-eu5",
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


_OPENVINO_MIXTRAL_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "de", "fr", "es", "it"],
    library_name="openvino",
    base_model="mistralai/Mixtral-8x7B-Instruct-v0.1",
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


__all__ = [
    "_BLOOMZ_7B1_CARD_DATA",
    "_BLOOMZ_7B1_CONFIG",
    "_GLM45_AIR_REAP_CARD_DATA",
    "_GLM45_AIR_REAP_CONFIG",
    "_MINIMAX_M2_CARD_DATA",
    "_MINIMAX_M2_CONFIG",
    "_OCCIGLOT_CARD_DATA",
    "_OCCIGLOT_CONFIG",
    "_OCCIGLOT_TOKENIZER_SENTINEL",
    "_OPENVINO_MIXTRAL_CARD_DATA",
    "_OPENVINO_MIXTRAL_CONFIG",
    "_PHARIA_ALIGNED_CARD_DATA",
    "_PHARIA_CONTROL_CARD_DATA",
    "_patch_bloomz_7b1",
    "_patch_crow_9b",
    "_patch_glm45_air_reap",
    "_patch_hermes_3_llama_3b",
    "_patch_llama_3_2_3b_instruct",
    "_patch_minimax_m2",
    "_patch_occiglot",
    "_patch_openvino_mixtral",
    "_patch_opt_iml",
    "_patch_pharia_aligned",
    "_patch_pharia_control",
    "_patch_qwen3_reap",
    "_patch_stablelm_zephyr",
    "_patch_tinyllama_chat",
]
