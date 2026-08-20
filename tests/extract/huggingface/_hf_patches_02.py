# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for Hugging Face model metadata tests (part 2 of 10).

See also: conftest.py, which re-exports everything via ``from
._hf_patches_02 import *``. Sibling test modules import helper names
from ``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_01 import _make_card_data, _patch_hf_calls


def _patch_aya_vision() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated - config.json returns 401
        tokenizer_config=None,  # Gated
        card_data={},  # Gated - ModelCard.load() returns error
        hub_info={"author": "CohereLabs"},
        # _detect_license_from_hf_files also returns (None, None) because
        # list_repo_files may succeed but license file downloads are gated.
    )


def _patch_inkubalm() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated - config.json returns 401
        tokenizer_config=None,  # Gated
        card_data={},  # Gated - ModelCard.load() returns error
        hub_info={
            "author": "lelapa",
            # model_info.tags carry the dataset link even when the card is gated.
            "tags": [
                "text-generation",
                "license:cc-by-nc-4.0",
                "dataset:lelapa/Inkuba-Mono",
                "en",
                "sw",
                "zu",
                "xh",
                "ha",
                "yo",
            ],
        },
    )


_NLLB_CONFIG: dict[str, Any] = {
    "model_type": "m2m_100",
    "architectures": ["M2M100ForConditionalGeneration"],
    "d_model": 1024,  # encoder/decoder hidden dim - NOT in _HYPER_KEYS
    "encoder_layers": 12,  # NOT in _HYPER_KEYS (uses num_hidden_layers alias)
    "decoder_layers": 12,  # NOT in _HYPER_KEYS
    "num_hidden_layers": 12,  # present in config alongside encoder/decoder_layers
    "encoder_attention_heads": 16,  # NOT in _HYPER_KEYS
    "decoder_attention_heads": 16,  # NOT in _HYPER_KEYS
    "max_position_embeddings": 1024,
    "vocab_size": 256206,
    "torch_dtype": "float32",
    "is_encoder_decoder": True,
}

_NLLB_TOKENIZER_CONFIG: dict[str, Any] = {
    "tokenizer_class": "NllbTokenizer",
    "model_max_length": 1024,  # Real limit - NOT the unlimited sentinel
}


def _patch_nllb() -> Any:
    return _patch_hf_calls(
        config=_NLLB_CONFIG,
        tokenizer_config=_NLLB_TOKENIZER_CONFIG,
        card_data={},  # No model card - ModelCard.load() fails
        hub_info={"author": "facebook"},
    )


_SONOISA_CONFIG: dict[str, Any] = {
    "architectures": ["BertForMaskedLM"],
    "vocab_size": 32000,
    "num_hidden_layers": 12,
    "num_attention_heads": 12,
    "hidden_size": 768,
}

_SONOISA_CARD_DATA = _make_card_data(
    license="cc-by-sa-4.0",
    pipeline_tag="feature-extraction",
    tags=["sentence-transformers", "sentence-bert", "sentence-similarity"],
    language="ja",  # scalar string - triggers the fix
)


def _patch_sonoisa() -> Any:
    return _patch_hf_calls(
        config=_SONOISA_CONFIG,
        card_data=_SONOISA_CARD_DATA,
        hub_info={"author": "sonoisa"},
    )


_WAV2VEC2_JP_CONFIG: dict[str, Any] = {
    "model_type": "wav2vec2",
    "architectures": ["Wav2Vec2ForCTC"],
    "vocab_size": 2341,
    "num_hidden_layers": 24,
    "hidden_size": 1024,
}

_WAV2VEC2_JP_MODEL_INDEX = [
    {
        "name": "XLSR Wav2Vec2 Japanese by Jonatas Grosman",
        "results": [
            {
                "task": {"type": "automatic-speech-recognition"},
                "dataset": {"name": "Common Voice ja", "type": "common_voice"},
                "metrics": [{"type": "wer", "value": 81.8, "name": "Test WER"}],
            }
        ],
    }
]

_WAV2VEC2_JP_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="automatic-speech-recognition",
    tags=["audio", "speech", "xlsr-fine-tuning-week"],
    language="ja",  # scalar string
    datasets=["common_voice"],
    model_index=_WAV2VEC2_JP_MODEL_INDEX,
)


def _patch_wav2vec2_jp() -> Any:
    return _patch_hf_calls(
        config=_WAV2VEC2_JP_CONFIG,
        tokenizer_config=None,
        card_data=_WAV2VEC2_JP_CARD_DATA,
        hub_info={
            "author": "jonatasgrosman",
            "tags": ["doi:10.57967/hf/3568"],
        },
    )


_WANGCHANX_LEGAL_CONFIG: dict[str, Any] = {
    "model_type": "xlm-roberta",
    "architectures": ["XLMRobertaModel"],
    "vocab_size": 250002,
    "num_hidden_layers": 24,
    "hidden_size": 1024,
}

_WANGCHANX_LEGAL_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="sentence-similarity",
    tags=["legal", "RAG"],
    language=["th"],
    datasets=["airesearch/WangchanX-Legal-ThaiCCL-RAG"],
    base_model=["BAAI/bge-m3"],
)


