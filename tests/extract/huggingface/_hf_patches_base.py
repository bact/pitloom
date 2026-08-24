# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared Hugging Face patch/mock helpers used by all topic-specific
``_hf_patches_*`` submodules: the generic ``_patch_hf_calls`` context manager,
the ``_make_card_data`` builder, and Mistral's default config/card fixtures.

See also: _hf_patches_text_generation_pretrained.py,
_hf_patches_text_generation_instruct.py,
_hf_patches_text_generation_regional.py, _hf_patches_gated_metadata.py,
_hf_patches_speech_audio.py, _hf_patches_multimodal.py,
_hf_patches_omni_modal.py, _hf_patches_embeddings.py, _hf_patches_vision.py,
_hf_patches_structured_text.py, _hf_patches_generative_3d.py. Sibling test
modules import helper names from ``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch


def _make_card_data(
    license: str | None = "apache-2.0",
    pipeline_tag: str | None = "text-generation",
    tags: list[str] | None = None,
    language: Any = None,  # str scalar or list[str]
    datasets: list[str] | None = None,
    library_name: str | None = None,
    license_name: str | None = None,
    model_index: list[Any] | None = None,
    base_model: Any = None,  # str or list[str]
) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if license is not None:
        data["license"] = license
    if pipeline_tag is not None:
        data["pipeline_tag"] = pipeline_tag
    if tags is not None:
        data["tags"] = tags
    if language is not None:
        data["language"] = language
    if datasets is not None:
        data["datasets"] = datasets
    if library_name is not None:
        data["library_name"] = library_name
    if license_name is not None:
        data["license_name"] = license_name
    if model_index is not None:
        data["model-index"] = model_index
    if base_model is not None:
        data["base_model"] = base_model
    return data


_MISTRAL_CONFIG: dict[str, Any] = {
    "model_type": "mistral",
    "architectures": ["MistralForCausalLM"],
    "vocab_size": 32000,
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "num_attention_heads": 32,
    "torch_dtype": "bfloat16",
}


_MISTRAL_TOKENIZER_CONFIG: dict[str, Any] = {
    "tokenizer_class": "LlamaTokenizer",
    "model_max_length": 32768,
}


_MISTRAL_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    tags=["pretrained"],
    language=["en"],
    library_name="transformers",
)


# pylint: disable=dangerous-default-value
def _patch_hf_calls(
    config: dict[str, Any] | None = _MISTRAL_CONFIG,
    tokenizer_config: dict[str, Any] | None = _MISTRAL_TOKENIZER_CONFIG,
    generation_config: dict[str, Any] | None = None,
    card_text: str | None = "---\nlicense: apache-2.0\n---\n\nA great model.",
    card_data: dict[str, Any] | None = None,
    hub_info: dict[str, Any] | None = None,
) -> Any:
    """Return a context manager that patches all HF I/O helpers."""

    def _json_side_effect(
        model_id: str, filename: str, revision: str | None = None
    ) -> dict[str, Any] | None:
        _ = model_id
        _ = revision
        if filename == "config.json":
            return config
        if filename == "tokenizer_config.json":
            return tokenizer_config
        if filename == "generation_config.json":
            return generation_config
        return None

    return patch.multiple(
        "pitloom.extract._huggingface_fetch",
        _safe_load_json=MagicMock(side_effect=_json_side_effect),
        _load_model_card=MagicMock(
            return_value=(
                card_text,
                _MISTRAL_CARD_DATA if card_data is None else card_data,
            )
        ),
        _load_model_info=MagicMock(
            return_value=hub_info
            or {
                "author": "mistralai",
                "sha": "deadbeef",
                "created_at": "2023-09-20T13:03:50+00:00",
            }
        ),
        # Prevent real network calls for license file detection in tests.
        # Override per-test via an extra patch when file detection is under test.
        _detect_license_from_hf_files=MagicMock(return_value=(None, None)),
    )


__all__ = [
    "_MISTRAL_CARD_DATA",
    "_MISTRAL_CONFIG",
    "_MISTRAL_TOKENIZER_CONFIG",
    "_make_card_data",
    "_patch_hf_calls",
]
