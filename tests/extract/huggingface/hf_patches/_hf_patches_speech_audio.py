# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for speech and audio models: automatic speech recognition, text-
to-speech, voice activity detection, and speaker diarization.

See also: _hf_patches_base.py, _hf_patches_text_generation_pretrained.py,
_hf_patches_text_generation_instruct.py,
_hf_patches_text_generation_regional.py, _hf_patches_gated_metadata.py,
_hf_patches_gated_access.py, _hf_patches_multimodal.py,
_hf_patches_omni_modal.py, _hf_patches_embeddings.py, _hf_patches_vision.py,
_hf_patches_structured_text.py, _hf_patches_generative_3d.py. Sibling test
modules import these names directly from the matching topic module.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)

_KOKORO_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-to-speech",
    tags=None,
    language=["en"],
    library_name=None,
)


_KOKORO_CONFIG: dict[str, Any] = {
    # Custom Kokoro schema - no model_type or architectures
    "istftnet": {},
    "dim_in": 64,
    "hidden_dim": 512,
    "n_layer": 3,
    "n_mels": 80,
    "multispeaker": True,
}


def _patch_kokoro() -> Any:
    return _patch_hf_calls(
        config=_KOKORO_CONFIG,
        tokenizer_config=None,
        card_data=_KOKORO_CARD_DATA,
        card_text="---\nlicense: apache-2.0\n---\n\nA small TTS model.",
        hub_info={"author": "hexgrad"},
    )


_WHISPER_LANGUAGES: list[Any] = [
    "en",
    "zh",
    "de",
    "es",
    "ru",
    "ko",
    "fr",
    "ja",
    "pt",
    "tr",
    "pl",
    "ca",
    "nl",
    "ar",
    "sv",
    "it",
    "id",
    "hi",
    "fi",
    "vi",
    "he",
    "uk",
    "el",
    "ms",
    "cs",
    "ro",
    "da",
    "hu",
    "ta",
    False,  # YAML 1.1 parses "no" (Norwegian Bokmål) as False
    "th",
    "ur",
    "hr",
    "bg",
    "lt",
]


_WHISPER_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="automatic-speech-recognition",
    tags=["audio", "automatic-speech-recognition", "hf-asr-leaderboard"],
    language=_WHISPER_LANGUAGES,
    library_name=None,
)


_WHISPER_CONFIG: dict[str, Any] = {
    "model_type": "whisper",
    "architectures": ["WhisperForConditionalGeneration"],
    "vocab_size": 51865,
    "num_hidden_layers": 32,
    "max_source_positions": 1500,
}


def _patch_whisper() -> Any:
    return _patch_hf_calls(
        config=_WHISPER_CONFIG,
        tokenizer_config=None,
        card_data=_WHISPER_CARD_DATA,
        hub_info={"author": "openai"},
    )


_WAV2VEC2_JP_MODEL_INDEX = [
    {
        "name": "XLSR Wav2Vec2 Japanese by Jonatas Grosman",
        "results": [
            {
                "task": {"type": "automatic-speech-recognition"},
                "dataset": {"name": "Common Voice ja", "type": "common_voice"},
                "metrics": [{"type": "wer", "value": 81.8, "name": "Test WER"}],
            }
        ],
    }
]


_WAV2VEC2_JP_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="automatic-speech-recognition",
    tags=["audio", "speech", "xlsr-fine-tuning-week"],
    language="ja",  # scalar string
    datasets=["common_voice"],
    model_index=_WAV2VEC2_JP_MODEL_INDEX,
)


_WAV2VEC2_JP_CONFIG: dict[str, Any] = {
    "model_type": "wav2vec2",
    "architectures": ["Wav2Vec2ForCTC"],
    "vocab_size": 2341,
    "num_hidden_layers": 24,
    "hidden_size": 1024,
}


def _patch_wav2vec2_jp() -> Any:
    return _patch_hf_calls(
        config=_WAV2VEC2_JP_CONFIG,
        tokenizer_config=None,
        card_data=_WAV2VEC2_JP_CARD_DATA,
        hub_info={
            "author": "jonatasgrosman",
            "tags": ["doi:10.57967/hf/3568"],
        },
    )


