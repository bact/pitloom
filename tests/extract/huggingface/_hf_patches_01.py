# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for Hugging Face model metadata tests (part 1 of 10).

See also: conftest.py, which re-exports everything via ``from
._hf_patches_01 import *``. Sibling test modules import helper names
from ``conftest``, not from this module directly.
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

_OPENTHAIGPT_CONFIG: dict[str, Any] = {
    "model_type": "qwen2",
    "architectures": ["Qwen2ForCausalLM"],
    "vocab_size": 152064,
    "hidden_size": 5120,
    "num_hidden_layers": 64,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_OPENTHAIGPT_CARD_DATA = _make_card_data(
    license="other",
    license_name="qwen",
    pipeline_tag="text-generation",
    tags=["openthaigpt", "qwen", "reasoning"],
    language=["th", "en"],
    library_name="transformers",
    model_index=[
        {
            "name": "openthaigpt-r1-32b-instruct",
            "results": [{"task": {"type": "reasoning"}, "dataset": {"name": "custom"}}],
        }
    ],
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
        "pitloom.extract._huggingface",
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


def _patch_openthaigpt() -> Any:
    return _patch_hf_calls(
        config=_OPENTHAIGPT_CONFIG,
        tokenizer_config={
            "tokenizer_class": "Qwen2Tokenizer",
            "model_max_length": 131072,
        },
        card_data=_OPENTHAIGPT_CARD_DATA,
        card_text=(
            "---\nlicense: other\n---\n\nA Thai-English bilingual reasoning model."
        ),
        hub_info={"author": "openthaigpt", "sha": "cafebabe"},
    )


_KOKORO_CONFIG: dict[str, Any] = {
    # Custom Kokoro schema - no model_type or architectures
    "istftnet": {},
    "dim_in": 64,
    "hidden_dim": 512,
    "n_layer": 3,
    "n_mels": 80,
    "multispeaker": True,
}

_KOKORO_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-to-speech",
    tags=None,
    language=["en"],
    library_name=None,
)


def _patch_kokoro() -> Any:
    return _patch_hf_calls(
        config=_KOKORO_CONFIG,
        tokenizer_config=None,
        card_data=_KOKORO_CARD_DATA,
        card_text="---\nlicense: apache-2.0\n---\n\nA small TTS model.",
        hub_info={"author": "hexgrad"},
    )


_STARCODER2_CONFIG: dict[str, Any] = {
    "model_type": "starcoder2",
    "architectures": ["Starcoder2ForCausalLM"],
    "hidden_size": 3072,
    "num_hidden_layers": 30,
    "num_attention_heads": 24,
    "vocab_size": 49152,
    "torch_dtype": "float32",
}

_STARCODER2_CARD_DATA = _make_card_data(
    license="bigcode-openrail-m",
    pipeline_tag="text-generation",
    tags=["code"],
    language=None,
    datasets=["bigcode/the-stack-v2-train"],
    library_name="transformers",
)


def _patch_starcoder2() -> Any:
    return _patch_hf_calls(
        config=_STARCODER2_CONFIG,
        card_data=_STARCODER2_CARD_DATA,
        hub_info={"author": "bigcode"},
    )


_WHISPER_CONFIG: dict[str, Any] = {
    "model_type": "whisper",
    "architectures": ["WhisperForConditionalGeneration"],
    "vocab_size": 51865,
    "num_hidden_layers": 32,
    "max_source_positions": 1500,
}

_WHISPER_LANGUAGES: list[Any] = [
    "en",
    "zh",
    "de",
    "es",
    "ru",
    "ko",
    "fr",
    "ja",
    "pt",
    "tr",
    "pl",
    "ca",
    "nl",
    "ar",
    "sv",
    "it",
    "id",
    "hi",
    "fi",
    "vi",
    "he",
    "uk",
    "el",
    "ms",
    "cs",
    "ro",
    "da",
    "hu",
    "ta",
    False,  # YAML 1.1 parses "no" (Norwegian Bokmål) as False
    "th",
    "ur",
    "hr",
    "bg",
    "lt",
]

_WHISPER_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="automatic-speech-recognition",
    tags=["audio", "automatic-speech-recognition", "hf-asr-leaderboard"],
    language=_WHISPER_LANGUAGES,
    library_name=None,
)


