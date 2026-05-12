# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
# pylint: disable=too-many-lines

"""Tests for the Hugging Face model metadata extractor."""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.core.dataset_metadata import DatasetReference
from pitloom.extract._huggingface import (
    _detect_license_from_hf_files,
    is_huggingface_source,
    parse_hf_model_id,
    read_huggingface,
)

# ---------------------------------------------------------------------------
# parse_hf_model_id / is_huggingface_source
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected_id"),
    [
        (
            "https://huggingface.co/mistralai/Mistral-7B-v0.1",
            "mistralai/Mistral-7B-v0.1",
        ),
        (
            "https://huggingface.co/mistralai/Mistral-7B-v0.1/tree/main",
            "mistralai/Mistral-7B-v0.1",
        ),
        (
            "https://huggingface.co/Qwen/Qwen3-235B-A22B",
            "Qwen/Qwen3-235B-A22B",
        ),
        (
            "https://huggingface.co/Qwen/Qwen3-235B-A22B/blob/main/config.json",
            "Qwen/Qwen3-235B-A22B",
        ),
        (
            "https://huggingface.co/openthaigpt/openthaigpt-r1-32b-instruct",
            "openthaigpt/openthaigpt-r1-32b-instruct",
        ),
        ("mistralai/Mistral-7B-v0.1", "mistralai/Mistral-7B-v0.1"),
        ("Qwen/Qwen3-235B-A22B", "Qwen/Qwen3-235B-A22B"),
        (
            "openthaigpt/openthaigpt-r1-32b-instruct",
            "openthaigpt/openthaigpt-r1-32b-instruct",
        ),
    ],
)
def test_parse_hf_model_id_valid(source: str, expected_id: str) -> None:
    assert parse_hf_model_id(source) == expected_id


@pytest.mark.parametrize(
    "source",
    [
        "/path/to/model.safetensors",
        "./models/my_model.gguf",
        "just-a-filename.onnx",
        "https://example.com/model",
        "",
    ],
)
def test_parse_hf_model_id_invalid(source: str) -> None:
    assert parse_hf_model_id(source) is None


def test_is_huggingface_source_url() -> None:
    assert is_huggingface_source("https://huggingface.co/mistralai/Mistral-7B-v0.1")


def test_is_huggingface_source_model_id() -> None:
    assert is_huggingface_source("Qwen/Qwen3-235B-A22B")


def test_is_huggingface_source_local_path() -> None:
    assert not is_huggingface_source("/path/to/model.onnx")


def test_is_huggingface_source_plain_filename() -> None:
    assert not is_huggingface_source("model.safetensors")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


# pylint: disable=too-many-arguments,too-many-positional-arguments,redefined-builtin
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

# OpenThaiGPT-style card with multilingual + custom license + model-index
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


def _patch_hf_calls(  # pylint: disable=dangerous-default-value
    config: dict[str, Any] | None = _MISTRAL_CONFIG,
    tokenizer_config: dict[str, Any] | None = _MISTRAL_TOKENIZER_CONFIG,
    generation_config: dict[str, Any] | None = None,
    card_text: str | None = "---\nlicense: apache-2.0\n---\n\nA great model.",
    card_data: dict[str, Any] | None = None,
    hub_info: dict[str, Any] | None = None,
) -> Any:
    """Return a context manager that patches all HF I/O helpers."""

    def _json_side_effect(model_id: str, filename: str) -> dict[str, Any] | None:
        _ = model_id
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


# ---------------------------------------------------------------------------
# read_huggingface - standard fields
# ---------------------------------------------------------------------------


def test_read_huggingface_name() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.name == "Mistral-7B-v0.1"


def test_read_huggingface_type_of_model() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.type_of_model == "mistral"


def test_read_huggingface_architecture() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.architecture == "MistralForCausalLM"


def test_read_huggingface_hyperparameters_include_vocab_size() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.hyperparameters.get("vocab_size") == 32000
    assert meta.hyperparameters.get("hidden_size") == 4096
    assert meta.hyperparameters.get("num_hidden_layers") == 32


def test_read_huggingface_license_from_card() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.license == "apache-2.0"


def test_read_huggingface_domain_from_pipeline_tag_via_usage() -> None:
    # pipeline_tag should land in usage.domains -> serialised to SPDX ai_domain
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert "text-generation" in meta.usage.domains


def test_read_huggingface_top_level_domain_empty_for_hf_models() -> None:
    # HF extractor uses usage.domains, not the top-level domain field
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert not meta.domain


def test_read_huggingface_datasets_as_dataset_references() -> None:
    card_data = _make_card_data(datasets=["the_pile", "c4"])
    with _patch_hf_calls(card_data=card_data):
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert len(meta.datasets) == 2
    assert all(isinstance(d, DatasetReference) for d in meta.datasets)
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "the_pile" in ds_names
    assert "c4" in ds_names


def test_read_huggingface_dataset_role_is_trained_on() -> None:
    card_data = _make_card_data(datasets=["openwebtext"])
    with _patch_hf_calls(card_data=card_data):
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.datasets[0].role == "trainedOn"


def test_read_huggingface_dataset_download_url() -> None:
    card_data = _make_card_data(datasets=["c4"])
    with _patch_hf_calls(card_data=card_data):
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert (
        meta.datasets[0].metadata.download_url == "https://huggingface.co/datasets/c4"
    )


def test_read_huggingface_format_is_unknown() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.format_info.model_format == AiModelFormat.UNKNOWN


def test_read_huggingface_generation_config_params() -> None:
    gen_cfg = {"temperature": 0.7, "top_p": 0.9, "max_new_tokens": 512}
    with _patch_hf_calls(generation_config=gen_cfg):
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.hyperparameters.get("generation.temperature") == 0.7
    assert meta.hyperparameters.get("generation.top_p") == 0.9
    assert meta.hyperparameters.get("generation.max_new_tokens") == 512


def test_read_huggingface_description_from_card_prose() -> None:
    card_text = "---\nlicense: mit\n---\n\nThis is a powerful language model."
    with _patch_hf_calls(card_text=card_text, card_data={"license": "mit"}):
        meta = read_huggingface("org/model")
    assert meta.description is not None
    assert "powerful language model" in meta.description


def test_read_huggingface_provenance_populated() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert "name" in meta.provenance
    assert "type_of_model" in meta.provenance
    assert "architecture" in meta.provenance
    assert "license" in meta.provenance


# ---------------------------------------------------------------------------
# extra_data slot
# ---------------------------------------------------------------------------


def test_read_huggingface_extra_data_contains_hf_url() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.extra_data.get("hf.url") == (
        "https://huggingface.co/mistralai/Mistral-7B-v0.1"
    )


def test_read_huggingface_extra_data_contains_model_id() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.extra_data.get("hf.model_id") == "mistralai/Mistral-7B-v0.1"


def test_read_huggingface_extra_data_contains_author() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.extra_data.get("hf.author") == "mistralai"


def test_read_huggingface_extra_data_contains_sha() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.extra_data.get("hf.sha") == "deadbeef"


def test_read_huggingface_extra_data_tokenizer_class() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.extra_data.get("hf.tokenizer_class") == "LlamaTokenizer"


def test_read_huggingface_extra_data_tokenizer_max_length() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.extra_data.get("hf.tokenizer_max_length") == 32768


def test_read_huggingface_extra_data_unlimited_max_length_omitted() -> None:
    tokenizer_config = {
        "tokenizer_class": "LlamaTokenizer",
        "model_max_length": 1_000_000_000_000_000_019_884_624_838_656,
    }
    with _patch_hf_calls(tokenizer_config=tokenizer_config):
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert "hf.tokenizer_max_length" not in meta.extra_data


def test_read_huggingface_extra_data_library_name() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.extra_data.get("hf.library_name") == "transformers"


# ---------------------------------------------------------------------------
# extra_lists slot
# ---------------------------------------------------------------------------


def test_read_huggingface_extra_lists_language_codes() -> None:
    # Language codes go to extra_lists, not domain
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.extra_lists.get("hf.language") == ["en"]


def test_read_huggingface_extra_lists_specific_tags() -> None:
    # Model-specific tags (non-domain) go to extra_lists["hf.tags"]
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "pretrained" in tags
    # Broad domain tag should NOT also appear in extra_lists
    assert "text-generation" not in tags


def test_read_huggingface_domain_tags_not_duplicated_in_extra_lists() -> None:
    # "text-generation" is a domain tag -> stays in usage.domains only
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert "text-generation" in meta.usage.domains
    assert "text-generation" not in meta.extra_lists.get("hf.tags", [])


# ---------------------------------------------------------------------------
# OpenThaiGPT model profile (multilingual + custom license + model-index)
# ---------------------------------------------------------------------------


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


def test_openthaigpt_name() -> None:
    with _patch_openthaigpt():
        meta = read_huggingface("openthaigpt/openthaigpt-r1-32b-instruct")
    assert meta.name == "openthaigpt-r1-32b-instruct"


def test_openthaigpt_architecture() -> None:
    with _patch_openthaigpt():
        meta = read_huggingface("openthaigpt/openthaigpt-r1-32b-instruct")
    assert meta.architecture == "Qwen2ForCausalLM"
    assert meta.type_of_model == "qwen2"


def test_openthaigpt_multilingual_in_extra_lists() -> None:
    with _patch_openthaigpt():
        meta = read_huggingface("openthaigpt/openthaigpt-r1-32b-instruct")
    languages = meta.extra_lists.get("hf.language", [])
    assert "th" in languages
    assert "en" in languages


def test_openthaigpt_vague_license_not_propagated() -> None:
    # "other" is a vague HF sentinel - not surfaced as the license field.
    with _patch_openthaigpt():
        meta = read_huggingface("openthaigpt/openthaigpt-r1-32b-instruct")
    assert meta.license is None


def test_openthaigpt_vague_license_preserved_in_extra_data() -> None:
    # Raw "other" is stored in extra_data for consumer reference.
    with _patch_openthaigpt():
        meta = read_huggingface("openthaigpt/openthaigpt-r1-32b-instruct")
    assert meta.extra_data.get("hf.license_raw") == "other"


def test_openthaigpt_secondary_license_name_in_extra_data() -> None:
    with _patch_openthaigpt():
        meta = read_huggingface("openthaigpt/openthaigpt-r1-32b-instruct")
    assert meta.extra_data.get("hf.license_name") == "qwen"


def test_openthaigpt_specific_tags_in_extra_lists() -> None:
    with _patch_openthaigpt():
        meta = read_huggingface("openthaigpt/openthaigpt-r1-32b-instruct")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "openthaigpt" in tags
    assert "qwen" in tags
    assert "reasoning" in tags


def test_openthaigpt_model_index_in_extra_data() -> None:
    with _patch_openthaigpt():
        meta = read_huggingface("openthaigpt/openthaigpt-r1-32b-instruct")
    model_index = meta.extra_data.get("hf.model_index")
    assert model_index is not None
    assert isinstance(model_index, list)
    assert model_index[0]["name"] == "openthaigpt-r1-32b-instruct"


def test_openthaigpt_domain_from_pipeline_tag() -> None:
    with _patch_openthaigpt():
        meta = read_huggingface("openthaigpt/openthaigpt-r1-32b-instruct")
    assert "text-generation" in meta.usage.domains


# ---------------------------------------------------------------------------
# Robustness: missing sources
# ---------------------------------------------------------------------------


def test_read_huggingface_missing_config_does_not_raise() -> None:
    with _patch_hf_calls(config=None):
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert isinstance(meta, AiModelMetadata)
    assert meta.type_of_model is None
    assert meta.architecture is None
    assert not meta.hyperparameters


def test_read_huggingface_missing_card_does_not_raise() -> None:
    with _patch_hf_calls(card_text=None, card_data={}):
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert isinstance(meta, AiModelMetadata)
    assert meta.license is None
    assert not meta.datasets


# ---------------------------------------------------------------------------
# License: file-based detection
# ---------------------------------------------------------------------------


def test_license_from_file_when_card_has_none() -> None:
    # When model card has no license field, license files are checked.
    card_data = _make_card_data(license=None, pipeline_tag="text-generation")
    with _patch_hf_calls(card_data=card_data):
        with patch(
            "pitloom.extract._huggingface._detect_license_from_hf_files",
            return_value=(
                "Apache-2.0",
                "Source: Hugging Face Hub "
                "| File: LICENSE "
                "| Method: licenseid_detection",
            ),
        ):
            meta = read_huggingface("org/model")
    assert meta.license == "Apache-2.0"
    assert "licenseid_detection" in (meta.provenance.get("license") or "")


def test_license_from_file_when_card_says_other() -> None:
    # "other" triggers file detection; detected value replaces the vague sentinel.
    card_data = _make_card_data(license="other")
    with _patch_hf_calls(card_data=card_data):
        with patch(
            "pitloom.extract._huggingface._detect_license_from_hf_files",
            return_value=(
                "MIT",
                "Source: Hugging Face Hub "
                "| File: LICENSE "
                "| Method: licenseid_detection",
            ),
        ):
            meta = read_huggingface("org/model")
    assert meta.license == "MIT"
    # Raw vague value still stored for transparency
    assert meta.extra_data.get("hf.license_raw") == "other"


def test_vague_license_raw_not_stored_when_card_has_real_spdx_id() -> None:
    # A proper SPDX ID in the card YAML should NOT create hf.license_raw.
    with _patch_hf_calls():  # uses apache-2.0 card data
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert "hf.license_raw" not in meta.extra_data


def test_license_detection_not_called_when_card_has_real_spdx_id() -> None:
    # File detection must be skipped entirely when card YAML already has a valid ID.
    mock_detect = MagicMock(return_value=(None, None))
    with _patch_hf_calls():
        with patch(
            "pitloom.extract._huggingface._detect_license_from_hf_files", mock_detect
        ):
            read_huggingface("mistralai/Mistral-7B-v0.1")
    mock_detect.assert_not_called()


def test_license_remains_none_when_file_detection_also_fails() -> None:
    # Neither card YAML nor file detection -> license is None (not a vague string).
    card_data = _make_card_data(license=None)
    with _patch_hf_calls(card_data=card_data):
        # _detect_license_from_hf_files already mocked to (None, None) in base helper
        meta = read_huggingface("org/model")
    assert meta.license is None


def test_detect_license_from_hf_files_returns_none_on_empty_file(
    tmp_path: Any,
) -> None:
    # Empty licence file should not produce a match.
    with patch(
        "pitloom.extract._huggingface._list_license_files_in_repo",
        return_value=["LICENSE"],
    ):
        empty_file = tmp_path / "LICENSE"
        empty_file.write_text("", encoding="utf-8")
        with patch("huggingface_hub.hf_hub_download", return_value=str(empty_file)):
            detected_id, _ = _detect_license_from_hf_files("org/model")
    assert detected_id is None


def test_read_huggingface_invalid_source_raises() -> None:
    with pytest.raises(ValueError, match="Not a valid Hugging Face"):
        read_huggingface("/path/to/not/a/hf/model")


def test_read_huggingface_no_huggingface_hub_raises() -> None:
    original = sys.modules.get("huggingface_hub")
    sys.modules["huggingface_hub"] = None  # type: ignore[assignment]
    try:
        with pytest.raises(ImportError, match="huggingface_hub"):
            read_huggingface("mistralai/Mistral-7B-v0.1")
    finally:
        if original is None:
            del sys.modules["huggingface_hub"]
        else:
            sys.modules["huggingface_hub"] = original


# ===========================================================================
# Model zoo: varied real-world profiles (all mocked, no network calls)
# ===========================================================================
#
# Each fixture captures the real card/config data observed from Hugging Face Hub
# on 2026-05-08.  They exercise distinct characteristics:
#
#   Kokoro-82M          - TTS, custom config schema (no model_type/architectures)
#   starcoder2-3b       - code model, training dataset, non-standard license
#   whisper-large-v3    - 99 languages including YAML boolean False for "no"
#   Kimi-K2.6           - multimodal, license="other" -> file detection path
#   gemma-2b            - gated repo (no config.json), proprietary-style license
#   Llama-3.2-1B        - gated repo (no config.json), multilingual, has LICENSE.txt
#   DeepSeek-R1         - no pipeline_tag, MIT, has LICENSE file
#   Gemma-SEA-LION GGUF - GGUF-only repo, no config.json, SEA multilingual
#   SeaLLMs-v3-7B-Chat  - SEA multilingual, license="other", no pipeline_tag
#   typhoon-7b          - Thai-language, mistral base, has LICENSE.txt
# ===========================================================================


# ---------------------------------------------------------------------------
# hexgrad/Kokoro-82M  - TTS, custom non-transformer config format
# ---------------------------------------------------------------------------

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


def test_kokoro_name() -> None:
    with _patch_kokoro():
        meta = read_huggingface("hexgrad/Kokoro-82M")
    assert meta.name == "Kokoro-82M"


def test_kokoro_license() -> None:
    with _patch_kokoro():
        meta = read_huggingface("hexgrad/Kokoro-82M")
    assert meta.license == "apache-2.0"


def test_kokoro_tts_domain() -> None:
    with _patch_kokoro():
        meta = read_huggingface("hexgrad/Kokoro-82M")
    assert "text-to-speech" in meta.usage.domains


def test_kokoro_no_model_type_when_custom_config() -> None:
    # Custom config without model_type/architectures -> both fields are None
    with _patch_kokoro():
        meta = read_huggingface("hexgrad/Kokoro-82M")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_kokoro_hyperparameters_from_custom_config() -> None:
    # Known numeric fields in custom config are still extracted as hyperparameters
    # (none of the standard _HYPER_KEYS match, so hyperparameters should be empty)
    with _patch_kokoro():
        meta = read_huggingface("hexgrad/Kokoro-82M")
    # Kokoro config has no standard keys -> empty hyperparameters
    assert not meta.hyperparameters


# ---------------------------------------------------------------------------
# bigcode/starcoder2-3b  - code model, training dataset, non-standard license
# ---------------------------------------------------------------------------

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


def test_starcoder2_architecture() -> None:
    with _patch_starcoder2():
        meta = read_huggingface("bigcode/starcoder2-3b")
    assert meta.type_of_model == "starcoder2"
    assert meta.architecture == "Starcoder2ForCausalLM"


def test_starcoder2_non_standard_license_passed_through() -> None:
    # "bigcode-openrail-m" is not in _VAGUE_LICENSE_VALUES -> used directly
    with _patch_starcoder2():
        meta = read_huggingface("bigcode/starcoder2-3b")
    assert meta.license == "bigcode-openrail-m"


def test_starcoder2_training_dataset() -> None:
    with _patch_starcoder2():
        meta = read_huggingface("bigcode/starcoder2-3b")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "bigcode/the-stack-v2-train" in ds_names


def test_starcoder2_code_tag_in_domain() -> None:
    # "code" is in _DOMAIN_TAGS -> goes to usage.domains, NOT to extra_lists["hf.tags"]
    with _patch_starcoder2():
        meta = read_huggingface("bigcode/starcoder2-3b")
    assert "code" in meta.usage.domains
    assert "code" not in meta.extra_lists.get("hf.tags", [])


def test_starcoder2_no_language_codes_when_card_has_none() -> None:
    with _patch_starcoder2():
        meta = read_huggingface("bigcode/starcoder2-3b")
    assert "hf.language" not in meta.extra_lists


# ---------------------------------------------------------------------------
# openai/whisper-large-v3  - ASR, 99 languages, YAML boolean False for "no"
# ---------------------------------------------------------------------------

_WHISPER_CONFIG: dict[str, Any] = {
    "model_type": "whisper",
    "architectures": ["WhisperForConditionalGeneration"],
    "vocab_size": 51865,
    "num_hidden_layers": 32,
    "max_source_positions": 1500,
}

# Whisper card has 99 language codes - "no" (Norwegian) is parsed by YAML 1.1
# as the Python boolean False.  All other entries are valid string codes.
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


def test_whisper_architecture() -> None:
    with _patch_whisper():
        meta = read_huggingface("openai/whisper-large-v3")
    assert meta.type_of_model == "whisper"
    assert meta.architecture == "WhisperForConditionalGeneration"


def test_whisper_asr_domain() -> None:
    with _patch_whisper():
        meta = read_huggingface("openai/whisper-large-v3")
    assert "automatic-speech-recognition" in meta.usage.domains


def test_whisper_boolean_false_filtered_from_languages() -> None:
    # The YAML boolean False (from "no" = Norwegian) must not appear in the
    # language list as the string "False" - it must be silently dropped.
    with _patch_whisper():
        meta = read_huggingface("openai/whisper-large-v3")
    languages = meta.extra_lists.get("hf.language", [])
    assert "False" not in languages
    assert False not in languages


def test_whisper_valid_languages_preserved() -> None:
    with _patch_whisper():
        meta = read_huggingface("openai/whisper-large-v3")
    languages = meta.extra_lists.get("hf.language", [])
    assert "en" in languages
    assert "th" in languages
    assert "zh" in languages


def test_whisper_audio_tag_in_extra_lists() -> None:
    with _patch_whisper():
        meta = read_huggingface("openai/whisper-large-v3")
    # "audio" is not a domain tag -> goes to extra_lists["hf.tags"]
    assert "audio" in meta.extra_lists.get("hf.tags", [])


# ---------------------------------------------------------------------------
# moonshotai/Kimi-K2.6  - multimodal, license="other", has LICENSE file
# ---------------------------------------------------------------------------

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


def test_kimi_architecture() -> None:
    with _patch_kimi():
        meta = read_huggingface("moonshotai/Kimi-K2.6")
    assert meta.type_of_model == "kimi_k25"
    assert meta.architecture == "KimiK25ForConditionalGeneration"


def test_kimi_vague_license_triggers_file_detection() -> None:
    detected_mock = MagicMock(
        return_value=(
            "MIT",
            "Source: Hugging Face Hub | File: LICENSE | Method: licenseid_detection",
        )
    )
    with _patch_kimi():
        with patch(
            "pitloom.extract._huggingface._detect_license_from_hf_files", detected_mock
        ):
            meta = read_huggingface("moonshotai/Kimi-K2.6")
    detected_mock.assert_called_once_with("moonshotai/Kimi-K2.6")
    assert meta.license == "MIT"
    assert meta.extra_data.get("hf.license_raw") == "other"


def test_kimi_multimodal_domain() -> None:
    with _patch_kimi():
        meta = read_huggingface("moonshotai/Kimi-K2.6")
    assert "image-text-to-text" in meta.usage.domains


# ---------------------------------------------------------------------------
# google/gemma-2b  - gated repo (no config.json), proprietary-style license
# ---------------------------------------------------------------------------

