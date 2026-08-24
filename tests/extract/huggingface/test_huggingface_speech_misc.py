# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for speech and audio models: text-to-speech, speaker diarization,
automatic speech recognition, and quantized/fine-tuned ASR variants.

See also: test_huggingface_embeddings.py, test_huggingface_gated_access.py,
test_huggingface_gated_metadata.py, test_huggingface_granite_misc.py,
test_huggingface_multimodal.py, test_huggingface_omni_modal.py,
test_huggingface_structured_text.py,
test_huggingface_text_generation_instruct.py,
test_huggingface_text_generation_pretrained.py, test_huggingface_text_misc.py,
test_huggingface_vision.py, test_huggingface_vision_robotics.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .hf_patches._hf_patches_speech_audio import (
    _patch_firered_vad,
    _patch_granite_speech,
    _patch_indic_conformer,
    _patch_ipa_whisper,
    _patch_kokoro,
    _patch_llasa_3b,
    _patch_mimo_asr_gguf,
    _patch_omnivoice,
    _patch_omnivoice_bf16,
    _patch_pyannote_diar,
    _patch_seamless_m4t,
    _patch_vibevoice_asr,
    _patch_voxtral_mini,
    _patch_wav2vec2_id_jv_su,
    _patch_wav2vec2_jp,
    _patch_whisper,
)


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
    # "audio-to-audio" in tags -> captured as domain (audio-to-audio domain tag).
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


def test_firered_vad_voice_activity_detection_domain() -> None:
    # voice-activity-detection added to _DOMAIN_TAGS
    with _patch_firered_vad():
        meta = read_huggingface("FireRedTeam/FireRedVAD")
    assert "voice-activity-detection" in meta.usage.domains


def test_firered_vad_no_architecture() -> None:
    with _patch_firered_vad():
        meta = read_huggingface("FireRedTeam/FireRedVAD")
    assert meta.type_of_model is None
