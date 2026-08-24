# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for models with a fetchable config and card but no pipeline_tag.

See also: test_huggingface_embeddings.py, test_huggingface_gated_access.py,
test_huggingface_granite_misc.py, test_huggingface_multimodal.py,
test_huggingface_omni_modal.py, test_huggingface_speech_misc.py,
test_huggingface_structured_text.py,
test_huggingface_text_generation_instruct.py,
test_huggingface_text_generation_pretrained.py, test_huggingface_text_misc.py,
test_huggingface_vision.py, test_huggingface_vision_robotics.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .hf_patches._hf_patches_gated_metadata import (
    _patch_bert_turkish,
    _patch_deepseek,
    _patch_eurollm_1b7,
    _patch_openeurollm,
    _patch_resnet18,
    _patch_seallms,
    _patch_swin,
)


def test_deepseek_architecture() -> None:
    with _patch_deepseek():
        meta = read_huggingface("deepseek-ai/DeepSeek-R1")
    assert meta.type_of_model == "deepseek_v3"
    assert meta.architecture == "DeepseekV3ForCausalLM"


def test_deepseek_no_domain_when_no_pipeline_tag() -> None:
    with _patch_deepseek():
        meta = read_huggingface("deepseek-ai/DeepSeek-R1")
    assert not meta.usage.domains


def test_deepseek_hyperparameters() -> None:
    with _patch_deepseek():
        meta = read_huggingface("deepseek-ai/DeepSeek-R1")
    assert meta.hyperparameters.get("vocab_size") == 129280
    assert meta.hyperparameters.get("num_hidden_layers") == 61


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


def test_swin_no_pipeline_tag_but_image_classification_from_tags() -> None:
    with _patch_swin():
        meta = read_huggingface("microsoft/swin-tiny-patch4-window7-224")
    # pipeline_tag absent in card -> domain comes from card tags
    assert "image-classification" in meta.usage.domains


def test_swin_imagenet_dataset() -> None:
    with _patch_swin():
        meta = read_huggingface("microsoft/swin-tiny-patch4-window7-224")
    assert any("imagenet-1k" in d.metadata.name for d in meta.datasets)


def test_resnet18_architecture() -> None:
    with _patch_resnet18():
        meta = read_huggingface("microsoft/resnet-18")
    assert meta.type_of_model == "resnet"
    assert meta.architecture == "ResNetForImageClassification"


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
    # num_key_value_heads == num_attention_heads == 32 -> standard MHA, no GQA
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


def test_bert_turkish_type_of_model() -> None:
    # model_type present even though architectures field is absent
    with _patch_bert_turkish():
        meta = read_huggingface("dbmdz/bert-base-turkish-cased")
    assert meta.type_of_model == "bert"


def test_bert_turkish_architecture_none() -> None:
    # architectures key absent from config -> architecture=None
    with _patch_bert_turkish():
        meta = read_huggingface("dbmdz/bert-base-turkish-cased")
    assert meta.architecture is None


def test_bert_turkish_no_pipeline_tag_empty_domains() -> None:
    # No pipeline_tag in card -> empty usage.domains
    with _patch_bert_turkish():
        meta = read_huggingface("dbmdz/bert-base-turkish-cased")
    assert not meta.usage.domains


def test_bert_turkish_language() -> None:
    with _patch_bert_turkish():
        meta = read_huggingface("dbmdz/bert-base-turkish-cased")
    langs = (meta.extra_lists or {}).get("hf.language", [])
    assert langs == ["tr"]


def test_bert_turkish_hyperparameters() -> None:
    # Standard BERT keys are captured despite no architectures field
    with _patch_bert_turkish():
        meta = read_huggingface("dbmdz/bert-base-turkish-cased")
    assert meta.hyperparameters.get("hidden_size") == 768
    assert meta.hyperparameters.get("vocab_size") == 32000
