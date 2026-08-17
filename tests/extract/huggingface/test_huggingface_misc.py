# ruff: noqa: F403, F405
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from pitloom.extract._huggingface import (
    _load_model_card,
    _load_model_info,
    _safe_load_json,
    is_huggingface_source,
    read_huggingface,
)

from .conftest import *


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
        with caplog.at_level(logging.DEBUG, logger="pitloom.extract._huggingface"):
            result = _safe_load_json("org/model", "config.json")
    assert result is None
    assert any("config.json" in r.message for r in caplog.records)


def test_load_model_card_failure_logs_and_returns_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with patch(
        "huggingface_hub.ModelCard.load", side_effect=OSError("card fetch failed")
    ):
        with caplog.at_level(logging.DEBUG, logger="pitloom.extract._huggingface"):
            text, data = _load_model_card("org/model")
    assert text is None
    assert data == {}
    assert any("org/model" in r.message for r in caplog.records)


def test_load_model_info_failure_logs_and_returns_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with patch("huggingface_hub.model_info", side_effect=OSError("info fetch failed")):
        with caplog.at_level(logging.DEBUG, logger="pitloom.extract._huggingface"):
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


def test_nllb_m2m100_architecture() -> None:
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert meta.type_of_model == "m2m_100"
    assert meta.architecture == "M2M100ForConditionalGeneration"


def test_nllb_large_multilingual_vocab() -> None:
    # 256 206-token vocabulary for 200-language coverage
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert meta.hyperparameters.get("vocab_size") == 256206


def test_nllb_num_hidden_layers_captured() -> None:
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert meta.hyperparameters.get("num_hidden_layers") == 12


def test_nllb_d_model_not_in_hyperparameters() -> None:
    # "d_model" is the m2m_100 hidden-dimension key but is not in _HYPER_KEYS
    # (which looks for "hidden_size") - silently skipped.
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert "d_model" not in meta.hyperparameters


def test_nllb_tokenizer_real_max_length_captured() -> None:
    # model_max_length=1024 is a real limit (below the unlimited sentinel)
    # and must appear in extra_data - contrast with serengeti's filtered value.
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert meta.extra_data.get("hf.tokenizer_max_length") == 1024
    assert meta.extra_data.get("hf.tokenizer_class") == "NllbTokenizer"


def test_nllb_no_domain_when_no_card() -> None:
    # "translation" and "text2text-generation" are domain tags but live only
    # in model_info.tags - not captured when there is no model card.
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert not meta.usage.domains


def test_nllb_no_language_when_no_card() -> None:
    # 200 language codes are in model_info.tags but not captured without a card.
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert "hf.language" not in meta.extra_lists


def test_sonoisa_language_scalar_string_normalised() -> None:
    # "ja" as a scalar must be stored as ["ja"], not as individual chars ["j","a"].
    with _patch_sonoisa():
        meta = read_huggingface("sonoisa/sentence-bert-base-ja-mean-tokens")
    assert meta.extra_lists.get("hf.language") == ["ja"]


def test_sonoisa_feature_extraction_domain() -> None:
    with _patch_sonoisa():
        meta = read_huggingface("sonoisa/sentence-bert-base-ja-mean-tokens")
    assert "feature-extraction" in meta.usage.domains


def test_sonoisa_sentence_bert_tags_in_extra_lists() -> None:
    # "sentence-bert" is not a domain tag -> extra_lists["hf.tags"]
    with _patch_sonoisa():
        meta = read_huggingface("sonoisa/sentence-bert-base-ja-mean-tokens")
    assert "sentence-bert" in meta.extra_lists.get("hf.tags", [])


def test_wav2vec2_jp_language_scalar_normalised() -> None:
    with _patch_wav2vec2_jp():
        meta = read_huggingface("jonatasgrosman/wav2vec2-large-xlsr-53-japanese")
    assert meta.extra_lists.get("hf.language") == ["ja"]


def test_wav2vec2_jp_doi_extracted() -> None:
    with _patch_wav2vec2_jp():
        meta = read_huggingface("jonatasgrosman/wav2vec2-large-xlsr-53-japanese")
    assert meta.extra_data.get("hf.doi") == "10.57967/hf/3568"


def test_wav2vec2_jp_model_index_in_extra_data() -> None:
    with _patch_wav2vec2_jp():
        meta = read_huggingface("jonatasgrosman/wav2vec2-large-xlsr-53-japanese")
    assert meta.extra_data.get("hf.model_index") is not None


def test_wav2vec2_jp_asr_domain() -> None:
    with _patch_wav2vec2_jp():
        meta = read_huggingface("jonatasgrosman/wav2vec2-large-xlsr-53-japanese")
    assert "automatic-speech-recognition" in meta.usage.domains


def test_wangchanx_legal_base_model_extracted() -> None:
    with _patch_wangchanx_legal():
        meta = read_huggingface("airesearch/WangchanX-Legal-ThaiCCL-Retriever")
    assert meta.extra_data.get("hf.base_model") == "BAAI/bge-m3"


def test_wangchanx_legal_base_model_relation_finetune() -> None:
    with _patch_wangchanx_legal():
        meta = read_huggingface("airesearch/WangchanX-Legal-ThaiCCL-Retriever")
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_wangchanx_legal_xlm_roberta_architecture() -> None:
    with _patch_wangchanx_legal():
        meta = read_huggingface("airesearch/WangchanX-Legal-ThaiCCL-Retriever")
    assert meta.type_of_model == "xlm-roberta"
    assert meta.architecture == "XLMRobertaModel"


def test_wangchanx_legal_dataset_reference() -> None:
    with _patch_wangchanx_legal():
        meta = read_huggingface("airesearch/WangchanX-Legal-ThaiCCL-Retriever")
    assert any("WangchanX-Legal-ThaiCCL-RAG" in d.metadata.name for d in meta.datasets)


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


def test_ruri_arxiv_extracted() -> None:
    with _patch_ruri():
        meta = read_huggingface("cl-nagoya/ruri-v3-310m")
    assert "2409.07737" in meta.extra_lists.get("hf.arxiv", [])


def test_ruri_base_model_and_relation() -> None:
    with _patch_ruri():
        meta = read_huggingface("cl-nagoya/ruri-v3-310m")
    assert meta.extra_data.get("hf.base_model") == "cl-nagoya/ruri-v3-pt-310m"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_ruri_modernbert_architecture() -> None:
    with _patch_ruri():
        meta = read_huggingface("cl-nagoya/ruri-v3-310m")
    assert meta.type_of_model == "modernbert"


