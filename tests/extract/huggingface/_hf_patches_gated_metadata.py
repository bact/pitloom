# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for models with no pipeline_tag or gated/inaccessible metadata
(config.json, tokenizer_config.json, or model card unavailable).

See also: _hf_patches_base.py, _hf_patches_text_generation_pretrained.py,
_hf_patches_text_generation_instruct.py,
_hf_patches_text_generation_regional.py, _hf_patches_speech_audio.py,
_hf_patches_multimodal.py, _hf_patches_omni_modal.py,
_hf_patches_embeddings.py, _hf_patches_vision.py,
_hf_patches_structured_text.py, _hf_patches_generative_3d.py. Sibling test
modules import helper names from ``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)

_GEMMA_CARD_DATA = _make_card_data(
    license="gemma",  # Non-standard but passes SPDX License ID regex -> not vague
    pipeline_tag=None,
    tags=None,
    language=None,
    library_name="transformers",
)


def _patch_gemma() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated - config.json inaccessible
        tokenizer_config=None,
        card_data=_GEMMA_CARD_DATA,
        hub_info={"author": "google"},
    )


_DEEPSEEK_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag=None,  # No pipeline_tag set
    tags=None,
    language=None,
    library_name="transformers",
)


_DEEPSEEK_CONFIG: dict[str, Any] = {
    "model_type": "deepseek_v3",
    "architectures": ["DeepseekV3ForCausalLM"],
    "hidden_size": 7168,
    "num_hidden_layers": 61,
    "num_attention_heads": 128,
    "vocab_size": 129280,
    "torch_dtype": "bfloat16",
}


def _patch_deepseek() -> Any:
    return _patch_hf_calls(
        config=_DEEPSEEK_CONFIG,
        card_data=_DEEPSEEK_CARD_DATA,
        hub_info={"author": "deepseek-ai"},
    )


_SEALLMS_CONFIG: dict[str, Any] = {
    "model_type": "qwen2",
    "architectures": ["Qwen2ForCausalLM"],
    "hidden_size": 3584,
    "num_hidden_layers": 28,
    "num_attention_heads": 28,
    "vocab_size": 152064,
    "torch_dtype": "bfloat16",
}


_SEALLMS_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag=None,
    tags=["sea", "multilingual"],
    language=["en", "zh", "id", "vi", "th", "ms", "tl", "ta", "jv", "lo", "km", "my"],
    library_name=None,
)


def _patch_seallms() -> Any:
    return _patch_hf_calls(
        config=_SEALLMS_CONFIG,
        card_data=_SEALLMS_CARD_DATA,
        hub_info={"author": "SeaLLMs"},
    )


_SERENGETI_CONFIG: dict[str, Any] = {
    "architectures": ["ElectraModel"],
    "model_type": "electra",
    "hidden_size": 768,
    "num_hidden_layers": 12,
    "num_attention_heads": 12,
    "intermediate_size": 3072,
    "max_position_embeddings": 512,
    "vocab_size": 250000,
    "torch_dtype": "float32",
}


_SERENGETI_TOKENIZER_CONFIG: dict[str, Any] = {
    "tokenizer_class": "ElectraTokenizer",
    "model_max_length": 1000000000000000019884624838656,
    "do_lower_case": True,
}


def _patch_serengeti() -> Any:
    return _patch_hf_calls(
        config=_SERENGETI_CONFIG,
        tokenizer_config=_SERENGETI_TOKENIZER_CONFIG,
        card_data={},  # No model card - ModelCard.load() fails
        hub_info={"author": "UBC-NLP", "downloads": 46},
    )


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


def _patch_opus_mt_th_en() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "marian",
            "architectures": ["MarianMTModel"],
            "vocab_size": 62307,
            "num_hidden_layers": 6,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag=None,
            tags=["translation"],
            language=["th", "en"],
        ),
        hub_info={"author": "Helsinki-NLP"},
    )


def _patch_hunyuan_mt() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "hunyuan_v1_dense",
            "architectures": ["HunYuanDenseV1ForCausalLM"],
            "vocab_size": 120818,
            "num_hidden_layers": 32,
            "hidden_size": 2048,
        },
        tokenizer_config={
            "tokenizer_class": "PreTrainedTokenizerFast",
            "model_max_length": 1000000000000000019884624838656,
        },
        card_data=_make_card_data(
            license=None,
            pipeline_tag=None,
            tags=["translation"],
            language=["zh", "en", "fr", "pt", "es", "ja", "tr"],
        ),
        hub_info={"author": "tencent"},
    )


def _patch_hunyuan_mt7b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "hunyuan_v1_dense",
            "architectures": ["HunYuanDenseV1ForCausalLM"],
            "vocab_size": 128256,
            "num_hidden_layers": 32,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag=None,
            tags=["translation"],
            library_name="transformers",
        ),
        hub_info={"author": "tencent"},
    )