_GEMMA_CARD_DATA = _make_card_data(
    license="gemma",  # Non-standard but passes SPDX ID regex -> not vague
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


def test_gemma_name() -> None:
    with _patch_gemma():
        meta = read_huggingface("google/gemma-2b")
    assert meta.name == "gemma-2b"


def test_gemma_proprietary_license_used_directly() -> None:
    # "gemma" is not in _VAGUE_LICENSE_VALUES - used as-is
    with _patch_gemma():
        meta = read_huggingface("google/gemma-2b")
    assert meta.license == "gemma"
    assert "hf.license_raw" not in meta.extra_data


def test_gemma_no_architecture_when_gated_config() -> None:
    with _patch_gemma():
        meta = read_huggingface("google/gemma-2b")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_gemma_no_domain_when_no_pipeline_tag() -> None:
    with _patch_gemma():
        meta = read_huggingface("google/gemma-2b")
    assert not meta.usage.domains


# ---------------------------------------------------------------------------
# meta-llama/Llama-3.2-1B  - gated, multilingual, custom license, LICENSE.txt
# ---------------------------------------------------------------------------

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


def test_llama_custom_license_used_directly() -> None:
    # "llama3.2" matches SPDX ID regex - treated as a license identifier
    with _patch_llama():
        meta = read_huggingface("meta-llama/Llama-3.2-1B")
    assert meta.license == "llama3.2"


def test_llama_multilingual_in_extra_lists() -> None:
    with _patch_llama():
        meta = read_huggingface("meta-llama/Llama-3.2-1B")
    languages = meta.extra_lists.get("hf.language", [])
    for lang in ("en", "de", "fr", "it", "pt", "hi", "es", "th"):
        assert lang in languages


def test_llama_model_specific_tags_in_extra_lists() -> None:
    with _patch_llama():
        meta = read_huggingface("meta-llama/Llama-3.2-1B")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "llama" in tags
    assert "llama-3" in tags
    assert "facebook" in tags


def test_llama_no_architecture_when_gated() -> None:
    with _patch_llama():
        meta = read_huggingface("meta-llama/Llama-3.2-1B")
    assert meta.type_of_model is None
    assert meta.architecture is None


# ---------------------------------------------------------------------------
# deepseek-ai/DeepSeek-R1  - MIT, no pipeline_tag, has LICENSE file
# ---------------------------------------------------------------------------

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


def test_deepseek_architecture() -> None:
    with _patch_deepseek():
        meta = read_huggingface("deepseek-ai/DeepSeek-R1")
    assert meta.type_of_model == "deepseek_v3"
    assert meta.architecture == "DeepseekV3ForCausalLM"


def test_deepseek_mit_license() -> None:
    with _patch_deepseek():
        meta = read_huggingface("deepseek-ai/DeepSeek-R1")
    assert meta.license == "mit"


def test_deepseek_no_domain_when_no_pipeline_tag() -> None:
    with _patch_deepseek():
        meta = read_huggingface("deepseek-ai/DeepSeek-R1")
    assert not meta.usage.domains


def test_deepseek_hyperparameters() -> None:
    with _patch_deepseek():
        meta = read_huggingface("deepseek-ai/DeepSeek-R1")
    assert meta.hyperparameters.get("vocab_size") == 129280
    assert meta.hyperparameters.get("num_hidden_layers") == 61


# ---------------------------------------------------------------------------
# aisingapore/Gemma-SEA-LION-v4-4B-VL-GGUF  - GGUF-only repo, SEA languages
# ---------------------------------------------------------------------------
# This repo contains only GGUF files and no config.json.
# It exercises the "no config" + "gemma license" + SEA multilingual path.

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


def test_sealion_gguf_name() -> None:
    with _patch_sealion_gguf():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-4B-VL-GGUF")
    assert meta.name == "Gemma-SEA-LION-v4-4B-VL-GGUF"


def test_sealion_gguf_sea_languages() -> None:
    with _patch_sealion_gguf():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-4B-VL-GGUF")
    languages = meta.extra_lists.get("hf.language", [])
    for lang in ("en", "th", "id", "vi", "ms", "my", "ta", "zh", "fil"):
        assert lang in languages, f"{lang!r} missing from hf.language"


def test_sealion_gguf_no_architecture_without_config() -> None:
    with _patch_sealion_gguf():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-4B-VL-GGUF")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_sealion_gguf_gemma_license() -> None:
    with _patch_sealion_gguf():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-4B-VL-GGUF")
    assert meta.license == "gemma"


# ---------------------------------------------------------------------------
# SeaLLMs/SeaLLMs-v3-7B-Chat  - SEA multilingual, license="other", qwen2 base
# ---------------------------------------------------------------------------

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


def test_seallms_architecture() -> None:
    with _patch_seallms():
        meta = read_huggingface("SeaLLMs/SeaLLMs-v3-7B-Chat")
    assert meta.type_of_model == "qwen2"
    assert meta.architecture == "Qwen2ForCausalLM"


def test_seallms_sea_languages() -> None:
    with _patch_seallms():
        meta = read_huggingface("SeaLLMs/SeaLLMs-v3-7B-Chat")
    languages = meta.extra_lists.get("hf.language", [])
    for lang in (
        "en",
        "th",
        "id",
        "vi",
        "ms",
        "tl",
        "ta",
        "zh",
        "lo",
        "km",
        "jv",
        "my",
    ):
        assert lang in languages, f"{lang!r} missing from hf.language"


def test_seallms_vague_license_not_propagated() -> None:
    with _patch_seallms():
        meta = read_huggingface("SeaLLMs/SeaLLMs-v3-7B-Chat")
    assert meta.license is None
    assert meta.extra_data.get("hf.license_raw") == "other"


def test_seallms_specific_tags_in_extra_lists() -> None:
    # "sea" and "multilingual" are not standard domain tags
    with _patch_seallms():
        meta = read_huggingface("SeaLLMs/SeaLLMs-v3-7B-Chat")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "sea" in tags
    assert "multilingual" in tags


def test_seallms_no_domain_without_pipeline_tag() -> None:
    with _patch_seallms():
        meta = read_huggingface("SeaLLMs/SeaLLMs-v3-7B-Chat")
    assert not meta.usage.domains


# ---------------------------------------------------------------------------
# typhoon-ai/typhoon-7b  - Thai-language, mistral base, has LICENSE.txt
# ---------------------------------------------------------------------------

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


def test_typhoon_architecture() -> None:
    with _patch_typhoon():
        meta = read_huggingface("typhoon-ai/typhoon-7b")
    assert meta.type_of_model == "mistral"
    assert meta.architecture == "MistralForCausalLM"


def test_typhoon_thai_language() -> None:
    with _patch_typhoon():
        meta = read_huggingface("typhoon-ai/typhoon-7b")
    languages = meta.extra_lists.get("hf.language", [])
    assert languages == ["th"]


def test_typhoon_license() -> None:
    with _patch_typhoon():
        meta = read_huggingface("typhoon-ai/typhoon-7b")
    assert meta.license == "apache-2.0"


def test_typhoon_grouped_query_attention_hyperparameter() -> None:
    # num_key_value_heads < num_attention_heads -> GQA
    with _patch_typhoon():
        meta = read_huggingface("typhoon-ai/typhoon-7b")
    assert meta.hyperparameters.get("num_key_value_heads") == 8
    assert meta.hyperparameters.get("num_attention_heads") == 32


def test_typhoon_pretrained_tag_in_extra_lists() -> None:
    with _patch_typhoon():
        meta = read_huggingface("typhoon-ai/typhoon-7b")
    assert "pretrained" in meta.extra_lists.get("hf.tags", [])


# ---------------------------------------------------------------------------
# UBC-NLP/serengeti-E250  - no model card, electra, 250K-vocab African-language
# ---------------------------------------------------------------------------
# serengeti-E250 has no README.md / model card on the Hub (ModelCard.load()
# returns an error).  All domain/language information lives only in
# model_info().tags (e.g. the 26 African ISO codes and pipeline_tag="fill-mask"),
# but the current extractor reads those fields from card YAML, not from the
# model_info response.  This fixture documents that gap: when there is no card,
# usage.domains and extra_lists["hf.language"] are empty even though the Hub
# API has the data in model_info.
#
# What IS captured comes from config.json:
#   model_type="electra", architectures=["ElectraModel"], vocab_size=250000
# and from tokenizer_config.json:
#   tokenizer_class="ElectraTokenizer" (model_max_length is the unlimited sentinel
#   1e30 and is therefore filtered out).

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

# tokenizer_config.json is present but model_max_length is the "unlimited"
# sentinel (10^30) - the extractor filters it out.
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


def test_serengeti_name() -> None:
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert meta.name == "serengeti-E250"


def test_serengeti_electra_type_and_architecture() -> None:
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert meta.type_of_model == "electra"
    assert meta.architecture == "ElectraModel"


def test_serengeti_large_multilingual_vocab() -> None:
    # 250 000-token vocabulary designed for African-language coverage
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert meta.hyperparameters.get("vocab_size") == 250000


def test_serengeti_no_domain_when_no_card() -> None:
    # pipeline_tag="fill-mask" exists in model_info.tags but the extractor
    # reads it from card YAML - absent card -> empty domains.
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert not meta.usage.domains


def test_serengeti_no_language_when_no_card() -> None:
    # 26 African ISO language codes are in model_info.tags but are not
    # extracted when there is no model card.
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert "hf.language" not in meta.extra_lists


def test_serengeti_no_license_when_no_card_and_no_file() -> None:
    # No card license + file detection mock returns nothing -> license is None.
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert meta.license is None


def test_serengeti_tokenizer_class_from_tokenizer_config() -> None:
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert meta.extra_data.get("hf.tokenizer_class") == "ElectraTokenizer"


def test_serengeti_unlimited_tokenizer_max_length_filtered() -> None:
    # The sentinel value (1e30) must NOT appear in extra_data.
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert "hf.tokenizer_max_length" not in meta.extra_data


# ---------------------------------------------------------------------------
# CohereLabs/aya-vision-8b  - gated multimodal, cc-by-nc-4.0 only in model_info
# ---------------------------------------------------------------------------
# aya-vision-8b is a gated multimodal (image-text-to-text) model.  Access
# to config.json and the model card text requires authentication, so both
# _safe_load_json("config.json") and _load_model_card() return empty results.
#
# The Hub API (model_info) does report license="cc-by-nc-4.0" and 23 language
# codes in model_info.card_data - but the current extractor reads those fields
# from the ModelCard YAML, not from the model_info response.  As a result,
# license and language are not captured for fully gated repos.
#
# This fixture documents that known limitation: when both the model card and
# config.json are inaccessible, the extractor returns a metadata object that
# is nearly empty except for the name derived from the model ID.
#
# If/when _load_model_info is extended to also extract license and language
# from model_info.card_data, these tests should be updated accordingly.


def _patch_aya_vision() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated - config.json returns 401
        tokenizer_config=None,  # Gated
        card_data={},  # Gated - ModelCard.load() returns error
        hub_info={"author": "CohereLabs"},
        # _detect_license_from_hf_files also returns (None, None) because
        # list_repo_files may succeed but license file downloads are gated.
    )


def test_aya_vision_name() -> None:
    with _patch_aya_vision():
        meta = read_huggingface("CohereLabs/aya-vision-8b")
    assert meta.name == "aya-vision-8b"


def test_aya_vision_no_architecture_when_gated() -> None:
    with _patch_aya_vision():
        meta = read_huggingface("CohereLabs/aya-vision-8b")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_aya_vision_no_domain_when_gated() -> None:
    # pipeline_tag="image-text-to-text" is in model_info but not extracted
    # when the card is inaccessible.
    with _patch_aya_vision():
        meta = read_huggingface("CohereLabs/aya-vision-8b")
    assert not meta.usage.domains


def test_aya_vision_no_license_when_gated() -> None:
    # model_info reports license="cc-by-nc-4.0" but the extractor reads
    # license from card YAML -> absent card -> license is None.
    # This test documents a known gap: license is only captured when the
    # model card YAML is accessible or a license file can be downloaded.
    with _patch_aya_vision():
        meta = read_huggingface("CohereLabs/aya-vision-8b")
    assert meta.license is None


def test_aya_vision_no_language_when_gated() -> None:
    # 23 languages are listed in model_info.card_data.language but are
    # not captured when the card is inaccessible.
    with _patch_aya_vision():
        meta = read_huggingface("CohereLabs/aya-vision-8b")
    assert "hf.language" not in meta.extra_lists


def test_aya_vision_extra_data_has_hf_url() -> None:
    # Even for fully gated models, the HF URL is always populated.
    with _patch_aya_vision():
        meta = read_huggingface("CohereLabs/aya-vision-8b")
    assert (
        meta.extra_data.get("hf.url")
        == "https://huggingface.co/CohereLabs/aya-vision-8b"
    )
    assert meta.extra_data.get("hf.model_id") == "CohereLabs/aya-vision-8b"


# ---------------------------------------------------------------------------
# lelapa/InkubaLM-0.4B  - gated African LLM, cc-by-nc-4.0, Inkuba-Mono dataset
# ---------------------------------------------------------------------------
# InkubaLM-0.4B is a small (0.4 B parameter) African-language LLM covering
# English, Swahili, Zulu, Xhosa, Hausa, and Yoruba.  The repo is gated:
# both config.json and the model card README.md return 401.
#
# Like CohereLabs/aya-vision-8b, the model_info() API response does expose
# useful metadata (license="cc-by-nc-4.0", six language codes, and a dataset
# reference to "lelapa/Inkuba-Mono") - but the extractor reads those fields
# from the ModelCard YAML and config.json, not from the model_info response.
#
# Additional gap: the tags list contains a "dataset:lelapa/Inkuba-Mono" entry
# using the Hub's prefix-tag convention for dataset links.  The extractor does
# not parse this tag form, so no DatasetReference is produced even though the
# dataset is encoded in model_info.
#
# Result: the extractor returns only name + hub provenance fields.


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


def test_inkubalm_name() -> None:
    with _patch_inkubalm():
        meta = read_huggingface("lelapa/InkubaLM-0.4B")
    assert meta.name == "InkubaLM-0.4B"


def test_inkubalm_no_architecture_when_gated() -> None:
    with _patch_inkubalm():
        meta = read_huggingface("lelapa/InkubaLM-0.4B")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_inkubalm_no_license_when_gated() -> None:
    # model_info reports cc-by-nc-4.0 but the extractor reads license from
    # card YAML only - absent card -> license is None.
    with _patch_inkubalm():
        meta = read_huggingface("lelapa/InkubaLM-0.4B")
    assert meta.license is None


def test_inkubalm_no_african_languages_when_gated() -> None:
    # model_info reports ["en", "sw", "zu", "xh", "ha", "yo"] but they are
    # not captured when the card is inaccessible (language codes appear in
    # model_info.tags but are not extracted - only language: field from card YAML is).
    with _patch_inkubalm():
        meta = read_huggingface("lelapa/InkubaLM-0.4B")
    assert "hf.language" not in meta.extra_lists


def test_inkubalm_dataset_from_model_info_tags() -> None:
    # Even when the card is gated, the extractor falls back to "dataset:*"
    # prefix tags in model_info to populate datasets.
    with _patch_inkubalm():
        meta = read_huggingface("lelapa/InkubaLM-0.4B")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "lelapa/Inkuba-Mono" in ds_names


# ---------------------------------------------------------------------------
# facebook/nllb-200-distilled-600M  - 200-language translation, no card
# ---------------------------------------------------------------------------
# NLLB-200 (No Language Left Behind) is a seq2seq translation model covering
# 200 languages.  Like serengeti-E250, ModelCard.load() returns an error
# (no README.md), but config.json IS publicly accessible.
#
# Interesting contrasts with other "no card" fixtures:
#
# * Architecture: m2m_100 (encoder-decoder), M2M100ForConditionalGeneration -
#   unlike serengeti's encoder-only ElectraModel.
# * Vocabulary: 256 206 tokens (the largest of any fixture) for broad
#   multilingual coverage.
# * Tokenizer: NllbTokenizer with a real model_max_length of 1 024 - unlike
#   serengeti's unlimited sentinel, this value IS captured as
#   extra_data["hf.tokenizer_max_length"].
# * Hyperparameter gap: m2m_100's config uses "d_model" (not "hidden_size")
#   and "encoder_layers"/"decoder_layers" (not "num_hidden_layers" alone).
#   Keys not in _HYPER_KEYS are silently skipped, so d_model=1024 and the
#   per-stack layer counts are absent from hyperparameters.
# * Domain/language gap: "translation", "text2text-generation", and 200 ISO
#   language codes live only in model_info.tags - not captured without a card.

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


def test_nllb_m2m100_architecture() -> None:
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert meta.type_of_model == "m2m_100"
    assert meta.architecture == "M2M100ForConditionalGeneration"


def test_nllb_large_multilingual_vocab() -> None:
    # 256 206-token vocabulary for 200-language coverage
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert meta.hyperparameters.get("vocab_size") == 256206


def test_nllb_num_hidden_layers_captured() -> None:
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert meta.hyperparameters.get("num_hidden_layers") == 12


def test_nllb_d_model_not_in_hyperparameters() -> None:
    # "d_model" is the m2m_100 hidden-dimension key but is not in _HYPER_KEYS
    # (which looks for "hidden_size") - silently skipped.
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert "d_model" not in meta.hyperparameters


def test_nllb_tokenizer_real_max_length_captured() -> None:
    # model_max_length=1024 is a real limit (below the unlimited sentinel)
    # and must appear in extra_data - contrast with serengeti's filtered value.
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert meta.extra_data.get("hf.tokenizer_max_length") == 1024
    assert meta.extra_data.get("hf.tokenizer_class") == "NllbTokenizer"


def test_nllb_no_domain_when_no_card() -> None:
    # "translation" and "text2text-generation" are domain tags but live only
    # in model_info.tags - not captured when there is no model card.
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert not meta.usage.domains


def test_nllb_no_language_when_no_card() -> None:
    # 200 language codes are in model_info.tags but not captured without a card.
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert "hf.language" not in meta.extra_lists


# ===========================================================================
# NEW MODEL BATCH - 47 models covering new patterns introduced in this round
# ===========================================================================

# ---------------------------------------------------------------------------
# PATTERN: language field is a scalar string, not a list
# YAML 1.1 allows "language: ja" (scalar). Previously the extractor would
# iterate over the string character-by-character; fix wraps it in a list.
# ---------------------------------------------------------------------------

# sonoisa/sentence-bert-base-ja-mean-tokens
# Japanese sentence embedding model; card has `language: ja` (scalar string).
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


def test_sonoisa_language_scalar_string_normalised() -> None:
    # "ja" as a scalar must be stored as ["ja"], not as individual chars ["j","a"].
    with _patch_sonoisa():
        meta = read_huggingface("sonoisa/sentence-bert-base-ja-mean-tokens")
    assert meta.extra_lists.get("hf.language") == ["ja"]


def test_sonoisa_feature_extraction_domain() -> None:
    with _patch_sonoisa():
        meta = read_huggingface("sonoisa/sentence-bert-base-ja-mean-tokens")
    assert "feature-extraction" in meta.usage.domains


def test_sonoisa_sentence_bert_tags_in_extra_lists() -> None:
    # "sentence-bert" is not a domain tag -> extra_lists["hf.tags"]
    with _patch_sonoisa():
        meta = read_huggingface("sonoisa/sentence-bert-base-ja-mean-tokens")
    assert "sentence-bert" in meta.extra_lists.get("hf.tags", [])


# jonatasgrosman/wav2vec2-large-xlsr-53-japanese
# Japanese ASR; card has `language: ja` (scalar) and a model-index with eval results.
# model_info carries a doi: tag.
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


def test_wav2vec2_jp_language_scalar_normalised() -> None:
    with _patch_wav2vec2_jp():
        meta = read_huggingface("jonatasgrosman/wav2vec2-large-xlsr-53-japanese")
    assert meta.extra_lists.get("hf.language") == ["ja"]


def test_wav2vec2_jp_doi_extracted() -> None:
    with _patch_wav2vec2_jp():
        meta = read_huggingface("jonatasgrosman/wav2vec2-large-xlsr-53-japanese")
    assert meta.extra_data.get("hf.doi") == "10.57967/hf/3568"


def test_wav2vec2_jp_model_index_in_extra_data() -> None:
    with _patch_wav2vec2_jp():
        meta = read_huggingface("jonatasgrosman/wav2vec2-large-xlsr-53-japanese")
    assert meta.extra_data.get("hf.model_index") is not None


def test_wav2vec2_jp_asr_domain() -> None:
    with _patch_wav2vec2_jp():
        meta = read_huggingface("jonatasgrosman/wav2vec2-large-xlsr-53-japanese")
    assert "automatic-speech-recognition" in meta.usage.domains


# ---------------------------------------------------------------------------
# PATTERN: base_model extraction from card YAML + relation from model_info tags
# ---------------------------------------------------------------------------

# airesearch/WangchanX-Legal-ThaiCCL-Retriever
# Thai legal retrieval; fine-tuned from BAAI/bge-m3; base_model in card YAML.
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


def test_wangchanx_legal_base_model_extracted() -> None:
    with _patch_wangchanx_legal():
        meta = read_huggingface("airesearch/WangchanX-Legal-ThaiCCL-Retriever")
    assert meta.extra_data.get("hf.base_model") == "BAAI/bge-m3"


def test_wangchanx_legal_base_model_relation_finetune() -> None:
    with _patch_wangchanx_legal():
        meta = read_huggingface("airesearch/WangchanX-Legal-ThaiCCL-Retriever")
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_wangchanx_legal_xlm_roberta_architecture() -> None:
    with _patch_wangchanx_legal():
        meta = read_huggingface("airesearch/WangchanX-Legal-ThaiCCL-Retriever")
    assert meta.type_of_model == "xlm-roberta"
    assert meta.architecture == "XLMRobertaModel"


def test_wangchanx_legal_dataset_reference() -> None:
    with _patch_wangchanx_legal():
        meta = read_huggingface("airesearch/WangchanX-Legal-ThaiCCL-Retriever")
    assert any("WangchanX-Legal-ThaiCCL-RAG" in d.metadata.name for d in meta.datasets)


# iapp/chinda-qwen3-4b
# Thai LLM fine-tuned from Qwen3-4B; has doi: tag in model_info.
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


def test_chinda_base_model_and_relation() -> None:
    with _patch_chinda():
        meta = read_huggingface("iapp/chinda-qwen3-4b")
    assert meta.extra_data.get("hf.base_model") == "Qwen/Qwen3-4B"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_chinda_doi_extracted() -> None:
    with _patch_chinda():
        meta = read_huggingface("iapp/chinda-qwen3-4b")
    assert meta.extra_data.get("hf.doi") == "10.57967/hf/5709"


def test_chinda_qwen3_architecture() -> None:
    with _patch_chinda():
        meta = read_huggingface("iapp/chinda-qwen3-4b")
    assert meta.type_of_model == "qwen3"
    assert meta.architecture == "Qwen3ForCausalLM"


# iapp/chinda-qwen3-4b-gguf
# GGUF quantization of chinda-qwen3-4b; no config.json in a GGUF-only repo.
# base_model is a string (not a list) in this card.
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


def test_chinda_gguf_base_model_string_form() -> None:
    # base_model as a scalar string (not a list) must still be extracted.
    with _patch_chinda_gguf():
        meta = read_huggingface("iapp/chinda-qwen3-4b-gguf")
    assert meta.extra_data.get("hf.base_model") == "iapp/chinda-qwen3-4b"


def test_chinda_gguf_quantized_relation() -> None:
    with _patch_chinda_gguf():
        meta = read_huggingface("iapp/chinda-qwen3-4b-gguf")
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"


def test_chinda_gguf_no_architecture_without_config() -> None:
    with _patch_chinda_gguf():
        meta = read_huggingface("iapp/chinda-qwen3-4b-gguf")
    assert meta.type_of_model is None


# cl-nagoya/ruri-v3-310m
# Japanese embedding model (ModernBERT); fine-tuned; has arxiv: tag.
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


def test_ruri_arxiv_extracted() -> None:
    with _patch_ruri():
        meta = read_huggingface("cl-nagoya/ruri-v3-310m")
    assert "2409.07737" in meta.extra_lists.get("hf.arxiv", [])


def test_ruri_base_model_and_relation() -> None:
    with _patch_ruri():
        meta = read_huggingface("cl-nagoya/ruri-v3-310m")
    assert meta.extra_data.get("hf.base_model") == "cl-nagoya/ruri-v3-pt-310m"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_ruri_modernbert_architecture() -> None:
    with _patch_ruri():
        meta = read_huggingface("cl-nagoya/ruri-v3-310m")
    assert meta.type_of_model == "modernbert"


# nomic-ai/nomic-embed-text-v1.5-GGUF
# - GGUF quantization of a sentence-similarity model
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


def test_nomic_gguf_base_model_quantized() -> None:
    with _patch_nomic_gguf():
        meta = read_huggingface("nomic-ai/nomic-embed-text-v1.5-GGUF")
    assert meta.extra_data.get("hf.base_model") == "nomic-ai/nomic-embed-text-v1.5"
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"


# lmg-anon/vntl-llama3-8b-v2-gguf  - Japanese->English translation GGUF; llama3 license
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


def test_vntl_quantized_translation_gguf() -> None:
    with _patch_vntl():
        meta = read_huggingface("lmg-anon/vntl-llama3-8b-v2-gguf")
    assert meta.license == "llama3"
    assert meta.extra_data.get("hf.base_model") == "rinna/llama-3-youko-8b"
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"
    assert "translation" in meta.usage.domains


# sugoitoolkit/Sugoi-14B-Ultra-GGUF  - Japanese translation GGUF; list base_model
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


def test_sugoi_gguf_base_model_list_form() -> None:
    # base_model as a list ["sugoitoolkit/Sugoi-14B-Ultra-HF"]
    # - primary entry extracted.
    with _patch_sugoi():
        meta = read_huggingface("sugoitoolkit/Sugoi-14B-Ultra-GGUF")
    assert meta.extra_data.get("hf.base_model") == "sugoitoolkit/Sugoi-14B-Ultra-HF"
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"


# talkie-lm/talkie-1930-13b-it  - no config.json; fine-tuned from talkie base
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


def test_talkie_no_config_base_model_finetune() -> None:
    with _patch_talkie():
        meta = read_huggingface("talkie-lm/talkie-1930-13b-it")
    assert meta.extra_data.get("hf.base_model") == "talkie-lm/talkie-1930-13b-base"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"
    assert meta.type_of_model is None  # no config.json


# ---------------------------------------------------------------------------
# PATTERN: new pipeline_tag values (depth-estimation, keypoint-detection, etc.)
# ---------------------------------------------------------------------------


# apple/DepthPro-hf  - monocular depth estimation; apple-amlr license (non-standard)
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


def test_depth_pro_depth_estimation_domain() -> None:
    with _patch_depth_pro():
        meta = read_huggingface("apple/DepthPro-hf")
    assert "depth-estimation" in meta.usage.domains


def test_depth_pro_architecture() -> None:
    with _patch_depth_pro():
        meta = read_huggingface("apple/DepthPro-hf")
    assert meta.type_of_model == "depth_pro"
    assert meta.architecture == "DepthProForDepthEstimation"


def test_depth_pro_non_standard_license() -> None:
    # "apple-amlr" is not in _VAGUE_LICENSE_VALUES - passed through as-is.
    with _patch_depth_pro():
        meta = read_huggingface("apple/DepthPro-hf")
    assert meta.license == "apple-amlr"


# prs-eth/marigold-depth-v1-0  - depth estimation with diffusers; no config.json
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


def test_marigold_depth_estimation_domain() -> None:
    with _patch_marigold():
        meta = read_huggingface("prs-eth/marigold-depth-v1-0")
    assert "depth-estimation" in meta.usage.domains


def test_marigold_diffusers_library() -> None:
    with _patch_marigold():
        meta = read_huggingface("prs-eth/marigold-depth-v1-0")
    assert meta.extra_data.get("hf.library_name") == "diffusers"


# usyd-community/vitpose-plus-huge  - human pose estimation; keypoint-detection
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


def test_vitpose_keypoint_detection_domain() -> None:
    with _patch_vitpose():
        meta = read_huggingface("usyd-community/vitpose-plus-huge")
    assert "keypoint-detection" in meta.usage.domains


def test_vitpose_architecture() -> None:
    with _patch_vitpose():
        meta = read_huggingface("usyd-community/vitpose-plus-huge")
    assert meta.type_of_model == "vitpose"


# jinaai/jina-embeddings-v4
# - multimodal embedding; visual-document-retrieval; no license
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


def test_jina_v4_visual_document_retrieval_domain() -> None:
    with _patch_jina_v4():
        meta = read_huggingface("jinaai/jina-embeddings-v4")
    assert "visual-document-retrieval" in meta.usage.domains


def test_jina_v4_multilingual_language() -> None:
    # "multilingual" is not an ISO code but a valid language keyword
    # - preserved.
    with _patch_jina_v4():
        meta = read_huggingface("jinaai/jina-embeddings-v4")
    assert "multilingual" in meta.extra_lists.get("hf.language", [])


def test_jina_v4_no_license() -> None:
    with _patch_jina_v4():
        meta = read_huggingface("jinaai/jina-embeddings-v4")
    assert meta.license is None


def test_jina_v4_tokenizer_max_length() -> None:
    with _patch_jina_v4():
        meta = read_huggingface("jinaai/jina-embeddings-v4")
    assert meta.extra_data.get("hf.tokenizer_max_length") == 131072


# llava-hf/LLaVA-NeXT-Video-7B-hf  - video-language model; video-text-to-text
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


def test_llava_video_text_to_text_domain() -> None:
    with _patch_llava_video():
        meta = read_huggingface("llava-hf/LLaVA-NeXT-Video-7B-hf")
    assert "video-text-to-text" in meta.usage.domains


def test_llava_image_text_tag_also_domain() -> None:
    # "image-text-to-text" in tags list is also a domain tag -> usage.domains
    with _patch_llava_video():
        meta = read_huggingface("llava-hf/LLaVA-NeXT-Video-7B-hf")
    assert "image-text-to-text" in meta.usage.domains


def test_llava_dataset_reference() -> None:
    with _patch_llava_video():
        meta = read_huggingface("llava-hf/LLaVA-NeXT-Video-7B-hf")
    assert any("VideoChatGPT" in d.metadata.name for d in meta.datasets)


# naver-clova-ix/donut-base-finetuned-docvqa  - document QA; document-question-answering
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


def test_donut_document_question_answering_domain() -> None:
    with _patch_donut():
        meta = read_huggingface("naver-clova-ix/donut-base-finetuned-docvqa")
    assert "document-question-answering" in meta.usage.domains


def test_donut_image_to_text_also_domain() -> None:
    with _patch_donut():
        meta = read_huggingface("naver-clova-ix/donut-base-finetuned-docvqa")
    assert "image-to-text" in meta.usage.domains


# impira/layoutlm-document-qa  - document QA; card has `language: en` (scalar)
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


def test_layoutlm_document_question_answering() -> None:
    with _patch_layoutlm():
        meta = read_huggingface("impira/layoutlm-document-qa")
    assert "document-question-answering" in meta.usage.domains


def test_layoutlm_language_scalar_string() -> None:
    with _patch_layoutlm():
        meta = read_huggingface("impira/layoutlm-document-qa")
    assert meta.extra_lists.get("hf.language") == ["en"]


# google/tapas-large-finetuned-wtq  - table QA; card has `language: en` (scalar)
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


def test_tapas_table_question_answering_domain() -> None:
    with _patch_tapas():
        meta = read_huggingface("google/tapas-large-finetuned-wtq")
    assert "table-question-answering" in meta.usage.domains


def test_tapas_language_scalar_string() -> None:
    with _patch_tapas():
        meta = read_huggingface("google/tapas-large-finetuned-wtq")
    assert meta.extra_lists.get("hf.language") == ["en"]


def test_tapas_dataset_reference() -> None:
    with _patch_tapas():
        meta = read_huggingface("google/tapas-large-finetuned-wtq")
    assert any("wikitablequestions" in d.metadata.name for d in meta.datasets)


# briaai/RMBG-1.4  - background removal (image segmentation); license=other
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