def test_nomic_gguf_base_model_quantized() -> None:
    with _patch_nomic_gguf():
        meta = read_huggingface("nomic-ai/nomic-embed-text-v1.5-GGUF")
    assert meta.extra_data.get("hf.base_model") == "nomic-ai/nomic-embed-text-v1.5"
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"


def test_vntl_quantized_translation_gguf() -> None:
    with _patch_vntl():
        meta = read_huggingface("lmg-anon/vntl-llama3-8b-v2-gguf")
    assert meta.license == "llama3"
    assert meta.extra_data.get("hf.base_model") == "rinna/llama-3-youko-8b"
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"
    assert "translation" in meta.usage.domains


def test_sugoi_gguf_base_model_list_form() -> None:
    # base_model as a list ["sugoitoolkit/Sugoi-14B-Ultra-HF"]
    # - primary entry extracted.
    with _patch_sugoi():
        meta = read_huggingface("sugoitoolkit/Sugoi-14B-Ultra-GGUF")
    assert meta.extra_data.get("hf.base_model") == "sugoitoolkit/Sugoi-14B-Ultra-HF"
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"


def test_talkie_no_config_base_model_finetune() -> None:
    with _patch_talkie():
        meta = read_huggingface("talkie-lm/talkie-1930-13b-it")
    assert meta.extra_data.get("hf.base_model") == "talkie-lm/talkie-1930-13b-base"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"
    assert meta.type_of_model is None  # no config.json


def test_depth_pro_depth_estimation_domain() -> None:
    with _patch_depth_pro():
        meta = read_huggingface("apple/DepthPro-hf")
    assert "depth-estimation" in meta.usage.domains


def test_depth_pro_architecture() -> None:
    with _patch_depth_pro():
        meta = read_huggingface("apple/DepthPro-hf")
    assert meta.type_of_model == "depth_pro"
    assert meta.architecture == "DepthProForDepthEstimation"


def test_marigold_depth_estimation_domain() -> None:
    with _patch_marigold():
        meta = read_huggingface("prs-eth/marigold-depth-v1-0")
    assert "depth-estimation" in meta.usage.domains


def test_marigold_diffusers_library() -> None:
    with _patch_marigold():
        meta = read_huggingface("prs-eth/marigold-depth-v1-0")
    assert meta.extra_data.get("hf.library_name") == "diffusers"


def test_vitpose_keypoint_detection_domain() -> None:
    with _patch_vitpose():
        meta = read_huggingface("usyd-community/vitpose-plus-huge")
    assert "keypoint-detection" in meta.usage.domains


def test_vitpose_architecture() -> None:
    with _patch_vitpose():
        meta = read_huggingface("usyd-community/vitpose-plus-huge")
    assert meta.type_of_model == "vitpose"


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


def test_tapas_table_question_answering_domain() -> None:
    with _patch_tapas():
        meta = read_huggingface("google/tapas-large-finetuned-wtq")
    assert "table-question-answering" in meta.usage.domains


def test_tapas_language_scalar_string() -> None:
    with _patch_tapas():
        meta = read_huggingface("google/tapas-large-finetuned-wtq")
    assert meta.extra_lists.get("hf.language") == ["en"]


def test_tapas_dataset_reference() -> None:
    with _patch_tapas():
        meta = read_huggingface("google/tapas-large-finetuned-wtq")
    assert any("wikitablequestions" in d.metadata.name for d in meta.datasets)


def test_rmbg14_image_segmentation_domain() -> None:
    with _patch_rmbg14():
        meta = read_huggingface("briaai/RMBG-1.4")
    assert "image-segmentation" in meta.usage.domains


def test_rmbg14_custom_tags_in_extra_lists() -> None:
    with _patch_rmbg14():
        meta = read_huggingface("briaai/RMBG-1.4")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "remove background" in tags
    assert "legal liability" in tags


def test_rmbg20_gated_still_has_domain_from_card() -> None:
    # Pipeline tag is in card YAML, so domain is captured even without config.
    with _patch_rmbg20():
        meta = read_huggingface("briaai/RMBG-2.0")
    assert "image-segmentation" in meta.usage.domains
    assert meta.type_of_model is None


def test_fibo_edit_image_to_image_domain() -> None:
    with _patch_fibo_edit():
        meta = read_huggingface("briaai/Fibo-Edit-RMBG")
    assert "image-to-image" in meta.usage.domains


def test_fibo_edit_arxiv_extracted() -> None:
    with _patch_fibo_edit():
        meta = read_huggingface("briaai/Fibo-Edit-RMBG")
    assert "2511.06876" in meta.extra_lists.get("hf.arxiv", [])


def test_fibo_edit_base_model_relation() -> None:
    with _patch_fibo_edit():
        meta = read_huggingface("briaai/Fibo-Edit-RMBG")
    assert meta.extra_data.get("hf.base_model") == "briaai/Fibo-Edit"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_laion_clip_zero_shot_image_classification_domain() -> None:
    with _patch_laion_clip():
        meta = read_huggingface("laion/CLIP-convnext_base_w-laion2B-s13B-b82K-augreg")
    assert "zero-shot-image-classification" in meta.usage.domains


def test_laion_clip_no_config_no_architecture() -> None:
    with _patch_laion_clip():
        meta = read_huggingface("laion/CLIP-convnext_base_w-laion2B-s13B-b82K-augreg")
    assert meta.type_of_model is None


def test_streetclip_zero_shot_classification_domain() -> None:
    with _patch_streetclip():
        meta = read_huggingface("geolocal/StreetCLIP")
    assert "zero-shot-image-classification" in meta.usage.domains


def test_streetclip_clip_architecture() -> None:
    with _patch_streetclip():
        meta = read_huggingface("geolocal/StreetCLIP")
    assert meta.type_of_model == "clip"


def test_streetclip_geo_tags_in_extra_lists() -> None:
    with _patch_streetclip():
        meta = read_huggingface("geolocal/StreetCLIP")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "geolocalization" in tags


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


def test_dinov2_image_feature_extraction_domain() -> None:
    with _patch_dinov2():
        meta = read_huggingface("facebook/dinov2-small")
    assert "image-feature-extraction" in meta.usage.domains


def test_dinov2_architecture() -> None:
    with _patch_dinov2():
        meta = read_huggingface("facebook/dinov2-small")
    assert meta.type_of_model == "dinov2"
    assert meta.architecture == "Dinov2Model"


def test_rad_dino_image_feature_extraction() -> None:
    with _patch_rad_dino():
        meta = read_huggingface("microsoft/rad-dino")
    assert "image-feature-extraction" in meta.usage.domains


def test_uni2_pathology_tags_in_extra_lists() -> None:
    with _patch_uni2():
        meta = read_huggingface("MahmoodLab/UNI2-h")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "histology" in tags
    assert "pathology" in tags


