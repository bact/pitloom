# ruff: noqa: F403, F405
from __future__ import annotations

from pitloom.extract._huggingface import (
    read_huggingface,
)

from .hf_patches._hf_patches_text_generation_regional import (
    _patch_openthaigpt,
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
