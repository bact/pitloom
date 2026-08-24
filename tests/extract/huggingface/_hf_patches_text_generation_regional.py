# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for language- or region-specialised text-generation models (Thai,
Japanese, Korean, and Southeast Asian multilingual fine-tunes).

See also: _hf_patches_base.py, _hf_patches_text_generation_pretrained.py,
_hf_patches_text_generation_instruct.py, _hf_patches_gated_metadata.py,
_hf_patches_speech_audio.py, _hf_patches_multimodal.py,
_hf_patches_omni_modal.py, _hf_patches_embeddings.py, _hf_patches_vision.py,
_hf_patches_structured_text.py, _hf_patches_generative_3d.py. Sibling test
modules import helper names from ``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)

_OPENTHAIGPT_CARD_DATA = _make_card_data(
    license="other",
    license_name="qwen",
    pipeline_tag="text-generation",
    tags=["openthaigpt", "qwen", "reasoning"],
    language=["th", "en"],
    library_name="transformers",
    model_index=[
        {
            "name": "openthaigpt-r1-32b-instruct",
            "results": [{"task": {"type": "reasoning"}, "dataset": {"name": "custom"}}],
        }
    ],
)


_OPENTHAIGPT_CONFIG: dict[str, Any] = {
    "model_type": "qwen2",
    "architectures": ["Qwen2ForCausalLM"],
    "vocab_size": 152064,
    "hidden_size": 5120,
    "num_hidden_layers": 64,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}


def _patch_openthaigpt() -> Any:
    return _patch_hf_calls(
        config=_OPENTHAIGPT_CONFIG,
        tokenizer_config={
            "tokenizer_class": "Qwen2Tokenizer",
            "model_max_length": 131072,
        },
        card_data=_OPENTHAIGPT_CARD_DATA,
        card_text=(
            "---\nlicense: other\n---\n\nA Thai-English bilingual reasoning model."
        ),
        hub_info={"author": "openthaigpt", "sha": "cafebabe"},
    )


_TYPHOON_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    tags=["pretrained"],
    language=["th"],
    library_name="transformers",
)


_TYPHOON_CONFIG: dict[str, Any] = {
    "model_type": "mistral",
    "architectures": ["MistralForCausalLM"],
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "vocab_size": 32768,
    "torch_dtype": "bfloat16",
}


def _patch_typhoon() -> Any:
    return _patch_hf_calls(
        config=_TYPHOON_CONFIG,
        card_data=_TYPHOON_CARD_DATA,
        hub_info={"author": "typhoon-ai"},
    )


_CHINDA_CONFIG: dict[str, Any] = {
    "model_type": "qwen3",
    "architectures": ["Qwen3ForCausalLM"],
    "vocab_size": 151936,
    "num_hidden_layers": 36,
    "hidden_size": 2560,
}


_CHINDA_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    tags=["thai", "conversational"],
    language=["th", "en"],
    base_model=["Qwen/Qwen3-4B"],
)


def _patch_chinda() -> Any:
    return _patch_hf_calls(
        config=_CHINDA_CONFIG,
        card_data=_CHINDA_CARD_DATA,
        hub_info={
            "author": "iapp",
            "tags": [
                "base_model:Qwen/Qwen3-4B",
                "base_model:finetune:Qwen/Qwen3-4B",
                "doi:10.57967/hf/5709",
            ],
        },
    )


_CHINDA_GGUF_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    tags=["thai"],
    language=["th", "en"],
    base_model="iapp/chinda-qwen3-4b",  # string, not list
)


def _patch_chinda_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_CHINDA_GGUF_CARD_DATA,
        hub_info={
            "author": "iapp",
            "tags": [
                "base_model:iapp/chinda-qwen3-4b",
                "base_model:quantized:iapp/chinda-qwen3-4b",
            ],
        },
    )


def _patch_wangchanglm() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "xglm",
            "architectures": ["XGLMForCausalLM"],
            "vocab_size": 256008,
        },
        tokenizer_config={
            "tokenizer_class": "XGLMTokenizer",
            "model_max_length": 1000000000000000019884624838656,  # unlimited sentinel
        },
        card_data=_make_card_data(
            license="cc-by-sa-4.0",
            pipeline_tag="text-generation",
            tags=[],
            language=["en", "th", "ja", "vi"],
            datasets=[
                "laion/OIG",
                "Hello-SimpleAI/HC3",
                "databricks/databricks-dolly-15k",
            ],
        ),
        hub_info={"author": "pythainlp"},
    )