def test_timm_convnext_library_name() -> None:
    with _patch_timm_convnext():
        meta = read_huggingface("timm/convnext_large.dinov3_lvd1689m")
    assert meta.extra_data.get("hf.library_name") == "timm"


def test_groot_robotics_domain() -> None:
    with _patch_groot():
        meta = read_huggingface("nvidia/GR00T-N1.7-3B")
    assert "robotics" in meta.usage.domains


def test_openvla_robotics_and_multimodal_tags() -> None:
    with _patch_openvla():
        meta = read_huggingface("openvla/openvla-7b")
    assert "robotics" in meta.usage.domains
    assert "image-text-to-text" in meta.usage.domains


def test_openvla_architecture() -> None:
    with _patch_openvla():
        meta = read_huggingface("openvla/openvla-7b")
    assert meta.type_of_model == "openvla"


def test_pi05_lerobot_library() -> None:
    with _patch_pi05():
        meta = read_huggingface("lerobot/pi05_base")
    assert meta.extra_data.get("hf.library_name") == "lerobot"


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


def test_sealion_vl_gemma3_architecture_and_base_model() -> None:
    with _patch_sealion_vl():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-4B-VL")
    assert meta.type_of_model == "gemma3"
    assert meta.extra_data.get("hf.base_model") == "google/gemma-3-4b-it"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_sealion_vl_image_text_to_text_domain() -> None:
    with _patch_sealion_vl():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-4B-VL")
    assert "image-text-to-text" in meta.usage.domains


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


def test_dataset_card_yaml_takes_priority_over_info_tags() -> None:
    # When card_data has datasets, model_info tags are ignored for datasets.
    card = _make_card_data(
        license="cc-by-sa-4.0",
        pipeline_tag="text-generation",
        datasets=["from-card-dataset"],
    )
    with _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=card,
        hub_info={"tags": ["dataset:from-info-tag"]},
    ):
        meta = read_huggingface("pythainlp/wangchanglm-7.5B-sft-enth")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "from-card-dataset" in ds_names
    assert "from-info-tag" not in ds_names


def test_dataset_info_tag_fallback_when_no_card_datasets() -> None:
    # When card has no datasets, model_info tags with dataset: prefix are used.
    card = _make_card_data(license="mit", pipeline_tag="text-generation")
    with _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=card,
        hub_info={"tags": ["dataset:fallback-dataset"]},
    ):
        meta = read_huggingface("pythainlp/wangchanglm-7.5B-sft-enth")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "fallback-dataset" in ds_names


def test_vilt_vqa_domain() -> None:
    with _patch_vilt_vqa():
        meta = read_huggingface("dandelin/vilt-b32-finetuned-vqa")
    assert "visual-question-answering" in meta.usage.domains


def test_vilt_vqa_base_model_finetune() -> None:
    with _patch_vilt_vqa():
        meta = read_huggingface("dandelin/vilt-b32-finetuned-vqa")
    assert meta.extra_data.get("hf.base_model") == "dandelin/vilt-b32"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_vilt_vqa_arxiv() -> None:
    with _patch_vilt_vqa():
        meta = read_huggingface("dandelin/vilt-b32-finetuned-vqa")
    assert "2102.03334" in meta.extra_lists.get("hf.arxiv", [])


def test_deplot_vqa_domain() -> None:
    with _patch_deplot():
        meta = read_huggingface("google/deplot")
    assert "visual-question-answering" in meta.usage.domains


def test_deplot_image_text_tag_also_domain() -> None:
    # "image-text-to-text" in tags also captured as domain.
    with _patch_deplot():
        meta = read_huggingface("google/deplot")
    assert "image-text-to-text" in meta.usage.domains


def test_deplot_arxiv() -> None:
    with _patch_deplot():
        meta = read_huggingface("google/deplot")
    assert "2212.10505" in meta.extra_lists.get("hf.arxiv", [])


def test_blip_vqa_domain() -> None:
    with _patch_blip_vqa():
        meta = read_huggingface("Salesforce/blip-vqa-base")
    assert "visual-question-answering" in meta.usage.domains


def test_omnivoice_text_to_speech_domain() -> None:
    with _patch_omnivoice():
        meta = read_huggingface("k2-fsa/OmniVoice")
    assert "text-to-speech" in meta.usage.domains


def test_omnivoice_arxiv_and_base_model() -> None:
    with _patch_omnivoice():
        meta = read_huggingface("k2-fsa/OmniVoice")
    assert "2604.00688" in meta.extra_lists.get("hf.arxiv", [])
    assert meta.extra_data.get("hf.base_model") == "Qwen/Qwen3-0.6B"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_omnivoice_bf16_tts_domain_and_base_model() -> None:
    with _patch_omnivoice_bf16():
        meta = read_huggingface("drbaph/OmniVoice-bf16")
    assert "text-to-speech" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "k2-fsa/OmniVoice"


def test_pyannote_speaker_diarization_domain() -> None:
    with _patch_pyannote_diar():
        meta = read_huggingface("pyannote/speaker-diarization-community-1")
    assert "speaker-diarization" in meta.usage.domains


def test_pyannote_library_name() -> None:
    with _patch_pyannote_diar():
        meta = read_huggingface("pyannote/speaker-diarization-community-1")
    assert meta.extra_data.get("hf.library_name") == "pyannote.audio"


def test_seamless_asr_domain_from_pipeline_tag() -> None:
    with _patch_seamless_m4t():
        meta = read_huggingface("facebook/seamless-m4t-v2-large")
    assert "automatic-speech-recognition" in meta.usage.domains


def test_seamless_audio_to_audio_tag_in_domain() -> None:
    # "audio-to-audio" in tags → captured as domain (audio-to-audio domain tag).
    with _patch_seamless_m4t():
        meta = read_huggingface("facebook/seamless-m4t-v2-large")
    assert "audio-to-audio" in meta.usage.domains


def test_granite_speech_asr_domain() -> None:
    with _patch_granite_speech():
        meta = read_huggingface("ibm-granite/granite-speech-4.1-2b")
    assert "automatic-speech-recognition" in meta.usage.domains


def test_granite_speech_base_model_finetune() -> None:
    with _patch_granite_speech():
        meta = read_huggingface("ibm-granite/granite-speech-4.1-2b")
    assert meta.extra_data.get("hf.base_model") == "ibm-granite/granite-4.0-1b-base"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_indic_conformer_22_indian_languages() -> None:
    with _patch_indic_conformer():
        meta = read_huggingface("ai4bharat/indic-conformer-600m-multilingual")
    assert "automatic-speech-recognition" in meta.usage.domains
    langs = meta.extra_lists.get("hf.language", [])
    assert "hi" in langs and "ta" in langs and "te" in langs
    assert len(langs) == 22


