# ruff: noqa: F403, F405
# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pitloom.extract._huggingface import (
    read_huggingface,
)

from .conftest import (
    _patch_boba_food_gguf,
    _patch_clip_japanese_v2,
    _patch_crow_9b,
    _patch_darwin_kr_legal,
    _patch_distilbert_multilingual,
    _patch_ernie_image_turbo,
    _patch_exaone45_33b,
    _patch_exaone45_33b_awq,
    _patch_exaone45_33b_fp8,
    _patch_exaone45_33b_gguf,
    _patch_exaone_path,
    _patch_fineweb_edu,
    _patch_flood_image_detect,
    _patch_fujitsu_llm,
    _patch_glm45_air_reap,
    _patch_gpt_neo_2_7b,
    _patch_kanana_15v,
    _patch_line_distilbert,
    _patch_llama_3_2_3b,
    _patch_llama_3_2_3b_instruct,
    _patch_phi2,
    _patch_qwen3_235b,
    _patch_qwen3_reap,
    _patch_qwen3_swallow,
    _patch_qwen35_27b,
    _patch_sealion_27b_it,
    _patch_stablelm_zephyr,
    _patch_tinyllama_chat,
    _patch_xlm_roberta_base,
)


def test_flood_image_detect_domain_and_base_model() -> None:
    with _patch_flood_image_detect():
        meta = read_huggingface("prithivMLmods/Flood-Image-Detection")
    assert "image-classification" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "google/siglip2-base-patch16-512"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_xlm_roberta_fill_mask_domain_and_languages() -> None:
    with _patch_xlm_roberta_base():
        meta = read_huggingface("FacebookAI/xlm-roberta-base")
    assert "fill-mask" in meta.usage.domains
    langs = meta.extra_lists.get("hf.language", [])
    assert "hi" in langs and "ar" in langs and "zh" in langs


def test_distilbert_multilingual_fill_mask_and_6_layers() -> None:
    # DistilBERT halves BERT's 12 layers to 6.
    with _patch_distilbert_multilingual():
        meta = read_huggingface("distilbert/distilbert-base-multilingual-cased")
    assert "fill-mask" in meta.usage.domains
    assert meta.type_of_model == "distilbert"
    assert meta.hyperparameters.get("num_hidden_layers") == 6


def test_crow_9b_merge_relation() -> None:
    with _patch_crow_9b():
        meta = read_huggingface("Crownelius/Crow-9B-HERETIC-4.6")
    assert meta.extra_data.get("hf.base_model") == "Qwen/Qwen3.5-9B-Base"
    assert meta.extra_data.get("hf.base_model_relation") == "merge"


def test_crow_9b_26_languages() -> None:
    with _patch_crow_9b():
        meta = read_huggingface("Crownelius/Crow-9B-HERETIC-4.6")
    assert len(meta.extra_lists.get("hf.language", [])) == 26


def test_qwen3_reap_merge_relation_moe() -> None:
    with _patch_qwen3_reap():
        meta = read_huggingface("SamsungSAILMontreal/Qwen3-Coder-Next-REAP")
    assert meta.extra_data.get("hf.base_model") == "Qwen/Qwen3-Coder-Next"
    assert meta.extra_data.get("hf.base_model_relation") == "merge"
    assert meta.type_of_model == "qwen3_moe"


def test_gpt_neo_2_7b_architecture() -> None:
    with _patch_gpt_neo_2_7b():
        meta = read_huggingface("EleutherAI/gpt-neo-2.7B")
    assert meta.type_of_model == "gpt_neo"
    assert meta.architecture == "GPTNeoForCausalLM"


def test_stablelm_zephyr_architecture() -> None:
    with _patch_stablelm_zephyr():
        meta = read_huggingface("stabilityai/stablelm-2-zephyr-1_6b")
    assert meta.type_of_model == "stablelm_epoch"
    assert meta.architecture == "StableLMEpochForCausalLM"


def test_tinyllama_chat_architecture_and_depth() -> None:
    with _patch_tinyllama_chat():
        meta = read_huggingface("TinyLlama/TinyLlama-1.1B-Chat-v1.0")
    assert meta.type_of_model == "llama"
    assert meta.hyperparameters.get("num_hidden_layers") == 22


