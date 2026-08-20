# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for Hugging Face model metadata tests (part 6 of 10).

See also: conftest.py, which re-exports everything via ``from
._hf_patches_06 import *``. Sibling test modules import helper names
from ``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_01 import _make_card_data, _patch_hf_calls


def _patch_deberta_human_value() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "deberta_arg_classifier",
            "architectures": ["DebertaArgClassifier"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="openrail++",
            pipeline_tag="text-classification",
            tags=["custom_code", "human-values", "deberta"],
            language=["en"],
        ),
        hub_info={"author": "tum-nlp"},
    )


def _patch_aspect_finnlp_th() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "camembert",
            "architectures": ["CamembertForSequenceClassification"],
            "vocab_size": 25000,
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag="text-classification",
            tags=["generated_from_trainer"],
            language=["th"],
            base_model=["airesearch/wangchanberta-base-att-spm-uncased"],
        ),
        hub_info={
            "author": "nlp-chula",
            "tags": [
                "base_model:airesearch/wangchanberta-base-att-spm-uncased",
                "base_model:finetune:airesearch/wangchanberta-base-att-spm-uncased",
            ],
        },
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


def _patch_protonx_legal() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "t5",
            "architectures": ["T5ForConditionalGeneration"],
            "vocab_size": 32128,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="text2text-generation",
            tags=["text-to-text", "t5"],
            language=["vi"],
            base_model=["vit5-base"],
        ),
        hub_info={
            "author": "protonx-models",
            "tags": [
                "base_model:vit5-base",
                "base_model:finetune:vit5-base",
            ],
        },
    )


def _patch_legal_embed_ita() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "qwen3",
            "architectures": ["Qwen3Model"],
            "vocab_size": 151936,
            "num_hidden_layers": 28,
            "hidden_size": 1024,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="cc-by-nc-4.0",
            pipeline_tag="sentence-similarity",
            tags=["qwen3", "feature-extraction", "legal"],
            language=["it"],
            base_model=["Qwen/Qwen3-Embedding-0.6B"],
        ),
        hub_info={
            "author": "ReDiX",
            "tags": [
                "base_model:Qwen/Qwen3-Embedding-0.6B",
                "base_model:finetune:Qwen/Qwen3-Embedding-0.6B",
            ],
        },
    )


def _patch_arabic_legal_ocr() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "gemma3",
            "architectures": ["Gemma3ForConditionalGeneration"],
            "vocab_size": 262208,
            "num_hidden_layers": 34,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="gemma",
            pipeline_tag="image-text-to-text",
            tags=["ocr", "arabic", "vision", "lora"],
            language=["ar", "en"],
            base_model=["google/gemma-3-4b-it"],
        ),
        hub_info={
            "author": "bakrianoo",
            "tags": [
                "base_model:google/gemma-3-4b-it",
                "base_model:finetune:google/gemma-3-4b-it",
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


def _patch_boba_food_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="image-text-to-text",
            tags=["food", "nutrition", "vision", "on-device"],
            language=["en"],
            base_model=["Qwen/Qwen3.5-0.8B"],
        ),
        hub_info={
            "author": "Doses-AI",
            "tags": [
                "base_model:Qwen/Qwen3.5-0.8B",
                "base_model:finetune:Qwen/Qwen3.5-0.8B",
            ],
        },
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


_KANANA_15V_CONFIG: dict[str, Any] = {
    "model_type": "kanana-1.5-v",
    "architectures": ["KananaVForConditionalGeneration"],
    "vocab_size": 102400,
    "hidden_size": 3072,
    "num_hidden_layers": 28,
    "num_attention_heads": 16,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_KANANA_15V_CARD_DATA = _make_card_data(
    license="kanana-license",
    pipeline_tag="image-text-to-text",
    language=["ko", "en"],
    library_name="transformers",
)


def _patch_kanana_15v() -> Any:
    return _patch_hf_calls(
        config=_KANANA_15V_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_KANANA_15V_CARD_DATA,
        hub_info={"author": "kakaobank", "sha": "deadf00d"},
    )


_EXAONE45_33B_CONFIG: dict[str, Any] = {
    "model_type": "exaone4_5",
    "architectures": ["Exaone4_5_ForConditionalGeneration"],
    "vocab_size": 102400,
    "hidden_size": 7168,
    "num_hidden_layers": 64,
    "num_attention_heads": 56,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_EXAONE45_33B_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    language=["ko", "en", "zh", "ja", "es", "fr"],
    library_name="transformers",
)


def _patch_exaone45_33b() -> Any:
    return _patch_hf_calls(
        config=_EXAONE45_33B_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_EXAONE45_33B_CARD_DATA,
        hub_info={"author": "LGAI-EXAONE", "sha": "deadf00d"},
    )


_EXAONE45_33B_AWQ_CONFIG: dict[str, Any] = {
    "model_type": "exaone4_5",
    "architectures": ["Exaone4_5_ForConditionalGeneration"],
    "vocab_size": 102400,
    "hidden_size": 7168,
    "num_hidden_layers": 64,
    "num_attention_heads": 56,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "float16",
    "quantization_config": {"quant_type": "awq", "bits": 4},
}

_EXAONE45_33B_AWQ_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    language=["ko", "en"],
    library_name="transformers",
    base_model="LGAI-EXAONE/EXAONE-4.5-33B",
)


def _patch_exaone45_33b_awq() -> Any:
    return _patch_hf_calls(
        config=_EXAONE45_33B_AWQ_CONFIG,
        card_data=_EXAONE45_33B_AWQ_CARD_DATA,
        hub_info={
            "author": "LGAI-EXAONE",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:LGAI-EXAONE/EXAONE-4.5-33B"],
        },
    )


_EXAONE45_33B_FP8_CONFIG: dict[str, Any] = {
    "model_type": "exaone4_5",
    "architectures": ["Exaone4_5_ForConditionalGeneration"],
    "vocab_size": 102400,
    "hidden_size": 7168,
    "num_hidden_layers": 64,
    "num_attention_heads": 56,
    "max_position_embeddings": 131072,
    "torch_dtype": "float8_e4m3fn",
}

_EXAONE45_33B_FP8_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    language=["ko", "en"],
    library_name="transformers",
    base_model="LGAI-EXAONE/EXAONE-4.5-33B",
)