def test_mimo_asr_quantized_gguf() -> None:
    with _patch_mimo_asr_gguf():
        meta = read_huggingface("cstr/mimo-asr-GGUF")
    assert "automatic-speech-recognition" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "XiaomiMiMo/MiMo-V2.5-ASR"
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"


def test_vibevoice_asr_domain_and_arxiv() -> None:
    with _patch_vibevoice_asr():
        meta = read_huggingface("microsoft/VibeVoice-ASR")
    assert "automatic-speech-recognition" in meta.usage.domains
    assert "2601.18184" in meta.extra_lists.get("hf.arxiv", [])


def test_ipa_whisper_base_model_finetune() -> None:
    with _patch_ipa_whisper():
        meta = read_huggingface("neurlang/ipa-whisper-medium")
    assert meta.extra_data.get("hf.base_model") == "openai/whisper-medium"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_ipa_whisper_asr_domain() -> None:
    with _patch_ipa_whisper():
        meta = read_huggingface("neurlang/ipa-whisper-medium")
    assert "automatic-speech-recognition" in meta.usage.domains


def test_wav2vec2_id_asr_domain_three_languages() -> None:
    with _patch_wav2vec2_id_jv_su():
        meta = read_huggingface("indonesian-nlp/wav2vec2-indonesian-javanese-sundanese")
    assert "automatic-speech-recognition" in meta.usage.domains
    langs = meta.extra_lists.get("hf.language", [])
    assert "id" in langs and "jv" in langs and "su" in langs


def test_granite_4_1_8b_gqa_and_12_languages() -> None:
    with _patch_granite_4_1_8b():
        meta = read_huggingface("ibm-granite/granite-4.1-8b")
    assert meta.hyperparameters.get("num_key_value_heads") == 8
    langs = meta.extra_lists.get("hf.language", [])
    assert len(langs) == 12 and "ja" in langs and "ar" in langs


def test_granite_4_1_8b_base_model_finetune() -> None:
    with _patch_granite_4_1_8b():
        meta = read_huggingface("ibm-granite/granite-4.1-8b")
    assert meta.extra_data.get("hf.base_model") == "ibm-granite/granite-4.1-8b-base"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_granite_embed_modernbert_arch_and_library() -> None:
    with _patch_granite_embed():
        meta = read_huggingface("ibm-granite/granite-embedding-97m-multilingual-r2")
    assert meta.type_of_model == "modernbert"
    assert meta.extra_data.get("hf.library_name") == "sentence-transformers"


def test_granite_embed_feature_extraction_domain() -> None:
    with _patch_granite_embed():
        meta = read_huggingface("ibm-granite/granite-embedding-97m-multilingual-r2")
    assert "feature-extraction" in meta.usage.domains


def test_granite_geo_flood_image_segmentation_domain() -> None:
    with _patch_granite_geo_flood():
        meta = read_huggingface("ibm-granite/granite-geospatial-uki-flooddetection")
    assert "image-segmentation" in meta.usage.domains


def test_granite_geo_flood_dataset_refs_from_hf_dataset_repos() -> None:
    # Both flood dataset HF IDs captured as DatasetReference objects.
    with _patch_granite_geo_flood():
        meta = read_huggingface("ibm-granite/granite-geospatial-uki-flooddetection")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "ai-for-good-lab/ai4g-flood-dataset" in ds_names
    assert "blanchon/ETCI-2021-Flood-Detection" in ds_names


def test_granite_geo_flood_terratorch_library_and_base_model() -> None:
    with _patch_granite_geo_flood():
        meta = read_huggingface("ibm-granite/granite-geospatial-uki-flooddetection")
    assert meta.extra_data.get("hf.library_name") == "terratorch"
    assert meta.extra_data.get("hf.base_model") == "ibm-granite/granite-geospatial-uki"


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


def test_windowseat_no_architecture() -> None:
    # No config.json → type_of_model and architecture are None
    with _patch_windowseat():
        meta = read_huggingface("windowseat-ai/windowseat-reflection")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_windowseat_peft_library_name() -> None:
    # PEFT adapter: library_name="peft" → extra_data["hf.library_name"]
    with _patch_windowseat():
        meta = read_huggingface("windowseat-ai/windowseat-reflection")
    assert (meta.extra_data or {}).get("hf.library_name") == "peft"


def test_windowseat_image_to_image_domain() -> None:
    with _patch_windowseat():
        meta = read_huggingface("windowseat-ai/windowseat-reflection")
    assert "image-to-image" in meta.usage.domains


def test_moirai_no_type_of_model() -> None:
    # Config has no "model_type" key → type_of_model=None
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert meta.type_of_model is None


def test_moirai_no_architecture() -> None:
    # Config has no "architectures" key → architecture=None
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert meta.architecture is None


def test_moirai_empty_hyperparameters() -> None:
    # Custom config keys (patch_sizes, d_model, etc.) not in _HYPER_KEYS
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert not meta.hyperparameters


def test_moirai_time_series_forecasting_domain() -> None:
    # "time-series-forecasting" added to _DOMAIN_TAGS → captured as domain
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
    # vllm as serving framework: library_name="vllm" → hf.library_name
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
    # YaRN RoPE extends context from 8192 → 65536; max_position_embeddings captured
    with _patch_tildeopen_30b_64k():
        meta = read_huggingface("TildeAI/TildeOpen-30b-64k")
    assert meta.hyperparameters.get("max_position_embeddings") == 65536


def test_tildeopen_30b_64k_tokenizer_max_length() -> None:
    # model_max_length=65536 is a real value (not unlimited sentinel) → captured
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
    # LlamaTokenizer unlimited sentinel → hf.tokenizer_max_length NOT set
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
    # num_key_value_heads == num_attention_heads == 32 → standard MHA, no GQA
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
    # BLOOM uses n_layer (not num_hidden_layers) → not in _HYPER_KEYS → absent
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
    # seq_length added to _HYPER_KEYS → BLOOM context length now captured
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
    # sliding_window is in _HYPER_KEYS → captured as hyperparameter
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
    # Unlimited sentinel → hf.tokenizer_max_length not set
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
    # Custom "scaling" framework: library_name="scaling" → hf.library_name
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


def test_shap_e_text_to_3d_domain() -> None:
    with _patch_shap_e():
        meta = read_huggingface("openai/shap-e")
    assert "text-to-3d" in meta.usage.domains


def test_shap_e_no_architecture() -> None:
    with _patch_shap_e():
        meta = read_huggingface("openai/shap-e")
    assert meta.type_of_model is None


