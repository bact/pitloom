# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for Hugging Face model metadata tests (part 5 of 10).

See also: conftest.py, which re-exports everything via ``from
._hf_patches_05 import *``. Sibling test modules import helper names
from ``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_01 import _make_card_data, _patch_hf_calls


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


def _patch_granite_geo_flood() -> Any:
    return _patch_hf_calls(
        config=None,  # TerraTorch -- no standard transformers config.json
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="image-segmentation",
            tags=["geospatial", "flood-detection", "sentinel-2", "sentinel-1"],
            datasets=[
                "ai-for-good-lab/ai4g-flood-dataset",
                "blanchon/ETCI-2021-Flood-Detection",
            ],
            base_model=["ibm-granite/granite-geospatial-uki"],
            library_name="terratorch",
        ),
        hub_info={
            "author": "ibm-granite",
            "tags": [
                "base_model:ibm-granite/granite-geospatial-uki",
                "base_model:finetune:ibm-granite/granite-geospatial-uki",
            ],
        },
    )


def _patch_flood_image_detect() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "siglip",
            "architectures": ["SiglipForImageClassification"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="image-classification",
            tags=["siglip", "Flood-Detection", "climate"],
            language=["en"],
            base_model=["google/siglip2-base-patch16-512"],
        ),
        hub_info={
            "author": "prithivMLmods",
            "tags": [
                "arxiv:2502.14786",
                "base_model:google/siglip2-base-patch16-512",
                "base_model:finetune:google/siglip2-base-patch16-512",
            ],
        },
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


def _patch_opt_2_7b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "opt",
            "architectures": ["OPTForCausalLM"],
            "vocab_size": 50272,
            "num_hidden_layers": 32,
            "hidden_size": 2560,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="text-generation",
            tags=[],
        ),
        hub_info={"author": "facebook"},
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


def _patch_gpt_neo_2_7b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "gpt_neo",
            "architectures": ["GPTNeoForCausalLM"],
            "vocab_size": 50257,
            "num_hidden_layers": 32,
            "hidden_size": 2560,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=[],
            language=["en"],
        ),
        hub_info={"author": "EleutherAI"},
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


def _patch_phi2() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "phi",
            "architectures": ["PhiForCausalLM"],
            "vocab_size": 51200,
            "num_hidden_layers": 32,
            "hidden_size": 2560,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="text-generation",
            tags=["nlp", "code"],
            language=["en"],
        ),
        hub_info={"author": "microsoft"},
    )


def _patch_llama_3_2_3b() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated
        tokenizer_config=None,
        card_data=_make_card_data(
            license="llama3.2",
            pipeline_tag="text-generation",
            tags=[],
            language=["en", "de", "fr", "it", "pt", "hi", "es", "th"],
        ),
        hub_info={"author": "meta-llama"},
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


__all__ = [
    "_patch_crow_9b",
    "_patch_distilbert_multilingual",
    "_patch_fineweb_edu",
    "_patch_flood_image_detect",
    "_patch_gabert",
    "_patch_gpt_neo_2_7b",
    "_patch_granite_embed",
    "_patch_granite_geo_flood",
    "_patch_hermes_3_llama_3b",
    "_patch_llama_3_2_3b",
    "_patch_llama_3_2_3b_instruct",
    "_patch_opt_2_7b",
    "_patch_opt_iml",
    "_patch_phi2",
    "_patch_qwen3_reap",
    "_patch_stablelm_zephyr",
    "_patch_tinyllama_chat",
    "_patch_xlm_roberta_base",
]