def test_rmbg14_image_segmentation_domain() -> None:
    with _patch_rmbg14():
        meta = read_huggingface("briaai/RMBG-1.4")
    assert "image-segmentation" in meta.usage.domains


def test_rmbg14_vague_license_not_propagated() -> None:
    with _patch_rmbg14():
        meta = read_huggingface("briaai/RMBG-1.4")
    assert meta.license is None
    assert meta.extra_data.get("hf.license_raw") == "other"


def test_rmbg14_custom_tags_in_extra_lists() -> None:
    with _patch_rmbg14():
        meta = read_huggingface("briaai/RMBG-1.4")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "remove background" in tags
    assert "legal liability" in tags


# briaai/RMBG-2.0  - gated image-segmentation model; same domain, no config
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


def test_rmbg20_gated_still_has_domain_from_card() -> None:
    # Pipeline tag is in card YAML, so domain is captured even without config.
    with _patch_rmbg20():
        meta = read_huggingface("briaai/RMBG-2.0")
    assert "image-segmentation" in meta.usage.domains
    assert meta.type_of_model is None


# briaai/Fibo-Edit-RMBG  - image-to-image background editing; has arxiv: in model_info
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


def test_fibo_edit_image_to_image_domain() -> None:
    with _patch_fibo_edit():
        meta = read_huggingface("briaai/Fibo-Edit-RMBG")
    assert "image-to-image" in meta.usage.domains


def test_fibo_edit_arxiv_extracted() -> None:
    with _patch_fibo_edit():
        meta = read_huggingface("briaai/Fibo-Edit-RMBG")
    assert "2511.06876" in meta.extra_lists.get("hf.arxiv", [])


def test_fibo_edit_base_model_relation() -> None:
    with _patch_fibo_edit():
        meta = read_huggingface("briaai/Fibo-Edit-RMBG")
    assert meta.extra_data.get("hf.base_model") == "briaai/Fibo-Edit"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


# laion/CLIP-convnext_base_w  - zero-shot image classification; no config.json
# (open_clip)
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


def test_laion_clip_zero_shot_image_classification_domain() -> None:
    with _patch_laion_clip():
        meta = read_huggingface("laion/CLIP-convnext_base_w-laion2B-s13B-b82K-augreg")
    assert "zero-shot-image-classification" in meta.usage.domains


def test_laion_clip_no_config_no_architecture() -> None:
    with _patch_laion_clip():
        meta = read_huggingface("laion/CLIP-convnext_base_w-laion2B-s13B-b82K-augreg")
    assert meta.type_of_model is None


# geolocal/StreetCLIP  - geo-localisation CLIP; zero-shot-image-classification
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


def test_streetclip_zero_shot_classification_domain() -> None:
    with _patch_streetclip():
        meta = read_huggingface("geolocal/StreetCLIP")
    assert "zero-shot-image-classification" in meta.usage.domains


def test_streetclip_clip_architecture() -> None:
    with _patch_streetclip():
        meta = read_huggingface("geolocal/StreetCLIP")
    assert meta.type_of_model == "clip"


def test_streetclip_geo_tags_in_extra_lists() -> None:
    with _patch_streetclip():
        meta = read_huggingface("geolocal/StreetCLIP")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "geolocalization" in tags


# ---------------------------------------------------------------------------
# PATTERN: image-feature-extraction pipeline tag (new domain)
# ---------------------------------------------------------------------------


# microsoft/swin-tiny-patch4-window7-224  - Swin Transformer; pipeline_tag in model_info
# only (card does not set it); dataset: imagenet-1k in model_info.tags
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


def test_swin_no_pipeline_tag_but_image_classification_from_tags() -> None:
    with _patch_swin():
        meta = read_huggingface("microsoft/swin-tiny-patch4-window7-224")
    # pipeline_tag absent in card -> domain comes from card tags
    assert "image-classification" in meta.usage.domains


def test_swin_imagenet_dataset() -> None:
    with _patch_swin():
        meta = read_huggingface("microsoft/swin-tiny-patch4-window7-224")
    assert any("imagenet-1k" in d.metadata.name for d in meta.datasets)


# microsoft/resnet-18  - ResNet image classification; similar pattern to Swin
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


def test_resnet18_architecture() -> None:
    with _patch_resnet18():
        meta = read_huggingface("microsoft/resnet-18")
    assert meta.type_of_model == "resnet"
    assert meta.architecture == "ResNetForImageClassification"


# facebook/dinov2-small  - DINOv2 self-supervised ViT; image-feature-extraction
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


def test_dinov2_image_feature_extraction_domain() -> None:
    with _patch_dinov2():
        meta = read_huggingface("facebook/dinov2-small")
    assert "image-feature-extraction" in meta.usage.domains


def test_dinov2_architecture() -> None:
    with _patch_dinov2():
        meta = read_huggingface("facebook/dinov2-small")
    assert meta.type_of_model == "dinov2"
    assert meta.architecture == "Dinov2Model"


# microsoft/rad-dino  - DINOv2 fine-tuned on radiology; no license
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


def test_rad_dino_no_license() -> None:
    with _patch_rad_dino():
        meta = read_huggingface("microsoft/rad-dino")
    assert meta.license is None


def test_rad_dino_image_feature_extraction() -> None:
    with _patch_rad_dino():
        meta = read_huggingface("microsoft/rad-dino")
    assert "image-feature-extraction" in meta.usage.domains


# MahmoodLab/UNI2-h  - gated pathology foundation model; cc-by-nc-nd-4.0; timm-based
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


def test_uni2_nc_nd_license() -> None:
    with _patch_uni2():
        meta = read_huggingface("MahmoodLab/UNI2-h")
    assert meta.license == "cc-by-nc-nd-4.0"


def test_uni2_pathology_tags_in_extra_lists() -> None:
    with _patch_uni2():
        meta = read_huggingface("MahmoodLab/UNI2-h")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "histology" in tags
    assert "pathology" in tags


# timm/convnext_large.dinov3_lvd1689m  - timm model; no config.json; license=other
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


def test_timm_convnext_vague_license() -> None:
    with _patch_timm_convnext():
        meta = read_huggingface("timm/convnext_large.dinov3_lvd1689m")
    assert meta.license is None
    assert meta.extra_data.get("hf.license_raw") == "other"


def test_timm_convnext_library_name() -> None:
    with _patch_timm_convnext():
        meta = read_huggingface("timm/convnext_large.dinov3_lvd1689m")
    assert meta.extra_data.get("hf.library_name") == "timm"


# ---------------------------------------------------------------------------
# PATTERN: robotics pipeline tag
# ---------------------------------------------------------------------------


# nvidia/GR00T-N1.7-3B  - humanoid robot foundation model; no license; sparse card
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


def test_groot_robotics_domain() -> None:
    with _patch_groot():
        meta = read_huggingface("nvidia/GR00T-N1.7-3B")
    assert "robotics" in meta.usage.domains


def test_groot_no_license() -> None:
    with _patch_groot():
        meta = read_huggingface("nvidia/GR00T-N1.7-3B")
    assert meta.license is None


# openvla/openvla-7b  - vision-language-action robot policy; robotics + multimodal tags
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


def test_openvla_robotics_and_multimodal_tags() -> None:
    with _patch_openvla():
        meta = read_huggingface("openvla/openvla-7b")
    assert "robotics" in meta.usage.domains
    assert "image-text-to-text" in meta.usage.domains


def test_openvla_architecture() -> None:
    with _patch_openvla():
        meta = read_huggingface("openvla/openvla-7b")
    assert meta.type_of_model == "openvla"


# lerobot/pi05_base  - LeRobot PI0.5 policy; gemma license; lerobot library
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


def test_pi05_robotics_domain_gemma_license() -> None:
    with _patch_pi05():
        meta = read_huggingface("lerobot/pi05_base")
    assert "robotics" in meta.usage.domains
    assert meta.license == "gemma"


def test_pi05_lerobot_library() -> None:
    with _patch_pi05():
        meta = read_huggingface("lerobot/pi05_base")
    assert meta.extra_data.get("hf.library_name") == "lerobot"


# ---------------------------------------------------------------------------
# PATTERN: any-to-any and dataset-from-model_info
# ---------------------------------------------------------------------------


# nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16
# any-to-any model; license=other; datasets in both card YAML and model_info tags.
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


def test_nemotron_any_to_any_domain() -> None:
    with _patch_nemotron():
        meta = read_huggingface("nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16")
    assert "any-to-any" in meta.usage.domains


def test_nemotron_dataset_from_card_yaml() -> None:
    with _patch_nemotron():
        meta = read_huggingface("nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16")
    assert any("Nemotron-Image-Training" in d.metadata.name for d in meta.datasets)


# ---------------------------------------------------------------------------
# PATTERN: standard models - various new architectures / quick coverage
# ---------------------------------------------------------------------------


# pythainlp/wangchanglm-7.5B-sft-enth  - xglm Thai LLM; cc-by-sa-4.0; multiple datasets
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


def test_wangchanglm_architecture() -> None:
    with _patch_wangchanglm():
        meta = read_huggingface("pythainlp/wangchanglm-7.5B-sft-enth")
    assert meta.type_of_model == "xglm"


def test_wangchanglm_multiple_datasets() -> None:
    with _patch_wangchanglm():
        meta = read_huggingface("pythainlp/wangchanglm-7.5B-sft-enth")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "laion/OIG" in ds_names
    assert "Hello-SimpleAI/HC3" in ds_names


def test_wangchanglm_unlimited_tokenizer_filtered() -> None:
    with _patch_wangchanglm():
        meta = read_huggingface("pythainlp/wangchanglm-7.5B-sft-enth")
    assert "hf.tokenizer_max_length" not in meta.extra_data


# aisingapore/Gemma-SEA-LION-v4-4B-VL  - SEA multimodal; gemma3; base_model from card
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


def test_sealion_vl_gemma3_architecture_and_base_model() -> None:
    with _patch_sealion_vl():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-4B-VL")
    assert meta.type_of_model == "gemma3"
    assert meta.extra_data.get("hf.base_model") == "google/gemma-3-4b-it"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_sealion_vl_image_text_to_text_domain() -> None:
    with _patch_sealion_vl():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-4B-VL")
    assert "image-text-to-text" in meta.usage.domains


# mesolitica/mallam-1.1B-4096  - Malay LLM; no license; Mistral base
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


def test_mallam_no_license() -> None:
    with _patch_mallam():
        meta = read_huggingface("mesolitica/mallam-1.1B-4096")
    assert meta.license is None


def test_mallam_malay_language() -> None:
    with _patch_mallam():
        meta = read_huggingface("mesolitica/mallam-1.1B-4096")
    assert meta.extra_lists.get("hf.language") == ["ms"]


# llm-jp/llm-jp-3-1.8b  - Japanese+English LLM; LLaMA architecture
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


def test_llmjp_llama_architecture_large_vocab() -> None:
    # 99 584-token vocab designed for Japanese tokenization
    with _patch_llmjp():
        meta = read_huggingface("llm-jp/llm-jp-3-1.8b")
    assert meta.type_of_model == "llama"
    assert meta.hyperparameters.get("vocab_size") == 99584


# openai/privacy-filter  - token classification; ONNX+safetensors model
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


def test_privacy_filter_token_classification_domain() -> None:
    with _patch_privacy_filter():
        meta = read_huggingface("openai/privacy-filter")
    assert "token-classification" in meta.usage.domains


def test_privacy_filter_tokenizer_max_length() -> None:
    with _patch_privacy_filter():
        meta = read_huggingface("openai/privacy-filter")
    assert meta.extra_data.get("hf.tokenizer_max_length") == 128000


# mistralai/Mistral-Medium-3.5-128B  - no pipeline_tag; license=other; 24 languages
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


def test_mistral_medium_no_pipeline_tag_empty_domain() -> None:
    with _patch_mistral_medium():
        meta = read_huggingface("mistralai/Mistral-Medium-3.5-128B")
    assert not meta.usage.domains


def test_mistral_medium_many_languages() -> None:
    with _patch_mistral_medium():
        meta = read_huggingface("mistralai/Mistral-Medium-3.5-128B")
    langs = meta.extra_lists.get("hf.language", [])
    assert "ja" in langs and "ar" in langs and "hi" in langs


def test_mistral_medium_vague_license() -> None:
    with _patch_mistral_medium():
        meta = read_huggingface("mistralai/Mistral-Medium-3.5-128B")
    assert meta.license is None
    assert meta.extra_data.get("hf.license_raw") == "other"


# poolside/Laguna-XS.2  - custom Laguna architecture; vllm inference
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


def test_laguna_custom_architecture() -> None:
    with _patch_laguna():
        meta = read_huggingface("poolside/Laguna-XS.2")
    assert meta.type_of_model == "laguna"
    assert meta.architecture == "LagunaForCausalLM"


def test_laguna_custom_tags_in_extra_lists() -> None:
    with _patch_laguna():
        meta = read_huggingface("poolside/Laguna-XS.2")
    assert "laguna-xs.2" in meta.extra_lists.get("hf.tags", [])


# abeja/gpt-neox-japanese-2.7b  - Japanese GPT-NeoX; card has `language: ja` (scalar)
def _patch_gpt_neox_jp() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "gpt_neox_japanese",
            "architectures": ["GPTNeoXJapaneseForCausalLM"],
            "vocab_size": 32000,
            "num_hidden_layers": 32,
            "hidden_size": 2560,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="text-generation",
            tags=["ja", "japanese", "gpt_neox", "gpt", "lm", "nlp"],
            language="ja",  # scalar string
            datasets=["cc100", "wikipedia"],
        ),
        hub_info={"author": "abeja"},
    )


def test_gpt_neox_jp_language_scalar() -> None:
    with _patch_gpt_neox_jp():
        meta = read_huggingface("abeja/gpt-neox-japanese-2.7b")
    assert meta.extra_lists.get("hf.language") == ["ja"]


def test_gpt_neox_jp_datasets() -> None:
    with _patch_gpt_neox_jp():
        meta = read_huggingface("abeja/gpt-neox-japanese-2.7b")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "cc100" in ds_names and "wikipedia" in ds_names


# Falconsai/medical_summarization  - T5 summarization; medical domain tag
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


def test_falconsai_t5_summarization() -> None:
    with _patch_falconsai():
        meta = read_huggingface("Falconsai/medical_summarization")
    assert meta.type_of_model == "t5"
    assert "summarization" in meta.usage.domains


def test_falconsai_tokenizer_max_length() -> None:
    with _patch_falconsai():
        meta = read_huggingface("Falconsai/medical_summarization")
    assert meta.extra_data.get("hf.tokenizer_max_length") == 512


# Helsinki-NLP/opus-mt-th-en  - MarianMT Thai->English translation
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


def test_opus_mt_translation_domain_from_tag() -> None:
    # pipeline_tag absent; "translation" is a domain tag in card tags.
    with _patch_opus_mt_th_en():
        meta = read_huggingface("Helsinki-NLP/opus-mt-th-en")
    assert "translation" in meta.usage.domains


def test_opus_mt_marian_architecture() -> None:
    with _patch_opus_mt_th_en():
        meta = read_huggingface("Helsinki-NLP/opus-mt-th-en")
    assert meta.type_of_model == "marian"


# tencent/HY-MT1.5-1.8B  - HunYuan translation LLM; no license; translation in tags
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


def test_hunyuan_mt_translation_from_tag() -> None:
    with _patch_hunyuan_mt():
        meta = read_huggingface("tencent/HY-MT1.5-1.8B")
    assert "translation" in meta.usage.domains


def test_hunyuan_mt_no_license() -> None:
    with _patch_hunyuan_mt():
        meta = read_huggingface("tencent/HY-MT1.5-1.8B")
    assert meta.license is None


# tencent/Hy-MT1.5-1.8B-2bit-GGUF  - GGUF; lang=["multilingual"] keyword value
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


def test_hy_mt_gguf_multilingual_keyword_preserved() -> None:
    with _patch_hy_mt_gguf():
        meta = read_huggingface("tencent/Hy-MT1.5-1.8B-2bit-GGUF")
    assert "multilingual" in meta.extra_lists.get("hf.language", [])


def test_hy_mt_gguf_base_model_quantized() -> None:
    with _patch_hy_mt_gguf():
        meta = read_huggingface("tencent/Hy-MT1.5-1.8B-2bit-GGUF")
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"


# tencent/Hunyuan-MT-7B  - 7B translation; card has translation in tags, no pipeline_tag
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


def test_hunyuan_mt7b_translation_from_tag_no_pipeline() -> None:
    with _patch_hunyuan_mt7b():
        meta = read_huggingface("tencent/Hunyuan-MT-7B")
    assert "translation" in meta.usage.domains
    assert meta.license is None


# Intelligent-Internet/II-Medical-8B
# - Qwen3 fine-tuned for medical; empty card tags
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


def test_ii_medical_qwen3_architecture() -> None:
    with _patch_ii_medical():
        meta = read_huggingface("Intelligent-Internet/II-Medical-8B")
    assert meta.type_of_model == "qwen3"
    assert meta.hyperparameters.get("hidden_size") == 4096


# ---------------------------------------------------------------------------
# PATTERN: dataset fallback from model_info tags (no-card scenario)
# ---------------------------------------------------------------------------


# Demonstrating that dataset:* tags in model_info fill datasets
# when card is absent.
# Using wangchanglm as a control
# - it has BOTH card datasets AND model_info dataset tags.
def test_dataset_card_yaml_takes_priority_over_info_tags() -> None:
    # When card_data has datasets, model_info tags are ignored for datasets.
    card = _make_card_data(
        license="cc-by-sa-4.0",
        pipeline_tag="text-generation",
        datasets=["from-card-dataset"],
    )
    with _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=card,
        hub_info={"tags": ["dataset:from-info-tag"]},
    ):
        meta = read_huggingface("pythainlp/wangchanglm-7.5B-sft-enth")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "from-card-dataset" in ds_names
    assert "from-info-tag" not in ds_names


def test_dataset_info_tag_fallback_when_no_card_datasets() -> None:
    # When card has no datasets, model_info tags with dataset: prefix are used.
    card = _make_card_data(license="mit", pipeline_tag="text-generation")
    with _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=card,
        hub_info={"tags": ["dataset:fallback-dataset"]},
    ):
        meta = read_huggingface("pythainlp/wangchanglm-7.5B-sft-enth")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "fallback-dataset" in ds_names


# ===========================================================================
# NEW MODEL BATCH 4 -- 42 models covering new patterns
# ===========================================================================

# ---------------------------------------------------------------------------
# PATTERN: visual-question-answering pipeline tag
# ---------------------------------------------------------------------------


# dandelin/vilt-b32-finetuned-vqa
# ViLT fine-tuned on VQAv2; fine-tuned from dandelin/vilt-b32.
def _patch_vilt_vqa() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "vilt",
            "architectures": ["ViltForVisualQuestionAnswering"],
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="visual-question-answering",
            tags=["vilt", "visual-question-answering"],
            base_model=["dandelin/vilt-b32"],
        ),
        hub_info={
            "author": "dandelin",
            "tags": [
                "arxiv:2102.03334",
                "base_model:dandelin/vilt-b32",
                "base_model:finetune:dandelin/vilt-b32",
            ],
        },
    )


def test_vilt_vqa_domain() -> None:
    with _patch_vilt_vqa():
        meta = read_huggingface("dandelin/vilt-b32-finetuned-vqa")
    assert "visual-question-answering" in meta.usage.domains


def test_vilt_vqa_base_model_finetune() -> None:
    with _patch_vilt_vqa():
        meta = read_huggingface("dandelin/vilt-b32-finetuned-vqa")
    assert meta.extra_data.get("hf.base_model") == "dandelin/vilt-b32"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_vilt_vqa_arxiv() -> None:
    with _patch_vilt_vqa():
        meta = read_huggingface("dandelin/vilt-b32-finetuned-vqa")
    assert "2102.03334" in meta.extra_lists.get("hf.arxiv", [])


# google/deplot
# pix2struct for chart→table; VQA pipeline; image-text-to-text also in tags.
def _patch_deplot() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "pix2struct",
            "architectures": ["Pix2StructForConditionalGeneration"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="visual-question-answering",
            tags=["pix2struct", "image-text-to-text"],
            language=["en", "fr", "de", "es", "pt"],
        ),
        hub_info={
            "author": "google",
            "tags": ["arxiv:2212.10505"],
        },
    )


def test_deplot_vqa_domain() -> None:
    with _patch_deplot():
        meta = read_huggingface("google/deplot")
    assert "visual-question-answering" in meta.usage.domains


def test_deplot_image_text_tag_also_domain() -> None:
    # "image-text-to-text" in tags also captured as domain.
    with _patch_deplot():
        meta = read_huggingface("google/deplot")
    assert "image-text-to-text" in meta.usage.domains


def test_deplot_arxiv() -> None:
    with _patch_deplot():
        meta = read_huggingface("google/deplot")
    assert "2212.10505" in meta.extra_lists.get("hf.arxiv", [])


# Salesforce/blip-vqa-base
# BLIP for VQA; bsd-3-clause license (non-SPDX passthrough).
def _patch_blip_vqa() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "blip",
            "architectures": ["BlipForQuestionAnswering"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="bsd-3-clause",
            pipeline_tag="visual-question-answering",
            tags=["blip"],
            language=["en"],
        ),
        hub_info={
            "author": "Salesforce",
            "tags": ["arxiv:2201.12086"],
        },
    )


def test_blip_vqa_domain() -> None:
    with _patch_blip_vqa():
        meta = read_huggingface("Salesforce/blip-vqa-base")
    assert "visual-question-answering" in meta.usage.domains


def test_blip_vqa_bsd_license_passthrough() -> None:
    # bsd-3-clause not in _VAGUE_LICENSE_VALUES -- passed through as-is.
    with _patch_blip_vqa():
        meta = read_huggingface("Salesforce/blip-vqa-base")
    assert meta.license == "bsd-3-clause"


# ---------------------------------------------------------------------------
# PATTERN: text-to-speech domain tag
# ---------------------------------------------------------------------------


# k2-fsa/OmniVoice
# Zero-shot TTS; 646 languages; fine-tuned from Qwen3-0.6B; arxiv DOI.
def _patch_omnivoice() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-to-speech",
            tags=["zero-shot", "multilingual", "voice-cloning"],
            language=["multilingual"],
            base_model=["Qwen/Qwen3-0.6B"],
        ),
        hub_info={
            "author": "k2-fsa",
            "tags": [
                "arxiv:2604.00688",
                "base_model:Qwen/Qwen3-0.6B",
                "base_model:finetune:Qwen/Qwen3-0.6B",
            ],
        },
    )


def test_omnivoice_text_to_speech_domain() -> None:
    with _patch_omnivoice():
        meta = read_huggingface("k2-fsa/OmniVoice")
    assert "text-to-speech" in meta.usage.domains


def test_omnivoice_arxiv_and_base_model() -> None:
    with _patch_omnivoice():
        meta = read_huggingface("k2-fsa/OmniVoice")
    assert "2604.00688" in meta.extra_lists.get("hf.arxiv", [])
    assert meta.extra_data.get("hf.base_model") == "Qwen/Qwen3-0.6B"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


# drbaph/OmniVoice-bf16
# BF16 conversion of k2-fsa/OmniVoice.
def _patch_omnivoice_bf16() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-to-speech",
            tags=["omnivoice", "bf16"],
            language=["multilingual"],
            base_model=["k2-fsa/OmniVoice"],
        ),
        hub_info={
            "author": "drbaph",
            "tags": [
                "base_model:k2-fsa/OmniVoice",
                "base_model:finetune:k2-fsa/OmniVoice",
            ],
        },
    )


def test_omnivoice_bf16_tts_domain_and_base_model() -> None:
    with _patch_omnivoice_bf16():
        meta = read_huggingface("drbaph/OmniVoice-bf16")
    assert "text-to-speech" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "k2-fsa/OmniVoice"


# ---------------------------------------------------------------------------
# PATTERN: speaker-diarization (new domain tag, gated model)
# ---------------------------------------------------------------------------


# pyannote/speaker-diarization-community-1
# Gated (cc-by-4.0 acceptance required); pyannote.audio library.
def _patch_pyannote_diar() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="cc-by-4.0",
            pipeline_tag="speaker-diarization",
            tags=["pyannote", "speaker-diarization", "voice-activity-detection"],
            library_name="pyannote.audio",
        ),
        hub_info={"author": "pyannote"},
    )


def test_pyannote_speaker_diarization_domain() -> None:
    with _patch_pyannote_diar():
        meta = read_huggingface("pyannote/speaker-diarization-community-1")
    assert "speaker-diarization" in meta.usage.domains


def test_pyannote_library_name() -> None:
    with _patch_pyannote_diar():
        meta = read_huggingface("pyannote/speaker-diarization-community-1")
    assert meta.extra_data.get("hf.library_name") == "pyannote.audio"


# ---------------------------------------------------------------------------
# PATTERN: audio-to-audio (new domain tag) + multi-task speech model
# ---------------------------------------------------------------------------


# facebook/seamless-m4t-v2-large
# ASR + S2TT + T2ST + S2ST; cc-by-nc-4.0; audio-to-audio in tags.
def _patch_seamless_m4t() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "seamless_m4t_v2",
            "architectures": ["SeamlessM4Tv2Model"],
            "num_hidden_layers": 24,
            "hidden_size": 1024,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="cc-by-nc-4.0",
            pipeline_tag="automatic-speech-recognition",
            tags=["audio-to-audio", "text-to-speech", "speech-translation"],
            language=["en", "fr", "de", "es", "zh", "ar", "hi", "ja", "ko", "pt"],
        ),
        hub_info={
            "author": "facebook",
            "tags": ["arxiv:2312.05187"],
        },
    )


def test_seamless_asr_domain_from_pipeline_tag() -> None:
    with _patch_seamless_m4t():
        meta = read_huggingface("facebook/seamless-m4t-v2-large")
    assert "automatic-speech-recognition" in meta.usage.domains


def test_seamless_audio_to_audio_tag_in_domain() -> None:
    # "audio-to-audio" in tags → captured as domain (audio-to-audio domain tag).
    with _patch_seamless_m4t():
        meta = read_huggingface("facebook/seamless-m4t-v2-large")
    assert "audio-to-audio" in meta.usage.domains


def test_seamless_nc_license() -> None:
    with _patch_seamless_m4t():
        meta = read_huggingface("facebook/seamless-m4t-v2-large")
    assert meta.license == "cc-by-nc-4.0"


# ---------------------------------------------------------------------------
# PATTERN: ASR -- various architectures and bases
# ---------------------------------------------------------------------------


# ibm-granite/granite-speech-4.1-2b
# Conformer + Q-Former + LM; fine-tuned from granite-4.0-1b-base; 6 languages.
def _patch_granite_speech() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "granite_speech",
            "architectures": ["GraniteSpeechForConditionalGeneration"],
            "num_hidden_layers": 40,
            "hidden_size": 2560,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="automatic-speech-recognition",
            tags=["speech-translation", "multilingual-asr"],
            language=["en", "fr", "de", "es", "pt", "ja"],
            base_model=["ibm-granite/granite-4.0-1b-base"],
        ),
        hub_info={
            "author": "ibm-granite",
            "tags": [
                "base_model:ibm-granite/granite-4.0-1b-base",
                "base_model:finetune:ibm-granite/granite-4.0-1b-base",
            ],
        },
    )


def test_granite_speech_asr_domain() -> None:
    with _patch_granite_speech():
        meta = read_huggingface("ibm-granite/granite-speech-4.1-2b")
    assert "automatic-speech-recognition" in meta.usage.domains