def test_blenderllm_type_of_model() -> None:
    # Standard Qwen2 decoder with text-to-3d pipeline (Blender script generation)
    with _patch_blenderllm():
        meta = read_huggingface("FreedomIntelligence/BlenderLLM")
    assert meta.type_of_model == "qwen2"


def test_blenderllm_text_to_3d_domain() -> None:
    with _patch_blenderllm():
        meta = read_huggingface("FreedomIntelligence/BlenderLLM")
    assert "text-to-3d" in meta.usage.domains


def test_blenderllm_hyperparameters() -> None:
    with _patch_blenderllm():
        meta = read_huggingface("FreedomIntelligence/BlenderLLM")
    assert meta.hyperparameters.get("hidden_size") == 3584


def test_blenderllm_gguf_no_architecture() -> None:
    with _patch_blenderllm_gguf():
        meta = read_huggingface("hellork/BlenderLLM-IQ3_XXS-GGUF")
    assert meta.type_of_model is None


def test_blenderllm_gguf_text_to_3d_domain() -> None:
    with _patch_blenderllm_gguf():
        meta = read_huggingface("hellork/BlenderLLM-IQ3_XXS-GGUF")
    assert "text-to-3d" in meta.usage.domains


def test_blenderllm_gguf_quantized_relation() -> None:
    with _patch_blenderllm_gguf():
        meta = read_huggingface("hellork/BlenderLLM-IQ3_XXS-GGUF")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "quantized"
    assert (meta.extra_data or {}).get(
        "hf.base_model"
    ) == "FreedomIntelligence/BlenderLLM"


def test_hy_motion_text_to_3d_domain() -> None:
    with _patch_hy_motion():
        meta = read_huggingface("tencent/HY-Motion-1.0")
    assert "text-to-3d" in meta.usage.domains


def test_hy_motion_no_type_of_model() -> None:
    # Custom config keys, no model_type/architectures at top level
    with _patch_hy_motion():
        meta = read_huggingface("tencent/HY-Motion-1.0")
    assert meta.type_of_model is None
    assert not meta.hyperparameters


def test_hy_motion_library_name() -> None:
    with _patch_hy_motion():
        meta = read_huggingface("tencent/HY-Motion-1.0")
    assert (meta.extra_data or {}).get("hf.library_name") == "HY-Motion-1.0"


def test_apple_sharp_image_to_3d_domain() -> None:
    # image-to-3d added to _DOMAIN_TAGS
    with _patch_apple_sharp():
        meta = read_huggingface("apple/Sharp")
    assert "image-to-3d" in meta.usage.domains


def test_apple_sharp_ml_sharp_library() -> None:
    with _patch_apple_sharp():
        meta = read_huggingface("apple/Sharp")
    assert (meta.extra_data or {}).get("hf.library_name") == "ml-sharp"


def test_apple_sharp_no_architecture() -> None:
    with _patch_apple_sharp():
        meta = read_huggingface("apple/Sharp")
    assert meta.type_of_model is None


def test_firered_vad_voice_activity_detection_domain() -> None:
    # voice-activity-detection added to _DOMAIN_TAGS
    with _patch_firered_vad():
        meta = read_huggingface("FireRedTeam/FireRedVAD")
    assert "voice-activity-detection" in meta.usage.domains


def test_firered_vad_no_architecture() -> None:
    with _patch_firered_vad():
        meta = read_huggingface("FireRedTeam/FireRedVAD")
    assert meta.type_of_model is None


def test_gte_reranker_text_ranking_domain() -> None:
    # text-ranking added to _DOMAIN_TAGS; captured via pipeline_tag
    with _patch_gte_reranker():
        meta = read_huggingface("Alibaba-NLP/gte-multilingual-reranker-base")
    assert "text-ranking" in meta.usage.domains


def test_gte_reranker_model_type_placeholder() -> None:
    # model_type="new" is a literal placeholder string used by Alibaba GTE
    with _patch_gte_reranker():
        meta = read_huggingface("Alibaba-NLP/gte-multilingual-reranker-base")
    assert meta.type_of_model == "new"
    assert meta.architecture == "NewForSequenceClassification"


def test_gte_reranker_sentence_transformers_library() -> None:
    with _patch_gte_reranker():
        meta = read_huggingface("Alibaba-NLP/gte-multilingual-reranker-base")
    assert (meta.extra_data or {}).get("hf.library_name") == "sentence-transformers"


def test_openelm_270m_type_of_model() -> None:
    with _patch_openelm_270m():
        meta = read_huggingface("apple/OpenELM-270M")
    assert meta.type_of_model == "openelm"


def test_openelm_270m_architecture() -> None:
    with _patch_openelm_270m():
        meta = read_huggingface("apple/OpenELM-270M")
    assert meta.architecture == "OpenELMForCausalLM"


def test_openelm_270m_head_dim_captured() -> None:
    # head_dim is in _HYPER_KEYS → captured even for custom arch
    with _patch_openelm_270m():
        meta = read_huggingface("apple/OpenELM-270M")
    assert meta.hyperparameters.get("head_dim") == 64


def test_openelm_270m_apple_amlr_passthrough() -> None:
    with _patch_openelm_270m():
        meta = read_huggingface("apple/OpenELM-270M")
    assert meta.license == "apple-amlr"


def test_minimax_m2_type_of_model() -> None:
    with _patch_minimax_m2():
        meta = read_huggingface("MiniMaxAI/MiniMax-M2.7")
    assert meta.type_of_model == "minimax_m2"


def test_minimax_m2_architecture() -> None:
    with _patch_minimax_m2():
        meta = read_huggingface("MiniMaxAI/MiniMax-M2.7")
    assert meta.architecture == "MiniMaxM2ForCausalLM"


def test_minimax_m2_very_long_context() -> None:
    # max_position_embeddings=1_000_000 → captured
    with _patch_minimax_m2():
        meta = read_huggingface("MiniMaxAI/MiniMax-M2.7")
    assert meta.hyperparameters.get("max_position_embeddings") == 1_000_000


def test_llada2_moe_type_of_model() -> None:
    with _patch_llada2_moe():
        meta = read_huggingface("inclusionAI/LLaDA2.0-Uni")
    assert meta.type_of_model == "llada2_moe"


def test_llada2_moe_architecture() -> None:
    with _patch_llada2_moe():
        meta = read_huggingface("inclusionAI/LLaDA2.0-Uni")
    assert meta.architecture == "LLaDA2MoeModelLM"


def test_llada2_moe_any_to_any_domain() -> None:
    with _patch_llada2_moe():
        meta = read_huggingface("inclusionAI/LLaDA2.0-Uni")
    assert "any-to-any" in meta.usage.domains


