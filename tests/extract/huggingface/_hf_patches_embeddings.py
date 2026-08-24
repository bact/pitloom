# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for representation-learning models: sentence similarity, feature
extraction, reranking, and fill-mask encoders.

See also: _hf_patches_base.py, _hf_patches_text_generation_pretrained.py,
_hf_patches_text_generation_instruct.py,
_hf_patches_text_generation_regional.py, _hf_patches_gated_metadata.py,
_hf_patches_speech_audio.py, _hf_patches_multimodal.py,
_hf_patches_omni_modal.py, _hf_patches_vision.py,
_hf_patches_structured_text.py, _hf_patches_generative_3d.py. Sibling test
modules import helper names from ``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
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


_WANGCHANX_LEGAL_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="sentence-similarity",
    tags=["legal", "RAG"],
    language=["th"],
    datasets=["airesearch/WangchanX-Legal-ThaiCCL-RAG"],
    base_model=["BAAI/bge-m3"],
)


_WANGCHANX_LEGAL_CONFIG: dict[str, Any] = {
    "model_type": "xlm-roberta",
    "architectures": ["XLMRobertaModel"],
    "vocab_size": 250002,
    "num_hidden_layers": 24,
    "hidden_size": 1024,
}


def _patch_wangchanx_legal() -> Any:
    return _patch_hf_calls(
        config=_WANGCHANX_LEGAL_CONFIG,
        card_data=_WANGCHANX_LEGAL_CARD_DATA,
        hub_info={
            "author": "airesearch",
            "tags": ["base_model:BAAI/bge-m3", "base_model:finetune:BAAI/bge-m3"],
        },
    )


_RURI_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="sentence-similarity",
    tags=["sentence-similarity", "feature-extraction"],
    language=["ja"],
    datasets=["cl-nagoya/ruri-v3-dataset-ft"],
    base_model="cl-nagoya/ruri-v3-pt-310m",
)


_RURI_CONFIG: dict[str, Any] = {
    "model_type": "modernbert",
    "architectures": ["ModernBertModel"],
    "vocab_size": 102400,
    "num_hidden_layers": 25,
    "hidden_size": 768,
}


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


def _patch_dinov2() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "dinov2",
            "architectures": ["Dinov2Model"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="image-feature-extraction",
            tags=["dino", "vision"],
        ),
        hub_info={"author": "facebook"},
    )


def _patch_rad_dino() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "dinov2",
            "architectures": ["Dinov2Model"],
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag="image-feature-extraction",
            tags=[],
        ),
        hub_info={"author": "microsoft"},
    )


def _patch_uni2() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated
        tokenizer_config=None,
        card_data=_make_card_data(
            license="cc-by-nc-nd-4.0",
            pipeline_tag="image-feature-extraction",
            tags=["histology", "pathology", "vision", "self-supervised", "vit"],
            language=["en"],
        ),
        hub_info={"author": "MahmoodLab"},
    )


def _patch_timm_convnext() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="image-feature-extraction",
            tags=["timm", "transformers"],
            library_name="timm",
        ),
        hub_info={"author": "timm"},
    )


def _patch_granite_embed() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "modernbert",
            "architectures": ["ModernBertModel"],
            "vocab_size": 180000,
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="feature-extraction",
            tags=["granite", "embeddings", "multilingual", "mteb"],
            language=["multilingual"],
            library_name="sentence-transformers",
        ),
        hub_info={"author": "ibm-granite"},
    )


def _patch_xlm_roberta_base() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "xlm-roberta",
            "architectures": ["XLMRobertaForMaskedLM"],
            "vocab_size": 250002,
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="fill-mask",
            tags=[],
            language=[
                "af",
                "am",
                "ar",
                "en",
                "fr",
                "de",
                "hi",
                "ja",
                "ko",
                "pt",
                "ru",
                "es",
                "sw",
                "th",
                "tr",
                "vi",
                "yo",
                "zh",
            ],
        ),
        hub_info={"author": "FacebookAI"},
    )


def _patch_distilbert_multilingual() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "distilbert",
            "architectures": ["DistilBertForMaskedLM"],
            "vocab_size": 119547,
            "num_hidden_layers": 6,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="fill-mask",
            tags=[],
            language=["multilingual"],
        ),
        hub_info={"author": "distilbert"},
    )


def _patch_gabert() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "bert",
            "architectures": ["BertForMaskedLM"],
            "vocab_size": 30000,
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag="fill-mask",
            tags=["bert"],
            language=["ga"],
        ),
        hub_info={"author": "DCU-NLP"},
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


_LINE_DISTILBERT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="fill-mask",
    language=["ja"],
    library_name="transformers",
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


_GTE_RERANKER_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-ranking",
    language=["multilingual"],
    library_name="sentence-transformers",
)


_GTE_RERANKER_CONFIG: dict[str, Any] = {
    "model_type": "new",
    "architectures": ["NewForSequenceClassification"],
    "vocab_size": 250002,
    "hidden_size": 768,
    "num_hidden_layers": 12,
    "torch_dtype": "bfloat16",
}


