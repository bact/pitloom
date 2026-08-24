# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for regional/specialised text-generation, translation, and
summarization models, plus the any-to-any Nemotron omni model.

See also: test_huggingface_vision_robotics.py, test_huggingface_speech_misc.py,
and test_huggingface_granite_misc.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .conftest import (
    _patch_falconsai,
    _patch_gpt_neox_jp,
    _patch_hunyuan_mt,
    _patch_hunyuan_mt7b,
    _patch_hy_mt_gguf,
    _patch_ii_medical,
    _patch_laguna,
    _patch_llmjp,
    _patch_mallam,
    _patch_mistral_medium,
    _patch_nemotron,
    _patch_opus_mt_th_en,
    _patch_privacy_filter,
    _patch_wangchanglm,
)


def test_nemotron_any_to_any_domain() -> None:
    with _patch_nemotron():
        meta = read_huggingface("nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16")
    assert "any-to-any" in meta.usage.domains


def test_nemotron_dataset_from_card_yaml() -> None:
    with _patch_nemotron():
        meta = read_huggingface("nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16")
    assert any("Nemotron-Image-Training" in d.metadata.name for d in meta.datasets)


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


def test_mallam_malay_language() -> None:
    with _patch_mallam():
        meta = read_huggingface("mesolitica/mallam-1.1B-4096")
    assert meta.extra_lists.get("hf.language") == ["ms"]


def test_llmjp_llama_architecture_large_vocab() -> None:
    # 99 584-token vocab designed for Japanese tokenization
    with _patch_llmjp():
        meta = read_huggingface("llm-jp/llm-jp-3-1.8b")
    assert meta.type_of_model == "llama"
    assert meta.hyperparameters.get("vocab_size") == 99584


def test_privacy_filter_token_classification_domain() -> None:
    with _patch_privacy_filter():
        meta = read_huggingface("openai/privacy-filter")
    assert "token-classification" in meta.usage.domains


def test_privacy_filter_tokenizer_max_length() -> None:
    with _patch_privacy_filter():
        meta = read_huggingface("openai/privacy-filter")
    assert meta.extra_data.get("hf.tokenizer_max_length") == 128000


def test_mistral_medium_no_pipeline_tag_empty_domain() -> None:
    with _patch_mistral_medium():
        meta = read_huggingface("mistralai/Mistral-Medium-3.5-128B")
    assert not meta.usage.domains


def test_mistral_medium_many_languages() -> None:
    with _patch_mistral_medium():
        meta = read_huggingface("mistralai/Mistral-Medium-3.5-128B")
    langs = meta.extra_lists.get("hf.language", [])
    assert "ja" in langs and "ar" in langs and "hi" in langs


def test_laguna_custom_architecture() -> None:
    with _patch_laguna():
        meta = read_huggingface("poolside/Laguna-XS.2")
    assert meta.type_of_model == "laguna"
    assert meta.architecture == "LagunaForCausalLM"


def test_laguna_custom_tags_in_extra_lists() -> None:
    with _patch_laguna():
        meta = read_huggingface("poolside/Laguna-XS.2")
    assert "laguna-xs.2" in meta.extra_lists.get("hf.tags", [])


def test_gpt_neox_jp_language_scalar() -> None:
    with _patch_gpt_neox_jp():
        meta = read_huggingface("abeja/gpt-neox-japanese-2.7b")
    assert meta.extra_lists.get("hf.language") == ["ja"]


def test_gpt_neox_jp_datasets() -> None:
    with _patch_gpt_neox_jp():
        meta = read_huggingface("abeja/gpt-neox-japanese-2.7b")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "cc100" in ds_names and "wikipedia" in ds_names


def test_falconsai_t5_summarization() -> None:
    with _patch_falconsai():
        meta = read_huggingface("Falconsai/medical_summarization")
    assert meta.type_of_model == "t5"
    assert "summarization" in meta.usage.domains


def test_falconsai_tokenizer_max_length() -> None:
    with _patch_falconsai():
        meta = read_huggingface("Falconsai/medical_summarization")
    assert meta.extra_data.get("hf.tokenizer_max_length") == 512


def test_opus_mt_translation_domain_from_tag() -> None:
    # pipeline_tag absent; "translation" is a domain tag in card tags.
    with _patch_opus_mt_th_en():
        meta = read_huggingface("Helsinki-NLP/opus-mt-th-en")
    assert "translation" in meta.usage.domains


def test_opus_mt_marian_architecture() -> None:
    with _patch_opus_mt_th_en():
        meta = read_huggingface("Helsinki-NLP/opus-mt-th-en")
    assert meta.type_of_model == "marian"


def test_hunyuan_mt_translation_from_tag() -> None:
    with _patch_hunyuan_mt():
        meta = read_huggingface("tencent/HY-MT1.5-1.8B")
    assert "translation" in meta.usage.domains


def test_hy_mt_gguf_multilingual_keyword_preserved() -> None:
    with _patch_hy_mt_gguf():
        meta = read_huggingface("tencent/Hy-MT1.5-1.8B-2bit-GGUF")
    assert "multilingual" in meta.extra_lists.get("hf.language", [])


def test_hy_mt_gguf_base_model_quantized() -> None:
    with _patch_hy_mt_gguf():
        meta = read_huggingface("tencent/Hy-MT1.5-1.8B-2bit-GGUF")
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"


def test_hunyuan_mt7b_translation_from_tag_no_pipeline() -> None:
    with _patch_hunyuan_mt7b():
        meta = read_huggingface("tencent/Hunyuan-MT-7B")
    assert "translation" in meta.usage.domains
    assert meta.license is None


def test_ii_medical_qwen3_architecture() -> None:
    with _patch_ii_medical():
        meta = read_huggingface("Intelligent-Internet/II-Medical-8B")
    assert meta.type_of_model == "qwen3"
    assert meta.hyperparameters.get("hidden_size") == 4096