def test_bagel_type_of_model() -> None:
    with _patch_bagel():
        meta = read_huggingface("ByteDance-Seed/BAGEL-7B-MoT")
    assert meta.type_of_model == "bagel"


def test_bagel_empty_hyperparameters() -> None:
    # All numeric keys are nested inside llm_config/vit_config → not captured
    with _patch_bagel():
        meta = read_huggingface("ByteDance-Seed/BAGEL-7B-MoT")
    assert not meta.hyperparameters


def test_bagel_any_to_any_domain() -> None:
    with _patch_bagel():
        meta = read_huggingface("ByteDance-Seed/BAGEL-7B-MoT")
    assert "any-to-any" in meta.usage.domains


def test_bagel_bagel_mot_library() -> None:
    with _patch_bagel():
        meta = read_huggingface("ByteDance-Seed/BAGEL-7B-MoT")
    assert (meta.extra_data or {}).get("hf.library_name") == "bagel-mot"


def test_sensenova_type_of_model() -> None:
    with _patch_sensenova():
        meta = read_huggingface("sensenova/SenseNova-U1-8B-MoT")
    assert meta.type_of_model == "neo_chat"


def test_sensenova_architecture() -> None:
    with _patch_sensenova():
        meta = read_huggingface("sensenova/SenseNova-U1-8B-MoT")
    assert meta.architecture == "NEOChatModel"


def test_sensenova_empty_hyperparameters() -> None:
    # Numeric keys only in nested llm_config → not captured by extractor
    with _patch_sensenova():
        meta = read_huggingface("sensenova/SenseNova-U1-8B-MoT")
    assert not meta.hyperparameters


def test_sensenova_any_to_any_domain() -> None:
    with _patch_sensenova():
        meta = read_huggingface("sensenova/SenseNova-U1-8B-MoT")
    assert "any-to-any" in meta.usage.domains


def test_mmada_type_of_model() -> None:
    with _patch_mmada():
        meta = read_huggingface("Gen-Verse/MMaDA-8B-Base")
    assert meta.type_of_model == "llada"


def test_mmada_alibi_no_max_position_embeddings() -> None:
    # ALiBi: no max_position_embeddings in config → not in hyperparameters
    with _patch_mmada():
        meta = read_huggingface("Gen-Verse/MMaDA-8B-Base")
    assert "max_position_embeddings" not in meta.hyperparameters


def test_mmada_vocab_size_captured() -> None:
    with _patch_mmada():
        meta = read_huggingface("Gen-Verse/MMaDA-8B-Base")
    assert meta.hyperparameters.get("vocab_size") == 32000


def test_mmada_any_to_any_domain() -> None:
    with _patch_mmada():
        meta = read_huggingface("Gen-Verse/MMaDA-8B-Base")
    assert "any-to-any" in meta.usage.domains


def test_mimo_audio_model_type_is_qwen2() -> None:
    # model_type stays "qwen2" (base) even though architecture is MiMoAudioModel
    with _patch_mimo_audio():
        meta = read_huggingface("XiaomiMiMo/MiMo-Audio-7B-Instruct")
    assert meta.type_of_model == "qwen2"


def test_mimo_audio_custom_architecture() -> None:
    # architectures field contains the wrapper class, not the base Qwen2 class
    with _patch_mimo_audio():
        meta = read_huggingface("XiaomiMiMo/MiMo-Audio-7B-Instruct")
    assert meta.architecture == "MiMoAudioModel"


def test_mimo_audio_hyperparameters() -> None:
    with _patch_mimo_audio():
        meta = read_huggingface("XiaomiMiMo/MiMo-Audio-7B-Instruct")
    assert meta.hyperparameters.get("hidden_size") == 3584
    assert meta.hyperparameters.get("num_key_value_heads") == 4


def test_mimo_audio_any_to_any_domain() -> None:
    with _patch_mimo_audio():
        meta = read_huggingface("XiaomiMiMo/MiMo-Audio-7B-Instruct")
    assert "any-to-any" in meta.usage.domains


def test_lightglue_type_of_model() -> None:
    with _patch_lightglue():
        meta = read_huggingface("ETH-CVG/lightglue_superpoint")
    assert meta.type_of_model == "lightglue"


def test_lightglue_architecture() -> None:
    with _patch_lightglue():
        meta = read_huggingface("ETH-CVG/lightglue_superpoint")
    assert meta.architecture == "LightGlueForKeypointMatching"


def test_lightglue_empty_hyperparameters() -> None:
    # descriptor_dim, filter_threshold, depth_confidence not in _HYPER_KEYS
    with _patch_lightglue():
        meta = read_huggingface("ETH-CVG/lightglue_superpoint")
    assert not meta.hyperparameters


def test_aion_no_type_of_model() -> None:
    # Custom aion config: no model_type key
    with _patch_aion():
        meta = read_huggingface("polymathic-ai/aion-base")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_aion_empty_hyperparameters() -> None:
    # decoder_depth, encoder_depth, domains_in, patch_size not in _HYPER_KEYS
    with _patch_aion():
        meta = read_huggingface("polymathic-ai/aion-base")
    assert not meta.hyperparameters


def test_aion_any_to_any_domain() -> None:
    with _patch_aion():
        meta = read_huggingface("polymathic-ai/aion-base")
    assert "any-to-any" in meta.usage.domains


def test_aion_library_name() -> None:
    with _patch_aion():
        meta = read_huggingface("polymathic-ai/aion-base")
    assert (meta.extra_data or {}).get("hf.library_name") == "aion"


def test_stanza_fi_no_architecture() -> None:
    # Stanza: no config.json → no type_of_model or architecture
    with _patch_stanza_fi():
        meta = read_huggingface("stanfordnlp/stanza-fi")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_stanza_fi_stanza_library() -> None:
    with _patch_stanza_fi():
        meta = read_huggingface("stanfordnlp/stanza-fi")
    assert (meta.extra_data or {}).get("hf.library_name") == "stanza"


def test_stanza_fi_language() -> None:
    with _patch_stanza_fi():
        meta = read_huggingface("stanfordnlp/stanza-fi")
    langs = (meta.extra_lists or {}).get("hf.language", [])
    assert "fi" in langs


def test_stanza_fi_empty_domains() -> None:
    # No pipeline_tag → empty usage.domains
    with _patch_stanza_fi():
        meta = read_huggingface("stanfordnlp/stanza-fi")
    assert not meta.usage.domains


def test_stanza_de_stanza_library() -> None:
    with _patch_stanza_de():
        meta = read_huggingface("stanfordnlp/stanza-de")
    assert (meta.extra_data or {}).get("hf.library_name") == "stanza"