def test_granite_speech_base_model_finetune() -> None:
    with _patch_granite_speech():
        meta = read_huggingface("ibm-granite/granite-speech-4.1-2b")
    assert meta.extra_data.get("hf.base_model") == "ibm-granite/granite-4.0-1b-base"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


# ai4bharat/indic-conformer-600m-multilingual
# Gated; 22 Indian-language ASR; custom_code.
def _patch_indic_conformer() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="automatic-speech-recognition",
            tags=["custom_code", "ONNX"],
            language=[
                "as",
                "bn",
                "gu",
                "hi",
                "kn",
                "ml",
                "mr",
                "or",
                "pa",
                "sa",
                "ta",
                "te",
                "ur",
                "mai",
                "doi",
                "mni",
                "sat",
                "kok",
                "ks",
                "brx",
                "ne",
                "sd",
            ],
        ),
        hub_info={"author": "ai4bharat"},
    )


def test_indic_conformer_22_indian_languages() -> None:
    with _patch_indic_conformer():
        meta = read_huggingface("ai4bharat/indic-conformer-600m-multilingual")
    assert "automatic-speech-recognition" in meta.usage.domains
    langs = meta.extra_lists.get("hf.language", [])
    assert "hi" in langs and "ta" in langs and "te" in langs
    assert len(langs) == 22


# cstr/mimo-asr-GGUF
# GGUF ASR; quantized from XiaomiMiMo/MiMo-V2.5-ASR; Mandarin+English.
def _patch_mimo_asr_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="automatic-speech-recognition",
            tags=["GGUF", "audio", "mimo", "qwen2"],
            language=["zh", "en"],
            base_model=["XiaomiMiMo/MiMo-V2.5-ASR"],
        ),
        hub_info={
            "author": "cstr",
            "tags": [
                "base_model:XiaomiMiMo/MiMo-V2.5-ASR",
                "base_model:quantized:XiaomiMiMo/MiMo-V2.5-ASR",
            ],
        },
    )


def test_mimo_asr_quantized_gguf() -> None:
    with _patch_mimo_asr_gguf():
        meta = read_huggingface("cstr/mimo-asr-GGUF")
    assert "automatic-speech-recognition" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "XiaomiMiMo/MiMo-V2.5-ASR"
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"


# microsoft/VibeVoice-ASR
# Large ASR with speaker diarization; 51+ languages; arxiv paper.
def _patch_vibevoice_asr() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "vibevoice",
            "architectures": ["VibeVoiceForASRTraining"],
            "num_hidden_layers": 40,
            "hidden_size": 4096,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="automatic-speech-recognition",
            tags=["ASR", "Diarization", "Speech-to-Text"],
            language=["en", "zh", "fr", "de", "es", "ja", "ko", "ar"],
        ),
        hub_info={
            "author": "microsoft",
            "tags": ["arxiv:2601.18184"],
        },
    )


def test_vibevoice_asr_domain_and_arxiv() -> None:
    with _patch_vibevoice_asr():
        meta = read_huggingface("microsoft/VibeVoice-ASR")
    assert "automatic-speech-recognition" in meta.usage.domains
    assert "2601.18184" in meta.extra_lists.get("hf.arxiv", [])


# neurlang/ipa-whisper-medium
# Whisper fine-tuned for IPA phonetic output; 74 languages.
def _patch_ipa_whisper() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "whisper",
            "architectures": ["WhisperForConditionalGeneration"],
            "num_hidden_layers": 24,
            "hidden_size": 1024,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="automatic-speech-recognition",
            tags=["whisper", "IPA", "phonetic"],
            language=["en", "fr", "de", "es", "zh", "ar", "ja"],
            base_model=["openai/whisper-medium"],
        ),
        hub_info={
            "author": "neurlang",
            "tags": [
                "base_model:openai/whisper-medium",
                "base_model:finetune:openai/whisper-medium",
            ],
        },
    )


def test_ipa_whisper_base_model_finetune() -> None:
    with _patch_ipa_whisper():
        meta = read_huggingface("neurlang/ipa-whisper-medium")
    assert meta.extra_data.get("hf.base_model") == "openai/whisper-medium"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_ipa_whisper_asr_domain() -> None:
    with _patch_ipa_whisper():
        meta = read_huggingface("neurlang/ipa-whisper-medium")
    assert "automatic-speech-recognition" in meta.usage.domains


# indonesian-nlp/wav2vec2-indonesian-javanese-sundanese
# Indonesian + Javanese + Sundanese ASR; fine-tuned from xlsr-53.
def _patch_wav2vec2_id_jv_su() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "wav2vec2",
            "architectures": ["Wav2Vec2ForCTC"],
            "vocab_size": 63,
            "num_hidden_layers": 24,
            "hidden_size": 1024,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="automatic-speech-recognition",
            tags=["wav2vec2", "hf-asr-leaderboard"],
            language=["id", "jv", "su"],
            base_model=["facebook/wav2vec2-large-xlsr-53"],
        ),
        hub_info={
            "author": "indonesian-nlp",
            "tags": [
                "base_model:facebook/wav2vec2-large-xlsr-53",
                "base_model:finetune:facebook/wav2vec2-large-xlsr-53",
            ],
        },
    )


def test_wav2vec2_id_asr_domain_three_languages() -> None:
    with _patch_wav2vec2_id_jv_su():
        meta = read_huggingface("indonesian-nlp/wav2vec2-indonesian-javanese-sundanese")
    assert "automatic-speech-recognition" in meta.usage.domains
    langs = meta.extra_lists.get("hf.language", [])
    assert "id" in langs and "jv" in langs and "su" in langs


# ---------------------------------------------------------------------------
# PATTERN: IBM Granite family (three tasks: text, speech, geospatial, embed)
# ---------------------------------------------------------------------------


# ibm-granite/granite-4.1-8b
# Dense LLM; GQA; 12 languages; fine-tuned from granite-4.1-8b-base.
def _patch_granite_4_1_8b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "granite",
            "architectures": ["GraniteForCausalLM"],
            "vocab_size": 49152,
            "num_hidden_layers": 40,
            "hidden_size": 4096,
            "num_attention_heads": 32,
            "num_key_value_heads": 8,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["granite", "conversational"],
            language=[
                "en",
                "de",
                "es",
                "fr",
                "ja",
                "pt",
                "ar",
                "cs",
                "it",
                "ko",
                "nl",
                "zh",
            ],
            base_model=["ibm-granite/granite-4.1-8b-base"],
        ),
        hub_info={
            "author": "ibm-granite",
            "tags": [
                "base_model:ibm-granite/granite-4.1-8b-base",
                "base_model:finetune:ibm-granite/granite-4.1-8b-base",
            ],
        },
    )


def test_granite_4_1_8b_gqa_and_12_languages() -> None:
    with _patch_granite_4_1_8b():
        meta = read_huggingface("ibm-granite/granite-4.1-8b")
    assert meta.hyperparameters.get("num_key_value_heads") == 8
    langs = meta.extra_lists.get("hf.language", [])
    assert len(langs) == 12 and "ja" in langs and "ar" in langs


def test_granite_4_1_8b_base_model_finetune() -> None:
    with _patch_granite_4_1_8b():
        meta = read_huggingface("ibm-granite/granite-4.1-8b")
    assert meta.extra_data.get("hf.base_model") == "ibm-granite/granite-4.1-8b-base"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


# ibm-granite/granite-embedding-97m-multilingual-r2
# ModernBERT bi-encoder; 200+ languages; sentence-transformers library.
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


def test_granite_embed_modernbert_arch_and_library() -> None:
    with _patch_granite_embed():
        meta = read_huggingface("ibm-granite/granite-embedding-97m-multilingual-r2")
    assert meta.type_of_model == "modernbert"
    assert meta.extra_data.get("hf.library_name") == "sentence-transformers"


def test_granite_embed_feature_extraction_domain() -> None:
    with _patch_granite_embed():
        meta = read_huggingface("ibm-granite/granite-embedding-97m-multilingual-r2")
    assert "feature-extraction" in meta.usage.domains


# ibm-granite/granite-geospatial-uki-flooddetection
# TerraTorch-based; image-segmentation; references two HF dataset-namespace
# flood datasets.
# Note:
# ai-for-good-lab/ai4g-flood-dataset and blanchon/ETCI-2021-Flood-Detection
# are HuggingFace datasets (not model repos) referenced in this model's card.
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


def test_granite_geo_flood_image_segmentation_domain() -> None:
    with _patch_granite_geo_flood():
        meta = read_huggingface("ibm-granite/granite-geospatial-uki-flooddetection")
    assert "image-segmentation" in meta.usage.domains


def test_granite_geo_flood_dataset_refs_from_hf_dataset_repos() -> None:
    # Both flood dataset HF IDs captured as DatasetReference objects.
    with _patch_granite_geo_flood():
        meta = read_huggingface("ibm-granite/granite-geospatial-uki-flooddetection")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "ai-for-good-lab/ai4g-flood-dataset" in ds_names
    assert "blanchon/ETCI-2021-Flood-Detection" in ds_names


def test_granite_geo_flood_terratorch_library_and_base_model() -> None:
    with _patch_granite_geo_flood():
        meta = read_huggingface("ibm-granite/granite-geospatial-uki-flooddetection")
    assert meta.extra_data.get("hf.library_name") == "terratorch"
    assert meta.extra_data.get("hf.base_model") == "ibm-granite/granite-geospatial-uki"


# ---------------------------------------------------------------------------
# PATTERN: flood detection (image classification, siglip, arxiv)
# ---------------------------------------------------------------------------


# prithivMLmods/Flood-Image-Detection
# SiGLIP2 fine-tuned for binary flood/no-flood classification; arxiv.
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


def test_flood_image_detect_domain_and_base_model() -> None:
    with _patch_flood_image_detect():
        meta = read_huggingface("prithivMLmods/Flood-Image-Detection")
    assert "image-classification" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "google/siglip2-base-patch16-512"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


# ---------------------------------------------------------------------------
# PATTERN: fill-mask (multilingual BERT family)
# ---------------------------------------------------------------------------


# FacebookAI/xlm-roberta-base
# XLM-RoBERTa; fill-mask; MIT; 100+ languages.
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


def test_xlm_roberta_fill_mask_domain_and_languages() -> None:
    with _patch_xlm_roberta_base():
        meta = read_huggingface("FacebookAI/xlm-roberta-base")
    assert "fill-mask" in meta.usage.domains
    langs = meta.extra_lists.get("hf.language", [])
    assert "hi" in langs and "ar" in langs and "zh" in langs


# distilbert/distilbert-base-multilingual-cased
# 6-layer DistilBERT; fill-mask; apache-2.0; 104 languages.
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


def test_distilbert_multilingual_fill_mask_and_6_layers() -> None:
    # DistilBERT halves BERT's 12 layers to 6.
    with _patch_distilbert_multilingual():
        meta = read_huggingface("distilbert/distilbert-base-multilingual-cased")
    assert "fill-mask" in meta.usage.domains
    assert meta.type_of_model == "distilbert"
    assert meta.hyperparameters.get("num_hidden_layers") == 6


# DCU-NLP/bert-base-irish-cased-v1 (gaBERT)
# Irish BERT; fill-mask; no license in card YAML.
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


def test_gabert_fill_mask_irish_no_license() -> None:
    with _patch_gabert():
        meta = read_huggingface("DCU-NLP/bert-base-irish-cased-v1")
    assert "fill-mask" in meta.usage.domains
    assert meta.extra_lists.get("hf.language") == ["ga"]
    assert meta.license is None


# ---------------------------------------------------------------------------
# PATTERN: base_model merge relation
# ---------------------------------------------------------------------------


# Crownelius/Crow-9B-HERETIC-4.6
# Qwen3.5 merge model; 26 languages; merge relation.
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


def test_crow_9b_merge_relation() -> None:
    with _patch_crow_9b():
        meta = read_huggingface("Crownelius/Crow-9B-HERETIC-4.6")
    assert meta.extra_data.get("hf.base_model") == "Qwen/Qwen3.5-9B-Base"
    assert meta.extra_data.get("hf.base_model_relation") == "merge"


def test_crow_9b_26_languages() -> None:
    with _patch_crow_9b():
        meta = read_huggingface("Crownelius/Crow-9B-HERETIC-4.6")
    assert len(meta.extra_lists.get("hf.language", [])) == 26


# SamsungSAILMontreal/Qwen3-Coder-Next-REAP
# Qwen3-Next MoE compressed via REAP expert pruning; merge relation.
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


def test_qwen3_reap_merge_relation_moe() -> None:
    with _patch_qwen3_reap():
        meta = read_huggingface("SamsungSAILMontreal/Qwen3-Coder-Next-REAP")
    assert meta.extra_data.get("hf.base_model") == "Qwen/Qwen3-Coder-Next"
    assert meta.extra_data.get("hf.base_model_relation") == "merge"
    assert meta.type_of_model == "qwen3_moe"


# ---------------------------------------------------------------------------
# PATTERN: classic / early LLMs (diverse architectures)
# ---------------------------------------------------------------------------


# facebook/opt-2.7b
# OPT 2.7B; license=other (Meta non-commercial).
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


def test_opt_2_7b_vague_license_and_opt_arch() -> None:
    with _patch_opt_2_7b():
        meta = read_huggingface("facebook/opt-2.7b")
    assert meta.license is None
    assert meta.extra_data.get("hf.license_raw") == "other"
    assert meta.type_of_model == "opt"


# facebook/opt-iml-max-1.3b
# OPT instruction-tuned on ~2000 NLP tasks; arxiv.
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


def test_opt_iml_arxiv_and_vague_license() -> None:
    with _patch_opt_iml():
        meta = read_huggingface("facebook/opt-iml-max-1.3b")
    assert "2212.12017" in meta.extra_lists.get("hf.arxiv", [])
    assert meta.license is None
    assert meta.extra_data.get("hf.license_raw") == "other"


# EleutherAI/gpt-neo-2.7B
# GPT-Neo 2.7B; apache-2.0; English.
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


def test_gpt_neo_2_7b_architecture() -> None:
    with _patch_gpt_neo_2_7b():
        meta = read_huggingface("EleutherAI/gpt-neo-2.7B")
    assert meta.type_of_model == "gpt_neo"
    assert meta.architecture == "GPTNeoForCausalLM"


# stabilityai/stablelm-2-zephyr-1_6b
# StableLM 2 Zephyr; apache-2.0; 12 languages.
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


def test_stablelm_zephyr_architecture() -> None:
    with _patch_stablelm_zephyr():
        meta = read_huggingface("stabilityai/stablelm-2-zephyr-1_6b")
    assert meta.type_of_model == "stablelm_epoch"
    assert meta.architecture == "StableLMEpochForCausalLM"


# TinyLlama/TinyLlama-1.1B-Chat-v1.0
# TinyLlama 1.1B Chat; apache-2.0; English; 22 layers.
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


def test_tinyllama_chat_architecture_and_depth() -> None:
    with _patch_tinyllama_chat():
        meta = read_huggingface("TinyLlama/TinyLlama-1.1B-Chat-v1.0")
    assert meta.type_of_model == "llama"
    assert meta.hyperparameters.get("num_hidden_layers") == 22


# microsoft/phi-2
# Phi-2 (2.7B); MIT; English; "code" tag → usage.domains.
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


def test_phi2_phi_architecture_mit_license() -> None:
    with _patch_phi2():
        meta = read_huggingface("microsoft/phi-2")
    assert meta.type_of_model == "phi"
    assert meta.license == "mit"


def test_phi2_code_tag_in_domain() -> None:
    # "code" is in _DOMAIN_TAGS → usage.domains, not extra_lists["hf.tags"].
    with _patch_phi2():
        meta = read_huggingface("microsoft/phi-2")
    assert "code" in meta.usage.domains


# ---------------------------------------------------------------------------
# PATTERN: Llama 3.2 3B variants (gated base vs gated instruct)
# ---------------------------------------------------------------------------


# meta-llama/Llama-3.2-3B (gated base model)
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


def test_llama_3_2_3b_gated_base_no_architecture() -> None:
    with _patch_llama_3_2_3b():
        meta = read_huggingface("meta-llama/Llama-3.2-3B")
    assert meta.license == "llama3.2"
    assert meta.type_of_model is None  # config gated → not extractable


# meta-llama/Llama-3.2-3B-Instruct (gated, fine-tuned from 3B base)
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


def test_llama_3_2_3b_instruct_base_model_finetune() -> None:
    with _patch_llama_3_2_3b_instruct():
        meta = read_huggingface("meta-llama/Llama-3.2-3B-Instruct")
    assert meta.extra_data.get("hf.base_model") == "meta-llama/Llama-3.2-3B"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


# NousResearch/Hermes-3-Llama-3.2-3B (accessible, llama3 license)
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


def test_hermes_3_llama_3b_finetune_and_license() -> None:
    with _patch_hermes_3_llama_3b():
        meta = read_huggingface("NousResearch/Hermes-3-Llama-3.2-3B")
    assert meta.license == "llama3"
    assert meta.extra_data.get("hf.base_model") == "meta-llama/Llama-3.2-3B"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


# ---------------------------------------------------------------------------
# PATTERN: text-classification (multiple models)
# ---------------------------------------------------------------------------


# HuggingFaceFW/fineweb-edu-classifier
# Educational quality scorer (0–5); bert-like; fine-tuned from Snowflake arctic embed.
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


def test_fineweb_edu_text_classification_and_base_model() -> None:
    with _patch_fineweb_edu():
        meta = read_huggingface("HuggingFaceFW/fineweb-edu-classifier")
    assert "text-classification" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "Snowflake/snowflake-arctic-embed-m"


# tum-nlp/Deberta_Human_Value_Detector
# Custom DeBERTa (trust_remote_code); openrail++ license; 20 human value categories.
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


def test_deberta_human_value_openrail_license() -> None:
    # openrail++ is not in _VAGUE_LICENSE_VALUES -- passed through as-is.
    with _patch_deberta_human_value():
        meta = read_huggingface("tum-nlp/Deberta_Human_Value_Detector")
    assert meta.license == "openrail++"
    assert "text-classification" in meta.usage.domains


# nlp-chula/aspect-finnlp-th
# CamemBERT Thai financial NLP; no license; fine-tuned from wangchanberta.
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


def test_aspect_finnlp_th_camembert_no_license() -> None:
    with _patch_aspect_finnlp_th():
        meta = read_huggingface("nlp-chula/aspect-finnlp-th")
    assert meta.type_of_model == "camembert"
    assert meta.license is None
    assert "text-classification" in meta.usage.domains


# ---------------------------------------------------------------------------
# PATTERN: legal domain models (diverse languages and regions)
# ---------------------------------------------------------------------------


# FINAL-Bench/Darwin-28B-KR-Legal
# Korean legal LLM; Qwen3.5 arch; fine-tuned from Darwin-28B-KR.
def _patch_darwin_kr_legal() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "qwen3_5",
            "architectures": ["Qwen3_5ForCausalLM"],
            "vocab_size": 151936,
            "num_hidden_layers": 64,
            "hidden_size": 5120,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["korean", "legal", "conversational"],
            language=["ko", "en"],
            base_model=["FINAL-Bench/Darwin-28B-KR"],
        ),
        hub_info={
            "author": "FINAL-Bench",
            "tags": [
                "base_model:FINAL-Bench/Darwin-28B-KR",
                "base_model:finetune:FINAL-Bench/Darwin-28B-KR",
            ],
        },
    )


def test_darwin_kr_legal_architecture_and_finetune() -> None:
    with _patch_darwin_kr_legal():
        meta = read_huggingface("FINAL-Bench/Darwin-28B-KR-Legal")
    assert meta.type_of_model == "qwen3_5"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"
    assert "ko" in meta.extra_lists.get("hf.language", [])


# protonx-models/protonx-legal-tc
# Vietnamese legal text correction; seq2seq; proprietary NC license → other.
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


def test_protonx_legal_vietnamese_nc_license() -> None:
    # Proprietary NC license → "other" in card → hf.license_raw.
    with _patch_protonx_legal():
        meta = read_huggingface("protonx-models/protonx-legal-tc")
    assert meta.license is None
    assert meta.extra_data.get("hf.license_raw") == "other"
    assert "text2text-generation" in meta.usage.domains
    assert meta.extra_lists.get("hf.language") == ["vi"]


# ReDiX/Legal-Embedding-ita-0.6B
# Italian legal embedding; Qwen3-based; cc-by-nc-4.0.
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


def test_legal_embed_ita_nc_license_italian() -> None:
    with _patch_legal_embed_ita():
        meta = read_huggingface("ReDiX/Legal-Embedding-ita-0.6B")
    assert meta.license == "cc-by-nc-4.0"
    assert meta.extra_lists.get("hf.language") == ["it"]
    assert "sentence-similarity" in meta.usage.domains


# bakrianoo/arabic-legal-documents-ocr-1.0
# Gemma3-based Arabic+English OCR; gemma license; image-text-to-text.
def _patch_arabic_legal_ocr() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "gemma3",
            "architectures": ["Gemma3ForConditionalGeneration"],
            "vocab_size": 262208,
            "num_hidden_layers": 34,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="gemma",
            pipeline_tag="image-text-to-text",
            tags=["ocr", "arabic", "vision", "lora"],
            language=["ar", "en"],
            base_model=["google/gemma-3-4b-it"],
        ),
        hub_info={
            "author": "bakrianoo",
            "tags": [
                "base_model:google/gemma-3-4b-it",
                "base_model:finetune:google/gemma-3-4b-it",
            ],
        },
    )


def test_arabic_legal_ocr_domain_and_gemma_license() -> None:
    with _patch_arabic_legal_ocr():
        meta = read_huggingface("bakrianoo/arabic-legal-documents-ocr-1.0")
    assert "image-text-to-text" in meta.usage.domains
    assert meta.license == "gemma"
    assert "ar" in meta.extra_lists.get("hf.language", [])


# ---------------------------------------------------------------------------
# PATTERN: multimodal / specialty
# ---------------------------------------------------------------------------


# tokyotech-llm/Qwen3-Swallow-8B-SFT-v0.2
# Japanese Qwen3 SFT; English+Japanese; fine-tuned from Qwen3-Swallow CPT.
def _patch_qwen3_swallow() -> Any:
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
            pipeline_tag="text-generation",
            tags=["conversational"],
            language=["en", "ja"],
            base_model=["tokyotech-llm/Qwen3-Swallow-8B-CPT-v0.2"],
        ),
        hub_info={
            "author": "tokyotech-llm",
            "tags": [
                "base_model:tokyotech-llm/Qwen3-Swallow-8B-CPT-v0.2",
                "base_model:finetune:tokyotech-llm/Qwen3-Swallow-8B-CPT-v0.2",
            ],
        },
    )


def test_qwen3_swallow_sft_japanese_finetune() -> None:
    with _patch_qwen3_swallow():
        meta = read_huggingface("tokyotech-llm/Qwen3-Swallow-8B-SFT-v0.2")
    assert meta.type_of_model == "qwen3"
    langs = meta.extra_lists.get("hf.language", [])
    assert "ja" in langs and "en" in langs
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


# aisingapore/Gemma-SEA-LION-v4-27B-IT
# SEA LION 27B IT; 11 SEA languages; gemma license;
# text-generation + image-text-to-text tag.
def _patch_sealion_27b_it() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "gemma3",
            "architectures": ["Gemma3ForCausalLM"],
            "vocab_size": 262208,
            "num_hidden_layers": 62,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="gemma",
            pipeline_tag="text-generation",
            tags=["conversational", "image-text-to-text"],
            language=["my", "en", "id", "km", "lo", "ms", "zh", "tl", "ta", "th", "vi"],
            base_model=["google/gemma-3-27b-it"],
        ),
        hub_info={
            "author": "aisingapore",
            "tags": [
                "base_model:google/gemma-3-27b-it",
                "base_model:finetune:google/gemma-3-27b-it",
            ],
        },
    )


def test_sealion_27b_it_sea_languages_gemma_license() -> None:
    with _patch_sealion_27b_it():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-27B-IT")
    assert meta.license == "gemma"
    langs = meta.extra_lists.get("hf.language", [])
    assert len(langs) == 11 and "th" in langs and "vi" in langs


def test_sealion_27b_it_image_text_tag_also_domain() -> None:
    # "image-text-to-text" in tags → also captured as domain.
    with _patch_sealion_27b_it():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-27B-IT")
    assert "image-text-to-text" in meta.usage.domains


# Doses-AI/boba-0.8b-food-GGUF
# Tiny food/nutrition GGUF; image-text-to-text; no config.json.
def _patch_boba_food_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="image-text-to-text",
            tags=["food", "nutrition", "vision", "on-device"],
            language=["en"],
            base_model=["Qwen/Qwen3.5-0.8B"],
        ),
        hub_info={
            "author": "Doses-AI",
            "tags": [
                "base_model:Qwen/Qwen3.5-0.8B",
                "base_model:finetune:Qwen/Qwen3.5-0.8B",
            ],
        },
    )


def test_boba_food_gguf_domain_base_model_no_arch() -> None:
    with _patch_boba_food_gguf():
        meta = read_huggingface("Doses-AI/boba-0.8b-food-GGUF")
    assert "image-text-to-text" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "Qwen/Qwen3.5-0.8B"
    assert meta.type_of_model is None  # GGUF-only, no config.json


# baidu/ERNIE-Image-Turbo
# Distilled DiT text-to-image; diffusers; apache-2.0; Chinese+English.
def _patch_ernie_image_turbo() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-to-image",
            tags=["diffusion", "distilled"],
            language=["en", "zh"],
            library_name="diffusers",
        ),
        hub_info={"author": "baidu"},
    )


def test_ernie_image_turbo_text_to_image_domain_diffusers() -> None:
    with _patch_ernie_image_turbo():
        meta = read_huggingface("baidu/ERNIE-Image-Turbo")
    assert "text-to-image" in meta.usage.domains
    assert meta.extra_data.get("hf.library_name") == "diffusers"


# ---------------------------------------------------------------------------
# Qwen/Qwen3-235B-A22B  (MoE, qwen license, thinking-mode generation config)
# ---------------------------------------------------------------------------

# 235B sparse MoE (22B active params), 128 experts, 8 active per token.
# "qwen" is a custom HF license identifier -- not in _VAGUE_LICENSE_VALUES,
# so it passes through unchanged in meta.license.
# generation_config includes temperature + top_p (thinking-mode params).

