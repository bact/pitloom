# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for vision-language multimodal models: image/video text-to-text,
visual question answering, visual document retrieval, and document question
answering.

See also: _hf_patches_base.py, _hf_patches_text_generation_pretrained.py,
_hf_patches_text_generation_instruct.py,
_hf_patches_text_generation_regional.py, _hf_patches_gated_metadata.py,
_hf_patches_gated_access.py, _hf_patches_speech_audio.py,
_hf_patches_omni_modal.py, _hf_patches_embeddings.py, _hf_patches_vision.py,
_hf_patches_structured_text.py, _hf_patches_generative_3d.py. Sibling test
modules import these names directly from the matching topic module.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)

_KIMI_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    tags=["compressed-tensors"],
    language=None,
    library_name="transformers",
)


_KIMI_CONFIG: dict[str, Any] = {
    "model_type": "kimi_k25",
    "architectures": ["KimiK25ForConditionalGeneration"],
    "hidden_size": 7168,
    "num_hidden_layers": 61,
    "torch_dtype": "bfloat16",
}


def _patch_kimi() -> Any:
    return _patch_hf_calls(
        config=_KIMI_CONFIG,
        card_data=_KIMI_CARD_DATA,
        hub_info={"author": "moonshotai"},
    )


_SEALION_CARD_DATA = _make_card_data(
    license="gemma",
    pipeline_tag="image-text-to-text",
    tags=None,
    language=["en", "zh", "vi", "id", "th", "fil", "ta", "ms", "my"],
    library_name=None,
)


def _patch_sealion_gguf() -> Any:
    return _patch_hf_calls(
        config=None,  # No config.json in GGUF-only repo
        tokenizer_config=None,
        card_data=_SEALION_CARD_DATA,
        hub_info={"author": "aisingapore"},
    )


def _patch_jina_v4() -> Any:
    return _patch_hf_calls(
        config={"architectures": ["JinaEmbeddingsV4Model"], "num_hidden_layers": 36},
        tokenizer_config={
            "tokenizer_class": "Qwen2Tokenizer",
            "model_max_length": 131072,
        },
        card_data=_make_card_data(
            license=None,
            pipeline_tag="visual-document-retrieval",
            tags=[
                "feature-extraction",
                "sentence-similarity",
                "colpali",
                "multimodal-embedding",
            ],
            language=["multilingual"],
        ),
        hub_info={"author": "jinaai"},
    )


def _patch_llava_video() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "llava_next_video",
            "architectures": ["LlavaNextVideoForConditionalGeneration"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="llama2",
            pipeline_tag="video-text-to-text",
            tags=["image-text-to-text"],  # also appears as tag
            language=["en"],
            datasets=["lmms-lab/VideoChatGPT"],
        ),
        hub_info={"author": "llava-hf"},
    )


def _patch_donut() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "vision-encoder-decoder",
            "architectures": ["VisionEncoderDecoderModel"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="document-question-answering",
            tags=["donut", "image-to-text", "vision"],
        ),
        hub_info={"author": "naver-clova-ix"},
    )


def _patch_layoutlm() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "layoutlm",
            "architectures": ["LayoutLMForQuestionAnswering"],
            "vocab_size": 50265,
            "num_hidden_layers": 12,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="document-question-answering",
            tags=["layoutlm", "document-question-answering", "pdf"],
            language="en",  # scalar string
        ),
        hub_info={"author": "impira"},
    )


def _patch_sealion_vl() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "gemma3",
            "architectures": ["Gemma3ForConditionalGeneration"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="gemma",
            pipeline_tag="image-text-to-text",
            tags=["conversational"],
            language=["en", "zh", "vi", "id", "th", "fil", "ta", "ms", "my"],
            base_model=["google/gemma-3-4b-it"],
        ),
        hub_info={
            "author": "aisingapore",
            "tags": [
                "base_model:google/gemma-3-4b-it",
                "base_model:finetune:google/gemma-3-4b-it",
            ],
        },
    )