def test_stanza_de_german_language() -> None:
    with _patch_stanza_de():
        meta = read_huggingface("stanfordnlp/stanza-de")
    langs = (meta.extra_lists or {}).get("hf.language", [])
    assert langs == ["de"]


def test_stanza_de_no_architecture() -> None:
    with _patch_stanza_de():
        meta = read_huggingface("stanfordnlp/stanza-de")
    assert meta.type_of_model is None


def test_openvino_mixtral_type_of_model() -> None:
    # Config accessible despite OpenVINO quantization → model_type extractable
    with _patch_openvino_mixtral():
        meta = read_huggingface("OpenVINO/Mixtral-8x7B-Instruct-v0.1-int8-ov")
    assert meta.type_of_model == "mixtral"


def test_openvino_mixtral_int8_dtype_captured() -> None:
    # torch_dtype="int8" is in _HYPER_KEYS → captured even for quantized model
    with _patch_openvino_mixtral():
        meta = read_huggingface("OpenVINO/Mixtral-8x7B-Instruct-v0.1-int8-ov")
    assert meta.hyperparameters.get("torch_dtype") == "int8"


def test_openvino_mixtral_openvino_library() -> None:
    with _patch_openvino_mixtral():
        meta = read_huggingface("OpenVINO/Mixtral-8x7B-Instruct-v0.1-int8-ov")
    assert (meta.extra_data or {}).get("hf.library_name") == "openvino"


def test_openvino_mixtral_quantized_relation() -> None:
    with _patch_openvino_mixtral():
        meta = read_huggingface("OpenVINO/Mixtral-8x7B-Instruct-v0.1-int8-ov")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "quantized"


def test_mlx_gemma4_type_of_model() -> None:
    # MLX: config.json accessible → model_type extractable
    with _patch_mlx_gemma4():
        meta = read_huggingface("mlx-community/gemma-4-e2b-it-4bit")
    assert meta.type_of_model == "gemma4"


def test_mlx_gemma4_mlx_library() -> None:
    with _patch_mlx_gemma4():
        meta = read_huggingface("mlx-community/gemma-4-e2b-it-4bit")
    assert (meta.extra_data or {}).get("hf.library_name") == "mlx"


def test_mlx_gemma4_quantized_relation() -> None:
    with _patch_mlx_gemma4():
        meta = read_huggingface("mlx-community/gemma-4-e2b-it-4bit")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "quantized"


def test_mlx_gemma4_any_to_any_domain() -> None:
    with _patch_mlx_gemma4():
        meta = read_huggingface("mlx-community/gemma-4-e2b-it-4bit")
    assert "any-to-any" in meta.usage.domains


def test_onnx_gemma4_type_of_model() -> None:
    with _patch_onnx_gemma4():
        meta = read_huggingface("onnx-community/gemma-4-E2B-it-ONNX")
    assert meta.type_of_model == "gemma4"


def test_onnx_gemma4_transformers_js_library() -> None:
    with _patch_onnx_gemma4():
        meta = read_huggingface("onnx-community/gemma-4-E2B-it-ONNX")
    assert (meta.extra_data or {}).get("hf.library_name") == "transformers.js"


def test_onnx_gemma4_quantized_relation() -> None:
    with _patch_onnx_gemma4():
        meta = read_huggingface("onnx-community/gemma-4-E2B-it-ONNX")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "quantized"


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


def test_gte_modernbert_type_of_model() -> None:
    with _patch_gte_modernbert():
        meta = read_huggingface("Alibaba-NLP/gte-modernbert-base")
    assert meta.type_of_model == "modernbert"


def test_gte_modernbert_architecture() -> None:
    with _patch_gte_modernbert():
        meta = read_huggingface("Alibaba-NLP/gte-modernbert-base")
    assert meta.architecture == "ModernBertModel"


def test_gte_modernbert_sentence_similarity_domain() -> None:
    with _patch_gte_modernbert():
        meta = read_huggingface("Alibaba-NLP/gte-modernbert-base")
    assert "sentence-similarity" in meta.usage.domains


def test_gte_modernbert_hyperparameters() -> None:
    with _patch_gte_modernbert():
        meta = read_huggingface("Alibaba-NLP/gte-modernbert-base")
    assert meta.hyperparameters.get("max_position_embeddings") == 8192


def test_codeberta_type_of_model() -> None:
    with _patch_codeberta():
        meta = read_huggingface("huggingface/CodeBERTa-small-v1")
    assert meta.type_of_model == "roberta"


def test_codeberta_code_language_preserved() -> None:
    # "code" is not ISO 639-1 but the extractor preserves it as-is
    with _patch_codeberta():
        meta = read_huggingface("huggingface/CodeBERTa-small-v1")
    langs = (meta.extra_lists or {}).get("hf.language", [])
    assert langs == ["code"]


def test_codeberta_fill_mask_domain() -> None:
    with _patch_codeberta():
        meta = read_huggingface("huggingface/CodeBERTa-small-v1")
    assert "fill-mask" in meta.usage.domains


def test_tradepulse_type_of_model() -> None:
    with _patch_tradepulse():
        meta = read_huggingface("Bencode92/tradepulse-finbert-sentiment")
    assert meta.type_of_model == "bert"


def test_tradepulse_architecture() -> None:
    with _patch_tradepulse():
        meta = read_huggingface("Bencode92/tradepulse-finbert-sentiment")
    assert meta.architecture == "BertForSequenceClassification"


def test_tradepulse_text_classification_domain() -> None:
    with _patch_tradepulse():
        meta = read_huggingface("Bencode92/tradepulse-finbert-sentiment")
    assert "text-classification" in meta.usage.domains


def test_tradepulse_finetune_from_finbert() -> None:
    with _patch_tradepulse():
        meta = read_huggingface("Bencode92/tradepulse-finbert-sentiment")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "finetune"
    assert (meta.extra_data or {}).get("hf.base_model") == "ProsusAI/finbert"


def test_hrnetpose_keypoint_detection_domain() -> None:
    with _patch_hrnetpose():
        meta = read_huggingface("qualcomm/HRNetPose")
    assert "keypoint-detection" in meta.usage.domains


def test_hrnetpose_pytorch_library() -> None:
    # Qualcomm uses library_name=pytorch for native PyTorch format
    with _patch_hrnetpose():
        meta = read_huggingface("qualcomm/HRNetPose")
    assert (meta.extra_data or {}).get("hf.library_name") == "pytorch"


def test_hrnetpose_no_architecture() -> None:
    with _patch_hrnetpose():
        meta = read_huggingface("qualcomm/HRNetPose")
    assert meta.type_of_model is None


