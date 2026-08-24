# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for models that are gated or otherwise access-restricted on
the Hub: config.json, tokenizer_config.json, and/or the model card are
unavailable (401/gated) or come back empty.

See also: _hf_patches_base.py, _hf_patches_gated_metadata.py,
_hf_patches_text_generation_pretrained.py,
_hf_patches_text_generation_instruct.py,
_hf_patches_text_generation_regional.py, _hf_patches_speech_audio.py,
_hf_patches_multimodal.py, _hf_patches_omni_modal.py,
_hf_patches_embeddings.py, _hf_patches_vision.py,
_hf_patches_structured_text.py, _hf_patches_generative_3d.py.
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


__all__ = [
    "_GEMMA_CARD_DATA",
    "_NLLB_CONFIG",
    "_NLLB_TOKENIZER_CONFIG",
    "_SERENGETI_CONFIG",
    "_SERENGETI_TOKENIZER_CONFIG",
    "_STANZA_DE_CARD_DATA",
    "_STANZA_FI_CARD_DATA",
    "_TALKIE_CARD_DATA",
    "_patch_aya_vision",
    "_patch_cohere_aya_23",
    "_patch_gemma",
    "_patch_inkubalm",
    "_patch_nllb",
    "_patch_serengeti",
    "_patch_stanza_de",
    "_patch_stanza_fi",
    "_patch_talkie",
    "_patch_wmt22_cometkiwi",
]
