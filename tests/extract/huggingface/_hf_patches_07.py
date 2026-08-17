# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for Hugging Face model metadata tests (part 7 of 10).

See also: conftest.py, which re-exports everything via ``from
._hf_patches_07 import *``. Sibling test modules import helper names
from ``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_01 import _make_card_data, _patch_hf_calls

_EXAONE_PATH_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="pathology-image-analysis",
    language=["en"],
    library_name="transformers",
)


def _patch_exaone_path() -> Any:
    return _patch_hf_calls(
        config=None,  # gated → 401
        tokenizer_config=None,
        card_data=_EXAONE_PATH_CARD_DATA,
        hub_info={"author": "LGAI-EXAONE", "sha": "deadf00d"},
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

_GLM45_AIR_REAP_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "ko", "zh"],
    library_name="transformers",
    base_model="THUDM/GLM-4.5-Air",
)


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


_LINE_DISTILBERT_CONFIG: dict[str, Any] = {
    "model_type": "distilbert",
    "architectures": ["DistilBertForMaskedLM"],
    "vocab_size": 32000,
    "hidden_size": 768,
    "num_hidden_layers": 6,
    "num_attention_heads": 12,
    "max_position_embeddings": 512,
    "torch_dtype": "float32",
}

_LINE_DISTILBERT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="fill-mask",
    language=["ja"],
    library_name="transformers",
)


def _patch_line_distilbert() -> Any:
    return _patch_hf_calls(
        config=_LINE_DISTILBERT_CONFIG,
        tokenizer_config={"tokenizer_class": "BertJapaneseTokenizer"},
        card_data=_LINE_DISTILBERT_CARD_DATA,
        hub_info={"author": "line-corporation", "sha": "deadf00d"},
    )


_CLIP_JAPANESE_V2_CONFIG: dict[str, Any] = {
    "model_type": "clyp",
    "architectures": ["CLYPModel"],
    "hidden_size": 768,
    "vocab_size": 32000,
    "torch_dtype": "float32",
}

_CLIP_JAPANESE_V2_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="feature-extraction",
    language=["ja"],
    library_name="transformers",
)


def _patch_clip_japanese_v2() -> Any:
    return _patch_hf_calls(
        config=_CLIP_JAPANESE_V2_CONFIG,
        tokenizer_config={"tokenizer_class": "BertJapaneseTokenizer"},
        card_data=_CLIP_JAPANESE_V2_CARD_DATA,
        hub_info={"author": "line-corporation", "sha": "deadf00d"},
    )


_FUJITSU_LLM_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["ja", "en"],
    library_name="nemo",
)


def _patch_fujitsu_llm() -> Any:
    return _patch_hf_calls(
        config=None,  # gated → 401
        tokenizer_config=None,
        card_data=_FUJITSU_LLM_CARD_DATA,
        hub_info={"author": "Fujitsu", "sha": "deadf00d"},
    )


_WINDOWSEAT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="image-to-image",
    language=None,
    library_name="peft",
)


def _patch_windowseat() -> Any:
    return _patch_hf_calls(
        config=None,  # absent → 404
        tokenizer_config=None,
        card_data=_WINDOWSEAT_CARD_DATA,
        hub_info={"author": "windowseat-ai", "sha": "deadf00d"},
    )


_MOIRAI_CONFIG: dict[str, Any] = {
    "patch_sizes": [8, 16, 32, 64, 128],
    "d_model": 384,
    "num_encoder_layers": 6,
    "nhead": 8,
    "context_length": 4096,
}

_MOIRAI_CARD_DATA = _make_card_data(
    license="cc-by-nc-4.0",
    pipeline_tag="time-series-forecasting",
    language=None,
    library_name="transformers",
)


def _patch_moirai() -> Any:
    return _patch_hf_calls(
        config=_MOIRAI_CONFIG,
        tokenizer_config=None,
        card_data=_MOIRAI_CARD_DATA,
        hub_info={"author": "Salesforce", "sha": "deadf00d"},
    )


_LLASA_3B_CONFIG: dict[str, Any] = {
    "model_type": "llama",
    "architectures": ["LlamaForCausalLM"],
    "vocab_size": 193800,
    "hidden_size": 3072,
    "num_hidden_layers": 28,
    "num_attention_heads": 24,
    "num_key_value_heads": 8,
    "max_position_embeddings": 4096,
    "torch_dtype": "bfloat16",
}

_LLASA_3B_CARD_DATA = _make_card_data(
    license="cc-by-nc-4.0",
    pipeline_tag="text-to-speech",
    language=["en", "zh"],
    library_name="transformers",
)


