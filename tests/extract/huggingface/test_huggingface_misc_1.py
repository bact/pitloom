# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from pitloom.extract._huggingface import is_huggingface_source, read_huggingface
from pitloom.extract._huggingface_fetch import (
    _load_model_card,
    _load_model_info,
    _safe_load_json,
)

from .conftest import (
    _patch_aya_vision,
    _patch_deepseek,
    _patch_gemma,
    _patch_inkubalm,
    _patch_kimi,
    _patch_kokoro,
    _patch_llama,
    _patch_sealion_gguf,
    _patch_seallms,
    _patch_serengeti,
    _patch_starcoder2,
    _patch_typhoon,
    _patch_whisper,
)


def test_is_huggingface_source_url() -> None:
    assert is_huggingface_source("https://huggingface.co/mistralai/Mistral-7B-v0.1")


def test_is_huggingface_source_model_id() -> None:
    assert is_huggingface_source("Qwen/Qwen3-235B-A22B")


def test_is_huggingface_source_local_path() -> None:
    assert not is_huggingface_source("/path/to/model.onnx")


def test_is_huggingface_source_plain_filename() -> None:
    assert not is_huggingface_source("model.safetensors")


def test_safe_load_json_download_failure_logs_and_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with patch("huggingface_hub.hf_hub_download", side_effect=OSError("network down")):
        with caplog.at_level(
            logging.DEBUG, logger="pitloom.extract._huggingface_fetch"
        ):
            result = _safe_load_json("org/model", "config.json")
    assert result is None
    assert any("config.json" in r.message for r in caplog.records)


def test_load_model_card_failure_logs_and_returns_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with patch(
        "huggingface_hub.ModelCard.load", side_effect=OSError("card fetch failed")
    ):
        with caplog.at_level(
            logging.DEBUG, logger="pitloom.extract._huggingface_fetch"
        ):
            text, data = _load_model_card("org/model")
    assert text is None
    assert data == {}
    assert any("org/model" in r.message for r in caplog.records)


def test_load_model_info_failure_logs_and_returns_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with patch("huggingface_hub.model_info", side_effect=OSError("info fetch failed")):
        with caplog.at_level(
            logging.DEBUG, logger="pitloom.extract._huggingface_fetch"
        ):
            result = _load_model_info("org/model")
    assert not result
    assert any("org/model" in r.message for r in caplog.records)


def test_kokoro_name() -> None:
    with _patch_kokoro():
        meta = read_huggingface("hexgrad/Kokoro-82M")
    assert meta.name == "Kokoro-82M"


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


def test_kimi_architecture() -> None:
    with _patch_kimi():
        meta = read_huggingface("moonshotai/Kimi-K2.6")
    assert meta.type_of_model == "kimi_k25"
    assert meta.architecture == "KimiK25ForConditionalGeneration"


def test_kimi_multimodal_domain() -> None:
    with _patch_kimi():
        meta = read_huggingface("moonshotai/Kimi-K2.6")
    assert "image-text-to-text" in meta.usage.domains


def test_gemma_name() -> None:
    with _patch_gemma():
        meta = read_huggingface("google/gemma-2b")
    assert meta.name == "gemma-2b"


def test_gemma_no_architecture_when_gated_config() -> None:
    with _patch_gemma():
        meta = read_huggingface("google/gemma-2b")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_gemma_no_domain_when_no_pipeline_tag() -> None:
    with _patch_gemma():
        meta = read_huggingface("google/gemma-2b")
    assert not meta.usage.domains


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


def test_serengeti_tokenizer_class_from_tokenizer_config() -> None:
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert meta.extra_data.get("hf.tokenizer_class") == "ElectraTokenizer"


def test_serengeti_unlimited_tokenizer_max_length_filtered() -> None:
    # The sentinel value (1e30) must NOT appear in extra_data.
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert "hf.tokenizer_max_length" not in meta.extra_data


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


def test_inkubalm_name() -> None:
    with _patch_inkubalm():
        meta = read_huggingface("lelapa/InkubaLM-0.4B")
    assert meta.name == "InkubaLM-0.4B"


def test_inkubalm_no_architecture_when_gated() -> None:
    with _patch_inkubalm():
        meta = read_huggingface("lelapa/InkubaLM-0.4B")
    assert meta.type_of_model is None
    assert meta.architecture is None


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