def test_rtdetr_coco_o365_type_of_model() -> None:
    with _patch_rtdetr_coco_o365():
        meta = read_huggingface("PekingU/rtdetr_r50vd_coco_o365")
    assert meta.type_of_model == "rt_detr"


def test_rtdetr_coco_o365_architecture() -> None:
    with _patch_rtdetr_coco_o365():
        meta = read_huggingface("PekingU/rtdetr_r50vd_coco_o365")
    assert meta.architecture == "RTDetrForObjectDetection"


def test_rtdetr_coco_o365_object_detection_domain() -> None:
    # object-detection is in _DOMAIN_TAGS — captured as domain
    with _patch_rtdetr_coco_o365():
        meta = read_huggingface("PekingU/rtdetr_r50vd_coco_o365")
    assert "object-detection" in meta.usage.domains


def test_rtdetr_coco_o365_only_torch_dtype_in_hyperparameters() -> None:
    # Detection config has no LM keys; only torch_dtype matches _HYPER_KEYS
    with _patch_rtdetr_coco_o365():
        meta = read_huggingface("PekingU/rtdetr_r50vd_coco_o365")
    assert meta.hyperparameters.get("torch_dtype") == "float32"
    assert "hidden_size" not in meta.hyperparameters
    assert "vocab_size" not in meta.hyperparameters


def test_rtdetr_coco_o365_arxiv() -> None:
    with _patch_rtdetr_coco_o365():
        meta = read_huggingface("PekingU/rtdetr_r50vd_coco_o365")
    arxivs = (meta.extra_lists or {}).get("hf.arxiv", [])
    assert "2304.08069" in arxivs


def test_rtdetr_coco_o365_coco_dataset() -> None:
    with _patch_rtdetr_coco_o365():
        meta = read_huggingface("PekingU/rtdetr_r50vd_coco_o365")
    assert meta.datasets
    names = [d.metadata.name for d in meta.datasets if d.metadata and d.metadata.name]
    assert "coco" in names


def test_rtdetr_coco_type_of_model() -> None:
    with _patch_rtdetr_coco():
        meta = read_huggingface("PekingU/rtdetr_r50vd")
    assert meta.type_of_model == "rt_detr"


def test_rtdetr_coco_object_detection_domain() -> None:
    with _patch_rtdetr_coco():
        meta = read_huggingface("PekingU/rtdetr_r50vd")
    assert "object-detection" in meta.usage.domains


def test_rtdetr_coco_no_lm_hyperparameters() -> None:
    # Detection model: d_model, decoder_layers, etc. are NOT in _HYPER_KEYS
    with _patch_rtdetr_coco():
        meta = read_huggingface("PekingU/rtdetr_r50vd")
    assert "hidden_size" not in meta.hyperparameters
    assert "vocab_size" not in meta.hyperparameters


def test_sap_rpt_tabular_classification_domain() -> None:
    # tabular-classification is in _DOMAIN_TAGS
    with _patch_sap_rpt():
        meta = read_huggingface("SAP/sap-rpt-1-oss")
    assert "tabular-classification" in meta.usage.domains


def test_sap_rpt_no_architecture_gated() -> None:
    # Config 401 → no type_of_model or architecture
    with _patch_sap_rpt():
        meta = read_huggingface("SAP/sap-rpt-1-oss")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_sap_rpt_self_referential_library_name() -> None:
    # library_name = model-slug string (non-standard pattern)
    with _patch_sap_rpt():
        meta = read_huggingface("SAP/sap-rpt-1-oss")
    assert (meta.extra_data or {}).get("hf.library_name") == "sap-rpt-1-oss"


def test_sap_rpt_arxiv() -> None:
    with _patch_sap_rpt():
        meta = read_huggingface("SAP/sap-rpt-1-oss")
    arxivs = (meta.extra_lists or {}).get("hf.arxiv", [])
    assert "2506.10707" in arxivs


def test_sap_rpt_dataset() -> None:
    with _patch_sap_rpt():
        meta = read_huggingface("SAP/sap-rpt-1-oss")
    assert meta.datasets
    names = [d.metadata.name for d in meta.datasets if d.metadata and d.metadata.name]
    assert "mlfoundations/t4-full" in names


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
    # All LM numeric keys are inside text_config → not captured by _HYPER_KEYS
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


def test_bert_turkish_type_of_model() -> None:
    # model_type present even though architectures field is absent
    with _patch_bert_turkish():
        meta = read_huggingface("dbmdz/bert-base-turkish-cased")
    assert meta.type_of_model == "bert"


def test_bert_turkish_architecture_none() -> None:
    # architectures key absent from config → architecture=None
    with _patch_bert_turkish():
        meta = read_huggingface("dbmdz/bert-base-turkish-cased")
    assert meta.architecture is None


def test_bert_turkish_no_pipeline_tag_empty_domains() -> None:
    # No pipeline_tag in card → empty usage.domains
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


def test_cross_encoder_type_of_model() -> None:
    with _patch_cross_encoder():
        meta = read_huggingface("cross-encoder/ms-marco-MiniLM-L6-v2")
    assert meta.type_of_model == "bert"


def test_cross_encoder_architecture() -> None:
    with _patch_cross_encoder():
        meta = read_huggingface("cross-encoder/ms-marco-MiniLM-L6-v2")
    assert meta.architecture == "BertForSequenceClassification"


def test_cross_encoder_text_ranking_domain() -> None:
    with _patch_cross_encoder():
        meta = read_huggingface("cross-encoder/ms-marco-MiniLM-L6-v2")
    assert "text-ranking" in meta.usage.domains


def test_cross_encoder_small_hidden_size() -> None:
    # hidden_size=384 — half of standard BERT-base
    with _patch_cross_encoder():
        meta = read_huggingface("cross-encoder/ms-marco-MiniLM-L6-v2")
    assert meta.hyperparameters.get("hidden_size") == 384


def test_cross_encoder_quantized_relation() -> None:
    # base_model:quantized: tag used for layer-reduced/distilled model (not GGUF)
    with _patch_cross_encoder():
        meta = read_huggingface("cross-encoder/ms-marco-MiniLM-L6-v2")
    assert (meta.extra_data or {}).get("hf.base_model_relation") == "quantized"
    assert (meta.extra_data or {}).get(
        "hf.base_model"
    ) == "cross-encoder/ms-marco-MiniLM-L12-v2"


def test_cross_encoder_sentence_transformers_library() -> None:
    with _patch_cross_encoder():
        meta = read_huggingface("cross-encoder/ms-marco-MiniLM-L6-v2")
    assert (meta.extra_data or {}).get("hf.library_name") == "sentence-transformers"
