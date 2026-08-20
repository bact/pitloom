# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for Hugging Face model metadata tests (part 3 of 10).

See also: conftest.py, which re-exports everything via ``from
._hf_patches_03 import *``. Sibling test modules import helper names
from ``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_01 import _make_card_data, _patch_hf_calls


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


def _patch_rmbg14() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "SegformerForSemanticSegmentation",
            "architectures": ["BriaRMBG"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="image-segmentation",
            tags=[
                "remove background",
                "background-removal",
                "vision",
                "legal liability",
            ],
        ),
        hub_info={"author": "briaai"},
    )


def _patch_rmbg20() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated - config.json returns 401
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="image-segmentation",
            tags=["remove background", "background-removal", "vision"],
        ),
        hub_info={"author": "briaai"},
    )


def _patch_fibo_edit() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="image-to-image",
            tags=["art", "background-removal", "image-segmentation"],
            library_name="diffusers",
            base_model=["briaai/Fibo-Edit"],
        ),
        hub_info={
            "author": "briaai",
            "tags": [
                "arxiv:2511.06876",
                "base_model:briaai/Fibo-Edit",
                "base_model:finetune:briaai/Fibo-Edit",
            ],
        },
    )


def _patch_laion_clip() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="zero-shot-image-classification",
            tags=["clip"],
        ),
        hub_info={"author": "laion"},
    )


def _patch_streetclip() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "clip",
            "architectures": ["CLIPModel"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="cc-by-nc-4.0",
            pipeline_tag="zero-shot-image-classification",
            tags=[
                "geolocalization",
                "geolocation",
                "geographic",
                "clip",
                "multi-modal",
            ],
            language=["en"],
        ),
        hub_info={"author": "geolocal"},
    )


def _patch_swin() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "swin",
            "architectures": ["SwinForImageClassification"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag=None,  # card has no pipeline_tag
            tags=["vision", "image-classification"],
            datasets=["imagenet-1k"],
        ),
        hub_info={
            "author": "microsoft",
            "tags": ["dataset:imagenet-1k", "image-classification"],
        },
    )


def _patch_resnet18() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "resnet",
            "architectures": ["ResNetForImageClassification"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag=None,
            tags=["vision", "image-classification"],
            datasets=["imagenet-1k"],
        ),
        hub_info={"author": "microsoft"},
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


def _patch_groot() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "Gr00tN1d7",
            "architectures": ["Gr00tN1d7"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag="robotics",
            tags=["robotics"],
        ),
        hub_info={"author": "nvidia"},
    )


def _patch_openvla() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "openvla",
            "architectures": ["OpenVLAForActionPrediction"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="robotics",
            tags=["vla", "image-text-to-text", "multimodal", "pretraining"],
            language=["en"],
        ),
        hub_info={"author": "openvla"},
    )


def _patch_pi05() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="gemma",
            pipeline_tag="robotics",
            tags=["vision-language-action", "imitation-learning", "lerobot"],
            language=["en"],
            library_name="lerobot",
        ),
        hub_info={"author": "lerobot"},
    )


def _patch_nemotron() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "NemotronH_Nano_Omni_Reasoning_V3",
            "architectures": ["NemotronH_Nano_Omni_Reasoning_V3"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="any-to-any",
            tags=["nvidia", "pytorch", "multimodal"],
            library_name="transformers",
            datasets=["nvidia/Nemotron-Image-Training-v3"],
        ),
        hub_info={
            "author": "nvidia",
            "tags": ["dataset:nvidia/Nemotron-Image-Training-v3"],
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


def _patch_mistral_medium() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "mistral3",
            "architectures": ["Mistral3ForConditionalGeneration"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag=None,
            tags=["vLLM"],
            language=[
                "en",
                "fr",
                "de",
                "es",
                "pt",
                "it",
                "ja",
                "ko",
                "ru",
                "zh",
                "ar",
                "fa",
                "id",
                "ms",
                "pl",
                "ro",
                "sv",
                "tr",
                "uk",
                "vi",
                "hi",
                "bn",
            ],
        ),
        hub_info={"author": "mistralai"},
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


__all__ = [
    "_patch_dinov2",
    "_patch_fibo_edit",
    "_patch_groot",
    "_patch_laguna",
    "_patch_laion_clip",
    "_patch_llmjp",
    "_patch_mallam",
    "_patch_mistral_medium",
    "_patch_nemotron",
    "_patch_openvla",
    "_patch_pi05",
    "_patch_privacy_filter",
    "_patch_rad_dino",
    "_patch_resnet18",
    "_patch_rmbg14",
    "_patch_rmbg20",
    "_patch_sealion_vl",
    "_patch_streetclip",
    "_patch_swin",
    "_patch_tapas",
    "_patch_timm_convnext",
    "_patch_uni2",
    "_patch_wangchanglm",
]