def _patch_omnivoice() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-to-speech",
            tags=["zero-shot", "multilingual", "voice-cloning"],
            language=["multilingual"],
            base_model=["Qwen/Qwen3-0.6B"],
        ),
        hub_info={
            "author": "k2-fsa",
            "tags": [
                "arxiv:2604.00688",
                "base_model:Qwen/Qwen3-0.6B",
                "base_model:finetune:Qwen/Qwen3-0.6B",
            ],
        },
    )


def _patch_omnivoice_bf16() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-to-speech",
            tags=["omnivoice", "bf16"],
            language=["multilingual"],
            base_model=["k2-fsa/OmniVoice"],
        ),
        hub_info={
            "author": "drbaph",
            "tags": [
                "base_model:k2-fsa/OmniVoice",
                "base_model:finetune:k2-fsa/OmniVoice",
            ],
        },
    )


def _patch_pyannote_diar() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="cc-by-4.0",
            pipeline_tag="speaker-diarization",
            tags=["pyannote", "speaker-diarization", "voice-activity-detection"],
            library_name="pyannote.audio",
        ),
        hub_info={"author": "pyannote"},
    )


def _patch_seamless_m4t() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "seamless_m4t_v2",
            "architectures": ["SeamlessM4Tv2Model"],
            "num_hidden_layers": 24,
            "hidden_size": 1024,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="cc-by-nc-4.0",
            pipeline_tag="automatic-speech-recognition",
            tags=["audio-to-audio", "text-to-speech", "speech-translation"],
            language=["en", "fr", "de", "es", "zh", "ar", "hi", "ja", "ko", "pt"],
        ),
        hub_info={
            "author": "facebook",
            "tags": ["arxiv:2312.05187"],
        },
    )


def _patch_granite_speech() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "granite_speech",
            "architectures": ["GraniteSpeechForConditionalGeneration"],
            "num_hidden_layers": 40,
            "hidden_size": 2560,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="automatic-speech-recognition",
            tags=["speech-translation", "multilingual-asr"],
            language=["en", "fr", "de", "es", "pt", "ja"],
            base_model=["ibm-granite/granite-4.0-1b-base"],
        ),
        hub_info={
            "author": "ibm-granite",
            "tags": [
                "base_model:ibm-granite/granite-4.0-1b-base",
                "base_model:finetune:ibm-granite/granite-4.0-1b-base",
            ],
        },
    )


def _patch_indic_conformer() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="automatic-speech-recognition",
            tags=["custom_code", "ONNX"],
            language=[
                "as",
                "bn",
                "gu",
                "hi",
                "kn",
                "ml",
                "mr",
                "or",
                "pa",
                "sa",
                "ta",
                "te",
                "ur",
                "mai",
                "doi",
                "mni",
                "sat",
                "kok",
                "ks",
                "brx",
                "ne",
                "sd",
            ],
        ),
        hub_info={"author": "ai4bharat"},
    )


def _patch_mimo_asr_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="automatic-speech-recognition",
            tags=["GGUF", "audio", "mimo", "qwen2"],
            language=["zh", "en"],
            base_model=["XiaomiMiMo/MiMo-V2.5-ASR"],
        ),
        hub_info={
            "author": "cstr",
            "tags": [
                "base_model:XiaomiMiMo/MiMo-V2.5-ASR",
                "base_model:quantized:XiaomiMiMo/MiMo-V2.5-ASR",
            ],
        },
    )


def _patch_vibevoice_asr() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "vibevoice",
            "architectures": ["VibeVoiceForASRTraining"],
            "num_hidden_layers": 40,
            "hidden_size": 4096,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="automatic-speech-recognition",
            tags=["ASR", "Diarization", "Speech-to-Text"],
            language=["en", "zh", "fr", "de", "es", "ja", "ko", "ar"],
        ),
        hub_info={
            "author": "microsoft",
            "tags": ["arxiv:2601.18184"],
        },
    )


def _patch_ipa_whisper() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "whisper",
            "architectures": ["WhisperForConditionalGeneration"],
            "num_hidden_layers": 24,
            "hidden_size": 1024,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="automatic-speech-recognition",
            tags=["whisper", "IPA", "phonetic"],
            language=["en", "fr", "de", "es", "zh", "ar", "ja"],
            base_model=["openai/whisper-medium"],
        ),
        hub_info={
            "author": "neurlang",
            "tags": [
                "base_model:openai/whisper-medium",
                "base_model:finetune:openai/whisper-medium",
            ],
        },
    )