def test_phi2_code_tag_in_domain() -> None:
    # "code" is in _DOMAIN_TAGS → usage.domains, not extra_lists["hf.tags"].
    with _patch_phi2():
        meta = read_huggingface("microsoft/phi-2")
    assert "code" in meta.usage.domains


def test_llama_3_2_3b_gated_base_no_architecture() -> None:
    with _patch_llama_3_2_3b():
        meta = read_huggingface("meta-llama/Llama-3.2-3B")
    assert meta.license == "llama3.2"
    assert meta.type_of_model is None  # config gated → not extractable


def test_llama_3_2_3b_instruct_base_model_finetune() -> None:
    with _patch_llama_3_2_3b_instruct():
        meta = read_huggingface("meta-llama/Llama-3.2-3B-Instruct")
    assert meta.extra_data.get("hf.base_model") == "meta-llama/Llama-3.2-3B"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_fineweb_edu_text_classification_and_base_model() -> None:
    with _patch_fineweb_edu():
        meta = read_huggingface("HuggingFaceFW/fineweb-edu-classifier")
    assert "text-classification" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "Snowflake/snowflake-arctic-embed-m"


def test_darwin_kr_legal_architecture_and_finetune() -> None:
    with _patch_darwin_kr_legal():
        meta = read_huggingface("FINAL-Bench/Darwin-28B-KR-Legal")
    assert meta.type_of_model == "qwen3_5"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"
    assert "ko" in meta.extra_lists.get("hf.language", [])


def test_qwen3_swallow_sft_japanese_finetune() -> None:
    with _patch_qwen3_swallow():
        meta = read_huggingface("tokyotech-llm/Qwen3-Swallow-8B-SFT-v0.2")
    assert meta.type_of_model == "qwen3"
    langs = meta.extra_lists.get("hf.language", [])
    assert "ja" in langs and "en" in langs
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_sealion_27b_it_image_text_tag_also_domain() -> None:
    # "image-text-to-text" in tags → also captured as domain.
    with _patch_sealion_27b_it():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-27B-IT")
    assert "image-text-to-text" in meta.usage.domains


def test_boba_food_gguf_domain_base_model_no_arch() -> None:
    with _patch_boba_food_gguf():
        meta = read_huggingface("Doses-AI/boba-0.8b-food-GGUF")
    assert "image-text-to-text" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "Qwen/Qwen3.5-0.8B"
    assert meta.type_of_model is None  # GGUF-only, no config.json


def test_ernie_image_turbo_text_to_image_domain_diffusers() -> None:
    with _patch_ernie_image_turbo():
        meta = read_huggingface("baidu/ERNIE-Image-Turbo")
    assert "text-to-image" in meta.usage.domains
    assert meta.extra_data.get("hf.library_name") == "diffusers"


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


def test_exaone45_33b_gguf_image_text_to_text_domain() -> None:
    with _patch_exaone45_33b_gguf():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-GGUF")
    assert "image-text-to-text" in meta.usage.domains


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


def test_glm45_air_reap_type_of_model() -> None:
    with _patch_glm45_air_reap():
        meta = read_huggingface("THUDM/GLM-4.5-Air-REAP")
    assert meta.type_of_model == "glm4_moe"


def test_glm45_air_reap_architecture() -> None:
    with _patch_glm45_air_reap():
        meta = read_huggingface("THUDM/GLM-4.5-Air-REAP")
    assert meta.architecture == "Glm4MoeForCausalLM"


def test_glm45_air_reap_merge_relation() -> None:
    with _patch_glm45_air_reap():
        meta = read_huggingface("THUDM/GLM-4.5-Air-REAP")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "merge"


def test_glm45_air_reap_text_generation_domain() -> None:
    with _patch_glm45_air_reap():
        meta = read_huggingface("THUDM/GLM-4.5-Air-REAP")
    assert "text-generation" in meta.usage.domains


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


def test_clip_japanese_v2_hidden_size() -> None:
    with _patch_clip_japanese_v2():
        meta = read_huggingface("line-corporation/clip-japanese-base-v2")
    assert meta.hyperparameters.get("hidden_size") == 768


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


def test_fujitsu_llm_text_generation_domain() -> None:
    with _patch_fujitsu_llm():
        meta = read_huggingface("Fujitsu/Fujitsu-LLM-KG-8x7B")
    assert "text-generation" in meta.usage.domains