def _patch_whisper() -> Any:
    return _patch_hf_calls(
        config=_WHISPER_CONFIG,
        tokenizer_config=None,
        card_data=_WHISPER_CARD_DATA,
        hub_info={"author": "openai"},
    )


_KIMI_CONFIG: dict[str, Any] = {
    "model_type": "kimi_k25",
    "architectures": ["KimiK25ForConditionalGeneration"],
    "hidden_size": 7168,
    "num_hidden_layers": 61,
    "torch_dtype": "bfloat16",
}

_KIMI_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    tags=["compressed-tensors"],
    language=None,
    library_name="transformers",
)


def _patch_kimi() -> Any:
    return _patch_hf_calls(
        config=_KIMI_CONFIG,
        card_data=_KIMI_CARD_DATA,
        hub_info={"author": "moonshotai"},
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


_LLAMA_CARD_DATA = _make_card_data(
    license="llama3.2",  # Custom Meta license - not vague, not standard SPDX
    pipeline_tag="text-generation",
    tags=["facebook", "meta", "pytorch", "llama", "llama-3"],
    language=["en", "de", "fr", "it", "pt", "hi", "es", "th"],
    library_name="transformers",
)


def _patch_llama() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated - config.json inaccessible
        tokenizer_config=None,
        card_data=_LLAMA_CARD_DATA,
        hub_info={"author": "meta-llama"},
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

_DEEPSEEK_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag=None,  # No pipeline_tag set
    tags=None,
    language=None,
    library_name="transformers",
)


def _patch_deepseek() -> Any:
    return _patch_hf_calls(
        config=_DEEPSEEK_CONFIG,
        card_data=_DEEPSEEK_CARD_DATA,
        hub_info={"author": "deepseek-ai"},
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


_TYPHOON_CONFIG: dict[str, Any] = {
    "model_type": "mistral",
    "architectures": ["MistralForCausalLM"],
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "vocab_size": 32768,
    "torch_dtype": "bfloat16",
}

_TYPHOON_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    tags=["pretrained"],
    language=["th"],
    library_name="transformers",
)


def _patch_typhoon() -> Any:
    return _patch_hf_calls(
        config=_TYPHOON_CONFIG,
        card_data=_TYPHOON_CARD_DATA,
        hub_info={"author": "typhoon-ai"},
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


__all__ = [
    "Any",
    "MagicMock",
    "_DEEPSEEK_CARD_DATA",
    "_DEEPSEEK_CONFIG",
    "_GEMMA_CARD_DATA",
    "_KIMI_CARD_DATA",
    "_KIMI_CONFIG",
    "_KOKORO_CARD_DATA",
    "_KOKORO_CONFIG",
    "_LLAMA_CARD_DATA",
    "_MISTRAL_CARD_DATA",
    "_MISTRAL_CONFIG",
    "_MISTRAL_TOKENIZER_CONFIG",
    "_OPENTHAIGPT_CARD_DATA",
    "_OPENTHAIGPT_CONFIG",
    "_SEALION_CARD_DATA",
    "_SEALLMS_CARD_DATA",
    "_SEALLMS_CONFIG",
    "_SERENGETI_CONFIG",
    "_SERENGETI_TOKENIZER_CONFIG",
    "_STARCODER2_CARD_DATA",
    "_STARCODER2_CONFIG",
    "_TYPHOON_CARD_DATA",
    "_TYPHOON_CONFIG",
    "_WHISPER_CARD_DATA",
    "_WHISPER_CONFIG",
    "_WHISPER_LANGUAGES",
    "_make_card_data",
    "_patch_deepseek",
    "_patch_gemma",
    "_patch_hf_calls",
    "_patch_kimi",
    "_patch_kokoro",
    "_patch_llama",
    "_patch_openthaigpt",
    "_patch_sealion_gguf",
    "_patch_seallms",
    "_patch_serengeti",
    "_patch_starcoder2",
    "_patch_typhoon",
    "_patch_whisper",
    "annotations",
    "patch",
]