def _patch_mallam() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "mistral",
            "architectures": ["MistralForCausalLM"],
            "vocab_size": 32000,
            "num_hidden_layers": 22,
            "hidden_size": 2048,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag="text-generation",
            tags=[],
            language=["ms"],
        ),
        hub_info={"author": "mesolitica"},
    )


def _patch_llmjp() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "llama",
            "architectures": ["LlamaForCausalLM"],
            "vocab_size": 99584,
            "num_hidden_layers": 24,
            "hidden_size": 2048,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=[],
            language=["en", "ja"],
        ),
        hub_info={"author": "llm-jp"},
    )


def _patch_laguna() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "laguna",
            "architectures": ["LagunaForCausalLM"],
            "vocab_size": 100352,
            "num_hidden_layers": 40,
            "hidden_size": 2048,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["laguna-xs.2", "vllm"],
            library_name="transformers",
        ),
        hub_info={"author": "poolside"},
    )


def _patch_gpt_neox_jp() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "gpt_neox_japanese",
            "architectures": ["GPTNeoXJapaneseForCausalLM"],
            "vocab_size": 32000,
            "num_hidden_layers": 32,
            "hidden_size": 2560,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="text-generation",
            tags=["ja", "japanese", "gpt_neox", "gpt", "lm", "nlp"],
            language="ja",  # scalar string
            datasets=["cc100", "wikipedia"],
        ),
        hub_info={"author": "abeja"},
    )


def _patch_darwin_kr_legal() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "qwen3_5",
            "architectures": ["Qwen3_5ForCausalLM"],
            "vocab_size": 151936,
            "num_hidden_layers": 64,
            "hidden_size": 5120,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["korean", "legal", "conversational"],
            language=["ko", "en"],
            base_model=["FINAL-Bench/Darwin-28B-KR"],
        ),
        hub_info={
            "author": "FINAL-Bench",
            "tags": [
                "base_model:FINAL-Bench/Darwin-28B-KR",
                "base_model:finetune:FINAL-Bench/Darwin-28B-KR",
            ],
        },
    )


def _patch_qwen3_swallow() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "qwen3",
            "architectures": ["Qwen3ForCausalLM"],
            "vocab_size": 151936,
            "num_hidden_layers": 36,
            "hidden_size": 4096,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["conversational"],
            language=["en", "ja"],
            base_model=["tokyotech-llm/Qwen3-Swallow-8B-CPT-v0.2"],
        ),
        hub_info={
            "author": "tokyotech-llm",
            "tags": [
                "base_model:tokyotech-llm/Qwen3-Swallow-8B-CPT-v0.2",
                "base_model:finetune:tokyotech-llm/Qwen3-Swallow-8B-CPT-v0.2",
            ],
        },
    )


def _patch_sealion_27b_it() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "gemma3",
            "architectures": ["Gemma3ForCausalLM"],
            "vocab_size": 262208,
            "num_hidden_layers": 62,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="gemma",
            pipeline_tag="text-generation",
            tags=["conversational", "image-text-to-text"],
            language=["my", "en", "id", "km", "lo", "ms", "zh", "tl", "ta", "th", "vi"],
            base_model=["google/gemma-3-27b-it"],
        ),
        hub_info={
            "author": "aisingapore",
            "tags": [
                "base_model:google/gemma-3-27b-it",
                "base_model:finetune:google/gemma-3-27b-it",
            ],
        },
    )


_FUJITSU_LLM_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["ja", "en"],
    library_name="nemo",
)


def _patch_fujitsu_llm() -> Any:
    return _patch_hf_calls(
        config=None,  # gated -> 401
        tokenizer_config=None,
        card_data=_FUJITSU_LLM_CARD_DATA,
        hub_info={"author": "Fujitsu", "sha": "deadf00d"},
    )


_TILDEOPEN_30B_64K_CARD_DATA = _make_card_data(
    license="cc-by-4.0",
    pipeline_tag="text-generation",
    language=[
        "af",
        "bg",
        "ca",
        "cs",
        "cy",
        "da",
        "de",
        "el",
        "en",
        "es",
        "et",
        "eu",
        "fi",
        "fr",
        "ga",
        "hr",
        "hu",
        "is",
        "it",
        "lt",
        "lv",
        "mk",
        "mt",
        "nl",
        "no",
        "pl",
        "pt",
        "ro",
        "sk",
        "sl",
        "sq",
        "sv",
        "uk",
        "la",
    ],
    library_name="transformers",
    datasets=[
        "HPLT/HPLT2.0_cleaned",
        "HPLT/hplt_monolingual_v1_2",
        "HuggingFaceFW/fineweb-2",
        "allenai/MADLAD-400",
        "uonlp/CulturaX",
        "bigcode/the-stack",
        "common-pile/arxiv_papers",
    ],
)


