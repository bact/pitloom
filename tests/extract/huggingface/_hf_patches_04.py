# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mock patches for Hugging Face model metadata tests (part 4 of 10).

See also: conftest.py, which re-exports everything via ``from
._hf_patches_04 import *``. Sibling test modules import helper names
from ``conftest``, not from this module directly.
"""

from __future__ import annotations

from typing import Any

from ._hf_patches_01 import _make_card_data, _patch_hf_calls


def _patch_gpt_neox_jp() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "gpt_neox_japanese",
            "architectures": ["GPTNeoXJapaneseForCausalLM"],
            "vocab_size": 32000,
            "num_hidden_layers": 32,
            "hidden_size": 2560,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="text-generation",
            tags=["ja", "japanese", "gpt_neox", "gpt", "lm", "nlp"],
            language="ja",  # scalar string
            datasets=["cc100", "wikipedia"],
        ),
        hub_info={"author": "abeja"},
    )


def _patch_falconsai() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "t5",
            "architectures": ["T5ForConditionalGeneration"],
            "vocab_size": 32128,
        },
        tokenizer_config={"tokenizer_class": "T5Tokenizer", "model_max_length": 512},
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="summarization",
            tags=["medical"],
            language=["en"],
        ),
        hub_info={"author": "Falconsai"},
    )


def _patch_opus_mt_th_en() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "marian",
            "architectures": ["MarianMTModel"],
            "vocab_size": 62307,
            "num_hidden_layers": 6,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag=None,
            tags=["translation"],
            language=["th", "en"],
        ),
        hub_info={"author": "Helsinki-NLP"},
    )


def _patch_hunyuan_mt() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "hunyuan_v1_dense",
            "architectures": ["HunYuanDenseV1ForCausalLM"],
            "vocab_size": 120818,
            "num_hidden_layers": 32,
            "hidden_size": 2048,
        },
        tokenizer_config={
            "tokenizer_class": "PreTrainedTokenizerFast",
            "model_max_length": 1000000000000000019884624838656,
        },
        card_data=_make_card_data(
            license=None,
            pipeline_tag=None,
            tags=["translation"],
            language=["zh", "en", "fr", "pt", "es", "ja", "tr"],
        ),
        hub_info={"author": "tencent"},
    )


def _patch_hy_mt_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag="translation",
            tags=["hy-mt", "quant", "2bit"],
            language=["multilingual"],  # keyword, not ISO code
            base_model="AngelSlim/Hy-MT1.5-1.8B-2bit",
        ),
        hub_info={
            "author": "tencent",
            "tags": [
                "base_model:AngelSlim/Hy-MT1.5-1.8B-2bit",
                "base_model:quantized:AngelSlim/Hy-MT1.5-1.8B-2bit",
            ],
        },
    )


def _patch_hunyuan_mt7b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "hunyuan_v1_dense",
            "architectures": ["HunYuanDenseV1ForCausalLM"],
            "vocab_size": 128256,
            "num_hidden_layers": 32,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag=None,
            tags=["translation"],
            library_name="transformers",
        ),
        hub_info={"author": "tencent"},
    )


def _patch_ii_medical() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "qwen3",
            "architectures": ["Qwen3ForCausalLM"],
            "vocab_size": 151936,
            "num_hidden_layers": 36,
            "hidden_size": 4096,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag=None,
            tags=[],
        ),
        hub_info={"author": "Intelligent-Internet"},
    )


def _patch_vilt_vqa() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "vilt",
            "architectures": ["ViltForVisualQuestionAnswering"],
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="visual-question-answering",
            tags=["vilt", "visual-question-answering"],
            base_model=["dandelin/vilt-b32"],
        ),
        hub_info={
            "author": "dandelin",
            "tags": [
                "arxiv:2102.03334",
                "base_model:dandelin/vilt-b32",
                "base_model:finetune:dandelin/vilt-b32",
            ],
        },
    )


def _patch_deplot() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "pix2struct",
            "architectures": ["Pix2StructForConditionalGeneration"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="visual-question-answering",
            tags=["pix2struct", "image-text-to-text"],
            language=["en", "fr", "de", "es", "pt"],
        ),
        hub_info={
            "author": "google",
            "tags": ["arxiv:2212.10505"],
        },
    )


def _patch_blip_vqa() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "blip",
            "architectures": ["BlipForQuestionAnswering"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="bsd-3-clause",
            pipeline_tag="visual-question-answering",
            tags=["blip"],
            language=["en"],
        ),
        hub_info={
            "author": "Salesforce",
            "tags": ["arxiv:2201.12086"],
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


def _patch_granite_4_1_8b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "granite",
            "architectures": ["GraniteForCausalLM"],
            "vocab_size": 49152,
            "num_hidden_layers": 40,
            "hidden_size": 4096,
            "num_attention_heads": 32,
            "num_key_value_heads": 8,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["granite", "conversational"],
            language=[
                "en",
                "de",
                "es",
                "fr",
                "ja",
                "pt",
                "ar",
                "cs",
                "it",
                "ko",
                "nl",
                "zh",
            ],
            base_model=["ibm-granite/granite-4.1-8b-base"],
        ),
        hub_info={
            "author": "ibm-granite",
            "tags": [
                "base_model:ibm-granite/granite-4.1-8b-base",
                "base_model:finetune:ibm-granite/granite-4.1-8b-base",
            ],
        },
    )


__all__ = [
    "_patch_blip_vqa",
    "_patch_deplot",
    "_patch_falconsai",
    "_patch_gpt_neox_jp",
    "_patch_granite_4_1_8b",
    "_patch_granite_speech",
    "_patch_hunyuan_mt",
    "_patch_hunyuan_mt7b",
    "_patch_hy_mt_gguf",
    "_patch_ii_medical",
    "_patch_indic_conformer",
    "_patch_ipa_whisper",
    "_patch_mimo_asr_gguf",
    "_patch_omnivoice",
    "_patch_omnivoice_bf16",
    "_patch_opus_mt_th_en",
    "_patch_pyannote_diar",
    "_patch_seamless_m4t",
    "_patch_vibevoice_asr",
    "_patch_vilt_vqa",
    "_patch_wav2vec2_id_jv_su",
]