def _patch_exaone45_33b_fp8() -> Any:
    return _patch_hf_calls(
        config=_EXAONE45_33B_FP8_CONFIG,
        card_data=_EXAONE45_33B_FP8_CARD_DATA,
        hub_info={
            "author": "LGAI-EXAONE",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:LGAI-EXAONE/EXAONE-4.5-33B"],
        },
    )


_EXAONE45_33B_GGUF_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    language=["ko", "en"],
    library_name="gguf",
    base_model="LGAI-EXAONE/EXAONE-4.5-33B",
)


def _patch_exaone45_33b_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_EXAONE45_33B_GGUF_CARD_DATA,
        hub_info={
            "author": "LGAI-EXAONE",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:LGAI-EXAONE/EXAONE-4.5-33B"],
        },
    )


__all__ = [
    "_EXAONE45_33B_AWQ_CARD_DATA",
    "_EXAONE45_33B_AWQ_CONFIG",
    "_EXAONE45_33B_CARD_DATA",
    "_EXAONE45_33B_CONFIG",
    "_EXAONE45_33B_FP8_CARD_DATA",
    "_EXAONE45_33B_FP8_CONFIG",
    "_EXAONE45_33B_GGUF_CARD_DATA",
    "_KANANA_15V_CARD_DATA",
    "_KANANA_15V_CONFIG",
    "_QWEN35_27B_CARD_DATA",
    "_QWEN35_27B_CONFIG",
    "_QWEN3_235B_CARD_DATA",
    "_QWEN3_235B_CONFIG",
    "_QWEN3_235B_GENERATION_CONFIG",
    "_patch_arabic_legal_ocr",
    "_patch_aspect_finnlp_th",
    "_patch_boba_food_gguf",
    "_patch_darwin_kr_legal",
    "_patch_deberta_human_value",
    "_patch_ernie_image_turbo",
    "_patch_exaone45_33b",
    "_patch_exaone45_33b_awq",
    "_patch_exaone45_33b_fp8",
    "_patch_exaone45_33b_gguf",
    "_patch_kanana_15v",
    "_patch_legal_embed_ita",
    "_patch_protonx_legal",
    "_patch_qwen35_27b",
    "_patch_qwen3_235b",
    "_patch_qwen3_swallow",
    "_patch_sealion_27b_it",
]