def _patch_vilt_vqa() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "vilt",
            "architectures": ["ViltForVisualQuestionAnswering"],
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="visual-question-answering",
            tags=["vilt", "visual-question-answering"],
            base_model=["dandelin/vilt-b32"],
        ),
        hub_info={
            "author": "dandelin",
            "tags": [
                "arxiv:2102.03334",
                "base_model:dandelin/vilt-b32",
                "base_model:finetune:dandelin/vilt-b32",
            ],
        },
    )


def _patch_deplot() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "pix2struct",
            "architectures": ["Pix2StructForConditionalGeneration"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="visual-question-answering",
            tags=["pix2struct", "image-text-to-text"],
            language=["en", "fr", "de", "es", "pt"],
        ),
        hub_info={
            "author": "google",
            "tags": ["arxiv:2212.10505"],
        },
    )


def _patch_blip_vqa() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "blip",
            "architectures": ["BlipForQuestionAnswering"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="bsd-3-clause",
            pipeline_tag="visual-question-answering",
            tags=["blip"],
            language=["en"],
        ),
        hub_info={
            "author": "Salesforce",
            "tags": ["arxiv:2201.12086"],
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


_EXAONE45_33B_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    language=["ko", "en", "zh", "ja", "es", "fr"],
    library_name="transformers",
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


_EXAONE45_33B_FP8_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    language=["ko", "en"],
    library_name="transformers",
    base_model="LGAI-EXAONE/EXAONE-4.5-33B",
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


_TIMELENS_CARD_DATA = _make_card_data(
    license="other",
    license_name="bsd-3-clause",
    pipeline_tag="video-text-to-text",
    language=["en"],
    library_name="transformers",
    datasets=["TencentARC/TimeLens-100K", "TencentARC/TimeLens-Bench"],
    base_model="Qwen/Qwen3-VL-8B-Instruct",
)


_TIMELENS_CONFIG: dict[str, Any] = {
    "model_type": "qwen3_vl",
    "architectures": ["Qwen3VLForConditionalGeneration"],
    "dtype": "bfloat16",  # non-standard: uses dtype, not torch_dtype
    # All LM numeric fields are nested inside text_config -- NOT at top level
    "text_config": {
        "vocab_size": 151936,
        "hidden_size": 4096,
        "num_hidden_layers": 36,
        "num_attention_heads": 32,
        "num_key_value_heads": 8,
        "head_dim": 128,
        "intermediate_size": 12288,
        "max_position_embeddings": 262144,
        "rope_theta": 5000000,
    },
    "vision_config": {
        "hidden_size": 1152,
        "depth": 27,
        "num_heads": 16,
    },
}


def _patch_timelens() -> Any:
    return _patch_hf_calls(
        config=_TIMELENS_CONFIG,
        tokenizer_config=None,
        card_data=_TIMELENS_CARD_DATA,
        hub_info={
            "author": "TencentARC",
            "sha": "deadf00d",
            "tags": [
                "arxiv:2512.14698",
                "base_model:Qwen/Qwen3-VL-8B-Instruct",
                "base_model:finetune:Qwen/Qwen3-VL-8B-Instruct",
            ],
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
    "_KIMI_CARD_DATA",
    "_KIMI_CONFIG",
    "_SEALION_CARD_DATA",
    "_TIMELENS_CARD_DATA",
    "_TIMELENS_CONFIG",
    "_patch_arabic_legal_ocr",
    "_patch_blip_vqa",
    "_patch_boba_food_gguf",
    "_patch_deplot",
    "_patch_donut",
    "_patch_exaone45_33b",
    "_patch_exaone45_33b_awq",
    "_patch_exaone45_33b_fp8",
    "_patch_exaone45_33b_gguf",
    "_patch_jina_v4",
    "_patch_kanana_15v",
    "_patch_kimi",
    "_patch_layoutlm",
    "_patch_llava_video",
    "_patch_sealion_gguf",
    "_patch_sealion_vl",
    "_patch_timelens",
    "_patch_vilt_vqa",
]