def _patch_wav2vec2_id_jv_su() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "wav2vec2",
            "architectures": ["Wav2Vec2ForCTC"],
            "vocab_size": 63,
            "num_hidden_layers": 24,
            "hidden_size": 1024,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="automatic-speech-recognition",
            tags=["wav2vec2", "hf-asr-leaderboard"],
            language=["id", "jv", "su"],
            base_model=["facebook/wav2vec2-large-xlsr-53"],
        ),
        hub_info={
            "author": "indonesian-nlp",
            "tags": [
                "base_model:facebook/wav2vec2-large-xlsr-53",
                "base_model:finetune:facebook/wav2vec2-large-xlsr-53",
            ],
        },
    )


_LLASA_3B_CONFIG: dict[str, Any] = {
    "model_type": "llama",
    "architectures": ["LlamaForCausalLM"],
    "vocab_size": 193800,
    "hidden_size": 3072,
    "num_hidden_layers": 28,
    "num_attention_heads": 24,
    "num_key_value_heads": 8,
    "max_position_embeddings": 4096,
    "torch_dtype": "bfloat16",
}


_LLASA_3B_CARD_DATA = _make_card_data(
    license="cc-by-nc-4.0",
    pipeline_tag="text-to-speech",
    language=["en", "zh"],
    library_name="transformers",
)


def _patch_llasa_3b() -> Any:
    return _patch_hf_calls(
        config=_LLASA_3B_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_LLASA_3B_CARD_DATA,
        hub_info={"author": "HKUSTAudio", "sha": "deadf00d"},
    )


_VOXTRAL_MINI_CONFIG: dict[str, Any] = {
    "model_type": "voxtral_realtime",
    "architectures": ["VoxtralRealtimeForConditionalGeneration"],
    "vocab_size": 131072,
    "hidden_size": 3072,
    "num_hidden_layers": 26,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
    "audio_config": {"audio_length_per_tok": 8},
    "projector_hidden_act": "gelu",
}


_VOXTRAL_MINI_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="automatic-speech-recognition",
    language=[
        "en",
        "fr",
        "es",
        "de",
        "ru",
        "zh",
        "ja",
        "it",
        "pt",
        "nl",
        "ar",
        "hi",
        "ko",
    ],
    library_name="vllm",
    base_model="mistralai/Ministral-3-3B-Base-2512",
)


def _patch_voxtral_mini() -> Any:
    return _patch_hf_calls(
        config=_VOXTRAL_MINI_CONFIG,
        tokenizer_config=None,
        card_data=_VOXTRAL_MINI_CARD_DATA,
        hub_info={
            "author": "mistralai",
            "sha": "deadf00d",
            "tags": ["base_model:finetune:mistralai/Ministral-3-3B-Base-2512"],
        },
    )


_FIRERED_VAD_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="voice-activity-detection",
    language=None,
    library_name=None,
)


def _patch_firered_vad() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_FIRERED_VAD_CARD_DATA,
        hub_info={"author": "FireRedTeam", "sha": "deadf00d"},
    )


__all__ = [
    "_FIRERED_VAD_CARD_DATA",
    "_KOKORO_CARD_DATA",
    "_KOKORO_CONFIG",
    "_LLASA_3B_CARD_DATA",
    "_LLASA_3B_CONFIG",
    "_VOXTRAL_MINI_CARD_DATA",
    "_VOXTRAL_MINI_CONFIG",
    "_WAV2VEC2_JP_CARD_DATA",
    "_WAV2VEC2_JP_CONFIG",
    "_WAV2VEC2_JP_MODEL_INDEX",
    "_WHISPER_CARD_DATA",
    "_WHISPER_CONFIG",
    "_WHISPER_LANGUAGES",
    "_patch_firered_vad",
    "_patch_granite_speech",
    "_patch_indic_conformer",
    "_patch_ipa_whisper",
    "_patch_kokoro",
    "_patch_llasa_3b",
    "_patch_mimo_asr_gguf",
    "_patch_omnivoice",
    "_patch_omnivoice_bf16",
    "_patch_pyannote_diar",
    "_patch_seamless_m4t",
    "_patch_vibevoice_asr",
    "_patch_voxtral_mini",
    "_patch_wav2vec2_id_jv_su",
    "_patch_wav2vec2_jp",
    "_patch_whisper",
]
