# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for regional/specialised text-generation, translation, and
summarization models, plus the any-to-any Nemotron omni model.

See also: test_huggingface_embeddings.py, test_huggingface_gated_access.py,
test_huggingface_gated_metadata.py, test_huggingface_granite_misc.py,
test_huggingface_multimodal.py, test_huggingface_omni_modal.py,
test_huggingface_speech_misc.py, test_huggingface_structured_text.py,
test_huggingface_text_generation_instruct.py,
test_huggingface_text_generation_pretrained.py, test_huggingface_vision.py,
test_huggingface_vision_robotics.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .hf_patches._hf_patches_gated_metadata import (
    _patch_hunyuan_mt,
    _patch_hunyuan_mt7b,
    _patch_ii_medical,
    _patch_mistral_medium,
    _patch_opus_mt_th_en,
)
from .hf_patches._hf_patches_omni_modal import (
    _patch_nemotron,
)
from .hf_patches._hf_patches_structured_text import (
    _patch_falconsai,
    _patch_hy_mt_gguf,
    _patch_privacy_filter,
)
from .hf_patches._hf_patches_text_generation_regional import (
    _patch_chinda,
    _patch_chinda_gguf,
    _patch_darwin_kr_legal,
    _patch_fujitsu_llm,
    _patch_gpt_neox_jp,
    _patch_laguna,
    _patch_llmjp,
    _patch_mallam,
    _patch_qwen3_swallow,
    _patch_sailor2_20b,
    _patch_sealion_27b_it,
    _patch_tildeopen_30b,
    _patch_tildeopen_30b_64k,
    _patch_typhoon,
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
    # "image-text-to-text" in tags -> also captured as domain.
    with _patch_sealion_27b_it():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-27B-IT")
    assert "image-text-to-text" in meta.usage.domains


def test_fujitsu_llm_no_architecture() -> None:
    # Config gated -> type_of_model and architecture not available
    with _patch_fujitsu_llm():
        meta = read_huggingface("Fujitsu/Fujitsu-LLM-KG-8x7B")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_fujitsu_llm_nemo_library_name() -> None:
    # NeMo framework: library_name="nemo" -> extra_data["hf.library_name"]
    with _patch_fujitsu_llm():
        meta = read_huggingface("Fujitsu/Fujitsu-LLM-KG-8x7B")
    assert (meta.extra_data or {}).get("hf.library_name") == "nemo"


def test_fujitsu_llm_text_generation_domain() -> None:
    with _patch_fujitsu_llm():
        meta = read_huggingface("Fujitsu/Fujitsu-LLM-KG-8x7B")
    assert "text-generation" in meta.usage.domains


def test_tildeopen_30b_64k_type_of_model() -> None:
    with _patch_tildeopen_30b_64k():
        meta = read_huggingface("TildeAI/TildeOpen-30b-64k")
    assert meta.type_of_model == "llama"


def test_tildeopen_30b_64k_yarn_extended_context() -> None:
    # YaRN RoPE extends context from 8192 -> 65536; max_position_embeddings captured
    with _patch_tildeopen_30b_64k():
        meta = read_huggingface("TildeAI/TildeOpen-30b-64k")
    assert meta.hyperparameters.get("max_position_embeddings") == 65536


def test_tildeopen_30b_64k_tokenizer_max_length() -> None:
    # model_max_length=65536 is a real value (not unlimited sentinel) -> captured
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


def test_tildeopen_30b_type_of_model() -> None:
    with _patch_tildeopen_30b():
        meta = read_huggingface("TildeAI/TildeOpen-30b")
    assert meta.type_of_model == "llama"


def test_tildeopen_30b_sentinel_tokenizer_max_length_filtered() -> None:
    # LlamaTokenizer unlimited sentinel -> hf.tokenizer_max_length NOT set
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
