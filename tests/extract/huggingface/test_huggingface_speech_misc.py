# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for speech and audio models: text-to-speech, speaker diarization,
automatic speech recognition, and quantized/fine-tuned ASR variants.

See also: test_huggingface_vision_robotics.py, test_huggingface_text_misc.py,
and test_huggingface_granite_misc.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .conftest import (
    _patch_granite_speech,
    _patch_indic_conformer,
    _patch_ipa_whisper,
    _patch_mimo_asr_gguf,
    _patch_omnivoice,
    _patch_omnivoice_bf16,
    _patch_pyannote_diar,
    _patch_seamless_m4t,
    _patch_vibevoice_asr,
    _patch_wav2vec2_id_jv_su,
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