_QWEN3_235B_CONFIG: dict[str, Any] = {
    "model_type": "qwen3_moe",
    "architectures": ["Qwen3MoeForCausalLM"],
    "vocab_size": 152064,
    "hidden_size": 7168,
    "num_hidden_layers": 94,
    "num_attention_heads": 64,
    "num_key_value_heads": 4,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_QWEN3_235B_GENERATION_CONFIG: dict[str, Any] = {
    "temperature": 0.6,
    "top_p": 0.95,
}

_QWEN3_235B_CARD_DATA = _make_card_data(
    license="qwen",
    pipeline_tag="text-generation",
    language=["multilingual"],
    library_name="transformers",
)


def _patch_qwen3_235b() -> Any:
    return _patch_hf_calls(
        config=_QWEN3_235B_CONFIG,
        tokenizer_config={
            "tokenizer_class": "Qwen2Tokenizer",
            "model_max_length": 32768,
        },
        generation_config=_QWEN3_235B_GENERATION_CONFIG,
        card_data=_QWEN3_235B_CARD_DATA,
        hub_info={"author": "Qwen", "sha": "abc123ef"},
    )


def test_qwen3_235b_moe_type_of_model() -> None:
    with _patch_qwen3_235b():
        meta = read_huggingface("Qwen/Qwen3-235B-A22B")
    assert meta.type_of_model == "qwen3_moe"


def test_qwen3_235b_moe_architecture() -> None:
    with _patch_qwen3_235b():
        meta = read_huggingface("Qwen/Qwen3-235B-A22B")
    assert meta.architecture == "Qwen3MoeForCausalLM"


def test_qwen3_235b_qwen_license_passthrough() -> None:
    # "qwen" not in _VAGUE_LICENSE_VALUES → stored as-is
    with _patch_qwen3_235b():
        meta = read_huggingface("Qwen/Qwen3-235B-A22B")
    assert meta.license == "qwen"


def test_qwen3_235b_text_generation_domain() -> None:
    with _patch_qwen3_235b():
        meta = read_huggingface("Qwen/Qwen3-235B-A22B")
    assert "text-generation" in meta.usage.domains


def test_qwen3_235b_generation_hyperparameters() -> None:
    with _patch_qwen3_235b():
        meta = read_huggingface("Qwen/Qwen3-235B-A22B")
    assert meta.hyperparameters.get("generation.temperature") == 0.6
    assert meta.hyperparameters.get("generation.top_p") == 0.95


# ---------------------------------------------------------------------------
# Qwen/Qwen3.5-27B  (dense Qwen3.5, GQA, apache-2.0)
# ---------------------------------------------------------------------------

# Dense 27B model in the Qwen3.5 family. Grouped-query attention (8 KV heads
# vs 40 attention heads). Standard apache-2.0 license. text-generation domain.

_QWEN35_27B_CONFIG: dict[str, Any] = {
    "model_type": "qwen3",
    "architectures": ["Qwen3ForCausalLM"],
    "vocab_size": 152064,
    "hidden_size": 5120,
    "num_hidden_layers": 64,
    "num_attention_heads": 40,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_QWEN35_27B_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["multilingual"],
    library_name="transformers",
)


def _patch_qwen35_27b() -> Any:
    return _patch_hf_calls(
        config=_QWEN35_27B_CONFIG,
        tokenizer_config={
            "tokenizer_class": "Qwen2Tokenizer",
            "model_max_length": 131072,
        },
        card_data=_QWEN35_27B_CARD_DATA,
        hub_info={"author": "Qwen", "sha": "deadf00d"},
    )


def test_qwen35_27b_type_of_model() -> None:
    with _patch_qwen35_27b():
        meta = read_huggingface("Qwen/Qwen3.5-27B")
    assert meta.type_of_model == "qwen3"


def test_qwen35_27b_architecture() -> None:
    with _patch_qwen35_27b():
        meta = read_huggingface("Qwen/Qwen3.5-27B")
    assert meta.architecture == "Qwen3ForCausalLM"


def test_qwen35_27b_apache_license() -> None:
    with _patch_qwen35_27b():
        meta = read_huggingface("Qwen/Qwen3.5-27B")
    assert meta.license == "apache-2.0"


def test_qwen35_27b_gqa() -> None:
    # GQA: num_key_value_heads=8 < num_attention_heads=40
    with _patch_qwen35_27b():
        meta = read_huggingface("Qwen/Qwen3.5-27B")
    assert meta.hyperparameters.get("num_key_value_heads") == 8
    assert meta.hyperparameters.get("num_attention_heads") == 40


def test_qwen35_27b_text_generation_domain() -> None:
    with _patch_qwen35_27b():
        meta = read_huggingface("Qwen/Qwen3.5-27B")
    assert "text-generation" in meta.usage.domains


# ---------------------------------------------------------------------------
# kakaobank/kanana-1.5-v-3b-instruct  (custom license passthrough, VLM)
# ---------------------------------------------------------------------------

# Korean multimodal VLM from Kakao Bank. Custom "kanana-license" identifier is
# NOT in _VAGUE_LICENSE_VALUES → stored as-is (passthrough).
# image-text-to-text pipeline tag.

_KANANA_15V_CONFIG: dict[str, Any] = {
    "model_type": "kanana-1.5-v",
    "architectures": ["KananaVForConditionalGeneration"],
    "vocab_size": 102400,
    "hidden_size": 3072,
    "num_hidden_layers": 28,
    "num_attention_heads": 16,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_KANANA_15V_CARD_DATA = _make_card_data(
    license="kanana-license",
    pipeline_tag="image-text-to-text",
    language=["ko", "en"],
    library_name="transformers",
)


def _patch_kanana_15v() -> Any:
    return _patch_hf_calls(
        config=_KANANA_15V_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_KANANA_15V_CARD_DATA,
        hub_info={"author": "kakaobank", "sha": "deadf00d"},
    )


def test_kanana_15v_type_of_model() -> None:
    with _patch_kanana_15v():
        meta = read_huggingface("kakaobank/kanana-1.5-v-3b-instruct")
    assert meta.type_of_model == "kanana-1.5-v"


def test_kanana_15v_architecture() -> None:
    with _patch_kanana_15v():
        meta = read_huggingface("kakaobank/kanana-1.5-v-3b-instruct")
    assert meta.architecture == "KananaVForConditionalGeneration"


def test_kanana_15v_license_passthrough() -> None:
    # "kanana-license" is not in _VAGUE_LICENSE_VALUES → stored as-is, no detection
    with _patch_kanana_15v():
        meta = read_huggingface("kakaobank/kanana-1.5-v-3b-instruct")
    assert meta.license == "kanana-license"
    assert "hf.license_raw" not in (meta.extra_data or {})


def test_kanana_15v_image_text_to_text_domain() -> None:
    with _patch_kanana_15v():
        meta = read_huggingface("kakaobank/kanana-1.5-v-3b-instruct")
    assert "image-text-to-text" in meta.usage.domains


def test_kanana_15v_korean_english_language() -> None:
    with _patch_kanana_15v():
        meta = read_huggingface("kakaobank/kanana-1.5-v-3b-instruct")
    langs = (meta.extra_lists or {}).get("hf.language", [])
    assert "ko" in langs
    assert "en" in langs


# ---------------------------------------------------------------------------
# LGAI-EXAONE/EXAONE-4.5-33B  (multimodal, vague license, Korean + multilingual)
# ---------------------------------------------------------------------------

# Korean multimodal LLM from LG AI Research. Pipeline tag image-text-to-text.
# Card license="other" → vague → _detect_license_from_hf_files triggered (mock
# returns (None, None)); license stored as hf.license_raw.

_EXAONE45_33B_CONFIG: dict[str, Any] = {
    "model_type": "exaone4_5",
    "architectures": ["Exaone4_5_ForConditionalGeneration"],
    "vocab_size": 102400,
    "hidden_size": 7168,
    "num_hidden_layers": 64,
    "num_attention_heads": 56,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_EXAONE45_33B_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    language=["ko", "en", "zh", "ja", "es", "fr"],
    library_name="transformers",
)


def _patch_exaone45_33b() -> Any:
    return _patch_hf_calls(
        config=_EXAONE45_33B_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_EXAONE45_33B_CARD_DATA,
        hub_info={"author": "LGAI-EXAONE", "sha": "deadf00d"},
    )


def test_exaone45_33b_type_of_model() -> None:
    with _patch_exaone45_33b():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B")
    assert meta.type_of_model == "exaone4_5"


def test_exaone45_33b_architecture() -> None:
    with _patch_exaone45_33b():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B")
    assert meta.architecture == "Exaone4_5_ForConditionalGeneration"


def test_exaone45_33b_vague_license() -> None:
    # license="other" → vague → detection mock returns (None, None) → license=None
    with _patch_exaone45_33b():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


def test_exaone45_33b_image_text_to_text_domain() -> None:
    with _patch_exaone45_33b():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B")
    assert "image-text-to-text" in meta.usage.domains


def test_exaone45_33b_multilingual() -> None:
    with _patch_exaone45_33b():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B")
    langs = (meta.extra_lists or {}).get("hf.language", [])
    assert "ko" in langs
    assert "en" in langs


# ---------------------------------------------------------------------------
# LGAI-EXAONE/EXAONE-4.5-33B-AWQ  (AWQ quantized, config accessible)
# ---------------------------------------------------------------------------

# AWQ quantization of EXAONE-4.5-33B. Unlike GGUF, config.json IS present and
# accessible. base_model_relation=quantized from hub tags.

_EXAONE45_33B_AWQ_CONFIG: dict[str, Any] = {
    "model_type": "exaone4_5",
    "architectures": ["Exaone4_5_ForConditionalGeneration"],
    "vocab_size": 102400,
    "hidden_size": 7168,
    "num_hidden_layers": 64,
    "num_attention_heads": 56,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "float16",
    "quantization_config": {"quant_type": "awq", "bits": 4},
}

_EXAONE45_33B_AWQ_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    language=["ko", "en"],
    library_name="transformers",
    base_model="LGAI-EXAONE/EXAONE-4.5-33B",
)


def _patch_exaone45_33b_awq() -> Any:
    return _patch_hf_calls(
        config=_EXAONE45_33B_AWQ_CONFIG,
        card_data=_EXAONE45_33B_AWQ_CARD_DATA,
        hub_info={
            "author": "LGAI-EXAONE",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:LGAI-EXAONE/EXAONE-4.5-33B"],
        },
    )


def test_exaone45_33b_awq_type_of_model() -> None:
    # AWQ: config.json is present (unlike GGUF) → type_of_model extractable
    with _patch_exaone45_33b_awq():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-AWQ")
    assert meta.type_of_model == "exaone4_5"


def test_exaone45_33b_awq_base_model_relation() -> None:
    with _patch_exaone45_33b_awq():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-AWQ")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "quantized"


def test_exaone45_33b_awq_base_model() -> None:
    with _patch_exaone45_33b_awq():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-AWQ")
    assert (meta.extra_data or {}).get("hf.base_model") == "LGAI-EXAONE/EXAONE-4.5-33B"


def test_exaone45_33b_awq_image_text_to_text_domain() -> None:
    with _patch_exaone45_33b_awq():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-AWQ")
    assert "image-text-to-text" in meta.usage.domains


def test_exaone45_33b_awq_vague_license() -> None:
    with _patch_exaone45_33b_awq():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-AWQ")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


# ---------------------------------------------------------------------------
# LGAI-EXAONE/EXAONE-4.5-33B-FP8  (FP8 quantized, torch_dtype in hyperparameters)
# ---------------------------------------------------------------------------

# FP8 quantization of EXAONE-4.5-33B. torch_dtype="float8_e4m3fn" is in
# _HYPER_KEYS → captured in hyperparameters dict.

_EXAONE45_33B_FP8_CONFIG: dict[str, Any] = {
    "model_type": "exaone4_5",
    "architectures": ["Exaone4_5_ForConditionalGeneration"],
    "vocab_size": 102400,
    "hidden_size": 7168,
    "num_hidden_layers": 64,
    "num_attention_heads": 56,
    "max_position_embeddings": 131072,
    "torch_dtype": "float8_e4m3fn",
}

_EXAONE45_33B_FP8_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    language=["ko", "en"],
    library_name="transformers",
    base_model="LGAI-EXAONE/EXAONE-4.5-33B",
)


def _patch_exaone45_33b_fp8() -> Any:
    return _patch_hf_calls(
        config=_EXAONE45_33B_FP8_CONFIG,
        card_data=_EXAONE45_33B_FP8_CARD_DATA,
        hub_info={
            "author": "LGAI-EXAONE",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:LGAI-EXAONE/EXAONE-4.5-33B"],
        },
    )


def test_exaone45_33b_fp8_type_of_model() -> None:
    with _patch_exaone45_33b_fp8():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-FP8")
    assert meta.type_of_model == "exaone4_5"


def test_exaone45_33b_fp8_dtype_in_hyperparameters() -> None:
    # torch_dtype is in _HYPER_KEYS → captured even for FP8 quantized dtype
    with _patch_exaone45_33b_fp8():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-FP8")
    assert meta.hyperparameters.get("torch_dtype") == "float8_e4m3fn"


def test_exaone45_33b_fp8_base_model_relation() -> None:
    with _patch_exaone45_33b_fp8():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-FP8")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "quantized"


def test_exaone45_33b_fp8_image_text_to_text_domain() -> None:
    with _patch_exaone45_33b_fp8():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-FP8")
    assert "image-text-to-text" in meta.usage.domains


def test_exaone45_33b_fp8_vague_license() -> None:
    with _patch_exaone45_33b_fp8():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-FP8")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


# ---------------------------------------------------------------------------
# LGAI-EXAONE/EXAONE-4.5-33B-GGUF  (GGUF format, no config.json)
# ---------------------------------------------------------------------------

# GGUF format: config.json absent → type_of_model and architecture are None.
# Card still carries license and pipeline_tag.

_EXAONE45_33B_GGUF_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    language=["ko", "en"],
    library_name="gguf",
    base_model="LGAI-EXAONE/EXAONE-4.5-33B",
)


def _patch_exaone45_33b_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_EXAONE45_33B_GGUF_CARD_DATA,
        hub_info={
            "author": "LGAI-EXAONE",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:LGAI-EXAONE/EXAONE-4.5-33B"],
        },
    )


def test_exaone45_33b_gguf_no_type_of_model() -> None:
    # GGUF: config.json absent → cannot determine model_type
    with _patch_exaone45_33b_gguf():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-GGUF")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_exaone45_33b_gguf_base_model_relation() -> None:
    with _patch_exaone45_33b_gguf():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-GGUF")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "quantized"


def test_exaone45_33b_gguf_vague_license() -> None:
    with _patch_exaone45_33b_gguf():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-GGUF")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


def test_exaone45_33b_gguf_image_text_to_text_domain() -> None:
    with _patch_exaone45_33b_gguf():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-GGUF")
    assert "image-text-to-text" in meta.usage.domains


# ---------------------------------------------------------------------------
# LGAI-EXAONE/EXAONE-Path-2.0-rev-EGFR  (gated, non-standard pipeline tag)
# ---------------------------------------------------------------------------

# Gated pathology vision model. pipeline_tag="pathology-image-analysis" is NOT
# in _DOMAIN_TAGS → usage.domains is empty. Config inaccessible (401 gated).

_EXAONE_PATH_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="pathology-image-analysis",
    language=["en"],
    library_name="transformers",
)


def _patch_exaone_path() -> Any:
    return _patch_hf_calls(
        config=None,  # gated → 401
        tokenizer_config=None,
        card_data=_EXAONE_PATH_CARD_DATA,
        hub_info={"author": "LGAI-EXAONE", "sha": "deadf00d"},
    )


def test_exaone_path_no_architecture() -> None:
    # Config gated → no type_of_model or architecture
    with _patch_exaone_path():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-Path-2.0-rev-EGFR")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_exaone_path_pipeline_tag_captured_as_domain() -> None:
    # pipeline_tag is always added to usage.domains regardless of _DOMAIN_TAGS.
    # _DOMAIN_TAGS only governs which card *tags* qualify as domains.
    with _patch_exaone_path():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-Path-2.0-rev-EGFR")
    assert "pathology-image-analysis" in meta.usage.domains


def test_exaone_path_only_pipeline_tag_domain() -> None:
    # Only the pipeline_tag domain is present; no other domain tags in card.
    with _patch_exaone_path():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-Path-2.0-rev-EGFR")
    assert meta.usage.domains == ["pathology-image-analysis"]


def test_exaone_path_vague_license() -> None:
    with _patch_exaone_path():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-Path-2.0-rev-EGFR")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


# ---------------------------------------------------------------------------
# THUDM/GLM-4.5-Air-REAP  (MoE, merge relation, apache-2.0)
# ---------------------------------------------------------------------------

# GLM4 MoE model adapted by Samsung (REAP). base_model_relation=merge.
# glm4_moe model_type; apache-2.0 license; text-generation domain.

_GLM45_AIR_REAP_CONFIG: dict[str, Any] = {
    "model_type": "glm4_moe",
    "architectures": ["Glm4MoeForCausalLM"],
    "vocab_size": 151552,
    "hidden_size": 4096,
    "num_hidden_layers": 62,
    "num_attention_heads": 32,
    "num_key_value_heads": 2,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_GLM45_AIR_REAP_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "ko", "zh"],
    library_name="transformers",
    base_model="THUDM/GLM-4.5-Air",
)


def _patch_glm45_air_reap() -> Any:
    return _patch_hf_calls(
        config=_GLM45_AIR_REAP_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_GLM45_AIR_REAP_CARD_DATA,
        hub_info={
            "author": "THUDM",
            "sha": "deadf00d",
            "tags": ["base_model:merge:THUDM/GLM-4.5-Air"],
        },
    )


def test_glm45_air_reap_type_of_model() -> None:
    with _patch_glm45_air_reap():
        meta = read_huggingface("THUDM/GLM-4.5-Air-REAP")
    assert meta.type_of_model == "glm4_moe"


def test_glm45_air_reap_architecture() -> None:
    with _patch_glm45_air_reap():
        meta = read_huggingface("THUDM/GLM-4.5-Air-REAP")
    assert meta.architecture == "Glm4MoeForCausalLM"


def test_glm45_air_reap_apache_license() -> None:
    with _patch_glm45_air_reap():
        meta = read_huggingface("THUDM/GLM-4.5-Air-REAP")
    assert meta.license == "apache-2.0"


def test_glm45_air_reap_merge_relation() -> None:
    with _patch_glm45_air_reap():
        meta = read_huggingface("THUDM/GLM-4.5-Air-REAP")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "merge"


def test_glm45_air_reap_text_generation_domain() -> None:
    with _patch_glm45_air_reap():
        meta = read_huggingface("THUDM/GLM-4.5-Air-REAP")
    assert "text-generation" in meta.usage.domains


# ---------------------------------------------------------------------------
# line-corporation/line-distilbert-base-japanese  (DistilBERT, fill-mask)
# ---------------------------------------------------------------------------

# Japanese DistilBERT: 6 transformer layers (half of BERT-base's 12).
# fill-mask pipeline tag. apache-2.0 license.

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

_LINE_DISTILBERT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="fill-mask",
    language=["ja"],
    library_name="transformers",
)


def _patch_line_distilbert() -> Any:
    return _patch_hf_calls(
        config=_LINE_DISTILBERT_CONFIG,
        tokenizer_config={"tokenizer_class": "BertJapaneseTokenizer"},
        card_data=_LINE_DISTILBERT_CARD_DATA,
        hub_info={"author": "line-corporation", "sha": "deadf00d"},
    )


def test_line_distilbert_type_of_model() -> None:
    with _patch_line_distilbert():
        meta = read_huggingface("line-corporation/line-distilbert-base-japanese")
    assert meta.type_of_model == "distilbert"


def test_line_distilbert_architecture() -> None:
    with _patch_line_distilbert():
        meta = read_huggingface("line-corporation/line-distilbert-base-japanese")
    assert meta.architecture == "DistilBertForMaskedLM"


def test_line_distilbert_six_layers() -> None:
    # DistilBERT halves BERT's 12 layers → 6 layers
    with _patch_line_distilbert():
        meta = read_huggingface("line-corporation/line-distilbert-base-japanese")
    assert meta.hyperparameters.get("num_hidden_layers") == 6


def test_line_distilbert_fill_mask_domain() -> None:
    with _patch_line_distilbert():
        meta = read_huggingface("line-corporation/line-distilbert-base-japanese")
    assert "fill-mask" in meta.usage.domains


def test_line_distilbert_apache_license() -> None:
    with _patch_line_distilbert():
        meta = read_huggingface("line-corporation/line-distilbert-base-japanese")
    assert meta.license == "apache-2.0"


# ---------------------------------------------------------------------------
# line-corporation/clip-japanese-base-v2  (CLYP / custom CLIP, feature-extraction)
# ---------------------------------------------------------------------------

# Line Corp custom CLIP variant (CLYP). model_type="clyp" is non-standard.
# feature-extraction pipeline tag; apache-2.0 license; Japanese text encoder.

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


def test_clip_japanese_v2_type_of_model() -> None:
    # Custom "clyp" model_type stored as-is
    with _patch_clip_japanese_v2():
        meta = read_huggingface("line-corporation/clip-japanese-base-v2")
    assert meta.type_of_model == "clyp"


def test_clip_japanese_v2_architecture() -> None:
    with _patch_clip_japanese_v2():
        meta = read_huggingface("line-corporation/clip-japanese-base-v2")
    assert meta.architecture == "CLYPModel"


def test_clip_japanese_v2_feature_extraction_domain() -> None:
    with _patch_clip_japanese_v2():
        meta = read_huggingface("line-corporation/clip-japanese-base-v2")
    assert "feature-extraction" in meta.usage.domains


def test_clip_japanese_v2_apache_license() -> None:
    with _patch_clip_japanese_v2():
        meta = read_huggingface("line-corporation/clip-japanese-base-v2")
    assert meta.license == "apache-2.0"


def test_clip_japanese_v2_hidden_size() -> None:
    with _patch_clip_japanese_v2():
        meta = read_huggingface("line-corporation/clip-japanese-base-v2")
    assert meta.hyperparameters.get("hidden_size") == 768


# ---------------------------------------------------------------------------
# Fujitsu/Fujitsu-LLM-KG-8x7B  (gated, NeMo library, apache-2.0)
# ---------------------------------------------------------------------------

# Gated Fujitsu MoE LLM built with NVIDIA NeMo framework.
# Config inaccessible (401); library_name="nemo" → extra_data["hf.library_name"].

_FUJITSU_LLM_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["ja", "en"],
    library_name="nemo",
)


def _patch_fujitsu_llm() -> Any:
    return _patch_hf_calls(
        config=None,  # gated → 401
        tokenizer_config=None,
        card_data=_FUJITSU_LLM_CARD_DATA,
        hub_info={"author": "Fujitsu", "sha": "deadf00d"},
    )


def test_fujitsu_llm_no_architecture() -> None:
    # Config gated → type_of_model and architecture not available
    with _patch_fujitsu_llm():
        meta = read_huggingface("Fujitsu/Fujitsu-LLM-KG-8x7B")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_fujitsu_llm_nemo_library_name() -> None:
    # NeMo framework: library_name="nemo" → extra_data["hf.library_name"]
    with _patch_fujitsu_llm():
        meta = read_huggingface("Fujitsu/Fujitsu-LLM-KG-8x7B")
    assert (meta.extra_data or {}).get("hf.library_name") == "nemo"


def test_fujitsu_llm_apache_license() -> None:
    with _patch_fujitsu_llm():
        meta = read_huggingface("Fujitsu/Fujitsu-LLM-KG-8x7B")
    assert meta.license == "apache-2.0"


def test_fujitsu_llm_text_generation_domain() -> None:
    with _patch_fujitsu_llm():
        meta = read_huggingface("Fujitsu/Fujitsu-LLM-KG-8x7B")
    assert "text-generation" in meta.usage.domains


# ---------------------------------------------------------------------------
# windowseat-ai/windowseat-reflection  (no config, PEFT library, image-to-image)
# ---------------------------------------------------------------------------

# PEFT adapter model for image-to-image; config.json absent (404).
# library_name="peft" → extra_data["hf.library_name"]; apache-2.0.

_WINDOWSEAT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="image-to-image",
    language=None,
    library_name="peft",
)


def _patch_windowseat() -> Any:
    return _patch_hf_calls(
        config=None,  # absent → 404
        tokenizer_config=None,
        card_data=_WINDOWSEAT_CARD_DATA,
        hub_info={"author": "windowseat-ai", "sha": "deadf00d"},
    )


def test_windowseat_no_architecture() -> None:
    # No config.json → type_of_model and architecture are None
    with _patch_windowseat():
        meta = read_huggingface("windowseat-ai/windowseat-reflection")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_windowseat_peft_library_name() -> None:
    # PEFT adapter: library_name="peft" → extra_data["hf.library_name"]
    with _patch_windowseat():
        meta = read_huggingface("windowseat-ai/windowseat-reflection")
    assert (meta.extra_data or {}).get("hf.library_name") == "peft"


def test_windowseat_image_to_image_domain() -> None:
    with _patch_windowseat():
        meta = read_huggingface("windowseat-ai/windowseat-reflection")
    assert "image-to-image" in meta.usage.domains


def test_windowseat_apache_license() -> None:
    with _patch_windowseat():
        meta = read_huggingface("windowseat-ai/windowseat-reflection")
    assert meta.license == "apache-2.0"


# ---------------------------------------------------------------------------
# Salesforce/moirai-2.0-R-small  (time-series-forecasting domain, custom config)
# ---------------------------------------------------------------------------

# Moirai time-series foundation model. pipeline_tag="time-series-forecasting"
# is a newly added _DOMAIN_TAGS entry. config.json has custom non-transformer
# keys (patch_sizes, d_model, context_length) → none match _HYPER_KEYS →
# hyperparameters is empty. model_type and architectures absent from config.

_MOIRAI_CONFIG: dict[str, Any] = {
    "patch_sizes": [8, 16, 32, 64, 128],
    "d_model": 384,
    "num_encoder_layers": 6,
    "nhead": 8,
    "context_length": 4096,
}

_MOIRAI_CARD_DATA = _make_card_data(
    license="cc-by-nc-4.0",
    pipeline_tag="time-series-forecasting",
    language=None,
    library_name="transformers",
)


def _patch_moirai() -> Any:
    return _patch_hf_calls(
        config=_MOIRAI_CONFIG,
        tokenizer_config=None,
        card_data=_MOIRAI_CARD_DATA,
        hub_info={"author": "Salesforce", "sha": "deadf00d"},
    )


def test_moirai_no_type_of_model() -> None:
    # Config has no "model_type" key → type_of_model=None
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert meta.type_of_model is None


def test_moirai_no_architecture() -> None:
    # Config has no "architectures" key → architecture=None
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert meta.architecture is None


def test_moirai_empty_hyperparameters() -> None:
    # Custom config keys (patch_sizes, d_model, etc.) not in _HYPER_KEYS
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert not meta.hyperparameters


def test_moirai_time_series_forecasting_domain() -> None:
    # "time-series-forecasting" added to _DOMAIN_TAGS → captured as domain
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert "time-series-forecasting" in meta.usage.domains


def test_moirai_cc_by_nc_license() -> None:
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert meta.license == "cc-by-nc-4.0"


# ---------------------------------------------------------------------------
# HKUSTAudio/Llasa-3B  (LLaMA for TTS, large vocabulary, cc-by-nc-4.0)
# ---------------------------------------------------------------------------

# LLaMA-based text-to-speech model. vocab_size=193800 (greatly extended for
# speech tokens). pipeline_tag="text-to-speech"; cc-by-nc-4.0 license.

_LLASA_3B_CONFIG: dict[str, Any] = {
    "model_type": "llama",
    "architectures": ["LlamaForCausalLM"],
    "vocab_size": 193800,
    "hidden_size": 3072,
    "num_hidden_layers": 28,
    "num_attention_heads": 24,
    "num_key_value_heads": 8,
    "max_position_embeddings": 4096,
    "torch_dtype": "bfloat16",
}

_LLASA_3B_CARD_DATA = _make_card_data(
    license="cc-by-nc-4.0",
    pipeline_tag="text-to-speech",
    language=["en", "zh"],
    library_name="transformers",
)


def _patch_llasa_3b() -> Any:
    return _patch_hf_calls(
        config=_LLASA_3B_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_LLASA_3B_CARD_DATA,
        hub_info={"author": "HKUSTAudio", "sha": "deadf00d"},
    )


