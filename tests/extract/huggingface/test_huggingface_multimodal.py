# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for vision-language and other multimodal models.

See also: test_huggingface_embeddings.py, test_huggingface_gated_access.py,
test_huggingface_gated_metadata.py, test_huggingface_granite_misc.py,
test_huggingface_omni_modal.py, test_huggingface_speech_misc.py,
test_huggingface_structured_text.py,
test_huggingface_text_generation_instruct.py,
test_huggingface_text_generation_pretrained.py, test_huggingface_text_misc.py,
test_huggingface_vision.py, test_huggingface_vision_robotics.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .hf_patches._hf_patches_multimodal import (
    _patch_boba_food_gguf,
    _patch_donut,
    _patch_exaone45_33b,
    _patch_exaone45_33b_awq,
    _patch_exaone45_33b_fp8,
    _patch_exaone45_33b_gguf,
    _patch_jina_v4,
    _patch_kanana_15v,
    _patch_kimi,
    _patch_layoutlm,
    _patch_llava_video,
    _patch_sealion_gguf,
    _patch_timelens,
)


def test_kimi_architecture() -> None:
    with _patch_kimi():
        meta = read_huggingface("moonshotai/Kimi-K2.6")
    assert meta.type_of_model == "kimi_k25"
    assert meta.architecture == "KimiK25ForConditionalGeneration"


def test_kimi_multimodal_domain() -> None:
    with _patch_kimi():
        meta = read_huggingface("moonshotai/Kimi-K2.6")
    assert "image-text-to-text" in meta.usage.domains


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


def test_jina_v4_tokenizer_max_length() -> None:
    with _patch_jina_v4():
        meta = read_huggingface("jinaai/jina-embeddings-v4")
    assert meta.extra_data.get("hf.tokenizer_max_length") == 131072


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


def test_donut_document_question_answering_domain() -> None:
    with _patch_donut():
        meta = read_huggingface("naver-clova-ix/donut-base-finetuned-docvqa")
    assert "document-question-answering" in meta.usage.domains


def test_donut_image_to_text_also_domain() -> None:
    with _patch_donut():
        meta = read_huggingface("naver-clova-ix/donut-base-finetuned-docvqa")
    assert "image-to-text" in meta.usage.domains


def test_layoutlm_document_question_answering() -> None:
    with _patch_layoutlm():
        meta = read_huggingface("impira/layoutlm-document-qa")
    assert "document-question-answering" in meta.usage.domains


def test_layoutlm_language_scalar_string() -> None:
    with _patch_layoutlm():
        meta = read_huggingface("impira/layoutlm-document-qa")
    assert meta.extra_lists.get("hf.language") == ["en"]


def test_boba_food_gguf_domain_base_model_no_arch() -> None:
    with _patch_boba_food_gguf():
        meta = read_huggingface("Doses-AI/boba-0.8b-food-GGUF")
    assert "image-text-to-text" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "Qwen/Qwen3.5-0.8B"
    assert meta.type_of_model is None  # GGUF-only, no config.json


def test_kanana_15v_type_of_model() -> None:
    with _patch_kanana_15v():
        meta = read_huggingface("kakaobank/kanana-1.5-v-3b-instruct")
    assert meta.type_of_model == "kanana-1.5-v"


def test_kanana_15v_architecture() -> None:
    with _patch_kanana_15v():
        meta = read_huggingface("kakaobank/kanana-1.5-v-3b-instruct")
    assert meta.architecture == "KananaVForConditionalGeneration"


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


def test_exaone45_33b_type_of_model() -> None:
    with _patch_exaone45_33b():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B")
    assert meta.type_of_model == "exaone4_5"


def test_exaone45_33b_architecture() -> None:
    with _patch_exaone45_33b():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B")
    assert meta.architecture == "Exaone4_5_ForConditionalGeneration"


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


def test_exaone45_33b_awq_type_of_model() -> None:
    # AWQ: config.json is present (unlike GGUF) -> type_of_model extractable
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


def test_exaone45_33b_fp8_type_of_model() -> None:
    with _patch_exaone45_33b_fp8():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-FP8")
    assert meta.type_of_model == "exaone4_5"


def test_exaone45_33b_fp8_dtype_in_hyperparameters() -> None:
    # torch_dtype is in _HYPER_KEYS -> captured even for FP8 quantized dtype
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


def test_exaone45_33b_gguf_no_type_of_model() -> None:
    # GGUF: config.json absent -> cannot determine model_type
    with _patch_exaone45_33b_gguf():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-GGUF")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_exaone45_33b_gguf_base_model_relation() -> None:
    with _patch_exaone45_33b_gguf():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-GGUF")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "quantized"


def test_exaone45_33b_gguf_image_text_to_text_domain() -> None:
    with _patch_exaone45_33b_gguf():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-GGUF")
    assert "image-text-to-text" in meta.usage.domains


def test_timelens_type_of_model() -> None:
    with _patch_timelens():
        meta = read_huggingface("TencentARC/TimeLens-8B")
    assert meta.type_of_model == "qwen3_vl"


def test_timelens_architecture() -> None:
    with _patch_timelens():
        meta = read_huggingface("TencentARC/TimeLens-8B")
    assert meta.architecture == "Qwen3VLForConditionalGeneration"


def test_timelens_video_text_to_text_domain() -> None:
    with _patch_timelens():
        meta = read_huggingface("TencentARC/TimeLens-8B")
    assert "video-text-to-text" in meta.usage.domains


def test_timelens_nested_text_config_empty_hyperparameters() -> None:
    # All LM numeric keys are inside text_config -> not captured by _HYPER_KEYS
    # dtype at top level is NOT in _HYPER_KEYS (only torch_dtype is)
    with _patch_timelens():
        meta = read_huggingface("TencentARC/TimeLens-8B")
    assert not meta.hyperparameters


def test_timelens_finetune_base_model() -> None:
    with _patch_timelens():
        meta = read_huggingface("TencentARC/TimeLens-8B")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "finetune"
    assert (meta.extra_data or {}).get("hf.base_model") == "Qwen/Qwen3-VL-8B-Instruct"


def test_timelens_arxiv() -> None:
    with _patch_timelens():
        meta = read_huggingface("TencentARC/TimeLens-8B")
    arxivs = (meta.extra_lists or {}).get("hf.arxiv", [])
    assert "2512.14698" in arxivs