def _patch_ii_medical() -> Any:
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
            pipeline_tag=None,
            tags=[],
        ),
        hub_info={"author": "Intelligent-Internet"},
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


def _patch_cohere_aya_23() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data={},  # gated card -> empty dict
        hub_info={"author": "CohereLabs", "sha": "deadf00d"},
    )


def _patch_wmt22_cometkiwi() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data={},  # gated -> empty
        hub_info={"author": "Unbabel", "sha": "deadf00d"},
    )


_EUROLLM_TOKENIZER_SENTINEL: int = 1_000_000_000_000_000_019_884_624_838_656


_EUROLLM_1B7_CONFIG: dict[str, Any] = {
    "model_type": "llama",
    "architectures": ["LlamaForCausalLM"],
    "vocab_size": 128000,
    "hidden_size": 2048,
    "num_hidden_layers": 24,
    "num_attention_heads": 16,
    "num_key_value_heads": 8,
    "max_position_embeddings": 4096,
    "torch_dtype": "bfloat16",
}


_EUROLLM_1B7_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag=None,
    language=[
        "en",
        "de",
        "es",
        "fr",
        "it",
        "pt",
        "pl",
        "nl",
        "tr",
        "sv",
        "cs",
        "el",
        "hu",
        "ro",
        "fi",
        "uk",
        "sl",
        "sk",
        "da",
        "lt",
        "lv",
        "et",
        "bg",
        "no",
        "ca",
        "hr",
        "ga",
        "mt",
        "gl",
        "zh",
        "ru",
        "ko",
        "ja",
        "ar",
    ],
    library_name="transformers",
)


def _patch_eurollm_1b7() -> Any:
    return _patch_hf_calls(
        config=_EUROLLM_1B7_CONFIG,
        tokenizer_config={
            "tokenizer_class": "LlamaTokenizer",
            "model_max_length": _EUROLLM_TOKENIZER_SENTINEL,
        },
        card_data=_EUROLLM_1B7_CARD_DATA,
        hub_info={"author": "utter-project", "sha": "deadf00d"},
    )


_STANZA_FI_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag=None,
    language=["fi"],
    library_name="stanza",
)


def _patch_stanza_fi() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_STANZA_FI_CARD_DATA,
        hub_info={"author": "stanfordnlp", "sha": "deadf00d"},
    )


_STANZA_DE_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag=None,
    language=["de"],
    library_name="stanza",
)


def _patch_stanza_de() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_STANZA_DE_CARD_DATA,
        hub_info={"author": "stanfordnlp", "sha": "deadf00d"},
    )


_BERT_TURKISH_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag=None,  # no pipeline_tag in card
    language=["tr"],
    library_name=None,
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


def _patch_bert_turkish() -> Any:
    return _patch_hf_calls(
        config=_BERT_TURKISH_CONFIG,
        tokenizer_config=None,
        card_data=_BERT_TURKISH_CARD_DATA,
        hub_info={"author": "dbmdz", "sha": "deadf00d"},
    )


__all__ = [
    "_BERT_TURKISH_CARD_DATA",
    "_BERT_TURKISH_CONFIG",
    "_DEEPSEEK_CARD_DATA",
    "_DEEPSEEK_CONFIG",
    "_EUROLLM_1B7_CARD_DATA",
    "_EUROLLM_1B7_CONFIG",
    "_EUROLLM_TOKENIZER_SENTINEL",
    "_GEMMA_CARD_DATA",
    "_NLLB_CONFIG",
    "_NLLB_TOKENIZER_CONFIG",
    "_OPENEUROLLM_CARD_DATA",
    "_OPENEUROLLM_CONFIG",
    "_SEALLMS_CARD_DATA",
    "_SEALLMS_CONFIG",
    "_SERENGETI_CONFIG",
    "_SERENGETI_TOKENIZER_CONFIG",
    "_STANZA_DE_CARD_DATA",
    "_STANZA_FI_CARD_DATA",
    "_TALKIE_CARD_DATA",
    "_patch_aya_vision",
    "_patch_bert_turkish",
    "_patch_cohere_aya_23",
    "_patch_deepseek",
    "_patch_eurollm_1b7",
    "_patch_gemma",
    "_patch_hunyuan_mt",
    "_patch_hunyuan_mt7b",
    "_patch_ii_medical",
    "_patch_inkubalm",
    "_patch_mistral_medium",
    "_patch_nllb",
    "_patch_openeurollm",
    "_patch_opus_mt_th_en",
    "_patch_resnet18",
    "_patch_seallms",
    "_patch_serengeti",
    "_patch_stanza_de",
    "_patch_stanza_fi",
    "_patch_swin",
    "_patch_talkie",
    "_patch_wmt22_cometkiwi",
]