def test_llasa_3b_type_of_model() -> None:
    # LLaMA architecture repurposed for TTS generation
    with _patch_llasa_3b():
        meta = read_huggingface("HKUSTAudio/Llasa-3B")
    assert meta.type_of_model == "llama"


def test_llasa_3b_architecture() -> None:
    with _patch_llasa_3b():
        meta = read_huggingface("HKUSTAudio/Llasa-3B")
    assert meta.architecture == "LlamaForCausalLM"


def test_llasa_3b_large_vocab_for_tts() -> None:
    # 193 800-token vocab: base LLaMA vocab + speech tokens
    with _patch_llasa_3b():
        meta = read_huggingface("HKUSTAudio/Llasa-3B")
    assert meta.hyperparameters.get("vocab_size") == 193800


def test_llasa_3b_text_to_speech_domain() -> None:
    with _patch_llasa_3b():
        meta = read_huggingface("HKUSTAudio/Llasa-3B")
    assert "text-to-speech" in meta.usage.domains


def test_llasa_3b_cc_by_nc_license() -> None:
    with _patch_llasa_3b():
        meta = read_huggingface("HKUSTAudio/Llasa-3B")
    assert meta.license == "cc-by-nc-4.0"


# ---------------------------------------------------------------------------
# mistralai/Voxtral-Mini-4B-Realtime-2602  (multimodal ASR, voxtral_realtime, vllm)
# ---------------------------------------------------------------------------

# Voxtral is a multimodal audio+text model: an audio encoder (970 M params)
# feeds into a Ministral text decoder (3.4 B params). library_name="vllm" →
# extra_data["hf.library_name"]. pipeline_tag=automatic-speech-recognition.
# The config carries nested audio_config; top-level _HYPER_KEYS are still
# present and captured (hidden_size etc. from the text decoder).

_VOXTRAL_MINI_CONFIG: dict[str, Any] = {
    "model_type": "voxtral_realtime",
    "architectures": ["VoxtralRealtimeForConditionalGeneration"],
    "vocab_size": 131072,
    "hidden_size": 3072,
    "num_hidden_layers": 26,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
    "audio_config": {"audio_length_per_tok": 8},
    "projector_hidden_act": "gelu",
}

_VOXTRAL_MINI_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="automatic-speech-recognition",
    language=[
        "en",
        "fr",
        "es",
        "de",
        "ru",
        "zh",
        "ja",
        "it",
        "pt",
        "nl",
        "ar",
        "hi",
        "ko",
    ],
    library_name="vllm",
    base_model="mistralai/Ministral-3-3B-Base-2512",
)


def _patch_voxtral_mini() -> Any:
    return _patch_hf_calls(
        config=_VOXTRAL_MINI_CONFIG,
        tokenizer_config=None,
        card_data=_VOXTRAL_MINI_CARD_DATA,
        hub_info={
            "author": "mistralai",
            "sha": "deadf00d",
            "tags": ["base_model:finetune:mistralai/Ministral-3-3B-Base-2512"],
        },
    )


def test_voxtral_mini_type_of_model() -> None:
    with _patch_voxtral_mini():
        meta = read_huggingface("mistralai/Voxtral-Mini-4B-Realtime-2602")
    assert meta.type_of_model == "voxtral_realtime"


def test_voxtral_mini_architecture() -> None:
    with _patch_voxtral_mini():
        meta = read_huggingface("mistralai/Voxtral-Mini-4B-Realtime-2602")
    assert meta.architecture == "VoxtralRealtimeForConditionalGeneration"


def test_voxtral_mini_asr_domain() -> None:
    with _patch_voxtral_mini():
        meta = read_huggingface("mistralai/Voxtral-Mini-4B-Realtime-2602")
    assert "automatic-speech-recognition" in meta.usage.domains


def test_voxtral_mini_vllm_library() -> None:
    # vllm as serving framework: library_name="vllm" → hf.library_name
    with _patch_voxtral_mini():
        meta = read_huggingface("mistralai/Voxtral-Mini-4B-Realtime-2602")
    assert (meta.extra_data or {}).get("hf.library_name") == "vllm"


def test_voxtral_mini_hyperparameters() -> None:
    with _patch_voxtral_mini():
        meta = read_huggingface("mistralai/Voxtral-Mini-4B-Realtime-2602")
    assert meta.hyperparameters.get("hidden_size") == 3072
    assert meta.hyperparameters.get("num_key_value_heads") == 8


# ---------------------------------------------------------------------------
# TildeAI/TildeOpen-30b-64k  (YaRN RoPE scaling, 34 EU langs, 7 datasets, cc-by-4.0)
# ---------------------------------------------------------------------------

# Tilde's 30B European LLM fine-tuned with YaRN RoPE to extend context from
# 8 192 → 65 536 tokens. rope_scaling is a dict in config, NOT in _HYPER_KEYS →
# silently skipped; max_position_embeddings=65536 IS captured.
# tokenizer model_max_length=65536 (real value, not unlimited sentinel).
# 7 training corpora in card YAML datasets list.

_TILDEOPEN_30B_64K_CONFIG: dict[str, Any] = {
    "model_type": "llama",
    "architectures": ["LlamaForCausalLM"],
    "vocab_size": 131072,
    "hidden_size": 6144,
    "num_hidden_layers": 60,
    "num_attention_heads": 48,
    "num_key_value_heads": 8,
    "max_position_embeddings": 65536,
    "torch_dtype": "bfloat16",
    "rope_scaling": {
        "rope_type": "yarn",
        "factor": 10.0,
        "original_max_position_embeddings": 8192,
    },
}

_TILDEOPEN_30B_64K_CARD_DATA = _make_card_data(
    license="cc-by-4.0",
    pipeline_tag="text-generation",
    language=[
        "af",
        "bg",
        "ca",
        "cs",
        "cy",
        "da",
        "de",
        "el",
        "en",
        "es",
        "et",
        "eu",
        "fi",
        "fr",
        "ga",
        "hr",
        "hu",
        "is",
        "it",
        "lt",
        "lv",
        "mk",
        "mt",
        "nl",
        "no",
        "pl",
        "pt",
        "ro",
        "sk",
        "sl",
        "sq",
        "sv",
        "uk",
        "la",
    ],
    library_name="transformers",
    datasets=[
        "HPLT/HPLT2.0_cleaned",
        "HPLT/hplt_monolingual_v1_2",
        "HuggingFaceFW/fineweb-2",
        "allenai/MADLAD-400",
        "uonlp/CulturaX",
        "bigcode/the-stack",
        "common-pile/arxiv_papers",
    ],
)


def _patch_tildeopen_30b_64k() -> Any:
    return _patch_hf_calls(
        config=_TILDEOPEN_30B_64K_CONFIG,
        tokenizer_config={
            "tokenizer_class": "PreTrainedTokenizerFast",
            "model_max_length": 65536,
        },
        card_data=_TILDEOPEN_30B_64K_CARD_DATA,
        hub_info={"author": "TildeAI", "sha": "deadf00d"},
    )


def test_tildeopen_30b_64k_type_of_model() -> None:
    with _patch_tildeopen_30b_64k():
        meta = read_huggingface("TildeAI/TildeOpen-30b-64k")
    assert meta.type_of_model == "llama"


def test_tildeopen_30b_64k_yarn_extended_context() -> None:
    # YaRN RoPE extends context from 8192 → 65536; max_position_embeddings captured
    with _patch_tildeopen_30b_64k():
        meta = read_huggingface("TildeAI/TildeOpen-30b-64k")
    assert meta.hyperparameters.get("max_position_embeddings") == 65536


def test_tildeopen_30b_64k_tokenizer_max_length() -> None:
    # model_max_length=65536 is a real value (not unlimited sentinel) → captured
    with _patch_tildeopen_30b_64k():
        meta = read_huggingface("TildeAI/TildeOpen-30b-64k")
    assert (meta.extra_data or {}).get("hf.tokenizer_max_length") == 65536


def test_tildeopen_30b_64k_seven_datasets() -> None:
    with _patch_tildeopen_30b_64k():
        meta = read_huggingface("TildeAI/TildeOpen-30b-64k")
    dataset_names = [d.metadata.name for d in (meta.datasets or [])]
    assert "HPLT/HPLT2.0_cleaned" in dataset_names
    assert "HuggingFaceFW/fineweb-2" in dataset_names
    assert "bigcode/the-stack" in dataset_names
    assert len(dataset_names) == 7


def test_tildeopen_30b_64k_cc_by_license() -> None:
    with _patch_tildeopen_30b_64k():
        meta = read_huggingface("TildeAI/TildeOpen-30b-64k")
    assert meta.license == "cc-by-4.0"


# ---------------------------------------------------------------------------
# TildeAI/TildeOpen-30b  (base model, no YaRN, unlimited tokenizer sentinel)
# ---------------------------------------------------------------------------

# Base 30B model without YaRN context extension. LlamaTokenizer returns the
# ~10^23 sentinel for model_max_length → filtered (not captured). Max position
# is the native 65536 before any extension. Same 7-corpus training dataset list.

_TILDEOPEN_30B_CONFIG: dict[str, Any] = {
    "model_type": "llama",
    "architectures": ["LlamaForCausalLM"],
    "vocab_size": 131072,
    "hidden_size": 6144,
    "num_hidden_layers": 60,
    "num_attention_heads": 48,
    "num_key_value_heads": 8,
    "max_position_embeddings": 65536,
    "torch_dtype": "bfloat16",
}

_TILDEOPEN_30B_CARD_DATA = _make_card_data(
    license="cc-by-4.0",
    pipeline_tag="text-generation",
    language=[
        "af",
        "bg",
        "ca",
        "cs",
        "cy",
        "da",
        "de",
        "el",
        "en",
        "es",
        "et",
        "eu",
        "fi",
        "fr",
        "ga",
        "hr",
        "hu",
        "is",
        "it",
        "lt",
        "lv",
        "mk",
        "mt",
        "nl",
        "no",
        "pl",
        "pt",
        "ro",
        "sk",
        "sl",
        "sq",
        "sv",
        "uk",
        "la",
    ],
    library_name="transformers",
    datasets=[
        "HPLT/HPLT2.0_cleaned",
        "HPLT/hplt_monolingual_v1_2",
        "HuggingFaceFW/fineweb-2",
        "allenai/MADLAD-400",
        "uonlp/CulturaX",
        "bigcode/the-stack",
        "common-pile/arxiv_papers",
    ],
)

# LlamaTokenizer sentinel: ~10^23 → _TOKENIZER_MAX_LEN_UNLIMITED threshold
_TILDEOPEN_TOKENIZER_SENTINEL: int = 1_000_000_000_000_000_019_884_624_838_656


def _patch_tildeopen_30b() -> Any:
    return _patch_hf_calls(
        config=_TILDEOPEN_30B_CONFIG,
        tokenizer_config={
            "tokenizer_class": "LlamaTokenizer",
            "model_max_length": _TILDEOPEN_TOKENIZER_SENTINEL,
        },
        card_data=_TILDEOPEN_30B_CARD_DATA,
        hub_info={"author": "TildeAI", "sha": "deadf00d"},
    )


def test_tildeopen_30b_type_of_model() -> None:
    with _patch_tildeopen_30b():
        meta = read_huggingface("TildeAI/TildeOpen-30b")
    assert meta.type_of_model == "llama"


def test_tildeopen_30b_sentinel_tokenizer_max_length_filtered() -> None:
    # LlamaTokenizer unlimited sentinel → hf.tokenizer_max_length NOT set
    with _patch_tildeopen_30b():
        meta = read_huggingface("TildeAI/TildeOpen-30b")
    assert "hf.tokenizer_max_length" not in (meta.extra_data or {})


def test_tildeopen_30b_seven_datasets() -> None:
    with _patch_tildeopen_30b():
        meta = read_huggingface("TildeAI/TildeOpen-30b")
    assert len(meta.datasets or []) == 7


def test_tildeopen_30b_text_generation_domain() -> None:
    with _patch_tildeopen_30b():
        meta = read_huggingface("TildeAI/TildeOpen-30b")
    assert "text-generation" in meta.usage.domains


# ---------------------------------------------------------------------------
# openeurollm/datamix-9b-80-20  (Gemma-3 tokenizer 262K vocab, no GQA, no pipeline_tag)
# ---------------------------------------------------------------------------

# European LLM pretrained with a Gemma-3-style tokenizer (262 400-token vocab,
# much larger than LLaMA's 128K). num_key_value_heads == num_attention_heads == 32
# (standard MHA, no GQA). No pipeline_tag → empty usage.domains. 3 training datasets.
# tokenizer_config.json absent (404) in real repo; mock uses None.

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


def test_openeurollm_type_of_model() -> None:
    with _patch_openeurollm():
        meta = read_huggingface("openeurollm/datamix-9b-80-20")
    assert meta.type_of_model == "llama"


def test_openeurollm_large_gemma3_vocab() -> None:
    # 262 400-token Gemma-3 tokenizer (vs 128 000 for typical LLaMA models)
    with _patch_openeurollm():
        meta = read_huggingface("openeurollm/datamix-9b-80-20")
    assert meta.hyperparameters.get("vocab_size") == 262400


def test_openeurollm_no_gqa() -> None:
    # num_key_value_heads == num_attention_heads == 32 → standard MHA, no GQA
    with _patch_openeurollm():
        meta = read_huggingface("openeurollm/datamix-9b-80-20")
    assert meta.hyperparameters.get("num_key_value_heads") == 32
    assert meta.hyperparameters.get("num_attention_heads") == 32


def test_openeurollm_no_pipeline_tag_empty_domains() -> None:
    with _patch_openeurollm():
        meta = read_huggingface("openeurollm/datamix-9b-80-20")
    assert not meta.usage.domains


def test_openeurollm_three_datasets() -> None:
    with _patch_openeurollm():
        meta = read_huggingface("openeurollm/datamix-9b-80-20")
    assert len(meta.datasets or []) == 3


# ---------------------------------------------------------------------------
# bigscience/bloom  (BLOOM 176B, custom key names, ALiBi, custom license)
# ---------------------------------------------------------------------------

# BigScience BLOOM 176B uses:
#  • n_layer / n_head instead of num_hidden_layers / num_attention_heads →
#    those keys are NOT in _HYPER_KEYS → layer count NOT captured
#  • No max_position_embeddings (uses ALiBi positional bias, not RoPE)
#  • seq_length (added to _HYPER_KEYS) is absent in the 176B config
#  • bigscience-bloom-rail-1.0 is a custom HF identifier NOT in
#    _VAGUE_LICENSE_VALUES → stored as-is (passthrough)
#  • 59 languages (46 natural + 13 programming languages)

_BLOOM_CONFIG: dict[str, Any] = {
    "model_type": "bloom",
    "architectures": ["BloomForCausalLM"],
    "vocab_size": 250880,
    "hidden_size": 14336,
    "n_layer": 70,  # BLOOM-specific: extractor does NOT capture (not in _HYPER_KEYS)
    "n_head": 112,  # BLOOM-specific: extractor does NOT capture (not in _HYPER_KEYS)
    "attention_softmax_in_fp32": True,
    "masked_softmax_fusion": True,
    # No max_position_embeddings (ALiBi)
    # No torch_dtype in config
}

_BLOOM_CARD_DATA = _make_card_data(
    license="bigscience-bloom-rail-1.0",
    pipeline_tag="text-generation",
    language=[
        "ak",
        "ar",
        "as",
        "bm",
        "bn",
        "ca",
        "code",
        "en",
        "es",
        "eu",
        "fon",
        "fr",
        "gu",
        "hi",
        "id",
        "ig",
        "ki",
        "kn",
        "lg",
        "ln",
        "ml",
        "mr",
        "ne",
        "nso",
        "ny",
        "or",
        "pa",
        "pt",
        "rn",
        "rw",
        "sn",
        "st",
        "sw",
        "ta",
        "te",
        "tn",
        "ts",
        "tum",
        "tw",
        "ur",
        "ve",
        "vi",
        "wo",
        "xh",
        "yo",
        "zh",
        "zu",
    ],
    library_name="transformers",
)


def _patch_bloom() -> Any:
    return _patch_hf_calls(
        config=_BLOOM_CONFIG,
        tokenizer_config={"tokenizer_class": "BloomTokenizerFast"},
        card_data=_BLOOM_CARD_DATA,
        hub_info={"author": "bigscience", "sha": "deadf00d"},
    )


def test_bloom_type_of_model() -> None:
    with _patch_bloom():
        meta = read_huggingface("bigscience/bloom")
    assert meta.type_of_model == "bloom"


def test_bloom_architecture() -> None:
    with _patch_bloom():
        meta = read_huggingface("bigscience/bloom")
    assert meta.architecture == "BloomForCausalLM"


def test_bloom_custom_license_passthrough() -> None:
    # "bigscience-bloom-rail-1.0" not in _VAGUE_LICENSE_VALUES → stored as-is
    with _patch_bloom():
        meta = read_huggingface("bigscience/bloom")
    assert meta.license == "bigscience-bloom-rail-1.0"
    assert "hf.license_raw" not in (meta.extra_data or {})


def test_bloom_vocab_size_captured() -> None:
    with _patch_bloom():
        meta = read_huggingface("bigscience/bloom")
    assert meta.hyperparameters.get("vocab_size") == 250880


def test_bloom_nonstandard_layer_key_not_captured() -> None:
    # BLOOM uses n_layer (not num_hidden_layers) → not in _HYPER_KEYS → absent
    with _patch_bloom():
        meta = read_huggingface("bigscience/bloom")
    assert "num_hidden_layers" not in meta.hyperparameters
    assert "n_layer" not in meta.hyperparameters


def test_bloom_no_max_position_embeddings() -> None:
    # ALiBi positional bias: no fixed max_position_embeddings in config
    with _patch_bloom():
        meta = read_huggingface("bigscience/bloom")
    assert "max_position_embeddings" not in meta.hyperparameters


# ---------------------------------------------------------------------------
# bigscience/bloomz-7b1  (BLOOM 7B, seq_length captured, xP3 dataset, finetune)
# ---------------------------------------------------------------------------

# Instruction-tuned 7B BLOOM variant. seq_length=2048 is BLOOM's context-length
# key (ALiBi models have no max_position_embeddings); added to _HYPER_KEYS so
# it IS now captured. base_model=bigscience/bloom-7b1 (finetune from base).

_BLOOMZ_7B1_CONFIG: dict[str, Any] = {
    "model_type": "bloom",
    "architectures": ["BloomForCausalLM"],
    "vocab_size": 250880,
    "hidden_size": 4096,
    "n_layer": 30,  # BLOOM-specific: not captured
    "n_head": 32,  # BLOOM-specific: not captured
    "seq_length": 2048,  # added to _HYPER_KEYS → captured as context length
    "attention_softmax_in_fp32": True,
    "masked_softmax_fusion": True,
    "bias_dropout_fusion": True,
}

_BLOOMZ_7B1_CARD_DATA = _make_card_data(
    license="bigscience-bloom-rail-1.0",
    pipeline_tag="text-generation",
    language=[
        "ak",
        "ar",
        "as",
        "bm",
        "bn",
        "ca",
        "code",
        "en",
        "es",
        "eu",
        "fon",
        "fr",
        "gu",
        "hi",
        "id",
        "ig",
        "ki",
        "kn",
        "lg",
        "ln",
        "ml",
        "mr",
        "ne",
        "nso",
        "ny",
        "or",
        "pa",
        "pt",
        "rn",
        "rw",
        "sn",
        "st",
        "sw",
        "ta",
        "te",
        "tn",
        "ts",
        "tum",
        "tw",
        "ur",
        "ve",
        "vi",
        "wo",
        "xh",
        "yo",
        "zh",
        "zu",
    ],
    library_name="transformers",
    base_model="bigscience/bloom-7b1",
    datasets=["bigscience/xP3"],
)


def _patch_bloomz_7b1() -> Any:
    return _patch_hf_calls(
        config=_BLOOMZ_7B1_CONFIG,
        tokenizer_config={"tokenizer_class": "BloomTokenizerFast"},
        card_data=_BLOOMZ_7B1_CARD_DATA,
        hub_info={
            "author": "bigscience",
            "sha": "deadf00d",
            "tags": ["base_model:finetune:bigscience/bloom-7b1"],
        },
    )


def test_bloomz_7b1_type_of_model() -> None:
    with _patch_bloomz_7b1():
        meta = read_huggingface("bigscience/bloomz-7b1")
    assert meta.type_of_model == "bloom"


def test_bloomz_7b1_seq_length_captured() -> None:
    # seq_length added to _HYPER_KEYS → BLOOM context length now captured
    with _patch_bloomz_7b1():
        meta = read_huggingface("bigscience/bloomz-7b1")
    assert meta.hyperparameters.get("seq_length") == 2048


def test_bloomz_7b1_base_model_finetune() -> None:
    with _patch_bloomz_7b1():
        meta = read_huggingface("bigscience/bloomz-7b1")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "finetune"
    assert (meta.extra_data or {}).get("hf.base_model") == "bigscience/bloom-7b1"


def test_bloomz_7b1_xp3_dataset() -> None:
    with _patch_bloomz_7b1():
        meta = read_huggingface("bigscience/bloomz-7b1")
    assert any(d.metadata.name == "bigscience/xP3" for d in (meta.datasets or []))


def test_bloomz_7b1_custom_license_passthrough() -> None:
    with _patch_bloomz_7b1():
        meta = read_huggingface("bigscience/bloomz-7b1")
    assert meta.license == "bigscience-bloom-rail-1.0"


# ---------------------------------------------------------------------------
# CohereLabs/aya-23-8B  (fully gated: card + config both 401)
# ---------------------------------------------------------------------------

# Cohere Aya 23 multilingual instruction model. Both model card and config.json
# return 401 → nearly empty metadata. Pattern matches CohereLabs/aya-vision-8b.


def _patch_cohere_aya_23() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data={},  # gated card → empty dict
        hub_info={"author": "CohereLabs", "sha": "deadf00d"},
    )


def test_cohere_aya_23_no_type_of_model() -> None:
    with _patch_cohere_aya_23():
        meta = read_huggingface("CohereLabs/aya-23-8B")
    assert meta.type_of_model is None


def test_cohere_aya_23_no_license() -> None:
    with _patch_cohere_aya_23():
        meta = read_huggingface("CohereLabs/aya-23-8B")
    assert meta.license is None


def test_cohere_aya_23_empty_domains() -> None:
    with _patch_cohere_aya_23():
        meta = read_huggingface("CohereLabs/aya-23-8B")
    assert not meta.usage.domains


def test_cohere_aya_23_author_captured_from_hub_info() -> None:
    with _patch_cohere_aya_23():
        meta = read_huggingface("CohereLabs/aya-23-8B")
    assert (meta.extra_data or {}).get("hf.author") == "CohereLabs"


# ---------------------------------------------------------------------------
# occiglot/occiglot-7b-eu5-instruct  (Mistral, sliding_window, 5 EU langs, finetune)
# ---------------------------------------------------------------------------

# European Mistral-based instruct model fine-tuned on 5 EU languages.
# sliding_window=4096 is in _HYPER_KEYS → captured. Tokenizer uses unlimited
# sentinel (LlamaTokenizer) → hf.tokenizer_max_length not set.

_OCCIGLOT_CONFIG: dict[str, Any] = {
    "model_type": "mistral",
    "architectures": ["MistralForCausalLM"],
    "vocab_size": 32002,
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "max_position_embeddings": 32768,
    "sliding_window": 4096,
    "torch_dtype": "bfloat16",
}

_OCCIGLOT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "es", "de", "fr", "it"],
    library_name="transformers",
    base_model="occiglot/occiglot-7b-eu5",
)

_OCCIGLOT_TOKENIZER_SENTINEL: int = 1_000_000_000_000_000_019_884_624_838_656


def _patch_occiglot() -> Any:
    return _patch_hf_calls(
        config=_OCCIGLOT_CONFIG,
        tokenizer_config={
            "tokenizer_class": "LlamaTokenizer",
            "model_max_length": _OCCIGLOT_TOKENIZER_SENTINEL,
        },
        card_data=_OCCIGLOT_CARD_DATA,
        hub_info={
            "author": "occiglot",
            "sha": "deadf00d",
            "tags": ["base_model:finetune:occiglot/occiglot-7b-eu5"],
        },
    )


def test_occiglot_type_of_model() -> None:
    with _patch_occiglot():
        meta = read_huggingface("occiglot/occiglot-7b-eu5-instruct")
    assert meta.type_of_model == "mistral"


def test_occiglot_sliding_window_captured() -> None:
    # sliding_window is in _HYPER_KEYS → captured as hyperparameter
    with _patch_occiglot():
        meta = read_huggingface("occiglot/occiglot-7b-eu5-instruct")
    assert meta.hyperparameters.get("sliding_window") == 4096


def test_occiglot_finetune_from_base() -> None:
    with _patch_occiglot():
        meta = read_huggingface("occiglot/occiglot-7b-eu5-instruct")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "finetune"
    assert (meta.extra_data or {}).get("hf.base_model") == "occiglot/occiglot-7b-eu5"


def test_occiglot_five_eu_languages() -> None:
    with _patch_occiglot():
        meta = read_huggingface("occiglot/occiglot-7b-eu5-instruct")
    langs = (meta.extra_lists or {}).get("hf.language", [])
    assert set(langs) == {"en", "es", "de", "fr", "it"}


def test_occiglot_sentinel_filtered() -> None:
    # Unlimited sentinel → hf.tokenizer_max_length not set
    with _patch_occiglot():
        meta = read_huggingface("occiglot/occiglot-7b-eu5-instruct")
    assert "hf.tokenizer_max_length" not in (meta.extra_data or {})


# ---------------------------------------------------------------------------
# Aleph-Alpha/Pharia-1-LLM-7B-control  (other + license_name, custom scaling lib)
# ---------------------------------------------------------------------------

# Aleph-Alpha's 7B LLM uses a custom "scaling" framework (not transformers).
# config.json is absent (404) — the model uses a proprietary weight format.
# Card: license=other + license_name=open-aleph-license (secondary field).
# 7 European languages.

_PHARIA_CONTROL_CARD_DATA = _make_card_data(
    license="other",
    license_name="open-aleph-license",
    pipeline_tag="text-generation",
    language=["de", "en", "fr", "es", "it", "pt", "nl"],
    library_name="scaling",
)


def _patch_pharia_control() -> Any:
    return _patch_hf_calls(
        config=None,  # absent (404) — custom scaling framework
        tokenizer_config=None,
        card_data=_PHARIA_CONTROL_CARD_DATA,
        hub_info={"author": "Aleph-Alpha", "sha": "deadf00d"},
    )


def test_pharia_control_no_architecture() -> None:
    # Config absent: no type_of_model or architecture
    with _patch_pharia_control():
        meta = read_huggingface("Aleph-Alpha/Pharia-1-LLM-7B-control")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_pharia_control_vague_license_with_license_name() -> None:
    # license=other (vague) → detection triggered → mock returns (None, None)
    # license_name=open-aleph-license stored in extra_data["hf.license_name"]
    with _patch_pharia_control():
        meta = read_huggingface("Aleph-Alpha/Pharia-1-LLM-7B-control")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"
    assert (meta.extra_data or {}).get("hf.license_name") == "open-aleph-license"


def test_pharia_control_scaling_library() -> None:
    # Custom "scaling" framework: library_name="scaling" → hf.library_name
    with _patch_pharia_control():
        meta = read_huggingface("Aleph-Alpha/Pharia-1-LLM-7B-control")
    assert (meta.extra_data or {}).get("hf.library_name") == "scaling"


