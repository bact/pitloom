# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for Hugging Face model metadata tests (part 10 of 10).

See also: conftest.py, which re-exports everything via ``from
._hf_patches_10 import *``. Sibling test modules import helper names
from ``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_01 import _make_card_data, _patch_hf_calls

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


_CODEBERTA_CONFIG: dict[str, Any] = {
    "model_type": "roberta",
    "architectures": ["RobertaForMaskedLM"],
    "vocab_size": 50265,
    "hidden_size": 512,
    "num_hidden_layers": 6,
    "num_attention_heads": 8,
    "max_position_embeddings": 514,
}

_CODEBERTA_CARD_DATA = _make_card_data(
    license=None,  # no license field in card
    pipeline_tag="fill-mask",
    language=["code"],  # non-ISO identifier for programming languages
    library_name="transformers",
)


def _patch_codeberta() -> Any:
    return _patch_hf_calls(
        config=_CODEBERTA_CONFIG,
        tokenizer_config={"tokenizer_class": "RobertaTokenizerFast"},
        card_data=_CODEBERTA_CARD_DATA,
        hub_info={"author": "huggingface", "sha": "deadf00d"},
    )


_TRADEPULSE_CONFIG: dict[str, Any] = {
    "model_type": "bert",
    "architectures": ["BertForSequenceClassification"],
    "vocab_size": 30522,
    "hidden_size": 768,
    "num_hidden_layers": 12,
    "num_attention_heads": 12,
    "max_position_embeddings": 512,
    "problem_type": "single_label_classification",  # non-standard (fine-tune config)
}

_TRADEPULSE_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-classification",
    language=["en"],
    library_name="transformers",
    base_model="ProsusAI/finbert",
)


def _patch_tradepulse() -> Any:
    return _patch_hf_calls(
        config=_TRADEPULSE_CONFIG,
        tokenizer_config={"tokenizer_class": "BertTokenizer"},
        card_data=_TRADEPULSE_CARD_DATA,
        hub_info={
            "author": "Bencode92",
            "sha": "deadf00d",
            "tags": ["base_model:finetune:ProsusAI/finbert"],
        },
    )


_HRNETPOSE_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="keypoint-detection",
    language=None,
    library_name="pytorch",
)


def _patch_hrnetpose() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_HRNETPOSE_CARD_DATA,
        hub_info={"author": "qualcomm", "sha": "deadf00d"},
    )


_RTDETR_COCO_O365_CONFIG: dict[str, Any] = {
    "model_type": "rt_detr",
    "architectures": ["RTDetrForObjectDetection"],
    "torch_dtype": "float32",
    # Detection-specific keys -- none in _HYPER_KEYS
    "d_model": 256,
    "decoder_attention_heads": 8,
    "encoder_attention_heads": 8,
    "decoder_layers": 6,
    "encoder_layers": 1,
    "num_queries": 300,
    "is_encoder_decoder": True,
}

_RTDETR_COCO_O365_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="object-detection",
    language=["en"],
    library_name="transformers",
    datasets=["coco"],
)


def _patch_rtdetr_coco_o365() -> Any:
    return _patch_hf_calls(
        config=_RTDETR_COCO_O365_CONFIG,
        tokenizer_config=None,
        card_data=_RTDETR_COCO_O365_CARD_DATA,
        hub_info={
            "author": "PekingU",
            "sha": "deadf00d",
            "tags": ["arxiv:2304.08069", "dataset:coco"],
        },
    )


_RTDETR_COCO_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="object-detection",
    language=["en"],
    library_name="transformers",
    datasets=["coco"],
)


def _patch_rtdetr_coco() -> Any:
    return _patch_hf_calls(
        config=_RTDETR_COCO_O365_CONFIG,  # same config schema
        tokenizer_config=None,
        card_data=_RTDETR_COCO_CARD_DATA,
        hub_info={
            "author": "PekingU",
            "sha": "deadf00d",
            "tags": ["arxiv:2304.08069", "dataset:coco"],
        },
    )


_SAP_RPT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="tabular-classification",
    language=None,
    library_name="sap-rpt-1-oss",
    datasets=["mlfoundations/t4-full"],
)


def _patch_sap_rpt() -> Any:
    return _patch_hf_calls(
        config=None,  # 401 gated
        tokenizer_config=None,
        card_data=_SAP_RPT_CARD_DATA,
        hub_info={
            "author": "SAP",
            "sha": "deadf00d",
            "tags": ["arxiv:2506.10707", "dataset:mlfoundations/t4-full"],
        },
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

_TIMELENS_CARD_DATA = _make_card_data(
    license="other",
    license_name="bsd-3-clause",
    pipeline_tag="video-text-to-text",
    language=["en"],
    library_name="transformers",
    datasets=["TencentARC/TimeLens-100K", "TencentARC/TimeLens-Bench"],
    base_model="Qwen/Qwen3-VL-8B-Instruct",
)


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


_BERT_TURKISH_CONFIG: dict[str, Any] = {
    "model_type": "bert",
    # "architectures" field absent -- different from [] (empty list)
    "vocab_size": 32000,
    "hidden_size": 768,
    "num_hidden_layers": 12,
    "num_attention_heads": 12,
    "intermediate_size": 3072,
    "max_position_embeddings": 512,
}

_BERT_TURKISH_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag=None,  # no pipeline_tag in card
    language=["tr"],
    library_name=None,
)


def _patch_bert_turkish() -> Any:
    return _patch_hf_calls(
        config=_BERT_TURKISH_CONFIG,
        tokenizer_config=None,
        card_data=_BERT_TURKISH_CARD_DATA,
        hub_info={"author": "dbmdz", "sha": "deadf00d"},
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

_CROSS_ENCODER_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-ranking",
    language=["en"],
    library_name="sentence-transformers",
    datasets=["sentence-transformers/msmarco"],
    base_model="cross-encoder/ms-marco-MiniLM-L12-v2",
)


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
    "_BERT_TURKISH_CARD_DATA",
    "_BERT_TURKISH_CONFIG",
    "_CODEBERTA_CARD_DATA",
    "_CODEBERTA_CONFIG",
    "_CROSS_ENCODER_CARD_DATA",
    "_CROSS_ENCODER_CONFIG",
    "_GTE_MODERNBERT_CARD_DATA",
    "_GTE_MODERNBERT_CONFIG",
    "_HRNETPOSE_CARD_DATA",
    "_RTDETR_COCO_CARD_DATA",
    "_RTDETR_COCO_O365_CARD_DATA",
    "_RTDETR_COCO_O365_CONFIG",
    "_SAP_RPT_CARD_DATA",
    "_TIMELENS_CARD_DATA",
    "_TIMELENS_CONFIG",
    "_TRADEPULSE_CARD_DATA",
    "_TRADEPULSE_CONFIG",
    "_patch_bert_turkish",
    "_patch_codeberta",
    "_patch_cross_encoder",
    "_patch_gte_modernbert",
    "_patch_hrnetpose",
    "_patch_rtdetr_coco",
    "_patch_rtdetr_coco_o365",
    "_patch_sap_rpt",
    "_patch_timelens",
    "_patch_tradepulse",
]
