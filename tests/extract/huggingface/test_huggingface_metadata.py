# ruff: noqa: F403, F405
from __future__ import annotations

import sys

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.core.dataset_metadata import DatasetReference
from pitloom.extract._huggingface import (
    read_huggingface,
)

from .hf_patches._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)


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
