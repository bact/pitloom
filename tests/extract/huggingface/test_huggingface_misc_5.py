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
    _patch_bloom,
    _patch_bloomz_7b1,
    _patch_cohere_aya_23,
    _patch_eurollm_1b7,
    _patch_llasa_3b,
    _patch_moirai,
    _patch_occiglot,
    _patch_openeurollm,
    _patch_pharia_aligned,
    _patch_pharia_control,
    _patch_stable_zero123,
    _patch_tildeopen_30b,
    _patch_tildeopen_30b_64k,
    _patch_voxtral_mini,
    _patch_windowseat,
    _patch_wmt22_cometkiwi,
)


def test_windowseat_no_architecture() -> None:
    # No config.json -> type_of_model and architecture are None
    with _patch_windowseat():
        meta = read_huggingface("windowseat-ai/windowseat-reflection")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_windowseat_peft_library_name() -> None:
    # PEFT adapter: library_name="peft" -> extra_data["hf.library_name"]
    with _patch_windowseat():
        meta = read_huggingface("windowseat-ai/windowseat-reflection")
    assert (meta.extra_data or {}).get("hf.library_name") == "peft"


def test_windowseat_image_to_image_domain() -> None:
    with _patch_windowseat():
        meta = read_huggingface("windowseat-ai/windowseat-reflection")
    assert "image-to-image" in meta.usage.domains


def test_moirai_no_type_of_model() -> None:
    # Config has no "model_type" key -> type_of_model=None
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert meta.type_of_model is None


def test_moirai_no_architecture() -> None:
    # Config has no "architectures" key -> architecture=None
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert meta.architecture is None


def test_moirai_empty_hyperparameters() -> None:
    # Custom config keys (patch_sizes, d_model, etc.) not in _HYPER_KEYS
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert not meta.hyperparameters


def test_moirai_time_series_forecasting_domain() -> None:
    # "time-series-forecasting" added to _DOMAIN_TAGS -> captured as domain
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert "time-series-forecasting" in meta.usage.domains


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
    # vllm as serving framework: library_name="vllm" -> hf.library_name
    with _patch_voxtral_mini():
        meta = read_huggingface("mistralai/Voxtral-Mini-4B-Realtime-2602")
    assert (meta.extra_data or {}).get("hf.library_name") == "vllm"


def test_voxtral_mini_hyperparameters() -> None:
    with _patch_voxtral_mini():
        meta = read_huggingface("mistralai/Voxtral-Mini-4B-Realtime-2602")
    assert meta.hyperparameters.get("hidden_size") == 3072
    assert meta.hyperparameters.get("num_key_value_heads") == 8


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


def test_bloomz_7b1_type_of_model() -> None:
    with _patch_bloomz_7b1():
        meta = read_huggingface("bigscience/bloomz-7b1")
    assert meta.type_of_model == "bloom"


def test_bloomz_7b1_seq_length_captured() -> None:
    # seq_length added to _HYPER_KEYS -> BLOOM context length now captured
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


def test_cohere_aya_23_no_type_of_model() -> None:
    with _patch_cohere_aya_23():
        meta = read_huggingface("CohereLabs/aya-23-8B")
    assert meta.type_of_model is None


def test_cohere_aya_23_empty_domains() -> None:
    with _patch_cohere_aya_23():
        meta = read_huggingface("CohereLabs/aya-23-8B")
    assert not meta.usage.domains


def test_cohere_aya_23_author_captured_from_hub_info() -> None:
    with _patch_cohere_aya_23():
        meta = read_huggingface("CohereLabs/aya-23-8B")
    assert (meta.extra_data or {}).get("hf.author") == "CohereLabs"


def test_occiglot_type_of_model() -> None:
    with _patch_occiglot():
        meta = read_huggingface("occiglot/occiglot-7b-eu5-instruct")
    assert meta.type_of_model == "mistral"


def test_occiglot_sliding_window_captured() -> None:
    # sliding_window is in _HYPER_KEYS -> captured as hyperparameter
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
    # Unlimited sentinel -> hf.tokenizer_max_length not set
    with _patch_occiglot():
        meta = read_huggingface("occiglot/occiglot-7b-eu5-instruct")
    assert "hf.tokenizer_max_length" not in (meta.extra_data or {})


def test_pharia_control_no_architecture() -> None:
    # Config absent: no type_of_model or architecture
    with _patch_pharia_control():
        meta = read_huggingface("Aleph-Alpha/Pharia-1-LLM-7B-control")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_pharia_control_scaling_library() -> None:
    # Custom "scaling" framework: library_name="scaling" -> hf.library_name
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


def test_pharia_aligned_text_generation_domain() -> None:
    with _patch_pharia_aligned():
        meta = read_huggingface("Aleph-Alpha/Pharia-1-LLM-7B-control-aligned")
    assert "text-generation" in meta.usage.domains


def test_wmt22_cometkiwi_no_type_of_model() -> None:
    with _patch_wmt22_cometkiwi():
        meta = read_huggingface("Unbabel/wmt22-cometkiwi-da")
    assert meta.type_of_model is None


def test_wmt22_cometkiwi_empty_domains() -> None:
    with _patch_wmt22_cometkiwi():
        meta = read_huggingface("Unbabel/wmt22-cometkiwi-da")
    assert not meta.usage.domains


def test_wmt22_cometkiwi_author_from_hub_info() -> None:
    with _patch_wmt22_cometkiwi():
        meta = read_huggingface("Unbabel/wmt22-cometkiwi-da")
    assert (meta.extra_data or {}).get("hf.author") == "Unbabel"


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


def test_stable_zero123_text_to_3d_domain() -> None:
    # text-to-3d added to _DOMAIN_TAGS; as pipeline_tag it is captured directly
    with _patch_stable_zero123():
        meta = read_huggingface("stabilityai/stable-zero123")
    assert "text-to-3d" in meta.usage.domains


def test_stable_zero123_no_architecture() -> None:
    with _patch_stable_zero123():
        meta = read_huggingface("stabilityai/stable-zero123")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_stable_zero123_diffusers_library() -> None:
    with _patch_stable_zero123():
        meta = read_huggingface("stabilityai/stable-zero123")
    assert (meta.extra_data or {}).get("hf.library_name") == "diffusers"