def _patch_wangchanx_legal() -> Any:
    return _patch_hf_calls(
        config=_WANGCHANX_LEGAL_CONFIG,
        card_data=_WANGCHANX_LEGAL_CARD_DATA,
        hub_info={
            "author": "airesearch",
            "tags": ["base_model:BAAI/bge-m3", "base_model:finetune:BAAI/bge-m3"],
        },
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


_RURI_CONFIG: dict[str, Any] = {
    "model_type": "modernbert",
    "architectures": ["ModernBertModel"],
    "vocab_size": 102400,
    "num_hidden_layers": 25,
    "hidden_size": 768,
}

_RURI_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="sentence-similarity",
    tags=["sentence-similarity", "feature-extraction"],
    language=["ja"],
    datasets=["cl-nagoya/ruri-v3-dataset-ft"],
    base_model="cl-nagoya/ruri-v3-pt-310m",
)


def _patch_ruri() -> Any:
    return _patch_hf_calls(
        config=_RURI_CONFIG,
        card_data=_RURI_CARD_DATA,
        hub_info={
            "author": "cl-nagoya",
            "tags": [
                "arxiv:2409.07737",
                "base_model:cl-nagoya/ruri-v3-pt-310m",
                "base_model:finetune:cl-nagoya/ruri-v3-pt-310m",
            ],
        },
    )


_NOMIC_GGUF_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="sentence-similarity",
    tags=["feature-extraction", "sentence-similarity"],
    language=["en"],
    base_model="nomic-ai/nomic-embed-text-v1.5",
)


def _patch_nomic_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_NOMIC_GGUF_CARD_DATA,
        hub_info={
            "author": "nomic-ai",
            "tags": [
                "base_model:nomic-ai/nomic-embed-text-v1.5",
                "base_model:quantized:nomic-ai/nomic-embed-text-v1.5",
            ],
        },
    )


_VNTL_CARD_DATA = _make_card_data(
    license="llama3",
    pipeline_tag="translation",
    language=["ja", "en"],
    datasets=["lmg-anon/VNTL-v5-1k"],
    base_model="rinna/llama-3-youko-8b",
)


def _patch_vntl() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_VNTL_CARD_DATA,
        hub_info={
            "author": "lmg-anon",
            "tags": [
                "base_model:rinna/llama-3-youko-8b",
                "base_model:quantized:rinna/llama-3-youko-8b",
            ],
        },
    )


_SUGOI_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="translation",
    tags=["translation", "gguf"],
    language=["ja", "en"],
    base_model=["sugoitoolkit/Sugoi-14B-Ultra-HF"],
)


def _patch_sugoi() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_SUGOI_CARD_DATA,
        hub_info={
            "author": "sugoitoolkit",
            "tags": [
                "base_model:sugoitoolkit/Sugoi-14B-Ultra-HF",
                "base_model:quantized:sugoitoolkit/Sugoi-14B-Ultra-HF",
            ],
        },
    )


_TALKIE_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag=None,
    language=["en"],
    base_model=["talkie-lm/talkie-1930-13b-base"],
)


def _patch_talkie() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_TALKIE_CARD_DATA,
        hub_info={
            "author": "talkie-lm",
            "tags": [
                "base_model:talkie-lm/talkie-1930-13b-base",
                "base_model:finetune:talkie-lm/talkie-1930-13b-base",
            ],
        },
    )


def _patch_depth_pro() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "depth_pro",
            "architectures": ["DepthProForDepthEstimation"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apple-amlr",
            pipeline_tag="depth-estimation",
            tags=["vision", "depth-estimation"],
        ),
        hub_info={"author": "apple"},
    )


def _patch_marigold() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="depth-estimation",
            tags=["depth estimation", "image analysis", "computer vision", "zero-shot"],
            language=["en"],
            library_name="diffusers",
        ),
        hub_info={"author": "prs-eth"},
    )


def _patch_vitpose() -> Any:
    return _patch_hf_calls(
        config={"model_type": "vitpose", "architectures": ["VitPoseForPoseEstimation"]},
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="keypoint-detection",
            tags=[],
        ),
        hub_info={"author": "usyd-community"},
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


__all__ = [
    "_CHINDA_CARD_DATA",
    "_CHINDA_CONFIG",
    "_CHINDA_GGUF_CARD_DATA",
    "_NLLB_CONFIG",
    "_NLLB_TOKENIZER_CONFIG",
    "_NOMIC_GGUF_CARD_DATA",
    "_RURI_CARD_DATA",
    "_RURI_CONFIG",
    "_SONOISA_CARD_DATA",
    "_SONOISA_CONFIG",
    "_SUGOI_CARD_DATA",
    "_TALKIE_CARD_DATA",
    "_VNTL_CARD_DATA",
    "_WANGCHANX_LEGAL_CARD_DATA",
    "_WANGCHANX_LEGAL_CONFIG",
    "_WAV2VEC2_JP_CARD_DATA",
    "_WAV2VEC2_JP_CONFIG",
    "_WAV2VEC2_JP_MODEL_INDEX",
    "_patch_aya_vision",
    "_patch_chinda",
    "_patch_chinda_gguf",
    "_patch_depth_pro",
    "_patch_donut",
    "_patch_inkubalm",
    "_patch_jina_v4",
    "_patch_layoutlm",
    "_patch_llava_video",
    "_patch_marigold",
    "_patch_nllb",
    "_patch_nomic_gguf",
    "_patch_ruri",
    "_patch_sonoisa",
    "_patch_sugoi",
    "_patch_talkie",
    "_patch_vitpose",
    "_patch_vntl",
    "_patch_wangchanx_legal",
    "_patch_wav2vec2_jp",
]