def _patch_llasa_3b() -> Any:
    return _patch_hf_calls(
        config=_LLASA_3B_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_LLASA_3B_CARD_DATA,
        hub_info={"author": "HKUSTAudio", "sha": "deadf00d"},
    )


_VOXTRAL_MINI_CONFIG: dict[str, Any] = {
    "model_type": "voxtral_realtime",
    "architectures": ["VoxtralRealtimeForConditionalGeneration"],
    "vocab_size": 131072,
    "hidden_size": 3072,
    "num_hidden_layers": 26,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
    "audio_config": {"audio_length_per_tok": 8},
    "projector_hidden_act": "gelu",
}

_VOXTRAL_MINI_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="automatic-speech-recognition",
    language=[
        "en",
        "fr",
        "es",
        "de",
        "ru",
        "zh",
        "ja",
        "it",
        "pt",
        "nl",
        "ar",
        "hi",
        "ko",
    ],
    library_name="vllm",
    base_model="mistralai/Ministral-3-3B-Base-2512",
)


def _patch_voxtral_mini() -> Any:
    return _patch_hf_calls(
        config=_VOXTRAL_MINI_CONFIG,
        tokenizer_config=None,
        card_data=_VOXTRAL_MINI_CARD_DATA,
        hub_info={
            "author": "mistralai",
            "sha": "deadf00d",
            "tags": ["base_model:finetune:mistralai/Ministral-3-3B-Base-2512"],
        },
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


_OPENEUROLLM_CONFIG: dict[str, Any] = {
    "model_type": "llama",
    "architectures": ["LlamaForCausalLM"],
    "vocab_size": 262400,
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "num_attention_heads": 32,
    "num_key_value_heads": 32,
    "max_position_embeddings": 2048,
    "torch_dtype": "bfloat16",
    "tie_word_embeddings": True,
}

_OPENEUROLLM_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag=None,
    language=[
        "en",
        "de",
        "fr",
        "es",
        "pt",
        "it",
        "nl",
        "pl",
        "sv",
        "no",
        "da",
        "fi",
        "cs",
        "sk",
        "sl",
        "hr",
        "bg",
        "ro",
        "hu",
        "el",
        "lt",
        "lv",
        "et",
        "ga",
        "mt",
        "eu",
        "ca",
        "cy",
        "sq",
        "mk",
        "uk",
        "ru",
        "tr",
        "is",
    ],
    library_name="transformers",
    datasets=[
        "HPLT/HPLT2.0_cleaned",
        "HuggingFaceTB/finemath",
        "bigcode/starcoderdata",
    ],
)


def _patch_openeurollm() -> Any:
    return _patch_hf_calls(
        config=_OPENEUROLLM_CONFIG,
        tokenizer_config=None,  # 404 in real repo
        card_data=_OPENEUROLLM_CARD_DATA,
        hub_info={"author": "openeurollm", "sha": "deadf00d"},
    )


__all__ = [
    "_CLIP_JAPANESE_V2_CARD_DATA",
    "_CLIP_JAPANESE_V2_CONFIG",
    "_EXAONE_PATH_CARD_DATA",
    "_FUJITSU_LLM_CARD_DATA",
    "_GLM45_AIR_REAP_CARD_DATA",
    "_GLM45_AIR_REAP_CONFIG",
    "_LINE_DISTILBERT_CARD_DATA",
    "_LINE_DISTILBERT_CONFIG",
    "_LLASA_3B_CARD_DATA",
    "_LLASA_3B_CONFIG",
    "_MOIRAI_CARD_DATA",
    "_MOIRAI_CONFIG",
    "_OPENEUROLLM_CARD_DATA",
    "_OPENEUROLLM_CONFIG",
    "_TILDEOPEN_30B_64K_CARD_DATA",
    "_TILDEOPEN_30B_64K_CONFIG",
    "_TILDEOPEN_30B_CARD_DATA",
    "_TILDEOPEN_30B_CONFIG",
    "_TILDEOPEN_TOKENIZER_SENTINEL",
    "_VOXTRAL_MINI_CARD_DATA",
    "_VOXTRAL_MINI_CONFIG",
    "_WINDOWSEAT_CARD_DATA",
    "_patch_clip_japanese_v2",
    "_patch_exaone_path",
    "_patch_fujitsu_llm",
    "_patch_glm45_air_reap",
    "_patch_line_distilbert",
    "_patch_llasa_3b",
    "_patch_moirai",
    "_patch_openeurollm",
    "_patch_tildeopen_30b",
    "_patch_tildeopen_30b_64k",
    "_patch_voxtral_mini",
    "_patch_windowseat",
]
