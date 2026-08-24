# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for structured/classification text models: text and token
classification, translation, tabular and table QA, and summarization.

See also: _hf_patches_base.py, _hf_patches_text_generation_pretrained.py,
_hf_patches_text_generation_instruct.py,
_hf_patches_text_generation_regional.py, _hf_patches_gated_metadata.py,
_hf_patches_speech_audio.py, _hf_patches_multimodal.py,
_hf_patches_omni_modal.py, _hf_patches_embeddings.py, _hf_patches_vision.py,
_hf_patches_generative_3d.py. Sibling test modules import helper names from
``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
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


def _patch_tapas() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "tapas",
            "architectures": ["TapasForQuestionAnswering"],
            "vocab_size": 30522,
            "num_hidden_layers": 24,
            "hidden_size": 1024,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="table-question-answering",
            tags=["tapas", "table-question-answering"],
            language="en",  # scalar string
            datasets=["wikitablequestions"],
        ),
        hub_info={"author": "google"},
    )


def _patch_privacy_filter() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "openai_privacy_filter",
            "architectures": ["OpenAIPrivacyFilterForTokenClassification"],
            "vocab_size": 200064,
            "num_hidden_layers": 8,
            "hidden_size": 640,
        },
        tokenizer_config={
            "tokenizer_class": "TokenizersBackend",
            "model_max_length": 128000,
        },
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="token-classification",
            tags=["transformers.js"],
        ),
        hub_info={"author": "openai"},
    )


def _patch_falconsai() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "t5",
            "architectures": ["T5ForConditionalGeneration"],
            "vocab_size": 32128,
        },
        tokenizer_config={"tokenizer_class": "T5Tokenizer", "model_max_length": 512},
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="summarization",
            tags=["medical"],
            language=["en"],
        ),
        hub_info={"author": "Falconsai"},
    )


def _patch_hy_mt_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag="translation",
            tags=["hy-mt", "quant", "2bit"],
            language=["multilingual"],  # keyword, not ISO code
            base_model="AngelSlim/Hy-MT1.5-1.8B-2bit",
        ),
        hub_info={
            "author": "tencent",
            "tags": [
                "base_model:AngelSlim/Hy-MT1.5-1.8B-2bit",
                "base_model:quantized:AngelSlim/Hy-MT1.5-1.8B-2bit",
            ],
        },
    )


def _patch_fineweb_edu() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "bert",
            "architectures": ["BertForSequenceClassification"],
            "vocab_size": 30522,
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-classification",
            tags=["BERT"],
            language=["en"],
            base_model=["Snowflake/snowflake-arctic-embed-m"],
        ),
        hub_info={
            "author": "HuggingFaceFW",
            "tags": [
                "base_model:Snowflake/snowflake-arctic-embed-m",
                "base_model:finetune:Snowflake/snowflake-arctic-embed-m",
            ],
        },
    )


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


_MOIRAI_CARD_DATA = _make_card_data(
    license="cc-by-nc-4.0",
    pipeline_tag="time-series-forecasting",
    language=None,
    library_name="transformers",
)


_MOIRAI_CONFIG: dict[str, Any] = {
    "patch_sizes": [8, 16, 32, 64, 128],
    "d_model": 384,
    "num_encoder_layers": 6,
    "nhead": 8,
    "context_length": 4096,
}


def _patch_moirai() -> Any:
    return _patch_hf_calls(
        config=_MOIRAI_CONFIG,
        tokenizer_config=None,
        card_data=_MOIRAI_CARD_DATA,
        hub_info={"author": "Salesforce", "sha": "deadf00d"},
    )


_TRADEPULSE_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-classification",
    language=["en"],
    library_name="transformers",
    base_model="ProsusAI/finbert",
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


__all__ = [
    "_MOIRAI_CARD_DATA",
    "_MOIRAI_CONFIG",
    "_SAP_RPT_CARD_DATA",
    "_SUGOI_CARD_DATA",
    "_TRADEPULSE_CARD_DATA",
    "_TRADEPULSE_CONFIG",
    "_VNTL_CARD_DATA",
    "_patch_aspect_finnlp_th",
    "_patch_deberta_human_value",
    "_patch_falconsai",
    "_patch_fineweb_edu",
    "_patch_hy_mt_gguf",
    "_patch_moirai",
    "_patch_privacy_filter",
    "_patch_protonx_legal",
    "_patch_sap_rpt",
    "_patch_sugoi",
    "_patch_tapas",
    "_patch_tradepulse",
    "_patch_vntl",
]