def test_pharia_control_text_generation_domain() -> None:
    with _patch_pharia_control():
        meta = read_huggingface("Aleph-Alpha/Pharia-1-LLM-7B-control")
    assert "text-generation" in meta.usage.domains


def test_pharia_control_seven_eu_languages() -> None:
    with _patch_pharia_control():
        meta = read_huggingface("Aleph-Alpha/Pharia-1-LLM-7B-control")
    langs = (meta.extra_lists or {}).get("hf.language", [])
    assert set(langs) == {"de", "en", "fr", "es", "it", "pt", "nl"}


# ---------------------------------------------------------------------------
# Aleph-Alpha/Pharia-1-LLM-7B-control-aligned  (DPO-aligned variant of control)
# ---------------------------------------------------------------------------

# DPO/RLHF-aligned variant of Pharia-1-LLM-7B-control. Same custom "scaling"
# framework, same config-absent (404) pattern. base_model_relation=finetune
# from the unaligned control variant.

_PHARIA_ALIGNED_CARD_DATA = _make_card_data(
    license="other",
    license_name="open-aleph-license",
    pipeline_tag="text-generation",
    language=["de", "en", "fr", "es", "it", "pt", "nl"],
    library_name="scaling",
    base_model="Aleph-Alpha/Pharia-1-LLM-7B-control",
)


def _patch_pharia_aligned() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_PHARIA_ALIGNED_CARD_DATA,
        hub_info={
            "author": "Aleph-Alpha",
            "sha": "deadf00d",
            "tags": ["base_model:finetune:Aleph-Alpha/Pharia-1-LLM-7B-control"],
        },
    )


def test_pharia_aligned_no_architecture() -> None:
    with _patch_pharia_aligned():
        meta = read_huggingface("Aleph-Alpha/Pharia-1-LLM-7B-control-aligned")
    assert meta.type_of_model is None


def test_pharia_aligned_finetune_from_control() -> None:
    with _patch_pharia_aligned():
        meta = read_huggingface("Aleph-Alpha/Pharia-1-LLM-7B-control-aligned")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "finetune"
    assert (meta.extra_data or {}).get(
        "hf.base_model"
    ) == "Aleph-Alpha/Pharia-1-LLM-7B-control"


def test_pharia_aligned_vague_license_with_license_name() -> None:
    with _patch_pharia_aligned():
        meta = read_huggingface("Aleph-Alpha/Pharia-1-LLM-7B-control-aligned")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_name") == "open-aleph-license"


def test_pharia_aligned_text_generation_domain() -> None:
    with _patch_pharia_aligned():
        meta = read_huggingface("Aleph-Alpha/Pharia-1-LLM-7B-control-aligned")
    assert "text-generation" in meta.usage.domains


# ---------------------------------------------------------------------------
# Unbabel/wmt22-cometkiwi-da  (fully gated: card + config both 401)
# ---------------------------------------------------------------------------

# Unbabel's COMET-Kiwi quality estimation model for MT evaluation. Gated access
# requires accepting a license agreement; both card and config return 401.
# Pattern matches other fully gated repos (CohereLabs/aya-vision-8b, aya-23-8B).


def _patch_wmt22_cometkiwi() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data={},  # gated → empty
        hub_info={"author": "Unbabel", "sha": "deadf00d"},
    )


def test_wmt22_cometkiwi_no_type_of_model() -> None:
    with _patch_wmt22_cometkiwi():
        meta = read_huggingface("Unbabel/wmt22-cometkiwi-da")
    assert meta.type_of_model is None


def test_wmt22_cometkiwi_no_license() -> None:
    with _patch_wmt22_cometkiwi():
        meta = read_huggingface("Unbabel/wmt22-cometkiwi-da")
    assert meta.license is None


def test_wmt22_cometkiwi_empty_domains() -> None:
    with _patch_wmt22_cometkiwi():
        meta = read_huggingface("Unbabel/wmt22-cometkiwi-da")
    assert not meta.usage.domains


def test_wmt22_cometkiwi_author_from_hub_info() -> None:
    with _patch_wmt22_cometkiwi():
        meta = read_huggingface("Unbabel/wmt22-cometkiwi-da")
    assert (meta.extra_data or {}).get("hf.author") == "Unbabel"


# ---------------------------------------------------------------------------
# utter-project/EuroLLM-1.7B  (34 EU langs, GQA 16h/8kv, no pipeline_tag)
# ---------------------------------------------------------------------------

# Small multilingual European LLM. Grouped-query attention (8 KV heads vs 16
# attention heads). 34 languages (EU + some major world languages). No
# pipeline_tag → empty usage.domains. Unlimited tokenizer sentinel filtered.

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

_EUROLLM_TOKENIZER_SENTINEL: int = 1_000_000_000_000_000_019_884_624_838_656


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


def test_eurollm_1b7_type_of_model() -> None:
    with _patch_eurollm_1b7():
        meta = read_huggingface("utter-project/EuroLLM-1.7B")
    assert meta.type_of_model == "llama"


def test_eurollm_1b7_gqa() -> None:
    # GQA: 8 KV heads for 16 attention heads
    with _patch_eurollm_1b7():
        meta = read_huggingface("utter-project/EuroLLM-1.7B")
    assert meta.hyperparameters.get("num_attention_heads") == 16
    assert meta.hyperparameters.get("num_key_value_heads") == 8


def test_eurollm_1b7_no_pipeline_tag_empty_domains() -> None:
    with _patch_eurollm_1b7():
        meta = read_huggingface("utter-project/EuroLLM-1.7B")
    assert not meta.usage.domains


def test_eurollm_1b7_34_languages() -> None:
    with _patch_eurollm_1b7():
        meta = read_huggingface("utter-project/EuroLLM-1.7B")
    langs = (meta.extra_lists or {}).get("hf.language", [])
    assert len(langs) == 34
    assert "ga" in langs  # Irish (low-resource EU language)
    assert "mt" in langs  # Maltese


def test_eurollm_1b7_sentinel_filtered() -> None:
    with _patch_eurollm_1b7():
        meta = read_huggingface("utter-project/EuroLLM-1.7B")
    assert "hf.tokenizer_max_length" not in (meta.extra_data or {})


# ===========================================================================
# Batch 8 – 3D generation, new library formats, new architectures
# ===========================================================================

# ---------------------------------------------------------------------------
# stabilityai/stable-zero123  (text-to-3d, diffusers, vague license)
# ---------------------------------------------------------------------------

# Stable-Zero123 lifts 2-D images to 3-D objects. pipeline_tag=text-to-3d
# (new _DOMAIN_TAGS entry). Config absent (404); library_name=diffusers.
# Card: license=other → _detect_license_from_hf_files triggered.

_STABLE_ZERO123_CARD_DATA = _make_card_data(
    license="other",
    license_name="sai-nc-community",
    pipeline_tag="text-to-3d",
    language=None,
    library_name="diffusers",
)


def _patch_stable_zero123() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_STABLE_ZERO123_CARD_DATA,
        hub_info={"author": "stabilityai", "sha": "deadf00d"},
    )


def test_stable_zero123_text_to_3d_domain() -> None:
    # text-to-3d added to _DOMAIN_TAGS; as pipeline_tag it is captured directly
    with _patch_stable_zero123():
        meta = read_huggingface("stabilityai/stable-zero123")
    assert "text-to-3d" in meta.usage.domains


def test_stable_zero123_vague_license() -> None:
    with _patch_stable_zero123():
        meta = read_huggingface("stabilityai/stable-zero123")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"
    assert (meta.extra_data or {}).get("hf.license_name") == "sai-nc-community"


def test_stable_zero123_no_architecture() -> None:
    with _patch_stable_zero123():
        meta = read_huggingface("stabilityai/stable-zero123")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_stable_zero123_diffusers_library() -> None:
    with _patch_stable_zero123():
        meta = read_huggingface("stabilityai/stable-zero123")
    assert (meta.extra_data or {}).get("hf.library_name") == "diffusers"


# ---------------------------------------------------------------------------
# openai/shap-e  (text-to-3d, MIT, no config)
# ---------------------------------------------------------------------------

# Shap·E generates 3-D assets from text or images. No config.json (404).
# License: MIT. library_name absent.

_SHAP_E_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="text-to-3d",
    language=None,
    library_name=None,
)


def _patch_shap_e() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_SHAP_E_CARD_DATA,
        hub_info={"author": "openai", "sha": "deadf00d"},
    )


def test_shap_e_text_to_3d_domain() -> None:
    with _patch_shap_e():
        meta = read_huggingface("openai/shap-e")
    assert "text-to-3d" in meta.usage.domains


def test_shap_e_mit_license() -> None:
    with _patch_shap_e():
        meta = read_huggingface("openai/shap-e")
    assert meta.license == "mit"


def test_shap_e_no_architecture() -> None:
    with _patch_shap_e():
        meta = read_huggingface("openai/shap-e")
    assert meta.type_of_model is None


# ---------------------------------------------------------------------------
# FreedomIntelligence/BlenderLLM  (text-to-3d pipeline, Qwen2 LLM)
# ---------------------------------------------------------------------------

# BlenderLLM is a standard Qwen2 LLM fine-tuned to generate Blender Python
# scripts for 3-D modelling. pipeline_tag=text-to-3d even though the
# underlying arch is a plain decoder LLM (not a diffusion/3D model).

_BLENDERLLM_CONFIG: dict[str, Any] = {
    "model_type": "qwen2",
    "architectures": ["Qwen2ForCausalLM"],
    "vocab_size": 152064,
    "hidden_size": 3584,
    "num_hidden_layers": 28,
    "num_attention_heads": 28,
    "num_key_value_heads": 4,
    "max_position_embeddings": 32768,
    "torch_dtype": "bfloat16",
}

_BLENDERLLM_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-to-3d",
    language=["en"],
    library_name="transformers",
)


def _patch_blenderllm() -> Any:
    return _patch_hf_calls(
        config=_BLENDERLLM_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_BLENDERLLM_CARD_DATA,
        hub_info={"author": "FreedomIntelligence", "sha": "deadf00d"},
    )


def test_blenderllm_type_of_model() -> None:
    # Standard Qwen2 decoder with text-to-3d pipeline (Blender script generation)
    with _patch_blenderllm():
        meta = read_huggingface("FreedomIntelligence/BlenderLLM")
    assert meta.type_of_model == "qwen2"


def test_blenderllm_text_to_3d_domain() -> None:
    with _patch_blenderllm():
        meta = read_huggingface("FreedomIntelligence/BlenderLLM")
    assert "text-to-3d" in meta.usage.domains


def test_blenderllm_hyperparameters() -> None:
    with _patch_blenderllm():
        meta = read_huggingface("FreedomIntelligence/BlenderLLM")
    assert meta.hyperparameters.get("hidden_size") == 3584


# ---------------------------------------------------------------------------
# hellork/BlenderLLM-IQ3_XXS-GGUF  (GGUF of BlenderLLM, text-to-3d, quantized)
# ---------------------------------------------------------------------------

# GGUF quantization of BlenderLLM. No config.json (404). pipeline_tag=text-to-3d
# inherited from base. base_model_relation=quantized.

_BLENDERLLM_GGUF_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-to-3d",
    language=None,
    library_name="gguf",
    base_model="FreedomIntelligence/BlenderLLM",
)


def _patch_blenderllm_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_BLENDERLLM_GGUF_CARD_DATA,
        hub_info={
            "author": "hellork",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:FreedomIntelligence/BlenderLLM"],
        },
    )


def test_blenderllm_gguf_no_architecture() -> None:
    with _patch_blenderllm_gguf():
        meta = read_huggingface("hellork/BlenderLLM-IQ3_XXS-GGUF")
    assert meta.type_of_model is None


def test_blenderllm_gguf_text_to_3d_domain() -> None:
    with _patch_blenderllm_gguf():
        meta = read_huggingface("hellork/BlenderLLM-IQ3_XXS-GGUF")
    assert "text-to-3d" in meta.usage.domains


def test_blenderllm_gguf_quantized_relation() -> None:
    with _patch_blenderllm_gguf():
        meta = read_huggingface("hellork/BlenderLLM-IQ3_XXS-GGUF")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "quantized"
    assert (meta.extra_data or {}).get(
        "hf.base_model"
    ) == "FreedomIntelligence/BlenderLLM"


# ---------------------------------------------------------------------------
# tencent/HY-Motion-1.0  (text-to-3d, vague license, HY-Motion library)
# ---------------------------------------------------------------------------

# Tencent Hunyuan Motion generation model. pipeline_tag=text-to-3d. Library
# name is the model series name itself ("HY-Motion-1.0"). Card: license=other
# + license_name=tencent-hunyuan-community. Config accessible but uses
# custom keys (no standard _HYPER_KEYS present).

_HY_MOTION_CONFIG: dict[str, Any] = {
    "Name": "HunyuanMotion",  # non-standard metadata field
    "motion_module_type": "vanilla",
    "num_transformer_blocks": 20,
}

_HY_MOTION_CARD_DATA = _make_card_data(
    license="other",
    license_name="tencent-hunyuan-community",
    pipeline_tag="text-to-3d",
    language=["zh", "en"],
    library_name="HY-Motion-1.0",
)


def _patch_hy_motion() -> Any:
    return _patch_hf_calls(
        config=_HY_MOTION_CONFIG,
        tokenizer_config=None,
        card_data=_HY_MOTION_CARD_DATA,
        hub_info={"author": "tencent", "sha": "deadf00d"},
    )


def test_hy_motion_text_to_3d_domain() -> None:
    with _patch_hy_motion():
        meta = read_huggingface("tencent/HY-Motion-1.0")
    assert "text-to-3d" in meta.usage.domains


def test_hy_motion_vague_license_with_license_name() -> None:
    # license=other (vague) + license_name=tencent-hunyuan-community
    with _patch_hy_motion():
        meta = read_huggingface("tencent/HY-Motion-1.0")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"
    assert (meta.extra_data or {}).get("hf.license_name") == "tencent-hunyuan-community"


def test_hy_motion_no_type_of_model() -> None:
    # Custom config keys, no model_type/architectures at top level
    with _patch_hy_motion():
        meta = read_huggingface("tencent/HY-Motion-1.0")
    assert meta.type_of_model is None
    assert not meta.hyperparameters


def test_hy_motion_library_name() -> None:
    with _patch_hy_motion():
        meta = read_huggingface("tencent/HY-Motion-1.0")
    assert (meta.extra_data or {}).get("hf.library_name") == "HY-Motion-1.0"


# ---------------------------------------------------------------------------
# apple/Sharp  (image-to-3d, apple-amlr passthrough, ml-sharp library)
# ---------------------------------------------------------------------------

# Apple Sharp generates 3-D from a single 2-D image. pipeline_tag=image-to-3d
# (new _DOMAIN_TAGS entry). library_name=ml-sharp (Apple's custom library).
# license=apple-amlr → passthrough (not in _VAGUE_LICENSE_VALUES). No config.

_APPLE_SHARP_CARD_DATA = _make_card_data(
    license="apple-amlr",
    pipeline_tag="image-to-3d",
    language=None,
    library_name="ml-sharp",
)


def _patch_apple_sharp() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_APPLE_SHARP_CARD_DATA,
        hub_info={"author": "apple", "sha": "deadf00d"},
    )


def test_apple_sharp_image_to_3d_domain() -> None:
    # image-to-3d added to _DOMAIN_TAGS
    with _patch_apple_sharp():
        meta = read_huggingface("apple/Sharp")
    assert "image-to-3d" in meta.usage.domains


def test_apple_sharp_apple_amlr_license_passthrough() -> None:
    # apple-amlr not in _VAGUE_LICENSE_VALUES → stored as-is
    with _patch_apple_sharp():
        meta = read_huggingface("apple/Sharp")
    assert meta.license == "apple-amlr"
    assert "hf.license_raw" not in (meta.extra_data or {})


def test_apple_sharp_ml_sharp_library() -> None:
    with _patch_apple_sharp():
        meta = read_huggingface("apple/Sharp")
    assert (meta.extra_data or {}).get("hf.library_name") == "ml-sharp"


def test_apple_sharp_no_architecture() -> None:
    with _patch_apple_sharp():
        meta = read_huggingface("apple/Sharp")
    assert meta.type_of_model is None


# ---------------------------------------------------------------------------
# FireRedTeam/FireRedVAD  (voice-activity-detection, no config)
# ---------------------------------------------------------------------------

# Voice Activity Detection model. pipeline_tag=voice-activity-detection
# (new _DOMAIN_TAGS entry). No config.json (404).

_FIRERED_VAD_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="voice-activity-detection",
    language=None,
    library_name=None,
)


def _patch_firered_vad() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_FIRERED_VAD_CARD_DATA,
        hub_info={"author": "FireRedTeam", "sha": "deadf00d"},
    )


def test_firered_vad_voice_activity_detection_domain() -> None:
    # voice-activity-detection added to _DOMAIN_TAGS
    with _patch_firered_vad():
        meta = read_huggingface("FireRedTeam/FireRedVAD")
    assert "voice-activity-detection" in meta.usage.domains


def test_firered_vad_apache_license() -> None:
    with _patch_firered_vad():
        meta = read_huggingface("FireRedTeam/FireRedVAD")
    assert meta.license == "apache-2.0"


def test_firered_vad_no_architecture() -> None:
    with _patch_firered_vad():
        meta = read_huggingface("FireRedTeam/FireRedVAD")
    assert meta.type_of_model is None


# ---------------------------------------------------------------------------
# Alibaba-NLP/gte-multilingual-reranker-base  (text-ranking, "new" model_type)
# ---------------------------------------------------------------------------

# GTE multilingual reranker uses pipeline_tag=text-ranking (new _DOMAIN_TAGS
# entry). Unusually, model_type="new" is a literal placeholder string used by
# the GTE model family — not a descriptive name. architectures uses the same
# placeholder: NewForSequenceClassification.

_GTE_RERANKER_CONFIG: dict[str, Any] = {
    "model_type": "new",
    "architectures": ["NewForSequenceClassification"],
    "vocab_size": 250002,
    "hidden_size": 768,
    "num_hidden_layers": 12,
    "torch_dtype": "bfloat16",
}

_GTE_RERANKER_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-ranking",
    language=["multilingual"],
    library_name="sentence-transformers",
)


def _patch_gte_reranker() -> Any:
    return _patch_hf_calls(
        config=_GTE_RERANKER_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_GTE_RERANKER_CARD_DATA,
        hub_info={"author": "Alibaba-NLP", "sha": "deadf00d"},
    )


def test_gte_reranker_text_ranking_domain() -> None:
    # text-ranking added to _DOMAIN_TAGS; captured via pipeline_tag
    with _patch_gte_reranker():
        meta = read_huggingface("Alibaba-NLP/gte-multilingual-reranker-base")
    assert "text-ranking" in meta.usage.domains


def test_gte_reranker_model_type_placeholder() -> None:
    # model_type="new" is a literal placeholder string used by Alibaba GTE
    with _patch_gte_reranker():
        meta = read_huggingface("Alibaba-NLP/gte-multilingual-reranker-base")
    assert meta.type_of_model == "new"
    assert meta.architecture == "NewForSequenceClassification"


def test_gte_reranker_apache_license() -> None:
    with _patch_gte_reranker():
        meta = read_huggingface("Alibaba-NLP/gte-multilingual-reranker-base")
    assert meta.license == "apache-2.0"


def test_gte_reranker_sentence_transformers_library() -> None:
    with _patch_gte_reranker():
        meta = read_huggingface("Alibaba-NLP/gte-multilingual-reranker-base")
    assert (meta.extra_data or {}).get("hf.library_name") == "sentence-transformers"


# ---------------------------------------------------------------------------
# apple/OpenELM-270M  (openelm arch, apple-amlr passthrough, custom config)
# ---------------------------------------------------------------------------

# Apple OpenELM-270M uses a custom efficient architecture ("openelm").
# Config has non-standard keys (activation_fn_name, ffn_dim_divisor) alongside
# the standard head_dim (which IS in _HYPER_KEYS → captured).
# license=apple-amlr → passthrough.

_OPENELM_270M_CONFIG: dict[str, Any] = {
    "model_type": "openelm",
    "architectures": ["OpenELMForCausalLM"],
    "vocab_size": 32000,
    "hidden_size": 1280,
    "num_hidden_layers": 16,
    "num_attention_heads": 10,
    "head_dim": 64,
    "max_position_embeddings": 2048,
    "torch_dtype": "float16",
    "activation_fn_name": "swiglu",  # non-standard
    "ffn_dim_divisor": 256,  # non-standard
}

_OPENELM_270M_CARD_DATA = _make_card_data(
    license="apple-amlr",
    pipeline_tag="text-generation",
    language=["en"],
    library_name="transformers",
)


def _patch_openelm_270m() -> Any:
    return _patch_hf_calls(
        config=_OPENELM_270M_CONFIG,
        tokenizer_config={"tokenizer_class": "LlamaTokenizer"},
        card_data=_OPENELM_270M_CARD_DATA,
        hub_info={"author": "apple", "sha": "deadf00d"},
    )


def test_openelm_270m_type_of_model() -> None:
    with _patch_openelm_270m():
        meta = read_huggingface("apple/OpenELM-270M")
    assert meta.type_of_model == "openelm"


def test_openelm_270m_architecture() -> None:
    with _patch_openelm_270m():
        meta = read_huggingface("apple/OpenELM-270M")
    assert meta.architecture == "OpenELMForCausalLM"


def test_openelm_270m_head_dim_captured() -> None:
    # head_dim is in _HYPER_KEYS → captured even for custom arch
    with _patch_openelm_270m():
        meta = read_huggingface("apple/OpenELM-270M")
    assert meta.hyperparameters.get("head_dim") == 64


def test_openelm_270m_apple_amlr_passthrough() -> None:
    with _patch_openelm_270m():
        meta = read_huggingface("apple/OpenELM-270M")
    assert meta.license == "apple-amlr"


# ---------------------------------------------------------------------------
# MiniMaxAI/MiniMax-M2.7  (minimax_m2 arch, MoE with MTP, vague license)
# ---------------------------------------------------------------------------

# MiniMax M2 is a hybrid MoE model with multi-head latent attention and
# multi-token prediction (MTP). Custom config keys: attn_type_list (mixed
# attention types), mtp_transformer_layers (MTP depth), num_experts_per_tok
# (MoE routing) — none are in _HYPER_KEYS → silently skipped.
# license=other → vague → file detection triggered.

_MINIMAX_M2_CONFIG: dict[str, Any] = {
    "model_type": "minimax_m2",
    "architectures": ["MiniMaxM2ForCausalLM"],
    "vocab_size": 200064,
    "hidden_size": 7168,
    "num_hidden_layers": 80,
    "num_attention_heads": 64,
    "num_key_value_heads": 8,
    "max_position_embeddings": 1000000,
    "torch_dtype": "bfloat16",
    "attn_type_list": ["mhsa", "local"] * 40,  # non-standard: mixed attention
    "mtp_transformer_layers": 3,  # non-standard: multi-token prediction
    "num_experts_per_tok": 2,  # non-standard: MoE routing
}

_MINIMAX_M2_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="text-generation",
    language=["en", "zh"],
    library_name="transformers",
)


def _patch_minimax_m2() -> Any:
    return _patch_hf_calls(
        config=_MINIMAX_M2_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_MINIMAX_M2_CARD_DATA,
        hub_info={"author": "MiniMaxAI", "sha": "deadf00d"},
    )


def test_minimax_m2_type_of_model() -> None:
    with _patch_minimax_m2():
        meta = read_huggingface("MiniMaxAI/MiniMax-M2.7")
    assert meta.type_of_model == "minimax_m2"


def test_minimax_m2_architecture() -> None:
    with _patch_minimax_m2():
        meta = read_huggingface("MiniMaxAI/MiniMax-M2.7")
    assert meta.architecture == "MiniMaxM2ForCausalLM"


def test_minimax_m2_very_long_context() -> None:
    # max_position_embeddings=1_000_000 → captured
    with _patch_minimax_m2():
        meta = read_huggingface("MiniMaxAI/MiniMax-M2.7")
    assert meta.hyperparameters.get("max_position_embeddings") == 1_000_000


def test_minimax_m2_vague_license() -> None:
    with _patch_minimax_m2():
        meta = read_huggingface("MiniMaxAI/MiniMax-M2.7")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


# ---------------------------------------------------------------------------
# inclusionAI/LLaDA2.0-Uni  (llada2_moe arch, diffusion LM, any-to-any)
# ---------------------------------------------------------------------------

# LLaDA2.0-Uni is a Large Language Diffusion with mAsking model — it uses
# discrete diffusion (masked tokens) rather than autoregressive generation.
# model_type=llada2_moe; pipeline_tag=any-to-any (already in _DOMAIN_TAGS).

_LLADA2_MOE_CONFIG: dict[str, Any] = {
    "model_type": "llada2_moe",
    "architectures": ["LLaDA2MoeModelLM"],
    "vocab_size": 151936,
    "hidden_size": 2048,
    "num_hidden_layers": 28,
    "num_attention_heads": 16,
    "torch_dtype": "bfloat16",
    "use_qkv_bias": True,  # non-standard
    "use_qk_norm": True,  # non-standard
}

_LLADA2_MOE_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["en", "zh"],
    library_name="transformers",
)


def _patch_llada2_moe() -> Any:
    return _patch_hf_calls(
        config=_LLADA2_MOE_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_LLADA2_MOE_CARD_DATA,
        hub_info={"author": "inclusionAI", "sha": "deadf00d"},
    )


def test_llada2_moe_type_of_model() -> None:
    with _patch_llada2_moe():
        meta = read_huggingface("inclusionAI/LLaDA2.0-Uni")
    assert meta.type_of_model == "llada2_moe"


def test_llada2_moe_architecture() -> None:
    with _patch_llada2_moe():
        meta = read_huggingface("inclusionAI/LLaDA2.0-Uni")
    assert meta.architecture == "LLaDA2MoeModelLM"


def test_llada2_moe_any_to_any_domain() -> None:
    with _patch_llada2_moe():
        meta = read_huggingface("inclusionAI/LLaDA2.0-Uni")
    assert "any-to-any" in meta.usage.domains


def test_llada2_moe_apache_license() -> None:
    with _patch_llada2_moe():
        meta = read_huggingface("inclusionAI/LLaDA2.0-Uni")
    assert meta.license == "apache-2.0"


# ---------------------------------------------------------------------------
# ByteDance-Seed/BAGEL-7B-MoT  (bagel arch, nested config, bagel-mot library)
# ---------------------------------------------------------------------------

# BAGEL is a Balanced multimodal model with Mixture-of-Tokens (MoT). The config
# has ONLY nested sub-configs (llm_config, vit_config, vae_config) — no top-level
# keys matching _HYPER_KEYS → hyperparameters is empty. library_name=bagel-mot.

_BAGEL_CONFIG: dict[str, Any] = {
    "model_type": "bagel",
    "architectures": ["BagelForConditionalGeneration"],
    "llm_config": {"hidden_size": 3584, "num_hidden_layers": 28},  # nested
    "vit_config": {"hidden_size": 1024, "num_hidden_layers": 24},  # nested
    "vae_config": {"in_channels": 8},  # nested
    "visual_gen": True,
    "visual_und": True,
}

_BAGEL_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["en"],
    library_name="bagel-mot",
)