def _patch_gte_reranker() -> Any:
    return _patch_hf_calls(
        config=_GTE_RERANKER_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_GTE_RERANKER_CARD_DATA,
        hub_info={"author": "Alibaba-NLP", "sha": "deadf00d"},
    )


_GTE_MODERNBERT_CONFIG: dict[str, Any] = {
    "model_type": "modernbert",
    "architectures": ["ModernBertModel"],
    "vocab_size": 30528,
    "hidden_size": 768,
    "num_hidden_layers": 22,
    "num_attention_heads": 12,
    "max_position_embeddings": 8192,
    "torch_dtype": "bfloat16",
}


_GTE_MODERNBERT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="sentence-similarity",
    language=["multilingual"],
    library_name="transformers",
)


def _patch_gte_modernbert() -> Any:
    return _patch_hf_calls(
        config=_GTE_MODERNBERT_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_GTE_MODERNBERT_CARD_DATA,
        hub_info={"author": "Alibaba-NLP", "sha": "deadf00d"},
    )


_CODEBERTA_CARD_DATA = _make_card_data(
    license=None,  # no license field in card
    pipeline_tag="fill-mask",
    language=["code"],  # non-ISO identifier for programming languages
    library_name="transformers",
)


_CODEBERTA_CONFIG: dict[str, Any] = {
    "model_type": "roberta",
    "architectures": ["RobertaForMaskedLM"],
    "vocab_size": 50265,
    "hidden_size": 512,
    "num_hidden_layers": 6,
    "num_attention_heads": 8,
    "max_position_embeddings": 514,
}


def _patch_codeberta() -> Any:
    return _patch_hf_calls(
        config=_CODEBERTA_CONFIG,
        tokenizer_config={"tokenizer_class": "RobertaTokenizerFast"},
        card_data=_CODEBERTA_CARD_DATA,
        hub_info={"author": "huggingface", "sha": "deadf00d"},
    )


_CROSS_ENCODER_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-ranking",
    language=["en"],
    library_name="sentence-transformers",
    datasets=["sentence-transformers/msmarco"],
    base_model="cross-encoder/ms-marco-MiniLM-L12-v2",
)


_CROSS_ENCODER_CONFIG: dict[str, Any] = {
    "model_type": "bert",
    "architectures": ["BertForSequenceClassification"],
    "vocab_size": 30522,
    "hidden_size": 384,
    "num_hidden_layers": 6,
    "num_attention_heads": 12,
    "intermediate_size": 1536,
    "max_position_embeddings": 512,
    # Sentence-transformers-specific config key
    "sbert_ce_default_activation_function": "torch.nn.modules.linear.Identity",
}


def _patch_cross_encoder() -> Any:
    return _patch_hf_calls(
        config=_CROSS_ENCODER_CONFIG,
        tokenizer_config={"tokenizer_class": "BertTokenizerFast"},
        card_data=_CROSS_ENCODER_CARD_DATA,
        hub_info={
            "author": "cross-encoder",
            "sha": "deadf00d",
            "tags": [
                "base_model:quantized:cross-encoder/ms-marco-MiniLM-L12-v2",
                "dataset:sentence-transformers/msmarco",
            ],
        },
    )


__all__ = [
    "_CLIP_JAPANESE_V2_CARD_DATA",
    "_CLIP_JAPANESE_V2_CONFIG",
    "_CODEBERTA_CARD_DATA",
    "_CODEBERTA_CONFIG",
    "_CROSS_ENCODER_CARD_DATA",
    "_CROSS_ENCODER_CONFIG",
    "_GTE_MODERNBERT_CARD_DATA",
    "_GTE_MODERNBERT_CONFIG",
    "_GTE_RERANKER_CARD_DATA",
    "_GTE_RERANKER_CONFIG",
    "_LINE_DISTILBERT_CARD_DATA",
    "_LINE_DISTILBERT_CONFIG",
    "_NOMIC_GGUF_CARD_DATA",
    "_RURI_CARD_DATA",
    "_RURI_CONFIG",
    "_SONOISA_CARD_DATA",
    "_SONOISA_CONFIG",
    "_WANGCHANX_LEGAL_CARD_DATA",
    "_WANGCHANX_LEGAL_CONFIG",
    "_patch_clip_japanese_v2",
    "_patch_codeberta",
    "_patch_cross_encoder",
    "_patch_dinov2",
    "_patch_distilbert_multilingual",
    "_patch_gabert",
    "_patch_granite_embed",
    "_patch_gte_modernbert",
    "_patch_gte_reranker",
    "_patch_legal_embed_ita",
    "_patch_line_distilbert",
    "_patch_nomic_gguf",
    "_patch_rad_dino",
    "_patch_ruri",
    "_patch_sonoisa",
    "_patch_timm_convnext",
    "_patch_uni2",
    "_patch_wangchanx_legal",
    "_patch_xlm_roberta_base",
]