_TILDEOPEN_30B_64K_CONFIG: dict[str, Any] = {
    "model_type": "llama",
    "architectures": ["LlamaForCausalLM"],
    "vocab_size": 131072,
    "hidden_size": 6144,
    "num_hidden_layers": 60,
    "num_attention_heads": 48,
    "num_key_value_heads": 8,
    "max_position_embeddings": 65536,
    "torch_dtype": "bfloat16",
    "rope_scaling": {
        "rope_type": "yarn",
        "factor": 10.0,
        "original_max_position_embeddings": 8192,
    },
}


def _patch_tildeopen_30b_64k() -> Any:
    return _patch_hf_calls(
        config=_TILDEOPEN_30B_64K_CONFIG,
        tokenizer_config={
            "tokenizer_class": "PreTrainedTokenizerFast",
            "model_max_length": 65536,
        },
        card_data=_TILDEOPEN_30B_64K_CARD_DATA,
        hub_info={"author": "TildeAI", "sha": "deadf00d"},
    )


_TILDEOPEN_30B_CARD_DATA = _make_card_data(
    license="cc-by-4.0",
    pipeline_tag="text-generation",
    language=[
        "af",
        "bg",
        "ca",
        "cs",
        "cy",
        "da",
        "de",
        "el",
        "en",
        "es",
        "et",
        "eu",
        "fi",
        "fr",
        "ga",
        "hr",
        "hu",
        "is",
        "it",
        "lt",
        "lv",
        "mk",
        "mt",
        "nl",
        "no",
        "pl",
        "pt",
        "ro",
        "sk",
        "sl",
        "sq",
        "sv",
        "uk",
        "la",
    ],
    library_name="transformers",
    datasets=[
        "HPLT/HPLT2.0_cleaned",
        "HPLT/hplt_monolingual_v1_2",
        "HuggingFaceFW/fineweb-2",
        "allenai/MADLAD-400",
        "uonlp/CulturaX",
        "bigcode/the-stack",
        "common-pile/arxiv_papers",
    ],
)


_TILDEOPEN_TOKENIZER_SENTINEL: int = 1_000_000_000_000_000_019_884_624_838_656


_TILDEOPEN_30B_CONFIG: dict[str, Any] = {
    "model_type": "llama",
    "architectures": ["LlamaForCausalLM"],
    "vocab_size": 131072,
    "hidden_size": 6144,
    "num_hidden_layers": 60,
    "num_attention_heads": 48,
    "num_key_value_heads": 8,
    "max_position_embeddings": 65536,
    "torch_dtype": "bfloat16",
}


def _patch_tildeopen_30b() -> Any:
    return _patch_hf_calls(
        config=_TILDEOPEN_30B_CONFIG,
        tokenizer_config={
            "tokenizer_class": "LlamaTokenizer",
            "model_max_length": _TILDEOPEN_TOKENIZER_SENTINEL,
        },
        card_data=_TILDEOPEN_30B_CARD_DATA,
        hub_info={"author": "TildeAI", "sha": "deadf00d"},
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
    "_CHINDA_CARD_DATA",
    "_CHINDA_CONFIG",
    "_CHINDA_GGUF_CARD_DATA",
    "_FUJITSU_LLM_CARD_DATA",
    "_OPENTHAIGPT_CARD_DATA",
    "_OPENTHAIGPT_CONFIG",
    "_SAILOR2_20B_CARD_DATA",
    "_SAILOR2_20B_CONFIG",
    "_TILDEOPEN_30B_64K_CARD_DATA",
    "_TILDEOPEN_30B_64K_CONFIG",
    "_TILDEOPEN_30B_CARD_DATA",
    "_TILDEOPEN_30B_CONFIG",
    "_TILDEOPEN_TOKENIZER_SENTINEL",
    "_TYPHOON_CARD_DATA",
    "_TYPHOON_CONFIG",
    "_patch_chinda",
    "_patch_chinda_gguf",
    "_patch_darwin_kr_legal",
    "_patch_fujitsu_llm",
    "_patch_gpt_neox_jp",
    "_patch_laguna",
    "_patch_llmjp",
    "_patch_mallam",
    "_patch_openthaigpt",
    "_patch_qwen3_swallow",
    "_patch_sailor2_20b",
    "_patch_sealion_27b_it",
    "_patch_tildeopen_30b",
    "_patch_tildeopen_30b_64k",
    "_patch_typhoon",
    "_patch_wangchanglm",
]