def _patch_bagel() -> Any:
    return _patch_hf_calls(
        config=_BAGEL_CONFIG,
        tokenizer_config=None,
        card_data=_BAGEL_CARD_DATA,
        hub_info={"author": "ByteDance-Seed", "sha": "deadf00d"},
    )


def test_bagel_type_of_model() -> None:
    with _patch_bagel():
        meta = read_huggingface("ByteDance-Seed/BAGEL-7B-MoT")
    assert meta.type_of_model == "bagel"


def test_bagel_empty_hyperparameters() -> None:
    # All numeric keys are nested inside llm_config/vit_config → not captured
    with _patch_bagel():
        meta = read_huggingface("ByteDance-Seed/BAGEL-7B-MoT")
    assert not meta.hyperparameters


def test_bagel_any_to_any_domain() -> None:
    with _patch_bagel():
        meta = read_huggingface("ByteDance-Seed/BAGEL-7B-MoT")
    assert "any-to-any" in meta.usage.domains


def test_bagel_bagel_mot_library() -> None:
    with _patch_bagel():
        meta = read_huggingface("ByteDance-Seed/BAGEL-7B-MoT")
    assert (meta.extra_data or {}).get("hf.library_name") == "bagel-mot"


# ---------------------------------------------------------------------------
# sensenova/SenseNova-U1-8B-MoT  (neo_chat arch, nested config, any-to-any)
# ---------------------------------------------------------------------------

# SenseNova U1 uses a proprietary "neo_chat" architecture. Like BAGEL, the
# config has a nested llm_config — top-level _HYPER_KEYS are absent →
# hyperparameters is empty.

_SENSENOVA_CONFIG: dict[str, Any] = {
    "model_type": "neo_chat",
    "architectures": ["NEOChatModel"],
    "llm_config": {"hidden_size": 3584, "num_hidden_layers": 28},  # nested
    "downsample_ratio": 2,  # non-standard
    "template": "chat",  # non-standard
}

_SENSENOVA_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["zh", "en"],
    library_name="transformers",
)


def _patch_sensenova() -> Any:
    return _patch_hf_calls(
        config=_SENSENOVA_CONFIG,
        tokenizer_config=None,
        card_data=_SENSENOVA_CARD_DATA,
        hub_info={"author": "sensenova", "sha": "deadf00d"},
    )


def test_sensenova_type_of_model() -> None:
    with _patch_sensenova():
        meta = read_huggingface("sensenova/SenseNova-U1-8B-MoT")
    assert meta.type_of_model == "neo_chat"


def test_sensenova_architecture() -> None:
    with _patch_sensenova():
        meta = read_huggingface("sensenova/SenseNova-U1-8B-MoT")
    assert meta.architecture == "NEOChatModel"


def test_sensenova_empty_hyperparameters() -> None:
    # Numeric keys only in nested llm_config → not captured by extractor
    with _patch_sensenova():
        meta = read_huggingface("sensenova/SenseNova-U1-8B-MoT")
    assert not meta.hyperparameters


def test_sensenova_any_to_any_domain() -> None:
    with _patch_sensenova():
        meta = read_huggingface("sensenova/SenseNova-U1-8B-MoT")
    assert "any-to-any" in meta.usage.domains


# ---------------------------------------------------------------------------
# Gen-Verse/MMaDA-8B-Base  (llada arch, ALiBi, any-to-any, MIT)
# ---------------------------------------------------------------------------

# MMaDA uses ALiBi positional bias (like BLOOM) — no max_position_embeddings.
# model_type=llada; architectures=LLaDAModelLM. The "alibi" and "alibi_bias_max"
# keys are non-standard and not in _HYPER_KEYS → not captured.

_MMADA_CONFIG: dict[str, Any] = {
    "model_type": "llada",
    "architectures": ["LLaDAModelLM"],
    "vocab_size": 32000,
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "alibi": True,  # ALiBi positional bias (non-standard, not in _HYPER_KEYS)
    "alibi_bias_max": 8,  # non-standard
    "attention_layer_norm": True,  # non-standard
    # No max_position_embeddings (ALiBi models don't have a fixed limit)
}

_MMADA_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="any-to-any",
    language=["en"],
    library_name="transformers",
)


def _patch_mmada() -> Any:
    return _patch_hf_calls(
        config=_MMADA_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_MMADA_CARD_DATA,
        hub_info={"author": "Gen-Verse", "sha": "deadf00d"},
    )


def test_mmada_type_of_model() -> None:
    with _patch_mmada():
        meta = read_huggingface("Gen-Verse/MMaDA-8B-Base")
    assert meta.type_of_model == "llada"


def test_mmada_alibi_no_max_position_embeddings() -> None:
    # ALiBi: no max_position_embeddings in config → not in hyperparameters
    with _patch_mmada():
        meta = read_huggingface("Gen-Verse/MMaDA-8B-Base")
    assert "max_position_embeddings" not in meta.hyperparameters


def test_mmada_vocab_size_captured() -> None:
    with _patch_mmada():
        meta = read_huggingface("Gen-Verse/MMaDA-8B-Base")
    assert meta.hyperparameters.get("vocab_size") == 32000


def test_mmada_any_to_any_domain() -> None:
    with _patch_mmada():
        meta = read_huggingface("Gen-Verse/MMaDA-8B-Base")
    assert "any-to-any" in meta.usage.domains


# ---------------------------------------------------------------------------
# XiaomiMiMo/MiMo-Audio-7B-Instruct  (MiMoAudioModel on qwen2, any-to-any)
# ---------------------------------------------------------------------------

# MiMo-Audio wraps a Qwen2 decoder with an audio front-end. Unusually,
# model_type="qwen2" (the base) but architectures=["MiMoAudioModel"] (the
# custom wrapper) — extractor captures the architectures field correctly.
# Non-standard audio keys (audio_channels, delay_pattern) are skipped.

_MIMO_AUDIO_CONFIG: dict[str, Any] = {
    "model_type": "qwen2",
    "architectures": ["MiMoAudioModel"],  # custom arch despite qwen2 model_type
    "vocab_size": 152064,
    "hidden_size": 3584,
    "num_hidden_layers": 28,
    "num_attention_heads": 28,
    "num_key_value_heads": 4,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
    "audio_channels": 128,  # non-standard
    "delay_pattern": "valley",  # non-standard
}

_MIMO_AUDIO_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="any-to-any",
    language=["en", "zh"],
    library_name="transformers",
)


def _patch_mimo_audio() -> Any:
    return _patch_hf_calls(
        config=_MIMO_AUDIO_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_MIMO_AUDIO_CARD_DATA,
        hub_info={"author": "XiaomiMiMo", "sha": "deadf00d"},
    )


def test_mimo_audio_model_type_is_qwen2() -> None:
    # model_type stays "qwen2" (base) even though architecture is MiMoAudioModel
    with _patch_mimo_audio():
        meta = read_huggingface("XiaomiMiMo/MiMo-Audio-7B-Instruct")
    assert meta.type_of_model == "qwen2"


def test_mimo_audio_custom_architecture() -> None:
    # architectures field contains the wrapper class, not the base Qwen2 class
    with _patch_mimo_audio():
        meta = read_huggingface("XiaomiMiMo/MiMo-Audio-7B-Instruct")
    assert meta.architecture == "MiMoAudioModel"


def test_mimo_audio_hyperparameters() -> None:
    with _patch_mimo_audio():
        meta = read_huggingface("XiaomiMiMo/MiMo-Audio-7B-Instruct")
    assert meta.hyperparameters.get("hidden_size") == 3584
    assert meta.hyperparameters.get("num_key_value_heads") == 4


def test_mimo_audio_any_to_any_domain() -> None:
    with _patch_mimo_audio():
        meta = read_huggingface("XiaomiMiMo/MiMo-Audio-7B-Instruct")
    assert "any-to-any" in meta.usage.domains


# ---------------------------------------------------------------------------
# ETH-CVG/lightglue_superpoint  (lightglue arch, keypoint-detection, vague)
# ---------------------------------------------------------------------------

# LightGlue+SuperPoint feature matching model. model_type=lightglue;
# architectures=LightGlueForKeypointMatching. Config has a nested
# keypoint_detector_config dict and custom numeric keys (descriptor_dim,
# filter_threshold, depth_confidence) — none are in _HYPER_KEYS → skipped.
# license=other → vague → file detection triggered.

_LIGHTGLUE_CONFIG: dict[str, Any] = {
    "model_type": "lightglue",
    "architectures": ["LightGlueForKeypointMatching"],
    "descriptor_dim": 256,  # non-standard
    "filter_threshold": 0.1,  # non-standard
    "depth_confidence": 0.95,  # non-standard
    "keypoint_detector_config": {"name": "superpoint", "descriptor_dim": 256},
}

_LIGHTGLUE_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="keypoint-detection",
    language=None,
    library_name="transformers",
)


def _patch_lightglue() -> Any:
    return _patch_hf_calls(
        config=_LIGHTGLUE_CONFIG,
        tokenizer_config=None,
        card_data=_LIGHTGLUE_CARD_DATA,
        hub_info={"author": "ETH-CVG", "sha": "deadf00d"},
    )


def test_lightglue_type_of_model() -> None:
    with _patch_lightglue():
        meta = read_huggingface("ETH-CVG/lightglue_superpoint")
    assert meta.type_of_model == "lightglue"


def test_lightglue_architecture() -> None:
    with _patch_lightglue():
        meta = read_huggingface("ETH-CVG/lightglue_superpoint")
    assert meta.architecture == "LightGlueForKeypointMatching"


def test_lightglue_empty_hyperparameters() -> None:
    # descriptor_dim, filter_threshold, depth_confidence not in _HYPER_KEYS
    with _patch_lightglue():
        meta = read_huggingface("ETH-CVG/lightglue_superpoint")
    assert not meta.hyperparameters


def test_lightglue_vague_license() -> None:
    with _patch_lightglue():
        meta = read_huggingface("ETH-CVG/lightglue_superpoint")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


# ---------------------------------------------------------------------------
# polymathic-ai/aion-base  (aion library, any-to-any, no model_type, custom config)
# ---------------------------------------------------------------------------

# Aion is a multi-domain scientific foundation model (fluid dynamics, climate,
# etc.). library_name=aion (custom framework). Config accessible but has NO
# model_type, NO architectures, and only custom keys (decoder_depth, domains_in,
# domains_out, encoder_depth) → type_of_model=None, architecture=None,
# hyperparameters={}.

_AION_CONFIG: dict[str, Any] = {
    "decoder_depth": 8,
    "encoder_depth": 8,
    "domains_in": ["fluids", "climate", "seismology"],
    "domains_out": ["fluids", "climate", "seismology"],
    "patch_size": 16,
}

_AION_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="any-to-any",
    language=None,
    library_name="aion",
)


def _patch_aion() -> Any:
    return _patch_hf_calls(
        config=_AION_CONFIG,
        tokenizer_config=None,
        card_data=_AION_CARD_DATA,
        hub_info={"author": "polymathic-ai", "sha": "deadf00d"},
    )


def test_aion_no_type_of_model() -> None:
    # Custom aion config: no model_type key
    with _patch_aion():
        meta = read_huggingface("polymathic-ai/aion-base")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_aion_empty_hyperparameters() -> None:
    # decoder_depth, encoder_depth, domains_in, patch_size not in _HYPER_KEYS
    with _patch_aion():
        meta = read_huggingface("polymathic-ai/aion-base")
    assert not meta.hyperparameters


def test_aion_any_to_any_domain() -> None:
    with _patch_aion():
        meta = read_huggingface("polymathic-ai/aion-base")
    assert "any-to-any" in meta.usage.domains


def test_aion_library_name() -> None:
    with _patch_aion():
        meta = read_huggingface("polymathic-ai/aion-base")
    assert (meta.extra_data or {}).get("hf.library_name") == "aion"


# ---------------------------------------------------------------------------
# stanfordnlp/stanza-fi  (stanza library, no config, Finnish)
# ---------------------------------------------------------------------------

# Stanford Stanza NLP pipeline model for Finnish. Uses the stanza Python
# library (not transformers). No config.json (404). No pipeline_tag.

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


def test_stanza_fi_no_architecture() -> None:
    # Stanza: no config.json → no type_of_model or architecture
    with _patch_stanza_fi():
        meta = read_huggingface("stanfordnlp/stanza-fi")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_stanza_fi_stanza_library() -> None:
    with _patch_stanza_fi():
        meta = read_huggingface("stanfordnlp/stanza-fi")
    assert (meta.extra_data or {}).get("hf.library_name") == "stanza"


def test_stanza_fi_language() -> None:
    with _patch_stanza_fi():
        meta = read_huggingface("stanfordnlp/stanza-fi")
    langs = (meta.extra_lists or {}).get("hf.language", [])
    assert "fi" in langs


def test_stanza_fi_empty_domains() -> None:
    # No pipeline_tag → empty usage.domains
    with _patch_stanza_fi():
        meta = read_huggingface("stanfordnlp/stanza-fi")
    assert not meta.usage.domains


# ---------------------------------------------------------------------------
# stanfordnlp/stanza-de  (stanza library, no config, German)
# ---------------------------------------------------------------------------

# Same pattern as stanza-fi; covers German (de) to verify the language field.

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


def test_stanza_de_stanza_library() -> None:
    with _patch_stanza_de():
        meta = read_huggingface("stanfordnlp/stanza-de")
    assert (meta.extra_data or {}).get("hf.library_name") == "stanza"


def test_stanza_de_german_language() -> None:
    with _patch_stanza_de():
        meta = read_huggingface("stanfordnlp/stanza-de")
    langs = (meta.extra_lists or {}).get("hf.language", [])
    assert langs == ["de"]


def test_stanza_de_no_architecture() -> None:
    with _patch_stanza_de():
        meta = read_huggingface("stanfordnlp/stanza-de")
    assert meta.type_of_model is None


# ---------------------------------------------------------------------------
# OpenVINO/Mixtral-8x7B-Instruct-v0.1-int8-ov  (openvino library, config accessible)
# ---------------------------------------------------------------------------

# OpenVINO int8-quantized Mixtral. Unlike GGUF, config.json IS accessible
# (200) and retains the original model_type and architectures → extractor can
# still identify the model. torch_dtype="int8" captured in hyperparameters.
# library_name=openvino → hf.library_name.

_OPENVINO_MIXTRAL_CONFIG: dict[str, Any] = {
    "model_type": "mixtral",
    "architectures": ["MixtralForCausalLM"],
    "vocab_size": 32000,
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "max_position_embeddings": 32768,
    "torch_dtype": "int8",  # quantized dtype captured
    "num_experts_per_tok": 2,  # non-standard (MoE)
    "router_aux_loss_coef": 0.001,  # non-standard (MoE routing)
}

_OPENVINO_MIXTRAL_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "de", "fr", "es", "it"],
    library_name="openvino",
    base_model="mistralai/Mixtral-8x7B-Instruct-v0.1",
)


def _patch_openvino_mixtral() -> Any:
    return _patch_hf_calls(
        config=_OPENVINO_MIXTRAL_CONFIG,
        tokenizer_config=None,
        card_data=_OPENVINO_MIXTRAL_CARD_DATA,
        hub_info={
            "author": "OpenVINO",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:mistralai/Mixtral-8x7B-Instruct-v0.1"],
        },
    )


def test_openvino_mixtral_type_of_model() -> None:
    # Config accessible despite OpenVINO quantization → model_type extractable
    with _patch_openvino_mixtral():
        meta = read_huggingface("OpenVINO/Mixtral-8x7B-Instruct-v0.1-int8-ov")
    assert meta.type_of_model == "mixtral"


def test_openvino_mixtral_int8_dtype_captured() -> None:
    # torch_dtype="int8" is in _HYPER_KEYS → captured even for quantized model
    with _patch_openvino_mixtral():
        meta = read_huggingface("OpenVINO/Mixtral-8x7B-Instruct-v0.1-int8-ov")
    assert meta.hyperparameters.get("torch_dtype") == "int8"


def test_openvino_mixtral_openvino_library() -> None:
    with _patch_openvino_mixtral():
        meta = read_huggingface("OpenVINO/Mixtral-8x7B-Instruct-v0.1-int8-ov")
    assert (meta.extra_data or {}).get("hf.library_name") == "openvino"


def test_openvino_mixtral_quantized_relation() -> None:
    with _patch_openvino_mixtral():
        meta = read_huggingface("OpenVINO/Mixtral-8x7B-Instruct-v0.1-int8-ov")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "quantized"


# ---------------------------------------------------------------------------
# mlx-community/gemma-4-e2b-it-4bit  (mlx library, gemma4 arch, quantized)
# ---------------------------------------------------------------------------

# Apple MLX 4-bit quantization of Gemma 4. Config accessible with model_type=gemma4.
# library_name=mlx → hf.library_name. pipeline_tag=any-to-any (multimodal gemma-4).

_MLX_GEMMA4_CONFIG: dict[str, Any] = {
    "model_type": "gemma4",
    "architectures": ["Gemma4ForConditionalGeneration"],
    "vocab_size": 262144,
    "hidden_size": 2560,
    "num_hidden_layers": 34,
    "num_attention_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_MLX_GEMMA4_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["multilingual"],
    library_name="mlx",
    base_model="google/gemma-4-e2b-it",
)


def _patch_mlx_gemma4() -> Any:
    return _patch_hf_calls(
        config=_MLX_GEMMA4_CONFIG,
        tokenizer_config=None,
        card_data=_MLX_GEMMA4_CARD_DATA,
        hub_info={
            "author": "mlx-community",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:google/gemma-4-e2b-it"],
        },
    )


def test_mlx_gemma4_type_of_model() -> None:
    # MLX: config.json accessible → model_type extractable
    with _patch_mlx_gemma4():
        meta = read_huggingface("mlx-community/gemma-4-e2b-it-4bit")
    assert meta.type_of_model == "gemma4"


def test_mlx_gemma4_mlx_library() -> None:
    with _patch_mlx_gemma4():
        meta = read_huggingface("mlx-community/gemma-4-e2b-it-4bit")
    assert (meta.extra_data or {}).get("hf.library_name") == "mlx"


def test_mlx_gemma4_quantized_relation() -> None:
    with _patch_mlx_gemma4():
        meta = read_huggingface("mlx-community/gemma-4-e2b-it-4bit")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "quantized"


def test_mlx_gemma4_any_to_any_domain() -> None:
    with _patch_mlx_gemma4():
        meta = read_huggingface("mlx-community/gemma-4-e2b-it-4bit")
    assert "any-to-any" in meta.usage.domains


# ---------------------------------------------------------------------------
# onnx-community/gemma-4-E2B-it-ONNX  (transformers.js library, gemma4)
# ---------------------------------------------------------------------------

# ONNX export of Gemma 4. library_name=transformers.js (the Transformers.js
# community typically uses this). Same gemma4 model_type; config accessible.

_ONNX_GEMMA4_CONFIG: dict[str, Any] = {
    "model_type": "gemma4",
    "architectures": ["Gemma4ForConditionalGeneration"],
    "vocab_size": 262144,
    "hidden_size": 2560,
    "num_hidden_layers": 34,
    "num_attention_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_ONNX_GEMMA4_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["multilingual"],
    library_name="transformers.js",
    base_model="google/gemma-4-E2B-it",
)


def _patch_onnx_gemma4() -> Any:
    return _patch_hf_calls(
        config=_ONNX_GEMMA4_CONFIG,
        tokenizer_config=None,
        card_data=_ONNX_GEMMA4_CARD_DATA,
        hub_info={
            "author": "onnx-community",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:google/gemma-4-E2B-it"],
        },
    )


def test_onnx_gemma4_type_of_model() -> None:
    with _patch_onnx_gemma4():
        meta = read_huggingface("onnx-community/gemma-4-E2B-it-ONNX")
    assert meta.type_of_model == "gemma4"


def test_onnx_gemma4_transformers_js_library() -> None:
    with _patch_onnx_gemma4():
        meta = read_huggingface("onnx-community/gemma-4-E2B-it-ONNX")
    assert (meta.extra_data or {}).get("hf.library_name") == "transformers.js"


def test_onnx_gemma4_quantized_relation() -> None:
    with _patch_onnx_gemma4():
        meta = read_huggingface("onnx-community/gemma-4-E2B-it-ONNX")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "quantized"


# ---------------------------------------------------------------------------
# sail/Sailor2-20B  (Qwen2-based, SEA multilingual, apache-2.0)
# ---------------------------------------------------------------------------

# Sailor2 is a South-East Asian multilingual LLM built on Qwen2. Covers 10+
# SEA and regional languages. Standard Qwen2 architecture and apache-2.0 license.

_SAILOR2_20B_CONFIG: dict[str, Any] = {
    "model_type": "qwen2",
    "architectures": ["Qwen2ForCausalLM"],
    "vocab_size": 151936,
    "hidden_size": 5120,
    "num_hidden_layers": 48,
    "num_attention_heads": 40,
    "num_key_value_heads": 8,
    "max_position_embeddings": 32768,
    "torch_dtype": "bfloat16",
}

_SAILOR2_20B_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "zh", "th", "id", "vi", "ms", "my", "km", "lo", "tl"],
    library_name="transformers",
)


def _patch_sailor2_20b() -> Any:
    return _patch_hf_calls(
        config=_SAILOR2_20B_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_SAILOR2_20B_CARD_DATA,
        hub_info={"author": "sail", "sha": "deadf00d"},
    )


def test_sailor2_20b_type_of_model() -> None:
    with _patch_sailor2_20b():
        meta = read_huggingface("sail/Sailor2-20B")
    assert meta.type_of_model == "qwen2"


def test_sailor2_20b_sea_languages() -> None:
    with _patch_sailor2_20b():
        meta = read_huggingface("sail/Sailor2-20B")
    langs = (meta.extra_lists or {}).get("hf.language", [])
    assert "th" in langs  # Thai
    assert "km" in langs  # Khmer
    assert "lo" in langs  # Lao


def test_sailor2_20b_gqa() -> None:
    with _patch_sailor2_20b():
        meta = read_huggingface("sail/Sailor2-20B")
    assert meta.hyperparameters.get("num_key_value_heads") == 8
    assert meta.hyperparameters.get("num_attention_heads") == 40


def test_sailor2_20b_text_generation_domain() -> None:
    with _patch_sailor2_20b():
        meta = read_huggingface("sail/Sailor2-20B")
    assert "text-generation" in meta.usage.domains


# ---------------------------------------------------------------------------
# Alibaba-NLP/gte-modernbert-base  (modernbert arch, sentence-similarity)
# ---------------------------------------------------------------------------

# GTE ModernBERT embedding model. model_type=modernbert; architectures=
# ModernBertModel (base encoder, not a masked-LM head). sentence-similarity
# pipeline tag → already in _DOMAIN_TAGS.

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


def test_gte_modernbert_type_of_model() -> None:
    with _patch_gte_modernbert():
        meta = read_huggingface("Alibaba-NLP/gte-modernbert-base")
    assert meta.type_of_model == "modernbert"


def test_gte_modernbert_architecture() -> None:
    with _patch_gte_modernbert():
        meta = read_huggingface("Alibaba-NLP/gte-modernbert-base")
    assert meta.architecture == "ModernBertModel"


def test_gte_modernbert_sentence_similarity_domain() -> None:
    with _patch_gte_modernbert():
        meta = read_huggingface("Alibaba-NLP/gte-modernbert-base")
    assert "sentence-similarity" in meta.usage.domains


def test_gte_modernbert_hyperparameters() -> None:
    with _patch_gte_modernbert():
        meta = read_huggingface("Alibaba-NLP/gte-modernbert-base")
    assert meta.hyperparameters.get("max_position_embeddings") == 8192


# ---------------------------------------------------------------------------
# huggingface/CodeBERTa-small-v1  (roberta, fill-mask, no license, code language)
# ---------------------------------------------------------------------------

# CodeBERTa-small is a RoBERTa model pre-trained on code (The Stack).
# No license field in the card YAML → meta.license=None.
# language=["code"] (not an ISO 639-1 code but used by HF for code content).

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


def test_codeberta_type_of_model() -> None:
    with _patch_codeberta():
        meta = read_huggingface("huggingface/CodeBERTa-small-v1")
    assert meta.type_of_model == "roberta"


def test_codeberta_no_license() -> None:
    # No license field in card YAML → meta.license=None
    with _patch_codeberta():
        meta = read_huggingface("huggingface/CodeBERTa-small-v1")
    assert meta.license is None
    assert "hf.license_raw" not in (meta.extra_data or {})


def test_codeberta_code_language_preserved() -> None:
    # "code" is not ISO 639-1 but the extractor preserves it as-is
    with _patch_codeberta():
        meta = read_huggingface("huggingface/CodeBERTa-small-v1")
    langs = (meta.extra_lists or {}).get("hf.language", [])
    assert langs == ["code"]


def test_codeberta_fill_mask_domain() -> None:
    with _patch_codeberta():
        meta = read_huggingface("huggingface/CodeBERTa-small-v1")
    assert "fill-mask" in meta.usage.domains


# ---------------------------------------------------------------------------
# Bencode92/tradepulse-finbert-sentiment  (bert, text-classification, FinBERT)
# ---------------------------------------------------------------------------

# TradePulse FinBERT is a financial sentiment classifier fine-tuned from
# ProsusAI/finbert. BertForSequenceClassification; text-classification domain.

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


def test_tradepulse_type_of_model() -> None:
    with _patch_tradepulse():
        meta = read_huggingface("Bencode92/tradepulse-finbert-sentiment")
    assert meta.type_of_model == "bert"


def test_tradepulse_architecture() -> None:
    with _patch_tradepulse():
        meta = read_huggingface("Bencode92/tradepulse-finbert-sentiment")
    assert meta.architecture == "BertForSequenceClassification"


def test_tradepulse_text_classification_domain() -> None:
    with _patch_tradepulse():
        meta = read_huggingface("Bencode92/tradepulse-finbert-sentiment")
    assert "text-classification" in meta.usage.domains


def test_tradepulse_finetune_from_finbert() -> None:
    with _patch_tradepulse():
        meta = read_huggingface("Bencode92/tradepulse-finbert-sentiment")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "finetune"
    assert (meta.extra_data or {}).get("hf.base_model") == "ProsusAI/finbert"


# ---------------------------------------------------------------------------
# qualcomm/HRNetPose  (keypoint-detection, pytorch library, vague license)
# ---------------------------------------------------------------------------

# Qualcomm HRNet pose estimation model. library_name=pytorch (Qualcomm publishes
# models in native PyTorch format). No config.json (404). license=other → vague
# → file detection triggered. pipeline_tag=keypoint-detection (in _DOMAIN_TAGS).

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


def test_hrnetpose_keypoint_detection_domain() -> None:
    with _patch_hrnetpose():
        meta = read_huggingface("qualcomm/HRNetPose")
    assert "keypoint-detection" in meta.usage.domains


def test_hrnetpose_pytorch_library() -> None:
    # Qualcomm uses library_name=pytorch for native PyTorch format
    with _patch_hrnetpose():
        meta = read_huggingface("qualcomm/HRNetPose")
    assert (meta.extra_data or {}).get("hf.library_name") == "pytorch"


def test_hrnetpose_vague_license() -> None:
    with _patch_hrnetpose():
        meta = read_huggingface("qualcomm/HRNetPose")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


def test_hrnetpose_no_architecture() -> None:
    with _patch_hrnetpose():
        meta = read_huggingface("qualcomm/HRNetPose")
    assert meta.type_of_model is None
