# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for base/pretrained text-generation models.

See also: test_huggingface_embeddings.py, test_huggingface_gated_access.py,
test_huggingface_gated_metadata.py, test_huggingface_granite_misc.py,
test_huggingface_multimodal.py, test_huggingface_omni_modal.py,
test_huggingface_speech_misc.py, test_huggingface_structured_text.py,
test_huggingface_text_generation_instruct.py, test_huggingface_text_misc.py,
test_huggingface_vision.py, test_huggingface_vision_robotics.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .hf_patches._hf_patches_text_generation_pretrained import (
    _patch_bloom,
    _patch_gpt_neo_2_7b,
    _patch_llama,
    _patch_llama_3_2_3b,
    _patch_openelm_270m,
    _patch_phi2,
    _patch_qwen3_235b,
    _patch_qwen35_27b,
    _patch_starcoder2,
)


def test_starcoder2_architecture() -> None:
    with _patch_starcoder2():
        meta = read_huggingface("bigcode/starcoder2-3b")
    assert meta.type_of_model == "starcoder2"
    assert meta.architecture == "Starcoder2ForCausalLM"


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


def test_gpt_neo_2_7b_architecture() -> None:
    with _patch_gpt_neo_2_7b():
        meta = read_huggingface("EleutherAI/gpt-neo-2.7B")
    assert meta.type_of_model == "gpt_neo"
    assert meta.architecture == "GPTNeoForCausalLM"


def test_phi2_code_tag_in_domain() -> None:
    # "code" is in _DOMAIN_TAGS -> usage.domains, not extra_lists["hf.tags"].
    with _patch_phi2():
        meta = read_huggingface("microsoft/phi-2")
    assert "code" in meta.usage.domains


def test_llama_3_2_3b_gated_base_no_architecture() -> None:
    with _patch_llama_3_2_3b():
        meta = read_huggingface("meta-llama/Llama-3.2-3B")
    assert meta.license == "llama3.2"
    assert meta.type_of_model is None  # config gated -> not extractable


def test_qwen3_235b_moe_type_of_model() -> None:
    with _patch_qwen3_235b():
        meta = read_huggingface("Qwen/Qwen3-235B-A22B")
    assert meta.type_of_model == "qwen3_moe"


def test_qwen3_235b_moe_architecture() -> None:
    with _patch_qwen3_235b():
        meta = read_huggingface("Qwen/Qwen3-235B-A22B")
    assert meta.architecture == "Qwen3MoeForCausalLM"


def test_qwen3_235b_text_generation_domain() -> None:
    with _patch_qwen3_235b():
        meta = read_huggingface("Qwen/Qwen3-235B-A22B")
    assert "text-generation" in meta.usage.domains


def test_qwen3_235b_generation_hyperparameters() -> None:
    with _patch_qwen3_235b():
        meta = read_huggingface("Qwen/Qwen3-235B-A22B")
    assert meta.hyperparameters.get("generation.temperature") == 0.6
    assert meta.hyperparameters.get("generation.top_p") == 0.95


def test_qwen35_27b_type_of_model() -> None:
    with _patch_qwen35_27b():
        meta = read_huggingface("Qwen/Qwen3.5-27B")
    assert meta.type_of_model == "qwen3"


def test_qwen35_27b_architecture() -> None:
    with _patch_qwen35_27b():
        meta = read_huggingface("Qwen/Qwen3.5-27B")
    assert meta.architecture == "Qwen3ForCausalLM"


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


def test_bloom_type_of_model() -> None:
    with _patch_bloom():
        meta = read_huggingface("bigscience/bloom")
    assert meta.type_of_model == "bloom"


def test_bloom_architecture() -> None:
    with _patch_bloom():
        meta = read_huggingface("bigscience/bloom")
    assert meta.architecture == "BloomForCausalLM"


def test_bloom_vocab_size_captured() -> None:
    with _patch_bloom():
        meta = read_huggingface("bigscience/bloom")
    assert meta.hyperparameters.get("vocab_size") == 250880


def test_bloom_nonstandard_layer_key_not_captured() -> None:
    # BLOOM uses n_layer (not num_hidden_layers) -> not in _HYPER_KEYS -> absent
    with _patch_bloom():
        meta = read_huggingface("bigscience/bloom")
    assert "num_hidden_layers" not in meta.hyperparameters
    assert "n_layer" not in meta.hyperparameters


def test_bloom_no_max_position_embeddings() -> None:
    # ALiBi positional bias: no fixed max_position_embeddings in config
    with _patch_bloom():
        meta = read_huggingface("bigscience/bloom")
    assert "max_position_embeddings" not in meta.hyperparameters


def test_openelm_270m_type_of_model() -> None:
    with _patch_openelm_270m():
        meta = read_huggingface("apple/OpenELM-270M")
    assert meta.type_of_model == "openelm"


def test_openelm_270m_architecture() -> None:
    with _patch_openelm_270m():
        meta = read_huggingface("apple/OpenELM-270M")
    assert meta.architecture == "OpenELMForCausalLM"


def test_openelm_270m_head_dim_captured() -> None:
    # head_dim is in _HYPER_KEYS -> captured even for custom arch
    with _patch_openelm_270m():
        meta = read_huggingface("apple/OpenELM-270M")
    assert meta.hyperparameters.get("head_dim") == 64


def test_openelm_270m_apple_amlr_passthrough() -> None:
    with _patch_openelm_270m():
        meta = read_huggingface("apple/OpenELM-270M")
    assert meta.license == "apple-amlr"
