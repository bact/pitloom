from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

"""Tests for the Hugging Face model metadata extractor."""


def _make_card_data(
    license: str | None = "apache-2.0",
    pipeline_tag: str | None = "text-generation",
    tags: list[str] | None = None,
    language: Any = None,  # str scalar or list[str]
    datasets: list[str] | None = None,
    library_name: str | None = None,
    license_name: str | None = None,
    model_index: list[Any] | None = None,
    base_model: Any = None,  # str or list[str]
) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if license is not None:
        data["license"] = license
    if pipeline_tag is not None:
        data["pipeline_tag"] = pipeline_tag
    if tags is not None:
        data["tags"] = tags
    if language is not None:
        data["language"] = language
    if datasets is not None:
        data["datasets"] = datasets
    if library_name is not None:
        data["library_name"] = library_name
    if license_name is not None:
        data["license_name"] = license_name
    if model_index is not None:
        data["model-index"] = model_index
    if base_model is not None:
        data["base_model"] = base_model
    return data


_MISTRAL_CONFIG: dict[str, Any] = {
    "model_type": "mistral",
    "architectures": ["MistralForCausalLM"],
    "vocab_size": 32000,
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "num_attention_heads": 32,
    "torch_dtype": "bfloat16",
}

_MISTRAL_TOKENIZER_CONFIG: dict[str, Any] = {
    "tokenizer_class": "LlamaTokenizer",
    "model_max_length": 32768,
}

_MISTRAL_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    tags=["pretrained"],
    language=["en"],
    library_name="transformers",
)

_OPENTHAIGPT_CONFIG: dict[str, Any] = {
    "model_type": "qwen2",
    "architectures": ["Qwen2ForCausalLM"],
    "vocab_size": 152064,
    "hidden_size": 5120,
    "num_hidden_layers": 64,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_OPENTHAIGPT_CARD_DATA = _make_card_data(
    license="other",
    license_name="qwen",
    pipeline_tag="text-generation",
    tags=["openthaigpt", "qwen", "reasoning"],
    language=["th", "en"],
    library_name="transformers",
    model_index=[
        {
            "name": "openthaigpt-r1-32b-instruct",
            "results": [{"task": {"type": "reasoning"}, "dataset": {"name": "custom"}}],
        }
    ],
)


def _patch_hf_calls(  # pylint: disable=dangerous-default-value
    config: dict[str, Any] | None = _MISTRAL_CONFIG,
    tokenizer_config: dict[str, Any] | None = _MISTRAL_TOKENIZER_CONFIG,
    generation_config: dict[str, Any] | None = None,
    card_text: str | None = "---\nlicense: apache-2.0\n---\n\nA great model.",
    card_data: dict[str, Any] | None = None,
    hub_info: dict[str, Any] | None = None,
) -> Any:
    """Return a context manager that patches all HF I/O helpers."""

    def _json_side_effect(
        model_id: str, filename: str, revision: str | None = None
    ) -> dict[str, Any] | None:
        _ = model_id
        _ = revision
        if filename == "config.json":
            return config
        if filename == "tokenizer_config.json":
            return tokenizer_config
        if filename == "generation_config.json":
            return generation_config
        return None

    return patch.multiple(
        "pitloom.extract._huggingface",
        _safe_load_json=MagicMock(side_effect=_json_side_effect),
        _load_model_card=MagicMock(
            return_value=(
                card_text,
                _MISTRAL_CARD_DATA if card_data is None else card_data,
            )
        ),
        _load_model_info=MagicMock(
            return_value=hub_info
            or {
                "author": "mistralai",
                "sha": "deadbeef",
                "created_at": "2023-09-20T13:03:50+00:00",
            }
        ),
        # Prevent real network calls for license file detection in tests.
        # Override per-test via an extra patch when file detection is under test.
        _detect_license_from_hf_files=MagicMock(return_value=(None, None)),
    )


def _patch_openthaigpt() -> Any:
    return _patch_hf_calls(
        config=_OPENTHAIGPT_CONFIG,
        tokenizer_config={
            "tokenizer_class": "Qwen2Tokenizer",
            "model_max_length": 131072,
        },
        card_data=_OPENTHAIGPT_CARD_DATA,
        card_text=(
            "---\nlicense: other\n---\n\nA Thai-English bilingual reasoning model."
        ),
        hub_info={"author": "openthaigpt", "sha": "cafebabe"},
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

_KOKORO_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-to-speech",
    tags=None,
    language=["en"],
    library_name=None,
)


def _patch_kokoro() -> Any:
    return _patch_hf_calls(
        config=_KOKORO_CONFIG,
        tokenizer_config=None,
        card_data=_KOKORO_CARD_DATA,
        card_text="---\nlicense: apache-2.0\n---\n\nA small TTS model.",
        hub_info={"author": "hexgrad"},
    )


_STARCODER2_CONFIG: dict[str, Any] = {
    "model_type": "starcoder2",
    "architectures": ["Starcoder2ForCausalLM"],
    "hidden_size": 3072,
    "num_hidden_layers": 30,
    "num_attention_heads": 24,
    "vocab_size": 49152,
    "torch_dtype": "float32",
}

_STARCODER2_CARD_DATA = _make_card_data(
    license="bigcode-openrail-m",
    pipeline_tag="text-generation",
    tags=["code"],
    language=None,
    datasets=["bigcode/the-stack-v2-train"],
    library_name="transformers",
)


def _patch_starcoder2() -> Any:
    return _patch_hf_calls(
        config=_STARCODER2_CONFIG,
        card_data=_STARCODER2_CARD_DATA,
        hub_info={"author": "bigcode"},
    )


_WHISPER_CONFIG: dict[str, Any] = {
    "model_type": "whisper",
    "architectures": ["WhisperForConditionalGeneration"],
    "vocab_size": 51865,
    "num_hidden_layers": 32,
    "max_source_positions": 1500,
}

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


def _patch_whisper() -> Any:
    return _patch_hf_calls(
        config=_WHISPER_CONFIG,
        tokenizer_config=None,
        card_data=_WHISPER_CARD_DATA,
        hub_info={"author": "openai"},
    )


_KIMI_CONFIG: dict[str, Any] = {
    "model_type": "kimi_k25",
    "architectures": ["KimiK25ForConditionalGeneration"],
    "hidden_size": 7168,
    "num_hidden_layers": 61,
    "torch_dtype": "bfloat16",
}

_KIMI_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    tags=["compressed-tensors"],
    language=None,
    library_name="transformers",
)


def _patch_kimi() -> Any:
    return _patch_hf_calls(
        config=_KIMI_CONFIG,
        card_data=_KIMI_CARD_DATA,
        hub_info={"author": "moonshotai"},
    )


_GEMMA_CARD_DATA = _make_card_data(
    license="gemma",  # Non-standard but passes SPDX License ID regex -> not vague
    pipeline_tag=None,
    tags=None,
    language=None,
    library_name="transformers",
)


def _patch_gemma() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated - config.json inaccessible
        tokenizer_config=None,
        card_data=_GEMMA_CARD_DATA,
        hub_info={"author": "google"},
    )


_LLAMA_CARD_DATA = _make_card_data(
    license="llama3.2",  # Custom Meta license - not vague, not standard SPDX
    pipeline_tag="text-generation",
    tags=["facebook", "meta", "pytorch", "llama", "llama-3"],
    language=["en", "de", "fr", "it", "pt", "hi", "es", "th"],
    library_name="transformers",
)


def _patch_llama() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated - config.json inaccessible
        tokenizer_config=None,
        card_data=_LLAMA_CARD_DATA,
        hub_info={"author": "meta-llama"},
    )


_DEEPSEEK_CONFIG: dict[str, Any] = {
    "model_type": "deepseek_v3",
    "architectures": ["DeepseekV3ForCausalLM"],
    "hidden_size": 7168,
    "num_hidden_layers": 61,
    "num_attention_heads": 128,
    "vocab_size": 129280,
    "torch_dtype": "bfloat16",
}

_DEEPSEEK_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag=None,  # No pipeline_tag set
    tags=None,
    language=None,
    library_name="transformers",
)


def _patch_deepseek() -> Any:
    return _patch_hf_calls(
        config=_DEEPSEEK_CONFIG,
        card_data=_DEEPSEEK_CARD_DATA,
        hub_info={"author": "deepseek-ai"},
    )


_SEALION_CARD_DATA = _make_card_data(
    license="gemma",
    pipeline_tag="image-text-to-text",
    tags=None,
    language=["en", "zh", "vi", "id", "th", "fil", "ta", "ms", "my"],
    library_name=None,
)


def _patch_sealion_gguf() -> Any:
    return _patch_hf_calls(
        config=None,  # No config.json in GGUF-only repo
        tokenizer_config=None,
        card_data=_SEALION_CARD_DATA,
        hub_info={"author": "aisingapore"},
    )


_SEALLMS_CONFIG: dict[str, Any] = {
    "model_type": "qwen2",
    "architectures": ["Qwen2ForCausalLM"],
    "hidden_size": 3584,
    "num_hidden_layers": 28,
    "num_attention_heads": 28,
    "vocab_size": 152064,
    "torch_dtype": "bfloat16",
}

_SEALLMS_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag=None,
    tags=["sea", "multilingual"],
    language=["en", "zh", "id", "vi", "th", "ms", "tl", "ta", "jv", "lo", "km", "my"],
    library_name=None,
)


def _patch_seallms() -> Any:
    return _patch_hf_calls(
        config=_SEALLMS_CONFIG,
        card_data=_SEALLMS_CARD_DATA,
        hub_info={"author": "SeaLLMs"},
    )


_TYPHOON_CONFIG: dict[str, Any] = {
    "model_type": "mistral",
    "architectures": ["MistralForCausalLM"],
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "vocab_size": 32768,
    "torch_dtype": "bfloat16",
}

_TYPHOON_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    tags=["pretrained"],
    language=["th"],
    library_name="transformers",
)


def _patch_typhoon() -> Any:
    return _patch_hf_calls(
        config=_TYPHOON_CONFIG,
        card_data=_TYPHOON_CARD_DATA,
        hub_info={"author": "typhoon-ai"},
    )


_SERENGETI_CONFIG: dict[str, Any] = {
    "architectures": ["ElectraModel"],
    "model_type": "electra",
    "hidden_size": 768,
    "num_hidden_layers": 12,
    "num_attention_heads": 12,
    "intermediate_size": 3072,
    "max_position_embeddings": 512,
    "vocab_size": 250000,
    "torch_dtype": "float32",
}

_SERENGETI_TOKENIZER_CONFIG: dict[str, Any] = {
    "tokenizer_class": "ElectraTokenizer",
    "model_max_length": 1000000000000000019884624838656,
    "do_lower_case": True,
}


def _patch_serengeti() -> Any:
    return _patch_hf_calls(
        config=_SERENGETI_CONFIG,
        tokenizer_config=_SERENGETI_TOKENIZER_CONFIG,
        card_data={},  # No model card - ModelCard.load() fails
        hub_info={"author": "UBC-NLP", "downloads": 46},
    )


def _patch_aya_vision() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated - config.json returns 401
        tokenizer_config=None,  # Gated
        card_data={},  # Gated - ModelCard.load() returns error
        hub_info={"author": "CohereLabs"},
        # _detect_license_from_hf_files also returns (None, None) because
        # list_repo_files may succeed but license file downloads are gated.
    )


def _patch_inkubalm() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated - config.json returns 401
        tokenizer_config=None,  # Gated
        card_data={},  # Gated - ModelCard.load() returns error
        hub_info={
            "author": "lelapa",
            # model_info.tags carry the dataset link even when the card is gated.
            "tags": [
                "text-generation",
                "license:cc-by-nc-4.0",
                "dataset:lelapa/Inkuba-Mono",
                "en",
                "sw",
                "zu",
                "xh",
                "ha",
                "yo",
            ],
        },
    )


_NLLB_CONFIG: dict[str, Any] = {
    "model_type": "m2m_100",
    "architectures": ["M2M100ForConditionalGeneration"],
    "d_model": 1024,  # encoder/decoder hidden dim - NOT in _HYPER_KEYS
    "encoder_layers": 12,  # NOT in _HYPER_KEYS (uses num_hidden_layers alias)
    "decoder_layers": 12,  # NOT in _HYPER_KEYS
    "num_hidden_layers": 12,  # present in config alongside encoder/decoder_layers
    "encoder_attention_heads": 16,  # NOT in _HYPER_KEYS
    "decoder_attention_heads": 16,  # NOT in _HYPER_KEYS
    "max_position_embeddings": 1024,
    "vocab_size": 256206,
    "torch_dtype": "float32",
    "is_encoder_decoder": True,
}

_NLLB_TOKENIZER_CONFIG: dict[str, Any] = {
    "tokenizer_class": "NllbTokenizer",
    "model_max_length": 1024,  # Real limit - NOT the unlimited sentinel
}


def _patch_nllb() -> Any:
    return _patch_hf_calls(
        config=_NLLB_CONFIG,
        tokenizer_config=_NLLB_TOKENIZER_CONFIG,
        card_data={},  # No model card - ModelCard.load() fails
        hub_info={"author": "facebook"},
    )


_SONOISA_CONFIG: dict[str, Any] = {
    "architectures": ["BertForMaskedLM"],
    "vocab_size": 32000,
    "num_hidden_layers": 12,
    "num_attention_heads": 12,
    "hidden_size": 768,
}

_SONOISA_CARD_DATA = _make_card_data(
    license="cc-by-sa-4.0",
    pipeline_tag="feature-extraction",
    tags=["sentence-transformers", "sentence-bert", "sentence-similarity"],
    language="ja",  # scalar string - triggers the fix
)


def _patch_sonoisa() -> Any:
    return _patch_hf_calls(
        config=_SONOISA_CONFIG,
        card_data=_SONOISA_CARD_DATA,
        hub_info={"author": "sonoisa"},
    )


_WAV2VEC2_JP_CONFIG: dict[str, Any] = {
    "model_type": "wav2vec2",
    "architectures": ["Wav2Vec2ForCTC"],
    "vocab_size": 2341,
    "num_hidden_layers": 24,
    "hidden_size": 1024,
}

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


_WANGCHANX_LEGAL_CONFIG: dict[str, Any] = {
    "model_type": "xlm-roberta",
    "architectures": ["XLMRobertaModel"],
    "vocab_size": 250002,
    "num_hidden_layers": 24,
    "hidden_size": 1024,
}

_WANGCHANX_LEGAL_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="sentence-similarity",
    tags=["legal", "RAG"],
    language=["th"],
    datasets=["airesearch/WangchanX-Legal-ThaiCCL-RAG"],
    base_model=["BAAI/bge-m3"],
)


def _patch_wangchanx_legal() -> Any:
    return _patch_hf_calls(
        config=_WANGCHANX_LEGAL_CONFIG,
        card_data=_WANGCHANX_LEGAL_CARD_DATA,
        hub_info={
            "author": "airesearch",
            "tags": ["base_model:BAAI/bge-m3", "base_model:finetune:BAAI/bge-m3"],
        },
    )


_CHINDA_CONFIG: dict[str, Any] = {
    "model_type": "qwen3",
    "architectures": ["Qwen3ForCausalLM"],
    "vocab_size": 151936,
    "num_hidden_layers": 36,
    "hidden_size": 2560,
}

_CHINDA_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    tags=["thai", "conversational"],
    language=["th", "en"],
    base_model=["Qwen/Qwen3-4B"],
)


def _patch_chinda() -> Any:
    return _patch_hf_calls(
        config=_CHINDA_CONFIG,
        card_data=_CHINDA_CARD_DATA,
        hub_info={
            "author": "iapp",
            "tags": [
                "base_model:Qwen/Qwen3-4B",
                "base_model:finetune:Qwen/Qwen3-4B",
                "doi:10.57967/hf/5709",
            ],
        },
    )


_CHINDA_GGUF_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    tags=["thai"],
    language=["th", "en"],
    base_model="iapp/chinda-qwen3-4b",  # string, not list
)


def _patch_chinda_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_CHINDA_GGUF_CARD_DATA,
        hub_info={
            "author": "iapp",
            "tags": [
                "base_model:iapp/chinda-qwen3-4b",
                "base_model:quantized:iapp/chinda-qwen3-4b",
            ],
        },
    )


_RURI_CONFIG: dict[str, Any] = {
    "model_type": "modernbert",
    "architectures": ["ModernBertModel"],
    "vocab_size": 102400,
    "num_hidden_layers": 25,
    "hidden_size": 768,
}

_RURI_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="sentence-similarity",
    tags=["sentence-similarity", "feature-extraction"],
    language=["ja"],
    datasets=["cl-nagoya/ruri-v3-dataset-ft"],
    base_model="cl-nagoya/ruri-v3-pt-310m",
)


def _patch_ruri() -> Any:
    return _patch_hf_calls(
        config=_RURI_CONFIG,
        card_data=_RURI_CARD_DATA,
        hub_info={
            "author": "cl-nagoya",
            "tags": [
                "arxiv:2409.07737",
                "base_model:cl-nagoya/ruri-v3-pt-310m",
                "base_model:finetune:cl-nagoya/ruri-v3-pt-310m",
            ],
        },
    )


_NOMIC_GGUF_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="sentence-similarity",
    tags=["feature-extraction", "sentence-similarity"],
    language=["en"],
    base_model="nomic-ai/nomic-embed-text-v1.5",
)


def _patch_nomic_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_NOMIC_GGUF_CARD_DATA,
        hub_info={
            "author": "nomic-ai",
            "tags": [
                "base_model:nomic-ai/nomic-embed-text-v1.5",
                "base_model:quantized:nomic-ai/nomic-embed-text-v1.5",
            ],
        },
    )


_VNTL_CARD_DATA = _make_card_data(
    license="llama3",
    pipeline_tag="translation",
    language=["ja", "en"],
    datasets=["lmg-anon/VNTL-v5-1k"],
    base_model="rinna/llama-3-youko-8b",
)


def _patch_vntl() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_VNTL_CARD_DATA,
        hub_info={
            "author": "lmg-anon",
            "tags": [
                "base_model:rinna/llama-3-youko-8b",
                "base_model:quantized:rinna/llama-3-youko-8b",
            ],
        },
    )


_SUGOI_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="translation",
    tags=["translation", "gguf"],
    language=["ja", "en"],
    base_model=["sugoitoolkit/Sugoi-14B-Ultra-HF"],
)


def _patch_sugoi() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_SUGOI_CARD_DATA,
        hub_info={
            "author": "sugoitoolkit",
            "tags": [
                "base_model:sugoitoolkit/Sugoi-14B-Ultra-HF",
                "base_model:quantized:sugoitoolkit/Sugoi-14B-Ultra-HF",
            ],
        },
    )


_TALKIE_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag=None,
    language=["en"],
    base_model=["talkie-lm/talkie-1930-13b-base"],
)


def _patch_talkie() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_TALKIE_CARD_DATA,
        hub_info={
            "author": "talkie-lm",
            "tags": [
                "base_model:talkie-lm/talkie-1930-13b-base",
                "base_model:finetune:talkie-lm/talkie-1930-13b-base",
            ],
        },
    )


def _patch_depth_pro() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "depth_pro",
            "architectures": ["DepthProForDepthEstimation"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apple-amlr",
            pipeline_tag="depth-estimation",
            tags=["vision", "depth-estimation"],
        ),
        hub_info={"author": "apple"},
    )


def _patch_marigold() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="depth-estimation",
            tags=["depth estimation", "image analysis", "computer vision", "zero-shot"],
            language=["en"],
            library_name="diffusers",
        ),
        hub_info={"author": "prs-eth"},
    )


def _patch_vitpose() -> Any:
    return _patch_hf_calls(
        config={"model_type": "vitpose", "architectures": ["VitPoseForPoseEstimation"]},
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="keypoint-detection",
            tags=[],
        ),
        hub_info={"author": "usyd-community"},
    )


def _patch_jina_v4() -> Any:
    return _patch_hf_calls(
        config={"architectures": ["JinaEmbeddingsV4Model"], "num_hidden_layers": 36},
        tokenizer_config={
            "tokenizer_class": "Qwen2Tokenizer",
            "model_max_length": 131072,
        },
        card_data=_make_card_data(
            license=None,
            pipeline_tag="visual-document-retrieval",
            tags=[
                "feature-extraction",
                "sentence-similarity",
                "colpali",
                "multimodal-embedding",
            ],
            language=["multilingual"],
        ),
        hub_info={"author": "jinaai"},
    )


def _patch_llava_video() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "llava_next_video",
            "architectures": ["LlavaNextVideoForConditionalGeneration"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="llama2",
            pipeline_tag="video-text-to-text",
            tags=["image-text-to-text"],  # also appears as tag
            language=["en"],
            datasets=["lmms-lab/VideoChatGPT"],
        ),
        hub_info={"author": "llava-hf"},
    )


def _patch_donut() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "vision-encoder-decoder",
            "architectures": ["VisionEncoderDecoderModel"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="document-question-answering",
            tags=["donut", "image-to-text", "vision"],
        ),
        hub_info={"author": "naver-clova-ix"},
    )


def _patch_layoutlm() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "layoutlm",
            "architectures": ["LayoutLMForQuestionAnswering"],
            "vocab_size": 50265,
            "num_hidden_layers": 12,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="document-question-answering",
            tags=["layoutlm", "document-question-answering", "pdf"],
            language="en",  # scalar string
        ),
        hub_info={"author": "impira"},
    )


def _patch_tapas() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "tapas",
            "architectures": ["TapasForQuestionAnswering"],
            "vocab_size": 30522,
            "num_hidden_layers": 24,
            "hidden_size": 1024,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="table-question-answering",
            tags=["tapas", "table-question-answering"],
            language="en",  # scalar string
            datasets=["wikitablequestions"],
        ),
        hub_info={"author": "google"},
    )


def _patch_rmbg14() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "SegformerForSemanticSegmentation",
            "architectures": ["BriaRMBG"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="image-segmentation",
            tags=[
                "remove background",
                "background-removal",
                "vision",
                "legal liability",
            ],
        ),
        hub_info={"author": "briaai"},
    )


def _patch_rmbg20() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated - config.json returns 401
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="image-segmentation",
            tags=["remove background", "background-removal", "vision"],
        ),
        hub_info={"author": "briaai"},
    )


def _patch_fibo_edit() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="image-to-image",
            tags=["art", "background-removal", "image-segmentation"],
            library_name="diffusers",
            base_model=["briaai/Fibo-Edit"],
        ),
        hub_info={
            "author": "briaai",
            "tags": [
                "arxiv:2511.06876",
                "base_model:briaai/Fibo-Edit",
                "base_model:finetune:briaai/Fibo-Edit",
            ],
        },
    )


def _patch_laion_clip() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="zero-shot-image-classification",
            tags=["clip"],
        ),
        hub_info={"author": "laion"},
    )


def _patch_streetclip() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "clip",
            "architectures": ["CLIPModel"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="cc-by-nc-4.0",
            pipeline_tag="zero-shot-image-classification",
            tags=[
                "geolocalization",
                "geolocation",
                "geographic",
                "clip",
                "multi-modal",
            ],
            language=["en"],
        ),
        hub_info={"author": "geolocal"},
    )


def _patch_swin() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "swin",
            "architectures": ["SwinForImageClassification"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag=None,  # card has no pipeline_tag
            tags=["vision", "image-classification"],
            datasets=["imagenet-1k"],
        ),
        hub_info={
            "author": "microsoft",
            "tags": ["dataset:imagenet-1k", "image-classification"],
        },
    )


def _patch_resnet18() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "resnet",
            "architectures": ["ResNetForImageClassification"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag=None,
            tags=["vision", "image-classification"],
            datasets=["imagenet-1k"],
        ),
        hub_info={"author": "microsoft"},
    )


def _patch_dinov2() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "dinov2",
            "architectures": ["Dinov2Model"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="image-feature-extraction",
            tags=["dino", "vision"],
        ),
        hub_info={"author": "facebook"},
    )


def _patch_rad_dino() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "dinov2",
            "architectures": ["Dinov2Model"],
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag="image-feature-extraction",
            tags=[],
        ),
        hub_info={"author": "microsoft"},
    )


def _patch_uni2() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated
        tokenizer_config=None,
        card_data=_make_card_data(
            license="cc-by-nc-nd-4.0",
            pipeline_tag="image-feature-extraction",
            tags=["histology", "pathology", "vision", "self-supervised", "vit"],
            language=["en"],
        ),
        hub_info={"author": "MahmoodLab"},
    )


def _patch_timm_convnext() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="image-feature-extraction",
            tags=["timm", "transformers"],
            library_name="timm",
        ),
        hub_info={"author": "timm"},
    )


def _patch_groot() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "Gr00tN1d7",
            "architectures": ["Gr00tN1d7"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag="robotics",
            tags=["robotics"],
        ),
        hub_info={"author": "nvidia"},
    )


def _patch_openvla() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "openvla",
            "architectures": ["OpenVLAForActionPrediction"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="robotics",
            tags=["vla", "image-text-to-text", "multimodal", "pretraining"],
            language=["en"],
        ),
        hub_info={"author": "openvla"},
    )


def _patch_pi05() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="gemma",
            pipeline_tag="robotics",
            tags=["vision-language-action", "imitation-learning", "lerobot"],
            language=["en"],
            library_name="lerobot",
        ),
        hub_info={"author": "lerobot"},
    )


def _patch_nemotron() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "NemotronH_Nano_Omni_Reasoning_V3",
            "architectures": ["NemotronH_Nano_Omni_Reasoning_V3"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="any-to-any",
            tags=["nvidia", "pytorch", "multimodal"],
            library_name="transformers",
            datasets=["nvidia/Nemotron-Image-Training-v3"],
        ),
        hub_info={
            "author": "nvidia",
            "tags": ["dataset:nvidia/Nemotron-Image-Training-v3"],
        },
    )


def _patch_wangchanglm() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "xglm",
            "architectures": ["XGLMForCausalLM"],
            "vocab_size": 256008,
        },
        tokenizer_config={
            "tokenizer_class": "XGLMTokenizer",
            "model_max_length": 1000000000000000019884624838656,  # unlimited sentinel
        },
        card_data=_make_card_data(
            license="cc-by-sa-4.0",
            pipeline_tag="text-generation",
            tags=[],
            language=["en", "th", "ja", "vi"],
            datasets=[
                "laion/OIG",
                "Hello-SimpleAI/HC3",
                "databricks/databricks-dolly-15k",
            ],
        ),
        hub_info={"author": "pythainlp"},
    )


def _patch_sealion_vl() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "gemma3",
            "architectures": ["Gemma3ForConditionalGeneration"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="gemma",
            pipeline_tag="image-text-to-text",
            tags=["conversational"],
            language=["en", "zh", "vi", "id", "th", "fil", "ta", "ms", "my"],
            base_model=["google/gemma-3-4b-it"],
        ),
        hub_info={
            "author": "aisingapore",
            "tags": [
                "base_model:google/gemma-3-4b-it",
                "base_model:finetune:google/gemma-3-4b-it",
            ],
        },
    )


def _patch_mallam() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "mistral",
            "architectures": ["MistralForCausalLM"],
            "vocab_size": 32000,
            "num_hidden_layers": 22,
            "hidden_size": 2048,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag="text-generation",
            tags=[],
            language=["ms"],
        ),
        hub_info={"author": "mesolitica"},
    )


def _patch_llmjp() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "llama",
            "architectures": ["LlamaForCausalLM"],
            "vocab_size": 99584,
            "num_hidden_layers": 24,
            "hidden_size": 2048,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=[],
            language=["en", "ja"],
        ),
        hub_info={"author": "llm-jp"},
    )


def _patch_privacy_filter() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "openai_privacy_filter",
            "architectures": ["OpenAIPrivacyFilterForTokenClassification"],
            "vocab_size": 200064,
            "num_hidden_layers": 8,
            "hidden_size": 640,
        },
        tokenizer_config={
            "tokenizer_class": "TokenizersBackend",
            "model_max_length": 128000,
        },
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="token-classification",
            tags=["transformers.js"],
        ),
        hub_info={"author": "openai"},
    )


def _patch_mistral_medium() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "mistral3",
            "architectures": ["Mistral3ForConditionalGeneration"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag=None,
            tags=["vLLM"],
            language=[
                "en",
                "fr",
                "de",
                "es",
                "pt",
                "it",
                "ja",
                "ko",
                "ru",
                "zh",
                "ar",
                "fa",
                "id",
                "ms",
                "pl",
                "ro",
                "sv",
                "tr",
                "uk",
                "vi",
                "hi",
                "bn",
            ],
        ),
        hub_info={"author": "mistralai"},
    )


def _patch_laguna() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "laguna",
            "architectures": ["LagunaForCausalLM"],
            "vocab_size": 100352,
            "num_hidden_layers": 40,
            "hidden_size": 2048,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["laguna-xs.2", "vllm"],
            library_name="transformers",
        ),
        hub_info={"author": "poolside"},
    )


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


def _patch_granite_embed() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "modernbert",
            "architectures": ["ModernBertModel"],
            "vocab_size": 180000,
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="feature-extraction",
            tags=["granite", "embeddings", "multilingual", "mteb"],
            language=["multilingual"],
            library_name="sentence-transformers",
        ),
        hub_info={"author": "ibm-granite"},
    )


def _patch_granite_geo_flood() -> Any:
    return _patch_hf_calls(
        config=None,  # TerraTorch -- no standard transformers config.json
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="image-segmentation",
            tags=["geospatial", "flood-detection", "sentinel-2", "sentinel-1"],
            datasets=[
                "ai-for-good-lab/ai4g-flood-dataset",
                "blanchon/ETCI-2021-Flood-Detection",
            ],
            base_model=["ibm-granite/granite-geospatial-uki"],
            library_name="terratorch",
        ),
        hub_info={
            "author": "ibm-granite",
            "tags": [
                "base_model:ibm-granite/granite-geospatial-uki",
                "base_model:finetune:ibm-granite/granite-geospatial-uki",
            ],
        },
    )


def _patch_flood_image_detect() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "siglip",
            "architectures": ["SiglipForImageClassification"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="image-classification",
            tags=["siglip", "Flood-Detection", "climate"],
            language=["en"],
            base_model=["google/siglip2-base-patch16-512"],
        ),
        hub_info={
            "author": "prithivMLmods",
            "tags": [
                "arxiv:2502.14786",
                "base_model:google/siglip2-base-patch16-512",
                "base_model:finetune:google/siglip2-base-patch16-512",
            ],
        },
    )


def _patch_xlm_roberta_base() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "xlm-roberta",
            "architectures": ["XLMRobertaForMaskedLM"],
            "vocab_size": 250002,
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="fill-mask",
            tags=[],
            language=[
                "af",
                "am",
                "ar",
                "en",
                "fr",
                "de",
                "hi",
                "ja",
                "ko",
                "pt",
                "ru",
                "es",
                "sw",
                "th",
                "tr",
                "vi",
                "yo",
                "zh",
            ],
        ),
        hub_info={"author": "FacebookAI"},
    )


def _patch_distilbert_multilingual() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "distilbert",
            "architectures": ["DistilBertForMaskedLM"],
            "vocab_size": 119547,
            "num_hidden_layers": 6,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="fill-mask",
            tags=[],
            language=["multilingual"],
        ),
        hub_info={"author": "distilbert"},
    )


def _patch_gabert() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "bert",
            "architectures": ["BertForMaskedLM"],
            "vocab_size": 30000,
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag="fill-mask",
            tags=["bert"],
            language=["ga"],
        ),
        hub_info={"author": "DCU-NLP"},
    )


def _patch_crow_9b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "qwen3_5",
            "architectures": ["Qwen3_5ForCausalLM"],
            "vocab_size": 151936,
            "num_hidden_layers": 40,
            "hidden_size": 3584,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["agent", "conversational"],
            language=[
                "en",
                "zh",
                "fr",
                "de",
                "es",
                "pt",
                "it",
                "ja",
                "ko",
                "ru",
                "ar",
                "hi",
                "nl",
                "pl",
                "sv",
                "da",
                "no",
                "fi",
                "cs",
                "hu",
                "ro",
                "tr",
                "vi",
                "id",
                "th",
                "uk",
            ],
            base_model=["Qwen/Qwen3.5-9B-Base"],
        ),
        hub_info={
            "author": "Crownelius",
            "tags": [
                "base_model:Qwen/Qwen3.5-9B-Base",
                "base_model:merge:Qwen/Qwen3.5-9B-Base",
            ],
        },
    )


def _patch_qwen3_reap() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "qwen3_moe",
            "architectures": ["Qwen3MoeForCausalLM"],
            "num_hidden_layers": 94,
            "hidden_size": 4096,
            "num_experts": 384,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["mixture-of-experts", "code", "expert-merging"],
            base_model=["Qwen/Qwen3-Coder-Next"],
        ),
        hub_info={
            "author": "SamsungSAILMontreal",
            "tags": [
                "base_model:Qwen/Qwen3-Coder-Next",
                "base_model:merge:Qwen/Qwen3-Coder-Next",
            ],
        },
    )


def _patch_opt_2_7b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "opt",
            "architectures": ["OPTForCausalLM"],
            "vocab_size": 50272,
            "num_hidden_layers": 32,
            "hidden_size": 2560,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="text-generation",
            tags=[],
        ),
        hub_info={"author": "facebook"},
    )


def _patch_opt_iml() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "opt",
            "architectures": ["OPTForCausalLM"],
            "vocab_size": 50272,
            "num_hidden_layers": 24,
            "hidden_size": 2048,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="text-generation",
            tags=["opt"],
        ),
        hub_info={
            "author": "facebook",
            "tags": ["arxiv:2212.12017"],
        },
    )


def _patch_gpt_neo_2_7b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "gpt_neo",
            "architectures": ["GPTNeoForCausalLM"],
            "vocab_size": 50257,
            "num_hidden_layers": 32,
            "hidden_size": 2560,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=[],
            language=["en"],
        ),
        hub_info={"author": "EleutherAI"},
    )


def _patch_stablelm_zephyr() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "stablelm_epoch",
            "architectures": ["StableLMEpochForCausalLM"],
            "vocab_size": 100352,
            "num_hidden_layers": 24,
            "hidden_size": 2048,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["conversational"],
            language=[
                "en",
                "de",
                "es",
                "fr",
                "it",
                "nl",
                "pt",
                "pl",
                "ru",
                "zh",
                "ja",
                "ko",
            ],
        ),
        hub_info={"author": "stabilityai"},
    )


def _patch_tinyllama_chat() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "llama",
            "architectures": ["LlamaForCausalLM"],
            "vocab_size": 32000,
            "num_hidden_layers": 22,
            "hidden_size": 2048,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["conversational"],
            language=["en"],
        ),
        hub_info={"author": "TinyLlama"},
    )


def _patch_phi2() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "phi",
            "architectures": ["PhiForCausalLM"],
            "vocab_size": 51200,
            "num_hidden_layers": 32,
            "hidden_size": 2560,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="mit",
            pipeline_tag="text-generation",
            tags=["nlp", "code"],
            language=["en"],
        ),
        hub_info={"author": "microsoft"},
    )


def _patch_llama_3_2_3b() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated
        tokenizer_config=None,
        card_data=_make_card_data(
            license="llama3.2",
            pipeline_tag="text-generation",
            tags=[],
            language=["en", "de", "fr", "it", "pt", "hi", "es", "th"],
        ),
        hub_info={"author": "meta-llama"},
    )


def _patch_llama_3_2_3b_instruct() -> Any:
    return _patch_hf_calls(
        config=None,  # Gated
        tokenizer_config=None,
        card_data=_make_card_data(
            license="llama3.2",
            pipeline_tag="text-generation",
            tags=["conversational"],
            language=["en", "de", "fr", "it", "pt", "hi", "es", "th"],
            base_model=["meta-llama/Llama-3.2-3B"],
        ),
        hub_info={
            "author": "meta-llama",
            "tags": [
                "base_model:meta-llama/Llama-3.2-3B",
                "base_model:finetune:meta-llama/Llama-3.2-3B",
            ],
        },
    )


def _patch_hermes_3_llama_3b() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "llama",
            "architectures": ["LlamaForCausalLM"],
            "vocab_size": 128256,
            "num_hidden_layers": 28,
            "hidden_size": 3072,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="llama3",
            pipeline_tag="text-generation",
            tags=["chatml", "instruct", "function-calling"],
            language=["en"],
            base_model=["meta-llama/Llama-3.2-3B"],
        ),
        hub_info={
            "author": "NousResearch",
            "tags": [
                "base_model:meta-llama/Llama-3.2-3B",
                "base_model:finetune:meta-llama/Llama-3.2-3B",
            ],
        },
    )


def _patch_fineweb_edu() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "bert",
            "architectures": ["BertForSequenceClassification"],
            "vocab_size": 30522,
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-classification",
            tags=["BERT"],
            language=["en"],
            base_model=["Snowflake/snowflake-arctic-embed-m"],
        ),
        hub_info={
            "author": "HuggingFaceFW",
            "tags": [
                "base_model:Snowflake/snowflake-arctic-embed-m",
                "base_model:finetune:Snowflake/snowflake-arctic-embed-m",
            ],
        },
    )


def _patch_deberta_human_value() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "deberta_arg_classifier",
            "architectures": ["DebertaArgClassifier"],
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="openrail++",
            pipeline_tag="text-classification",
            tags=["custom_code", "human-values", "deberta"],
            language=["en"],
        ),
        hub_info={"author": "tum-nlp"},
    )


def _patch_aspect_finnlp_th() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "camembert",
            "architectures": ["CamembertForSequenceClassification"],
            "vocab_size": 25000,
            "num_hidden_layers": 12,
            "hidden_size": 768,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license=None,
            pipeline_tag="text-classification",
            tags=["generated_from_trainer"],
            language=["th"],
            base_model=["airesearch/wangchanberta-base-att-spm-uncased"],
        ),
        hub_info={
            "author": "nlp-chula",
            "tags": [
                "base_model:airesearch/wangchanberta-base-att-spm-uncased",
                "base_model:finetune:airesearch/wangchanberta-base-att-spm-uncased",
            ],
        },
    )


def _patch_darwin_kr_legal() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "qwen3_5",
            "architectures": ["Qwen3_5ForCausalLM"],
            "vocab_size": 151936,
            "num_hidden_layers": 64,
            "hidden_size": 5120,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-generation",
            tags=["korean", "legal", "conversational"],
            language=["ko", "en"],
            base_model=["FINAL-Bench/Darwin-28B-KR"],
        ),
        hub_info={
            "author": "FINAL-Bench",
            "tags": [
                "base_model:FINAL-Bench/Darwin-28B-KR",
                "base_model:finetune:FINAL-Bench/Darwin-28B-KR",
            ],
        },
    )


def _patch_protonx_legal() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "t5",
            "architectures": ["T5ForConditionalGeneration"],
            "vocab_size": 32128,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="other",
            pipeline_tag="text2text-generation",
            tags=["text-to-text", "t5"],
            language=["vi"],
            base_model=["vit5-base"],
        ),
        hub_info={
            "author": "protonx-models",
            "tags": [
                "base_model:vit5-base",
                "base_model:finetune:vit5-base",
            ],
        },
    )


def _patch_legal_embed_ita() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "qwen3",
            "architectures": ["Qwen3Model"],
            "vocab_size": 151936,
            "num_hidden_layers": 28,
            "hidden_size": 1024,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="cc-by-nc-4.0",
            pipeline_tag="sentence-similarity",
            tags=["qwen3", "feature-extraction", "legal"],
            language=["it"],
            base_model=["Qwen/Qwen3-Embedding-0.6B"],
        ),
        hub_info={
            "author": "ReDiX",
            "tags": [
                "base_model:Qwen/Qwen3-Embedding-0.6B",
                "base_model:finetune:Qwen/Qwen3-Embedding-0.6B",
            ],
        },
    )


def _patch_arabic_legal_ocr() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "gemma3",
            "architectures": ["Gemma3ForConditionalGeneration"],
            "vocab_size": 262208,
            "num_hidden_layers": 34,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="gemma",
            pipeline_tag="image-text-to-text",
            tags=["ocr", "arabic", "vision", "lora"],
            language=["ar", "en"],
            base_model=["google/gemma-3-4b-it"],
        ),
        hub_info={
            "author": "bakrianoo",
            "tags": [
                "base_model:google/gemma-3-4b-it",
                "base_model:finetune:google/gemma-3-4b-it",
            ],
        },
    )


def _patch_qwen3_swallow() -> Any:
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
            pipeline_tag="text-generation",
            tags=["conversational"],
            language=["en", "ja"],
            base_model=["tokyotech-llm/Qwen3-Swallow-8B-CPT-v0.2"],
        ),
        hub_info={
            "author": "tokyotech-llm",
            "tags": [
                "base_model:tokyotech-llm/Qwen3-Swallow-8B-CPT-v0.2",
                "base_model:finetune:tokyotech-llm/Qwen3-Swallow-8B-CPT-v0.2",
            ],
        },
    )


def _patch_sealion_27b_it() -> Any:
    return _patch_hf_calls(
        config={
            "model_type": "gemma3",
            "architectures": ["Gemma3ForCausalLM"],
            "vocab_size": 262208,
            "num_hidden_layers": 62,
        },
        tokenizer_config=None,
        card_data=_make_card_data(
            license="gemma",
            pipeline_tag="text-generation",
            tags=["conversational", "image-text-to-text"],
            language=["my", "en", "id", "km", "lo", "ms", "zh", "tl", "ta", "th", "vi"],
            base_model=["google/gemma-3-27b-it"],
        ),
        hub_info={
            "author": "aisingapore",
            "tags": [
                "base_model:google/gemma-3-27b-it",
                "base_model:finetune:google/gemma-3-27b-it",
            ],
        },
    )


def _patch_boba_food_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="image-text-to-text",
            tags=["food", "nutrition", "vision", "on-device"],
            language=["en"],
            base_model=["Qwen/Qwen3.5-0.8B"],
        ),
        hub_info={
            "author": "Doses-AI",
            "tags": [
                "base_model:Qwen/Qwen3.5-0.8B",
                "base_model:finetune:Qwen/Qwen3.5-0.8B",
            ],
        },
    )


def _patch_ernie_image_turbo() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_make_card_data(
            license="apache-2.0",
            pipeline_tag="text-to-image",
            tags=["diffusion", "distilled"],
            language=["en", "zh"],
            library_name="diffusers",
        ),
        hub_info={"author": "baidu"},
    )


_QWEN3_235B_CONFIG: dict[str, Any] = {
    "model_type": "qwen3_moe",
    "architectures": ["Qwen3MoeForCausalLM"],
    "vocab_size": 152064,
    "hidden_size": 7168,
    "num_hidden_layers": 94,
    "num_attention_heads": 64,
    "num_key_value_heads": 4,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_QWEN3_235B_GENERATION_CONFIG: dict[str, Any] = {
    "temperature": 0.6,
    "top_p": 0.95,
}

_QWEN3_235B_CARD_DATA = _make_card_data(
    license="qwen",
    pipeline_tag="text-generation",
    language=["multilingual"],
    library_name="transformers",
)


def _patch_qwen3_235b() -> Any:
    return _patch_hf_calls(
        config=_QWEN3_235B_CONFIG,
        tokenizer_config={
            "tokenizer_class": "Qwen2Tokenizer",
            "model_max_length": 32768,
        },
        generation_config=_QWEN3_235B_GENERATION_CONFIG,
        card_data=_QWEN3_235B_CARD_DATA,
        hub_info={"author": "Qwen", "sha": "abc123ef"},
    )


_QWEN35_27B_CONFIG: dict[str, Any] = {
    "model_type": "qwen3",
    "architectures": ["Qwen3ForCausalLM"],
    "vocab_size": 152064,
    "hidden_size": 5120,
    "num_hidden_layers": 64,
    "num_attention_heads": 40,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_QWEN35_27B_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["multilingual"],
    library_name="transformers",
)


def _patch_qwen35_27b() -> Any:
    return _patch_hf_calls(
        config=_QWEN35_27B_CONFIG,
        tokenizer_config={
            "tokenizer_class": "Qwen2Tokenizer",
            "model_max_length": 131072,
        },
        card_data=_QWEN35_27B_CARD_DATA,
        hub_info={"author": "Qwen", "sha": "deadf00d"},
    )


_KANANA_15V_CONFIG: dict[str, Any] = {
    "model_type": "kanana-1.5-v",
    "architectures": ["KananaVForConditionalGeneration"],
    "vocab_size": 102400,
    "hidden_size": 3072,
    "num_hidden_layers": 28,
    "num_attention_heads": 16,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_KANANA_15V_CARD_DATA = _make_card_data(
    license="kanana-license",
    pipeline_tag="image-text-to-text",
    language=["ko", "en"],
    library_name="transformers",
)


def _patch_kanana_15v() -> Any:
    return _patch_hf_calls(
        config=_KANANA_15V_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_KANANA_15V_CARD_DATA,
        hub_info={"author": "kakaobank", "sha": "deadf00d"},
    )


_EXAONE45_33B_CONFIG: dict[str, Any] = {
    "model_type": "exaone4_5",
    "architectures": ["Exaone4_5_ForConditionalGeneration"],
    "vocab_size": 102400,
    "hidden_size": 7168,
    "num_hidden_layers": 64,
    "num_attention_heads": 56,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_EXAONE45_33B_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    language=["ko", "en", "zh", "ja", "es", "fr"],
    library_name="transformers",
)


def _patch_exaone45_33b() -> Any:
    return _patch_hf_calls(
        config=_EXAONE45_33B_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_EXAONE45_33B_CARD_DATA,
        hub_info={"author": "LGAI-EXAONE", "sha": "deadf00d"},
    )


_EXAONE45_33B_AWQ_CONFIG: dict[str, Any] = {
    "model_type": "exaone4_5",
    "architectures": ["Exaone4_5_ForConditionalGeneration"],
    "vocab_size": 102400,
    "hidden_size": 7168,
    "num_hidden_layers": 64,
    "num_attention_heads": 56,
    "num_key_value_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "float16",
    "quantization_config": {"quant_type": "awq", "bits": 4},
}

_EXAONE45_33B_AWQ_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    language=["ko", "en"],
    library_name="transformers",
    base_model="LGAI-EXAONE/EXAONE-4.5-33B",
)


def _patch_exaone45_33b_awq() -> Any:
    return _patch_hf_calls(
        config=_EXAONE45_33B_AWQ_CONFIG,
        card_data=_EXAONE45_33B_AWQ_CARD_DATA,
        hub_info={
            "author": "LGAI-EXAONE",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:LGAI-EXAONE/EXAONE-4.5-33B"],
        },
    )


_EXAONE45_33B_FP8_CONFIG: dict[str, Any] = {
    "model_type": "exaone4_5",
    "architectures": ["Exaone4_5_ForConditionalGeneration"],
    "vocab_size": 102400,
    "hidden_size": 7168,
    "num_hidden_layers": 64,
    "num_attention_heads": 56,
    "max_position_embeddings": 131072,
    "torch_dtype": "float8_e4m3fn",
}

_EXAONE45_33B_FP8_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    language=["ko", "en"],
    library_name="transformers",
    base_model="LGAI-EXAONE/EXAONE-4.5-33B",
)


def _patch_exaone45_33b_fp8() -> Any:
    return _patch_hf_calls(
        config=_EXAONE45_33B_FP8_CONFIG,
        card_data=_EXAONE45_33B_FP8_CARD_DATA,
        hub_info={
            "author": "LGAI-EXAONE",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:LGAI-EXAONE/EXAONE-4.5-33B"],
        },
    )


_EXAONE45_33B_GGUF_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="image-text-to-text",
    language=["ko", "en"],
    library_name="gguf",
    base_model="LGAI-EXAONE/EXAONE-4.5-33B",
)


def _patch_exaone45_33b_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_EXAONE45_33B_GGUF_CARD_DATA,
        hub_info={
            "author": "LGAI-EXAONE",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:LGAI-EXAONE/EXAONE-4.5-33B"],
        },
    )


_EXAONE_PATH_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="pathology-image-analysis",
    language=["en"],
    library_name="transformers",
)


def _patch_exaone_path() -> Any:
    return _patch_hf_calls(
        config=None,  # gated → 401
        tokenizer_config=None,
        card_data=_EXAONE_PATH_CARD_DATA,
        hub_info={"author": "LGAI-EXAONE", "sha": "deadf00d"},
    )


_GLM45_AIR_REAP_CONFIG: dict[str, Any] = {
    "model_type": "glm4_moe",
    "architectures": ["Glm4MoeForCausalLM"],
    "vocab_size": 151552,
    "hidden_size": 4096,
    "num_hidden_layers": 62,
    "num_attention_heads": 32,
    "num_key_value_heads": 2,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_GLM45_AIR_REAP_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "ko", "zh"],
    library_name="transformers",
    base_model="THUDM/GLM-4.5-Air",
)


def _patch_glm45_air_reap() -> Any:
    return _patch_hf_calls(
        config=_GLM45_AIR_REAP_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_GLM45_AIR_REAP_CARD_DATA,
        hub_info={
            "author": "THUDM",
            "sha": "deadf00d",
            "tags": ["base_model:merge:THUDM/GLM-4.5-Air"],
        },
    )


_LINE_DISTILBERT_CONFIG: dict[str, Any] = {
    "model_type": "distilbert",
    "architectures": ["DistilBertForMaskedLM"],
    "vocab_size": 32000,
    "hidden_size": 768,
    "num_hidden_layers": 6,
    "num_attention_heads": 12,
    "max_position_embeddings": 512,
    "torch_dtype": "float32",
}

_LINE_DISTILBERT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="fill-mask",
    language=["ja"],
    library_name="transformers",
)


def _patch_line_distilbert() -> Any:
    return _patch_hf_calls(
        config=_LINE_DISTILBERT_CONFIG,
        tokenizer_config={"tokenizer_class": "BertJapaneseTokenizer"},
        card_data=_LINE_DISTILBERT_CARD_DATA,
        hub_info={"author": "line-corporation", "sha": "deadf00d"},
    )


_CLIP_JAPANESE_V2_CONFIG: dict[str, Any] = {
    "model_type": "clyp",
    "architectures": ["CLYPModel"],
    "hidden_size": 768,
    "vocab_size": 32000,
    "torch_dtype": "float32",
}

_CLIP_JAPANESE_V2_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="feature-extraction",
    language=["ja"],
    library_name="transformers",
)


def _patch_clip_japanese_v2() -> Any:
    return _patch_hf_calls(
        config=_CLIP_JAPANESE_V2_CONFIG,
        tokenizer_config={"tokenizer_class": "BertJapaneseTokenizer"},
        card_data=_CLIP_JAPANESE_V2_CARD_DATA,
        hub_info={"author": "line-corporation", "sha": "deadf00d"},
    )


_FUJITSU_LLM_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["ja", "en"],
    library_name="nemo",
)


def _patch_fujitsu_llm() -> Any:
    return _patch_hf_calls(
        config=None,  # gated → 401
        tokenizer_config=None,
        card_data=_FUJITSU_LLM_CARD_DATA,
        hub_info={"author": "Fujitsu", "sha": "deadf00d"},
    )


_WINDOWSEAT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="image-to-image",
    language=None,
    library_name="peft",
)


def _patch_windowseat() -> Any:
    return _patch_hf_calls(
        config=None,  # absent → 404
        tokenizer_config=None,
        card_data=_WINDOWSEAT_CARD_DATA,
        hub_info={"author": "windowseat-ai", "sha": "deadf00d"},
    )


_MOIRAI_CONFIG: dict[str, Any] = {
    "patch_sizes": [8, 16, 32, 64, 128],
    "d_model": 384,
    "num_encoder_layers": 6,
    "nhead": 8,
    "context_length": 4096,
}

_MOIRAI_CARD_DATA = _make_card_data(
    license="cc-by-nc-4.0",
    pipeline_tag="time-series-forecasting",
    language=None,
    library_name="transformers",
)


def _patch_moirai() -> Any:
    return _patch_hf_calls(
        config=_MOIRAI_CONFIG,
        tokenizer_config=None,
        card_data=_MOIRAI_CARD_DATA,
        hub_info={"author": "Salesforce", "sha": "deadf00d"},
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


_TILDEOPEN_30B_64K_CONFIG: dict[str, Any] = {
    "model_type": "llama",
    "architectures": ["LlamaForCausalLM"],
    "vocab_size": 131072,
    "hidden_size": 6144,
    "num_hidden_layers": 60,
    "num_attention_heads": 48,
    "num_key_value_heads": 8,
    "max_position_embeddings": 65536,
    "torch_dtype": "bfloat16",
    "rope_scaling": {
        "rope_type": "yarn",
        "factor": 10.0,
        "original_max_position_embeddings": 8192,
    },
}

_TILDEOPEN_30B_64K_CARD_DATA = _make_card_data(
    license="cc-by-4.0",
    pipeline_tag="text-generation",
    language=[
        "af",
        "bg",
        "ca",
        "cs",
        "cy",
        "da",
        "de",
        "el",
        "en",
        "es",
        "et",
        "eu",
        "fi",
        "fr",
        "ga",
        "hr",
        "hu",
        "is",
        "it",
        "lt",
        "lv",
        "mk",
        "mt",
        "nl",
        "no",
        "pl",
        "pt",
        "ro",
        "sk",
        "sl",
        "sq",
        "sv",
        "uk",
        "la",
    ],
    library_name="transformers",
    datasets=[
        "HPLT/HPLT2.0_cleaned",
        "HPLT/hplt_monolingual_v1_2",
        "HuggingFaceFW/fineweb-2",
        "allenai/MADLAD-400",
        "uonlp/CulturaX",
        "bigcode/the-stack",
        "common-pile/arxiv_papers",
    ],
)


def _patch_tildeopen_30b_64k() -> Any:
    return _patch_hf_calls(
        config=_TILDEOPEN_30B_64K_CONFIG,
        tokenizer_config={
            "tokenizer_class": "PreTrainedTokenizerFast",
            "model_max_length": 65536,
        },
        card_data=_TILDEOPEN_30B_64K_CARD_DATA,
        hub_info={"author": "TildeAI", "sha": "deadf00d"},
    )


_TILDEOPEN_30B_CONFIG: dict[str, Any] = {
    "model_type": "llama",
    "architectures": ["LlamaForCausalLM"],
    "vocab_size": 131072,
    "hidden_size": 6144,
    "num_hidden_layers": 60,
    "num_attention_heads": 48,
    "num_key_value_heads": 8,
    "max_position_embeddings": 65536,
    "torch_dtype": "bfloat16",
}

_TILDEOPEN_30B_CARD_DATA = _make_card_data(
    license="cc-by-4.0",
    pipeline_tag="text-generation",
    language=[
        "af",
        "bg",
        "ca",
        "cs",
        "cy",
        "da",
        "de",
        "el",
        "en",
        "es",
        "et",
        "eu",
        "fi",
        "fr",
        "ga",
        "hr",
        "hu",
        "is",
        "it",
        "lt",
        "lv",
        "mk",
        "mt",
        "nl",
        "no",
        "pl",
        "pt",
        "ro",
        "sk",
        "sl",
        "sq",
        "sv",
        "uk",
        "la",
    ],
    library_name="transformers",
    datasets=[
        "HPLT/HPLT2.0_cleaned",
        "HPLT/hplt_monolingual_v1_2",
        "HuggingFaceFW/fineweb-2",
        "allenai/MADLAD-400",
        "uonlp/CulturaX",
        "bigcode/the-stack",
        "common-pile/arxiv_papers",
    ],
)

_TILDEOPEN_TOKENIZER_SENTINEL: int = 1_000_000_000_000_000_019_884_624_838_656


def _patch_tildeopen_30b() -> Any:
    return _patch_hf_calls(
        config=_TILDEOPEN_30B_CONFIG,
        tokenizer_config={
            "tokenizer_class": "LlamaTokenizer",
            "model_max_length": _TILDEOPEN_TOKENIZER_SENTINEL,
        },
        card_data=_TILDEOPEN_30B_CARD_DATA,
        hub_info={"author": "TildeAI", "sha": "deadf00d"},
    )


_OPENEUROLLM_CONFIG: dict[str, Any] = {
    "model_type": "llama",
    "architectures": ["LlamaForCausalLM"],
    "vocab_size": 262400,
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "num_attention_heads": 32,
    "num_key_value_heads": 32,
    "max_position_embeddings": 2048,
    "torch_dtype": "bfloat16",
    "tie_word_embeddings": True,
}

_OPENEUROLLM_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag=None,
    language=[
        "en",
        "de",
        "fr",
        "es",
        "pt",
        "it",
        "nl",
        "pl",
        "sv",
        "no",
        "da",
        "fi",
        "cs",
        "sk",
        "sl",
        "hr",
        "bg",
        "ro",
        "hu",
        "el",
        "lt",
        "lv",
        "et",
        "ga",
        "mt",
        "eu",
        "ca",
        "cy",
        "sq",
        "mk",
        "uk",
        "ru",
        "tr",
        "is",
    ],
    library_name="transformers",
    datasets=[
        "HPLT/HPLT2.0_cleaned",
        "HuggingFaceTB/finemath",
        "bigcode/starcoderdata",
    ],
)


def _patch_openeurollm() -> Any:
    return _patch_hf_calls(
        config=_OPENEUROLLM_CONFIG,
        tokenizer_config=None,  # 404 in real repo
        card_data=_OPENEUROLLM_CARD_DATA,
        hub_info={"author": "openeurollm", "sha": "deadf00d"},
    )


_BLOOM_CONFIG: dict[str, Any] = {
    "model_type": "bloom",
    "architectures": ["BloomForCausalLM"],
    "vocab_size": 250880,
    "hidden_size": 14336,
    "n_layer": 70,  # BLOOM-specific: extractor does NOT capture (not in _HYPER_KEYS)
    "n_head": 112,  # BLOOM-specific: extractor does NOT capture (not in _HYPER_KEYS)
    "attention_softmax_in_fp32": True,
    "masked_softmax_fusion": True,
    # No max_position_embeddings (ALiBi)
    # No torch_dtype in config
}

_BLOOM_CARD_DATA = _make_card_data(
    license="bigscience-bloom-rail-1.0",
    pipeline_tag="text-generation",
    language=[
        "ak",
        "ar",
        "as",
        "bm",
        "bn",
        "ca",
        "code",
        "en",
        "es",
        "eu",
        "fon",
        "fr",
        "gu",
        "hi",
        "id",
        "ig",
        "ki",
        "kn",
        "lg",
        "ln",
        "ml",
        "mr",
        "ne",
        "nso",
        "ny",
        "or",
        "pa",
        "pt",
        "rn",
        "rw",
        "sn",
        "st",
        "sw",
        "ta",
        "te",
        "tn",
        "ts",
        "tum",
        "tw",
        "ur",
        "ve",
        "vi",
        "wo",
        "xh",
        "yo",
        "zh",
        "zu",
    ],
    library_name="transformers",
)


def _patch_bloom() -> Any:
    return _patch_hf_calls(
        config=_BLOOM_CONFIG,
        tokenizer_config={"tokenizer_class": "BloomTokenizerFast"},
        card_data=_BLOOM_CARD_DATA,
        hub_info={"author": "bigscience", "sha": "deadf00d"},
    )


_BLOOMZ_7B1_CONFIG: dict[str, Any] = {
    "model_type": "bloom",
    "architectures": ["BloomForCausalLM"],
    "vocab_size": 250880,
    "hidden_size": 4096,
    "n_layer": 30,  # BLOOM-specific: not captured
    "n_head": 32,  # BLOOM-specific: not captured
    "seq_length": 2048,  # added to _HYPER_KEYS → captured as context length
    "attention_softmax_in_fp32": True,
    "masked_softmax_fusion": True,
    "bias_dropout_fusion": True,
}

_BLOOMZ_7B1_CARD_DATA = _make_card_data(
    license="bigscience-bloom-rail-1.0",
    pipeline_tag="text-generation",
    language=[
        "ak",
        "ar",
        "as",
        "bm",
        "bn",
        "ca",
        "code",
        "en",
        "es",
        "eu",
        "fon",
        "fr",
        "gu",
        "hi",
        "id",
        "ig",
        "ki",
        "kn",
        "lg",
        "ln",
        "ml",
        "mr",
        "ne",
        "nso",
        "ny",
        "or",
        "pa",
        "pt",
        "rn",
        "rw",
        "sn",
        "st",
        "sw",
        "ta",
        "te",
        "tn",
        "ts",
        "tum",
        "tw",
        "ur",
        "ve",
        "vi",
        "wo",
        "xh",
        "yo",
        "zh",
        "zu",
    ],
    library_name="transformers",
    base_model="bigscience/bloom-7b1",
    datasets=["bigscience/xP3"],
)


def _patch_bloomz_7b1() -> Any:
    return _patch_hf_calls(
        config=_BLOOMZ_7B1_CONFIG,
        tokenizer_config={"tokenizer_class": "BloomTokenizerFast"},
        card_data=_BLOOMZ_7B1_CARD_DATA,
        hub_info={
            "author": "bigscience",
            "sha": "deadf00d",
            "tags": ["base_model:finetune:bigscience/bloom-7b1"],
        },
    )


def _patch_cohere_aya_23() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data={},  # gated card → empty dict
        hub_info={"author": "CohereLabs", "sha": "deadf00d"},
    )


_OCCIGLOT_CONFIG: dict[str, Any] = {
    "model_type": "mistral",
    "architectures": ["MistralForCausalLM"],
    "vocab_size": 32002,
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "max_position_embeddings": 32768,
    "sliding_window": 4096,
    "torch_dtype": "bfloat16",
}

_OCCIGLOT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "es", "de", "fr", "it"],
    library_name="transformers",
    base_model="occiglot/occiglot-7b-eu5",
)

_OCCIGLOT_TOKENIZER_SENTINEL: int = 1_000_000_000_000_000_019_884_624_838_656


def _patch_occiglot() -> Any:
    return _patch_hf_calls(
        config=_OCCIGLOT_CONFIG,
        tokenizer_config={
            "tokenizer_class": "LlamaTokenizer",
            "model_max_length": _OCCIGLOT_TOKENIZER_SENTINEL,
        },
        card_data=_OCCIGLOT_CARD_DATA,
        hub_info={
            "author": "occiglot",
            "sha": "deadf00d",
            "tags": ["base_model:finetune:occiglot/occiglot-7b-eu5"],
        },
    )


_PHARIA_CONTROL_CARD_DATA = _make_card_data(
    license="other",
    license_name="open-aleph-license",
    pipeline_tag="text-generation",
    language=["de", "en", "fr", "es", "it", "pt", "nl"],
    library_name="scaling",
)


def _patch_pharia_control() -> Any:
    return _patch_hf_calls(
        config=None,  # absent (404) — custom scaling framework
        tokenizer_config=None,
        card_data=_PHARIA_CONTROL_CARD_DATA,
        hub_info={"author": "Aleph-Alpha", "sha": "deadf00d"},
    )


_PHARIA_ALIGNED_CARD_DATA = _make_card_data(
    license="other",
    license_name="open-aleph-license",
    pipeline_tag="text-generation",
    language=["de", "en", "fr", "es", "it", "pt", "nl"],
    library_name="scaling",
    base_model="Aleph-Alpha/Pharia-1-LLM-7B-control",
)


def _patch_pharia_aligned() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_PHARIA_ALIGNED_CARD_DATA,
        hub_info={
            "author": "Aleph-Alpha",
            "sha": "deadf00d",
            "tags": ["base_model:finetune:Aleph-Alpha/Pharia-1-LLM-7B-control"],
        },
    )


def _patch_wmt22_cometkiwi() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data={},  # gated → empty
        hub_info={"author": "Unbabel", "sha": "deadf00d"},
    )


_EUROLLM_1B7_CONFIG: dict[str, Any] = {
    "model_type": "llama",
    "architectures": ["LlamaForCausalLM"],
    "vocab_size": 128000,
    "hidden_size": 2048,
    "num_hidden_layers": 24,
    "num_attention_heads": 16,
    "num_key_value_heads": 8,
    "max_position_embeddings": 4096,
    "torch_dtype": "bfloat16",
}

_EUROLLM_1B7_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag=None,
    language=[
        "en",
        "de",
        "es",
        "fr",
        "it",
        "pt",
        "pl",
        "nl",
        "tr",
        "sv",
        "cs",
        "el",
        "hu",
        "ro",
        "fi",
        "uk",
        "sl",
        "sk",
        "da",
        "lt",
        "lv",
        "et",
        "bg",
        "no",
        "ca",
        "hr",
        "ga",
        "mt",
        "gl",
        "zh",
        "ru",
        "ko",
        "ja",
        "ar",
    ],
    library_name="transformers",
)

_EUROLLM_TOKENIZER_SENTINEL: int = 1_000_000_000_000_000_019_884_624_838_656


def _patch_eurollm_1b7() -> Any:
    return _patch_hf_calls(
        config=_EUROLLM_1B7_CONFIG,
        tokenizer_config={
            "tokenizer_class": "LlamaTokenizer",
            "model_max_length": _EUROLLM_TOKENIZER_SENTINEL,
        },
        card_data=_EUROLLM_1B7_CARD_DATA,
        hub_info={"author": "utter-project", "sha": "deadf00d"},
    )


_STABLE_ZERO123_CARD_DATA = _make_card_data(
    license="other",
    license_name="sai-nc-community",
    pipeline_tag="text-to-3d",
    language=None,
    library_name="diffusers",
)


def _patch_stable_zero123() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_STABLE_ZERO123_CARD_DATA,
        hub_info={"author": "stabilityai", "sha": "deadf00d"},
    )


_SHAP_E_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="text-to-3d",
    language=None,
    library_name=None,
)


def _patch_shap_e() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_SHAP_E_CARD_DATA,
        hub_info={"author": "openai", "sha": "deadf00d"},
    )


_BLENDERLLM_CONFIG: dict[str, Any] = {
    "model_type": "qwen2",
    "architectures": ["Qwen2ForCausalLM"],
    "vocab_size": 152064,
    "hidden_size": 3584,
    "num_hidden_layers": 28,
    "num_attention_heads": 28,
    "num_key_value_heads": 4,
    "max_position_embeddings": 32768,
    "torch_dtype": "bfloat16",
}

_BLENDERLLM_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-to-3d",
    language=["en"],
    library_name="transformers",
)


def _patch_blenderllm() -> Any:
    return _patch_hf_calls(
        config=_BLENDERLLM_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_BLENDERLLM_CARD_DATA,
        hub_info={"author": "FreedomIntelligence", "sha": "deadf00d"},
    )


_BLENDERLLM_GGUF_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-to-3d",
    language=None,
    library_name="gguf",
    base_model="FreedomIntelligence/BlenderLLM",
)


def _patch_blenderllm_gguf() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_BLENDERLLM_GGUF_CARD_DATA,
        hub_info={
            "author": "hellork",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:FreedomIntelligence/BlenderLLM"],
        },
    )


_HY_MOTION_CONFIG: dict[str, Any] = {
    "Name": "HunyuanMotion",  # non-standard metadata field
    "motion_module_type": "vanilla",
    "num_transformer_blocks": 20,
}

_HY_MOTION_CARD_DATA = _make_card_data(
    license="other",
    license_name="tencent-hunyuan-community",
    pipeline_tag="text-to-3d",
    language=["zh", "en"],
    library_name="HY-Motion-1.0",
)


def _patch_hy_motion() -> Any:
    return _patch_hf_calls(
        config=_HY_MOTION_CONFIG,
        tokenizer_config=None,
        card_data=_HY_MOTION_CARD_DATA,
        hub_info={"author": "tencent", "sha": "deadf00d"},
    )


_APPLE_SHARP_CARD_DATA = _make_card_data(
    license="apple-amlr",
    pipeline_tag="image-to-3d",
    language=None,
    library_name="ml-sharp",
)


def _patch_apple_sharp() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_APPLE_SHARP_CARD_DATA,
        hub_info={"author": "apple", "sha": "deadf00d"},
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


_GTE_RERANKER_CONFIG: dict[str, Any] = {
    "model_type": "new",
    "architectures": ["NewForSequenceClassification"],
    "vocab_size": 250002,
    "hidden_size": 768,
    "num_hidden_layers": 12,
    "torch_dtype": "bfloat16",
}

_GTE_RERANKER_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-ranking",
    language=["multilingual"],
    library_name="sentence-transformers",
)


def _patch_gte_reranker() -> Any:
    return _patch_hf_calls(
        config=_GTE_RERANKER_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_GTE_RERANKER_CARD_DATA,
        hub_info={"author": "Alibaba-NLP", "sha": "deadf00d"},
    )


_OPENELM_270M_CONFIG: dict[str, Any] = {
    "model_type": "openelm",
    "architectures": ["OpenELMForCausalLM"],
    "vocab_size": 32000,
    "hidden_size": 1280,
    "num_hidden_layers": 16,
    "num_attention_heads": 10,
    "head_dim": 64,
    "max_position_embeddings": 2048,
    "torch_dtype": "float16",
    "activation_fn_name": "swiglu",  # non-standard
    "ffn_dim_divisor": 256,  # non-standard
}

_OPENELM_270M_CARD_DATA = _make_card_data(
    license="apple-amlr",
    pipeline_tag="text-generation",
    language=["en"],
    library_name="transformers",
)


def _patch_openelm_270m() -> Any:
    return _patch_hf_calls(
        config=_OPENELM_270M_CONFIG,
        tokenizer_config={"tokenizer_class": "LlamaTokenizer"},
        card_data=_OPENELM_270M_CARD_DATA,
        hub_info={"author": "apple", "sha": "deadf00d"},
    )


_MINIMAX_M2_CONFIG: dict[str, Any] = {
    "model_type": "minimax_m2",
    "architectures": ["MiniMaxM2ForCausalLM"],
    "vocab_size": 200064,
    "hidden_size": 7168,
    "num_hidden_layers": 80,
    "num_attention_heads": 64,
    "num_key_value_heads": 8,
    "max_position_embeddings": 1000000,
    "torch_dtype": "bfloat16",
    "attn_type_list": ["mhsa", "local"] * 40,  # non-standard: mixed attention
    "mtp_transformer_layers": 3,  # non-standard: multi-token prediction
    "num_experts_per_tok": 2,  # non-standard: MoE routing
}

_MINIMAX_M2_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="text-generation",
    language=["en", "zh"],
    library_name="transformers",
)


def _patch_minimax_m2() -> Any:
    return _patch_hf_calls(
        config=_MINIMAX_M2_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_MINIMAX_M2_CARD_DATA,
        hub_info={"author": "MiniMaxAI", "sha": "deadf00d"},
    )


_LLADA2_MOE_CONFIG: dict[str, Any] = {
    "model_type": "llada2_moe",
    "architectures": ["LLaDA2MoeModelLM"],
    "vocab_size": 151936,
    "hidden_size": 2048,
    "num_hidden_layers": 28,
    "num_attention_heads": 16,
    "torch_dtype": "bfloat16",
    "use_qkv_bias": True,  # non-standard
    "use_qk_norm": True,  # non-standard
}

_LLADA2_MOE_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["en", "zh"],
    library_name="transformers",
)


def _patch_llada2_moe() -> Any:
    return _patch_hf_calls(
        config=_LLADA2_MOE_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_LLADA2_MOE_CARD_DATA,
        hub_info={"author": "inclusionAI", "sha": "deadf00d"},
    )


_BAGEL_CONFIG: dict[str, Any] = {
    "model_type": "bagel",
    "architectures": ["BagelForConditionalGeneration"],
    "llm_config": {"hidden_size": 3584, "num_hidden_layers": 28},  # nested
    "vit_config": {"hidden_size": 1024, "num_hidden_layers": 24},  # nested
    "vae_config": {"in_channels": 8},  # nested
    "visual_gen": True,
    "visual_und": True,
}

_BAGEL_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["en"],
    library_name="bagel-mot",
)


def _patch_bagel() -> Any:
    return _patch_hf_calls(
        config=_BAGEL_CONFIG,
        tokenizer_config=None,
        card_data=_BAGEL_CARD_DATA,
        hub_info={"author": "ByteDance-Seed", "sha": "deadf00d"},
    )


_SENSENOVA_CONFIG: dict[str, Any] = {
    "model_type": "neo_chat",
    "architectures": ["NEOChatModel"],
    "llm_config": {"hidden_size": 3584, "num_hidden_layers": 28},  # nested
    "downsample_ratio": 2,  # non-standard
    "template": "chat",  # non-standard
}

_SENSENOVA_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["zh", "en"],
    library_name="transformers",
)


def _patch_sensenova() -> Any:
    return _patch_hf_calls(
        config=_SENSENOVA_CONFIG,
        tokenizer_config=None,
        card_data=_SENSENOVA_CARD_DATA,
        hub_info={"author": "sensenova", "sha": "deadf00d"},
    )


_MMADA_CONFIG: dict[str, Any] = {
    "model_type": "llada",
    "architectures": ["LLaDAModelLM"],
    "vocab_size": 32000,
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "alibi": True,  # ALiBi positional bias (non-standard, not in _HYPER_KEYS)
    "alibi_bias_max": 8,  # non-standard
    "attention_layer_norm": True,  # non-standard
    # No max_position_embeddings (ALiBi models don't have a fixed limit)
}

_MMADA_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="any-to-any",
    language=["en"],
    library_name="transformers",
)


def _patch_mmada() -> Any:
    return _patch_hf_calls(
        config=_MMADA_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_MMADA_CARD_DATA,
        hub_info={"author": "Gen-Verse", "sha": "deadf00d"},
    )


_MIMO_AUDIO_CONFIG: dict[str, Any] = {
    "model_type": "qwen2",
    "architectures": ["MiMoAudioModel"],  # custom arch despite qwen2 model_type
    "vocab_size": 152064,
    "hidden_size": 3584,
    "num_hidden_layers": 28,
    "num_attention_heads": 28,
    "num_key_value_heads": 4,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
    "audio_channels": 128,  # non-standard
    "delay_pattern": "valley",  # non-standard
}

_MIMO_AUDIO_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="any-to-any",
    language=["en", "zh"],
    library_name="transformers",
)


def _patch_mimo_audio() -> Any:
    return _patch_hf_calls(
        config=_MIMO_AUDIO_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_MIMO_AUDIO_CARD_DATA,
        hub_info={"author": "XiaomiMiMo", "sha": "deadf00d"},
    )


_LIGHTGLUE_CONFIG: dict[str, Any] = {
    "model_type": "lightglue",
    "architectures": ["LightGlueForKeypointMatching"],
    "descriptor_dim": 256,  # non-standard
    "filter_threshold": 0.1,  # non-standard
    "depth_confidence": 0.95,  # non-standard
    "keypoint_detector_config": {"name": "superpoint", "descriptor_dim": 256},
}

_LIGHTGLUE_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="keypoint-detection",
    language=None,
    library_name="transformers",
)


def _patch_lightglue() -> Any:
    return _patch_hf_calls(
        config=_LIGHTGLUE_CONFIG,
        tokenizer_config=None,
        card_data=_LIGHTGLUE_CARD_DATA,
        hub_info={"author": "ETH-CVG", "sha": "deadf00d"},
    )


_AION_CONFIG: dict[str, Any] = {
    "decoder_depth": 8,
    "encoder_depth": 8,
    "domains_in": ["fluids", "climate", "seismology"],
    "domains_out": ["fluids", "climate", "seismology"],
    "patch_size": 16,
}

_AION_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag="any-to-any",
    language=None,
    library_name="aion",
)


def _patch_aion() -> Any:
    return _patch_hf_calls(
        config=_AION_CONFIG,
        tokenizer_config=None,
        card_data=_AION_CARD_DATA,
        hub_info={"author": "polymathic-ai", "sha": "deadf00d"},
    )


_STANZA_FI_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag=None,
    language=["fi"],
    library_name="stanza",
)


def _patch_stanza_fi() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_STANZA_FI_CARD_DATA,
        hub_info={"author": "stanfordnlp", "sha": "deadf00d"},
    )


_STANZA_DE_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag=None,
    language=["de"],
    library_name="stanza",
)


def _patch_stanza_de() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_STANZA_DE_CARD_DATA,
        hub_info={"author": "stanfordnlp", "sha": "deadf00d"},
    )


_OPENVINO_MIXTRAL_CONFIG: dict[str, Any] = {
    "model_type": "mixtral",
    "architectures": ["MixtralForCausalLM"],
    "vocab_size": 32000,
    "hidden_size": 4096,
    "num_hidden_layers": 32,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "max_position_embeddings": 32768,
    "torch_dtype": "int8",  # quantized dtype captured
    "num_experts_per_tok": 2,  # non-standard (MoE)
    "router_aux_loss_coef": 0.001,  # non-standard (MoE routing)
}

_OPENVINO_MIXTRAL_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "de", "fr", "es", "it"],
    library_name="openvino",
    base_model="mistralai/Mixtral-8x7B-Instruct-v0.1",
)


def _patch_openvino_mixtral() -> Any:
    return _patch_hf_calls(
        config=_OPENVINO_MIXTRAL_CONFIG,
        tokenizer_config=None,
        card_data=_OPENVINO_MIXTRAL_CARD_DATA,
        hub_info={
            "author": "OpenVINO",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:mistralai/Mixtral-8x7B-Instruct-v0.1"],
        },
    )


_MLX_GEMMA4_CONFIG: dict[str, Any] = {
    "model_type": "gemma4",
    "architectures": ["Gemma4ForConditionalGeneration"],
    "vocab_size": 262144,
    "hidden_size": 2560,
    "num_hidden_layers": 34,
    "num_attention_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_MLX_GEMMA4_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["multilingual"],
    library_name="mlx",
    base_model="google/gemma-4-e2b-it",
)


def _patch_mlx_gemma4() -> Any:
    return _patch_hf_calls(
        config=_MLX_GEMMA4_CONFIG,
        tokenizer_config=None,
        card_data=_MLX_GEMMA4_CARD_DATA,
        hub_info={
            "author": "mlx-community",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:google/gemma-4-e2b-it"],
        },
    )


_ONNX_GEMMA4_CONFIG: dict[str, Any] = {
    "model_type": "gemma4",
    "architectures": ["Gemma4ForConditionalGeneration"],
    "vocab_size": 262144,
    "hidden_size": 2560,
    "num_hidden_layers": 34,
    "num_attention_heads": 8,
    "max_position_embeddings": 131072,
    "torch_dtype": "bfloat16",
}

_ONNX_GEMMA4_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="any-to-any",
    language=["multilingual"],
    library_name="transformers.js",
    base_model="google/gemma-4-E2B-it",
)


def _patch_onnx_gemma4() -> Any:
    return _patch_hf_calls(
        config=_ONNX_GEMMA4_CONFIG,
        tokenizer_config=None,
        card_data=_ONNX_GEMMA4_CARD_DATA,
        hub_info={
            "author": "onnx-community",
            "sha": "deadf00d",
            "tags": ["base_model:quantized:google/gemma-4-E2B-it"],
        },
    )


_SAILOR2_20B_CONFIG: dict[str, Any] = {
    "model_type": "qwen2",
    "architectures": ["Qwen2ForCausalLM"],
    "vocab_size": 151936,
    "hidden_size": 5120,
    "num_hidden_layers": 48,
    "num_attention_heads": 40,
    "num_key_value_heads": 8,
    "max_position_embeddings": 32768,
    "torch_dtype": "bfloat16",
}

_SAILOR2_20B_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-generation",
    language=["en", "zh", "th", "id", "vi", "ms", "my", "km", "lo", "tl"],
    library_name="transformers",
)


def _patch_sailor2_20b() -> Any:
    return _patch_hf_calls(
        config=_SAILOR2_20B_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_SAILOR2_20B_CARD_DATA,
        hub_info={"author": "sail", "sha": "deadf00d"},
    )


_GTE_MODERNBERT_CONFIG: dict[str, Any] = {
    "model_type": "modernbert",
    "architectures": ["ModernBertModel"],
    "vocab_size": 30528,
    "hidden_size": 768,
    "num_hidden_layers": 22,
    "num_attention_heads": 12,
    "max_position_embeddings": 8192,
    "torch_dtype": "bfloat16",
}

_GTE_MODERNBERT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="sentence-similarity",
    language=["multilingual"],
    library_name="transformers",
)


def _patch_gte_modernbert() -> Any:
    return _patch_hf_calls(
        config=_GTE_MODERNBERT_CONFIG,
        tokenizer_config={"tokenizer_class": "PreTrainedTokenizerFast"},
        card_data=_GTE_MODERNBERT_CARD_DATA,
        hub_info={"author": "Alibaba-NLP", "sha": "deadf00d"},
    )


_CODEBERTA_CONFIG: dict[str, Any] = {
    "model_type": "roberta",
    "architectures": ["RobertaForMaskedLM"],
    "vocab_size": 50265,
    "hidden_size": 512,
    "num_hidden_layers": 6,
    "num_attention_heads": 8,
    "max_position_embeddings": 514,
}

_CODEBERTA_CARD_DATA = _make_card_data(
    license=None,  # no license field in card
    pipeline_tag="fill-mask",
    language=["code"],  # non-ISO identifier for programming languages
    library_name="transformers",
)


def _patch_codeberta() -> Any:
    return _patch_hf_calls(
        config=_CODEBERTA_CONFIG,
        tokenizer_config={"tokenizer_class": "RobertaTokenizerFast"},
        card_data=_CODEBERTA_CARD_DATA,
        hub_info={"author": "huggingface", "sha": "deadf00d"},
    )


_TRADEPULSE_CONFIG: dict[str, Any] = {
    "model_type": "bert",
    "architectures": ["BertForSequenceClassification"],
    "vocab_size": 30522,
    "hidden_size": 768,
    "num_hidden_layers": 12,
    "num_attention_heads": 12,
    "max_position_embeddings": 512,
    "problem_type": "single_label_classification",  # non-standard (fine-tune config)
}

_TRADEPULSE_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-classification",
    language=["en"],
    library_name="transformers",
    base_model="ProsusAI/finbert",
)


def _patch_tradepulse() -> Any:
    return _patch_hf_calls(
        config=_TRADEPULSE_CONFIG,
        tokenizer_config={"tokenizer_class": "BertTokenizer"},
        card_data=_TRADEPULSE_CARD_DATA,
        hub_info={
            "author": "Bencode92",
            "sha": "deadf00d",
            "tags": ["base_model:finetune:ProsusAI/finbert"],
        },
    )


_HRNETPOSE_CARD_DATA = _make_card_data(
    license="other",
    pipeline_tag="keypoint-detection",
    language=None,
    library_name="pytorch",
)


def _patch_hrnetpose() -> Any:
    return _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=_HRNETPOSE_CARD_DATA,
        hub_info={"author": "qualcomm", "sha": "deadf00d"},
    )


_RTDETR_COCO_O365_CONFIG: dict[str, Any] = {
    "model_type": "rt_detr",
    "architectures": ["RTDetrForObjectDetection"],
    "torch_dtype": "float32",
    # Detection-specific keys — none in _HYPER_KEYS
    "d_model": 256,
    "decoder_attention_heads": 8,
    "encoder_attention_heads": 8,
    "decoder_layers": 6,
    "encoder_layers": 1,
    "num_queries": 300,
    "is_encoder_decoder": True,
}

_RTDETR_COCO_O365_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="object-detection",
    language=["en"],
    library_name="transformers",
    datasets=["coco"],
)


def _patch_rtdetr_coco_o365() -> Any:
    return _patch_hf_calls(
        config=_RTDETR_COCO_O365_CONFIG,
        tokenizer_config=None,
        card_data=_RTDETR_COCO_O365_CARD_DATA,
        hub_info={
            "author": "PekingU",
            "sha": "deadf00d",
            "tags": ["arxiv:2304.08069", "dataset:coco"],
        },
    )


_RTDETR_COCO_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="object-detection",
    language=["en"],
    library_name="transformers",
    datasets=["coco"],
)


def _patch_rtdetr_coco() -> Any:
    return _patch_hf_calls(
        config=_RTDETR_COCO_O365_CONFIG,  # same config schema
        tokenizer_config=None,
        card_data=_RTDETR_COCO_CARD_DATA,
        hub_info={
            "author": "PekingU",
            "sha": "deadf00d",
            "tags": ["arxiv:2304.08069", "dataset:coco"],
        },
    )


_SAP_RPT_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="tabular-classification",
    language=None,
    library_name="sap-rpt-1-oss",
    datasets=["mlfoundations/t4-full"],
)


def _patch_sap_rpt() -> Any:
    return _patch_hf_calls(
        config=None,  # 401 gated
        tokenizer_config=None,
        card_data=_SAP_RPT_CARD_DATA,
        hub_info={
            "author": "SAP",
            "sha": "deadf00d",
            "tags": ["arxiv:2506.10707", "dataset:mlfoundations/t4-full"],
        },
    )


_TIMELENS_CONFIG: dict[str, Any] = {
    "model_type": "qwen3_vl",
    "architectures": ["Qwen3VLForConditionalGeneration"],
    "dtype": "bfloat16",  # non-standard: uses dtype, not torch_dtype
    # All LM numeric fields are nested inside text_config — NOT at top level
    "text_config": {
        "vocab_size": 151936,
        "hidden_size": 4096,
        "num_hidden_layers": 36,
        "num_attention_heads": 32,
        "num_key_value_heads": 8,
        "head_dim": 128,
        "intermediate_size": 12288,
        "max_position_embeddings": 262144,
        "rope_theta": 5000000,
    },
    "vision_config": {
        "hidden_size": 1152,
        "depth": 27,
        "num_heads": 16,
    },
}

_TIMELENS_CARD_DATA = _make_card_data(
    license="other",
    license_name="bsd-3-clause",
    pipeline_tag="video-text-to-text",
    language=["en"],
    library_name="transformers",
    datasets=["TencentARC/TimeLens-100K", "TencentARC/TimeLens-Bench"],
    base_model="Qwen/Qwen3-VL-8B-Instruct",
)


def _patch_timelens() -> Any:
    return _patch_hf_calls(
        config=_TIMELENS_CONFIG,
        tokenizer_config=None,
        card_data=_TIMELENS_CARD_DATA,
        hub_info={
            "author": "TencentARC",
            "sha": "deadf00d",
            "tags": [
                "arxiv:2512.14698",
                "base_model:Qwen/Qwen3-VL-8B-Instruct",
                "base_model:finetune:Qwen/Qwen3-VL-8B-Instruct",
            ],
        },
    )


_BERT_TURKISH_CONFIG: dict[str, Any] = {
    "model_type": "bert",
    # "architectures" field absent — different from [] (empty list)
    "vocab_size": 32000,
    "hidden_size": 768,
    "num_hidden_layers": 12,
    "num_attention_heads": 12,
    "intermediate_size": 3072,
    "max_position_embeddings": 512,
}

_BERT_TURKISH_CARD_DATA = _make_card_data(
    license="mit",
    pipeline_tag=None,  # no pipeline_tag in card
    language=["tr"],
    library_name=None,
)


def _patch_bert_turkish() -> Any:
    return _patch_hf_calls(
        config=_BERT_TURKISH_CONFIG,
        tokenizer_config=None,
        card_data=_BERT_TURKISH_CARD_DATA,
        hub_info={"author": "dbmdz", "sha": "deadf00d"},
    )


_CROSS_ENCODER_CONFIG: dict[str, Any] = {
    "model_type": "bert",
    "architectures": ["BertForSequenceClassification"],
    "vocab_size": 30522,
    "hidden_size": 384,
    "num_hidden_layers": 6,
    "num_attention_heads": 12,
    "intermediate_size": 1536,
    "max_position_embeddings": 512,
    # Sentence-transformers-specific config key
    "sbert_ce_default_activation_function": "torch.nn.modules.linear.Identity",
}

_CROSS_ENCODER_CARD_DATA = _make_card_data(
    license="apache-2.0",
    pipeline_tag="text-ranking",
    language=["en"],
    library_name="sentence-transformers",
    datasets=["sentence-transformers/msmarco"],
    base_model="cross-encoder/ms-marco-MiniLM-L12-v2",
)


def _patch_cross_encoder() -> Any:
    return _patch_hf_calls(
        config=_CROSS_ENCODER_CONFIG,
        tokenizer_config={"tokenizer_class": "BertTokenizerFast"},
        card_data=_CROSS_ENCODER_CARD_DATA,
        hub_info={
            "author": "cross-encoder",
            "sha": "deadf00d",
            "tags": [
                "base_model:quantized:cross-encoder/ms-marco-MiniLM-L12-v2",
                "dataset:sentence-transformers/msmarco",
            ],
        },
    )


__all__ = [
    "Any",
    "MagicMock",
    "_AION_CARD_DATA",
    "_AION_CONFIG",
    "_APPLE_SHARP_CARD_DATA",
    "_BAGEL_CARD_DATA",
    "_BAGEL_CONFIG",
    "_BERT_TURKISH_CARD_DATA",
    "_BERT_TURKISH_CONFIG",
    "_BLENDERLLM_CARD_DATA",
    "_BLENDERLLM_CONFIG",
    "_BLENDERLLM_GGUF_CARD_DATA",
    "_BLOOMZ_7B1_CARD_DATA",
    "_BLOOMZ_7B1_CONFIG",
    "_BLOOM_CARD_DATA",
    "_BLOOM_CONFIG",
    "_CHINDA_CARD_DATA",
    "_CHINDA_CONFIG",
    "_CHINDA_GGUF_CARD_DATA",
    "_CLIP_JAPANESE_V2_CARD_DATA",
    "_CLIP_JAPANESE_V2_CONFIG",
    "_CODEBERTA_CARD_DATA",
    "_CODEBERTA_CONFIG",
    "_CROSS_ENCODER_CARD_DATA",
    "_CROSS_ENCODER_CONFIG",
    "_DEEPSEEK_CARD_DATA",
    "_DEEPSEEK_CONFIG",
    "_EUROLLM_1B7_CARD_DATA",
    "_EUROLLM_1B7_CONFIG",
    "_EUROLLM_TOKENIZER_SENTINEL",
    "_EXAONE45_33B_AWQ_CARD_DATA",
    "_EXAONE45_33B_AWQ_CONFIG",
    "_EXAONE45_33B_CARD_DATA",
    "_EXAONE45_33B_CONFIG",
    "_EXAONE45_33B_FP8_CARD_DATA",
    "_EXAONE45_33B_FP8_CONFIG",
    "_EXAONE45_33B_GGUF_CARD_DATA",
    "_EXAONE_PATH_CARD_DATA",
    "_FIRERED_VAD_CARD_DATA",
    "_FUJITSU_LLM_CARD_DATA",
    "_GEMMA_CARD_DATA",
    "_GLM45_AIR_REAP_CARD_DATA",
    "_GLM45_AIR_REAP_CONFIG",
    "_GTE_MODERNBERT_CARD_DATA",
    "_GTE_MODERNBERT_CONFIG",
    "_GTE_RERANKER_CARD_DATA",
    "_GTE_RERANKER_CONFIG",
    "_HRNETPOSE_CARD_DATA",
    "_HY_MOTION_CARD_DATA",
    "_HY_MOTION_CONFIG",
    "_KANANA_15V_CARD_DATA",
    "_KANANA_15V_CONFIG",
    "_KIMI_CARD_DATA",
    "_KIMI_CONFIG",
    "_KOKORO_CARD_DATA",
    "_KOKORO_CONFIG",
    "_LIGHTGLUE_CARD_DATA",
    "_LIGHTGLUE_CONFIG",
    "_LINE_DISTILBERT_CARD_DATA",
    "_LINE_DISTILBERT_CONFIG",
    "_LLADA2_MOE_CARD_DATA",
    "_LLADA2_MOE_CONFIG",
    "_LLAMA_CARD_DATA",
    "_LLASA_3B_CARD_DATA",
    "_LLASA_3B_CONFIG",
    "_MIMO_AUDIO_CARD_DATA",
    "_MIMO_AUDIO_CONFIG",
    "_MINIMAX_M2_CARD_DATA",
    "_MINIMAX_M2_CONFIG",
    "_MISTRAL_CARD_DATA",
    "_MISTRAL_CONFIG",
    "_MISTRAL_TOKENIZER_CONFIG",
    "_MLX_GEMMA4_CARD_DATA",
    "_MLX_GEMMA4_CONFIG",
    "_MMADA_CARD_DATA",
    "_MMADA_CONFIG",
    "_MOIRAI_CARD_DATA",
    "_MOIRAI_CONFIG",
    "_NLLB_CONFIG",
    "_NLLB_TOKENIZER_CONFIG",
    "_NOMIC_GGUF_CARD_DATA",
    "_OCCIGLOT_CARD_DATA",
    "_OCCIGLOT_CONFIG",
    "_OCCIGLOT_TOKENIZER_SENTINEL",
    "_ONNX_GEMMA4_CARD_DATA",
    "_ONNX_GEMMA4_CONFIG",
    "_OPENELM_270M_CARD_DATA",
    "_OPENELM_270M_CONFIG",
    "_OPENEUROLLM_CARD_DATA",
    "_OPENEUROLLM_CONFIG",
    "_OPENTHAIGPT_CARD_DATA",
    "_OPENTHAIGPT_CONFIG",
    "_OPENVINO_MIXTRAL_CARD_DATA",
    "_OPENVINO_MIXTRAL_CONFIG",
    "_PHARIA_ALIGNED_CARD_DATA",
    "_PHARIA_CONTROL_CARD_DATA",
    "_QWEN35_27B_CARD_DATA",
    "_QWEN35_27B_CONFIG",
    "_QWEN3_235B_CARD_DATA",
    "_QWEN3_235B_CONFIG",
    "_QWEN3_235B_GENERATION_CONFIG",
    "_RTDETR_COCO_CARD_DATA",
    "_RTDETR_COCO_O365_CARD_DATA",
    "_RTDETR_COCO_O365_CONFIG",
    "_RURI_CARD_DATA",
    "_RURI_CONFIG",
    "_SAILOR2_20B_CARD_DATA",
    "_SAILOR2_20B_CONFIG",
    "_SAP_RPT_CARD_DATA",
    "_SEALION_CARD_DATA",
    "_SEALLMS_CARD_DATA",
    "_SEALLMS_CONFIG",
    "_SENSENOVA_CARD_DATA",
    "_SENSENOVA_CONFIG",
    "_SERENGETI_CONFIG",
    "_SERENGETI_TOKENIZER_CONFIG",
    "_SHAP_E_CARD_DATA",
    "_SONOISA_CARD_DATA",
    "_SONOISA_CONFIG",
    "_STABLE_ZERO123_CARD_DATA",
    "_STANZA_DE_CARD_DATA",
    "_STANZA_FI_CARD_DATA",
    "_STARCODER2_CARD_DATA",
    "_STARCODER2_CONFIG",
    "_SUGOI_CARD_DATA",
    "_TALKIE_CARD_DATA",
    "_TILDEOPEN_30B_64K_CARD_DATA",
    "_TILDEOPEN_30B_64K_CONFIG",
    "_TILDEOPEN_30B_CARD_DATA",
    "_TILDEOPEN_30B_CONFIG",
    "_TILDEOPEN_TOKENIZER_SENTINEL",
    "_TIMELENS_CARD_DATA",
    "_TIMELENS_CONFIG",
    "_TRADEPULSE_CARD_DATA",
    "_TRADEPULSE_CONFIG",
    "_TYPHOON_CARD_DATA",
    "_TYPHOON_CONFIG",
    "_VNTL_CARD_DATA",
    "_VOXTRAL_MINI_CARD_DATA",
    "_VOXTRAL_MINI_CONFIG",
    "_WANGCHANX_LEGAL_CARD_DATA",
    "_WANGCHANX_LEGAL_CONFIG",
    "_WAV2VEC2_JP_CARD_DATA",
    "_WAV2VEC2_JP_CONFIG",
    "_WAV2VEC2_JP_MODEL_INDEX",
    "_WHISPER_CARD_DATA",
    "_WHISPER_CONFIG",
    "_WHISPER_LANGUAGES",
    "_WINDOWSEAT_CARD_DATA",
    "_make_card_data",
    "_patch_aion",
    "_patch_apple_sharp",
    "_patch_arabic_legal_ocr",
    "_patch_aspect_finnlp_th",
    "_patch_aya_vision",
    "_patch_bagel",
    "_patch_bert_turkish",
    "_patch_blenderllm",
    "_patch_blenderllm_gguf",
    "_patch_blip_vqa",
    "_patch_bloom",
    "_patch_bloomz_7b1",
    "_patch_boba_food_gguf",
    "_patch_chinda",
    "_patch_chinda_gguf",
    "_patch_clip_japanese_v2",
    "_patch_codeberta",
    "_patch_cohere_aya_23",
    "_patch_cross_encoder",
    "_patch_crow_9b",
    "_patch_darwin_kr_legal",
    "_patch_deberta_human_value",
    "_patch_deepseek",
    "_patch_deplot",
    "_patch_depth_pro",
    "_patch_dinov2",
    "_patch_distilbert_multilingual",
    "_patch_donut",
    "_patch_ernie_image_turbo",
    "_patch_eurollm_1b7",
    "_patch_exaone45_33b",
    "_patch_exaone45_33b_awq",
    "_patch_exaone45_33b_fp8",
    "_patch_exaone45_33b_gguf",
    "_patch_exaone_path",
    "_patch_falconsai",
    "_patch_fibo_edit",
    "_patch_fineweb_edu",
    "_patch_firered_vad",
    "_patch_flood_image_detect",
    "_patch_fujitsu_llm",
    "_patch_gabert",
    "_patch_gemma",
    "_patch_glm45_air_reap",
    "_patch_gpt_neo_2_7b",
    "_patch_gpt_neox_jp",
    "_patch_granite_4_1_8b",
    "_patch_granite_embed",
    "_patch_granite_geo_flood",
    "_patch_granite_speech",
    "_patch_groot",
    "_patch_gte_modernbert",
    "_patch_gte_reranker",
    "_patch_hermes_3_llama_3b",
    "_patch_hf_calls",
    "_patch_hrnetpose",
    "_patch_hunyuan_mt",
    "_patch_hunyuan_mt7b",
    "_patch_hy_motion",
    "_patch_hy_mt_gguf",
    "_patch_ii_medical",
    "_patch_indic_conformer",
    "_patch_inkubalm",
    "_patch_ipa_whisper",
    "_patch_jina_v4",
    "_patch_kanana_15v",
    "_patch_kimi",
    "_patch_kokoro",
    "_patch_laguna",
    "_patch_laion_clip",
    "_patch_layoutlm",
    "_patch_legal_embed_ita",
    "_patch_lightglue",
    "_patch_line_distilbert",
    "_patch_llada2_moe",
    "_patch_llama",
    "_patch_llama_3_2_3b",
    "_patch_llama_3_2_3b_instruct",
    "_patch_llasa_3b",
    "_patch_llava_video",
    "_patch_llmjp",
    "_patch_mallam",
    "_patch_marigold",
    "_patch_mimo_asr_gguf",
    "_patch_mimo_audio",
    "_patch_minimax_m2",
    "_patch_mistral_medium",
    "_patch_mlx_gemma4",
    "_patch_mmada",
    "_patch_moirai",
    "_patch_nemotron",
    "_patch_nllb",
    "_patch_nomic_gguf",
    "_patch_occiglot",
    "_patch_omnivoice",
    "_patch_omnivoice_bf16",
    "_patch_onnx_gemma4",
    "_patch_openelm_270m",
    "_patch_openeurollm",
    "_patch_openthaigpt",
    "_patch_openvino_mixtral",
    "_patch_openvla",
    "_patch_opt_2_7b",
    "_patch_opt_iml",
    "_patch_opus_mt_th_en",
    "_patch_pharia_aligned",
    "_patch_pharia_control",
    "_patch_phi2",
    "_patch_pi05",
    "_patch_privacy_filter",
    "_patch_protonx_legal",
    "_patch_pyannote_diar",
    "_patch_qwen35_27b",
    "_patch_qwen3_235b",
    "_patch_qwen3_reap",
    "_patch_qwen3_swallow",
    "_patch_rad_dino",
    "_patch_resnet18",
    "_patch_rmbg14",
    "_patch_rmbg20",
    "_patch_rtdetr_coco",
    "_patch_rtdetr_coco_o365",
    "_patch_ruri",
    "_patch_sailor2_20b",
    "_patch_sap_rpt",
    "_patch_sealion_27b_it",
    "_patch_sealion_gguf",
    "_patch_sealion_vl",
    "_patch_seallms",
    "_patch_seamless_m4t",
    "_patch_sensenova",
    "_patch_serengeti",
    "_patch_shap_e",
    "_patch_sonoisa",
    "_patch_stable_zero123",
    "_patch_stablelm_zephyr",
    "_patch_stanza_de",
    "_patch_stanza_fi",
    "_patch_starcoder2",
    "_patch_streetclip",
    "_patch_sugoi",
    "_patch_swin",
    "_patch_talkie",
    "_patch_tapas",
    "_patch_tildeopen_30b",
    "_patch_tildeopen_30b_64k",
    "_patch_timelens",
    "_patch_timm_convnext",
    "_patch_tinyllama_chat",
    "_patch_tradepulse",
    "_patch_typhoon",
    "_patch_uni2",
    "_patch_vibevoice_asr",
    "_patch_vilt_vqa",
    "_patch_vitpose",
    "_patch_vntl",
    "_patch_voxtral_mini",
    "_patch_wangchanglm",
    "_patch_wangchanx_legal",
    "_patch_wav2vec2_id_jv_su",
    "_patch_wav2vec2_jp",
    "_patch_whisper",
    "_patch_windowseat",
    "_patch_wmt22_cometkiwi",
    "_patch_xlm_roberta_base",
    "annotations",
    "patch",
]

__all__ = [
    "Any",
    "MagicMock",
    "_AION_CARD_DATA",
    "_AION_CONFIG",
    "_APPLE_SHARP_CARD_DATA",
    "_BAGEL_CARD_DATA",
    "_BAGEL_CONFIG",
    "_BERT_TURKISH_CARD_DATA",
    "_BERT_TURKISH_CONFIG",
    "_BLENDERLLM_CARD_DATA",
    "_BLENDERLLM_CONFIG",
    "_BLENDERLLM_GGUF_CARD_DATA",
    "_BLOOMZ_7B1_CARD_DATA",
    "_BLOOMZ_7B1_CONFIG",
    "_BLOOM_CARD_DATA",
    "_BLOOM_CONFIG",
    "_CHINDA_CARD_DATA",
    "_CHINDA_CONFIG",
    "_CHINDA_GGUF_CARD_DATA",
    "_CLIP_JAPANESE_V2_CARD_DATA",
    "_CLIP_JAPANESE_V2_CONFIG",
    "_CODEBERTA_CARD_DATA",
    "_CODEBERTA_CONFIG",
    "_CROSS_ENCODER_CARD_DATA",
    "_CROSS_ENCODER_CONFIG",
    "_DEEPSEEK_CARD_DATA",
    "_DEEPSEEK_CONFIG",
    "_EUROLLM_1B7_CARD_DATA",
    "_EUROLLM_1B7_CONFIG",
    "_EUROLLM_TOKENIZER_SENTINEL",
    "_EXAONE45_33B_AWQ_CARD_DATA",
    "_EXAONE45_33B_AWQ_CONFIG",
    "_EXAONE45_33B_CARD_DATA",
    "_EXAONE45_33B_CONFIG",
    "_EXAONE45_33B_FP8_CARD_DATA",
    "_EXAONE45_33B_FP8_CONFIG",
    "_EXAONE45_33B_GGUF_CARD_DATA",
    "_EXAONE_PATH_CARD_DATA",
    "_FIRERED_VAD_CARD_DATA",
    "_FUJITSU_LLM_CARD_DATA",
    "_GEMMA_CARD_DATA",
    "_GLM45_AIR_REAP_CARD_DATA",
    "_GLM45_AIR_REAP_CONFIG",
    "_GTE_MODERNBERT_CARD_DATA",
    "_GTE_MODERNBERT_CONFIG",
    "_GTE_RERANKER_CARD_DATA",
    "_GTE_RERANKER_CONFIG",
    "_HRNETPOSE_CARD_DATA",
    "_HY_MOTION_CARD_DATA",
    "_HY_MOTION_CONFIG",
    "_KANANA_15V_CARD_DATA",
    "_KANANA_15V_CONFIG",
    "_KIMI_CARD_DATA",
    "_KIMI_CONFIG",
    "_KOKORO_CARD_DATA",
    "_KOKORO_CONFIG",
    "_LIGHTGLUE_CARD_DATA",
    "_LIGHTGLUE_CONFIG",
    "_LINE_DISTILBERT_CARD_DATA",
    "_LINE_DISTILBERT_CONFIG",
    "_LLADA2_MOE_CARD_DATA",
    "_LLADA2_MOE_CONFIG",
    "_LLAMA_CARD_DATA",
    "_LLASA_3B_CARD_DATA",
    "_LLASA_3B_CONFIG",
    "_MIMO_AUDIO_CARD_DATA",
    "_MIMO_AUDIO_CONFIG",
    "_MINIMAX_M2_CARD_DATA",
    "_MINIMAX_M2_CONFIG",
    "_MISTRAL_CARD_DATA",
    "_MISTRAL_CONFIG",
    "_MISTRAL_TOKENIZER_CONFIG",
    "_MLX_GEMMA4_CARD_DATA",
    "_MLX_GEMMA4_CONFIG",
    "_MMADA_CARD_DATA",
    "_MMADA_CONFIG",
    "_MOIRAI_CARD_DATA",
    "_MOIRAI_CONFIG",
    "_NLLB_CONFIG",
    "_NLLB_TOKENIZER_CONFIG",
    "_NOMIC_GGUF_CARD_DATA",
    "_OCCIGLOT_CARD_DATA",
    "_OCCIGLOT_CONFIG",
    "_OCCIGLOT_TOKENIZER_SENTINEL",
    "_ONNX_GEMMA4_CARD_DATA",
    "_ONNX_GEMMA4_CONFIG",
    "_OPENELM_270M_CARD_DATA",
    "_OPENELM_270M_CONFIG",
    "_OPENEUROLLM_CARD_DATA",
    "_OPENEUROLLM_CONFIG",
    "_OPENTHAIGPT_CARD_DATA",
    "_OPENTHAIGPT_CONFIG",
    "_OPENVINO_MIXTRAL_CARD_DATA",
    "_OPENVINO_MIXTRAL_CONFIG",
    "_PHARIA_ALIGNED_CARD_DATA",
    "_PHARIA_CONTROL_CARD_DATA",
    "_QWEN35_27B_CARD_DATA",
    "_QWEN35_27B_CONFIG",
    "_QWEN3_235B_CARD_DATA",
    "_QWEN3_235B_CONFIG",
    "_QWEN3_235B_GENERATION_CONFIG",
    "_RTDETR_COCO_CARD_DATA",
    "_RTDETR_COCO_O365_CARD_DATA",
    "_RTDETR_COCO_O365_CONFIG",
    "_RURI_CARD_DATA",
    "_RURI_CONFIG",
    "_SAILOR2_20B_CARD_DATA",
    "_SAILOR2_20B_CONFIG",
    "_SAP_RPT_CARD_DATA",
    "_SEALION_CARD_DATA",
    "_SEALLMS_CARD_DATA",
    "_SEALLMS_CONFIG",
    "_SENSENOVA_CARD_DATA",
    "_SENSENOVA_CONFIG",
    "_SERENGETI_CONFIG",
    "_SERENGETI_TOKENIZER_CONFIG",
    "_SHAP_E_CARD_DATA",
    "_SONOISA_CARD_DATA",
    "_SONOISA_CONFIG",
    "_STABLE_ZERO123_CARD_DATA",
    "_STANZA_DE_CARD_DATA",
    "_STANZA_FI_CARD_DATA",
    "_STARCODER2_CARD_DATA",
    "_STARCODER2_CONFIG",
    "_SUGOI_CARD_DATA",
    "_TALKIE_CARD_DATA",
    "_TILDEOPEN_30B_64K_CARD_DATA",
    "_TILDEOPEN_30B_64K_CONFIG",
    "_TILDEOPEN_30B_CARD_DATA",
    "_TILDEOPEN_30B_CONFIG",
    "_TILDEOPEN_TOKENIZER_SENTINEL",
    "_TIMELENS_CARD_DATA",
    "_TIMELENS_CONFIG",
    "_TRADEPULSE_CARD_DATA",
    "_TRADEPULSE_CONFIG",
    "_TYPHOON_CARD_DATA",
    "_TYPHOON_CONFIG",
    "_VNTL_CARD_DATA",
    "_VOXTRAL_MINI_CARD_DATA",
    "_VOXTRAL_MINI_CONFIG",
    "_WANGCHANX_LEGAL_CARD_DATA",
    "_WANGCHANX_LEGAL_CONFIG",
    "_WAV2VEC2_JP_CARD_DATA",
    "_WAV2VEC2_JP_CONFIG",
    "_WAV2VEC2_JP_MODEL_INDEX",
    "_WHISPER_CARD_DATA",
    "_WHISPER_CONFIG",
    "_WHISPER_LANGUAGES",
    "_WINDOWSEAT_CARD_DATA",
    "_make_card_data",
    "_patch_aion",
    "_patch_apple_sharp",
    "_patch_arabic_legal_ocr",
    "_patch_aspect_finnlp_th",
    "_patch_aya_vision",
    "_patch_bagel",
    "_patch_bert_turkish",
    "_patch_blenderllm",
    "_patch_blenderllm_gguf",
    "_patch_blip_vqa",
    "_patch_bloom",
    "_patch_bloomz_7b1",
    "_patch_boba_food_gguf",
    "_patch_chinda",
    "_patch_chinda_gguf",
    "_patch_clip_japanese_v2",
    "_patch_codeberta",
    "_patch_cohere_aya_23",
    "_patch_cross_encoder",
    "_patch_crow_9b",
    "_patch_darwin_kr_legal",
    "_patch_deberta_human_value",
    "_patch_deepseek",
    "_patch_deplot",
    "_patch_depth_pro",
    "_patch_dinov2",
    "_patch_distilbert_multilingual",
    "_patch_donut",
    "_patch_ernie_image_turbo",
    "_patch_eurollm_1b7",
    "_patch_exaone45_33b",
    "_patch_exaone45_33b_awq",
    "_patch_exaone45_33b_fp8",
    "_patch_exaone45_33b_gguf",
    "_patch_exaone_path",
    "_patch_falconsai",
    "_patch_fibo_edit",
    "_patch_fineweb_edu",
    "_patch_firered_vad",
    "_patch_flood_image_detect",
    "_patch_fujitsu_llm",
    "_patch_gabert",
    "_patch_gemma",
    "_patch_glm45_air_reap",
    "_patch_gpt_neo_2_7b",
    "_patch_gpt_neox_jp",
    "_patch_granite_4_1_8b",
    "_patch_granite_embed",
    "_patch_granite_geo_flood",
    "_patch_granite_speech",
    "_patch_groot",
    "_patch_gte_modernbert",
    "_patch_gte_reranker",
    "_patch_hermes_3_llama_3b",
    "_patch_hf_calls",
    "_patch_hrnetpose",
    "_patch_hunyuan_mt",
    "_patch_hunyuan_mt7b",
    "_patch_hy_motion",
    "_patch_hy_mt_gguf",
    "_patch_ii_medical",
    "_patch_indic_conformer",
    "_patch_inkubalm",
    "_patch_ipa_whisper",
    "_patch_jina_v4",
    "_patch_kanana_15v",
    "_patch_kimi",
    "_patch_kokoro",
    "_patch_laguna",
    "_patch_laion_clip",
    "_patch_layoutlm",
    "_patch_legal_embed_ita",
    "_patch_lightglue",
    "_patch_line_distilbert",
    "_patch_llada2_moe",
    "_patch_llama",
    "_patch_llama_3_2_3b",
    "_patch_llama_3_2_3b_instruct",
    "_patch_llasa_3b",
    "_patch_llava_video",
    "_patch_llmjp",
    "_patch_mallam",
    "_patch_marigold",
    "_patch_mimo_asr_gguf",
    "_patch_mimo_audio",
    "_patch_minimax_m2",
    "_patch_mistral_medium",
    "_patch_mlx_gemma4",
    "_patch_mmada",
    "_patch_moirai",
    "_patch_nemotron",
    "_patch_nllb",
    "_patch_nomic_gguf",
    "_patch_occiglot",
    "_patch_omnivoice",
    "_patch_omnivoice_bf16",
    "_patch_onnx_gemma4",
    "_patch_openelm_270m",
    "_patch_openeurollm",
    "_patch_openthaigpt",
    "_patch_openvino_mixtral",
    "_patch_openvla",
    "_patch_opt_2_7b",
    "_patch_opt_iml",
    "_patch_opus_mt_th_en",
    "_patch_pharia_aligned",
    "_patch_pharia_control",
    "_patch_phi2",
    "_patch_pi05",
    "_patch_privacy_filter",
    "_patch_protonx_legal",
    "_patch_pyannote_diar",
    "_patch_qwen35_27b",
    "_patch_qwen3_235b",
    "_patch_qwen3_reap",
    "_patch_qwen3_swallow",
    "_patch_rad_dino",
    "_patch_resnet18",
    "_patch_rmbg14",
    "_patch_rmbg20",
    "_patch_rtdetr_coco",
    "_patch_rtdetr_coco_o365",
    "_patch_ruri",
    "_patch_sailor2_20b",
    "_patch_sap_rpt",
    "_patch_sealion_27b_it",
    "_patch_sealion_gguf",
    "_patch_sealion_vl",
    "_patch_seallms",
    "_patch_seamless_m4t",
    "_patch_sensenova",
    "_patch_serengeti",
    "_patch_shap_e",
    "_patch_sonoisa",
    "_patch_stable_zero123",
    "_patch_stablelm_zephyr",
    "_patch_stanza_de",
    "_patch_stanza_fi",
    "_patch_starcoder2",
    "_patch_streetclip",
    "_patch_sugoi",
    "_patch_swin",
    "_patch_talkie",
    "_patch_tapas",
    "_patch_tildeopen_30b",
    "_patch_tildeopen_30b_64k",
    "_patch_timelens",
    "_patch_timm_convnext",
    "_patch_tinyllama_chat",
    "_patch_tradepulse",
    "_patch_typhoon",
    "_patch_uni2",
    "_patch_vibevoice_asr",
    "_patch_vilt_vqa",
    "_patch_vitpose",
    "_patch_vntl",
    "_patch_voxtral_mini",
    "_patch_wangchanglm",
    "_patch_wangchanx_legal",
    "_patch_wav2vec2_id_jv_su",
    "_patch_wav2vec2_jp",
    "_patch_whisper",
    "_patch_windowseat",
    "_patch_wmt22_cometkiwi",
    "_patch_xlm_roberta_base",
    "annotations",
    "patch",
]

__all__ = [
    "Any",
    "MagicMock",
    "_AION_CARD_DATA",
    "_AION_CONFIG",
    "_APPLE_SHARP_CARD_DATA",
    "_BAGEL_CARD_DATA",
    "_BAGEL_CONFIG",
    "_BERT_TURKISH_CARD_DATA",
    "_BERT_TURKISH_CONFIG",
    "_BLENDERLLM_CARD_DATA",
    "_BLENDERLLM_CONFIG",
    "_BLENDERLLM_GGUF_CARD_DATA",
    "_BLOOMZ_7B1_CARD_DATA",
    "_BLOOMZ_7B1_CONFIG",
    "_BLOOM_CARD_DATA",
    "_BLOOM_CONFIG",
    "_CHINDA_CARD_DATA",
    "_CHINDA_CONFIG",
    "_CHINDA_GGUF_CARD_DATA",
    "_CLIP_JAPANESE_V2_CARD_DATA",
    "_CLIP_JAPANESE_V2_CONFIG",
    "_CODEBERTA_CARD_DATA",
    "_CODEBERTA_CONFIG",
    "_CROSS_ENCODER_CARD_DATA",
    "_CROSS_ENCODER_CONFIG",
    "_DEEPSEEK_CARD_DATA",
    "_DEEPSEEK_CONFIG",
    "_EUROLLM_1B7_CARD_DATA",
    "_EUROLLM_1B7_CONFIG",
    "_EUROLLM_TOKENIZER_SENTINEL",
    "_EXAONE45_33B_AWQ_CARD_DATA",
    "_EXAONE45_33B_AWQ_CONFIG",
    "_EXAONE45_33B_CARD_DATA",
    "_EXAONE45_33B_CONFIG",
    "_EXAONE45_33B_FP8_CARD_DATA",
    "_EXAONE45_33B_FP8_CONFIG",
    "_EXAONE45_33B_GGUF_CARD_DATA",
    "_EXAONE_PATH_CARD_DATA",
    "_FIRERED_VAD_CARD_DATA",
    "_FUJITSU_LLM_CARD_DATA",
    "_GEMMA_CARD_DATA",
    "_GLM45_AIR_REAP_CARD_DATA",
    "_GLM45_AIR_REAP_CONFIG",
    "_GTE_MODERNBERT_CARD_DATA",
    "_GTE_MODERNBERT_CONFIG",
    "_GTE_RERANKER_CARD_DATA",
    "_GTE_RERANKER_CONFIG",
    "_HRNETPOSE_CARD_DATA",
    "_HY_MOTION_CARD_DATA",
    "_HY_MOTION_CONFIG",
    "_KANANA_15V_CARD_DATA",
    "_KANANA_15V_CONFIG",
    "_KIMI_CARD_DATA",
    "_KIMI_CONFIG",
    "_KOKORO_CARD_DATA",
    "_KOKORO_CONFIG",
    "_LIGHTGLUE_CARD_DATA",
    "_LIGHTGLUE_CONFIG",
    "_LINE_DISTILBERT_CARD_DATA",
    "_LINE_DISTILBERT_CONFIG",
    "_LLADA2_MOE_CARD_DATA",
    "_LLADA2_MOE_CONFIG",
    "_LLAMA_CARD_DATA",
    "_LLASA_3B_CARD_DATA",
    "_LLASA_3B_CONFIG",
    "_MIMO_AUDIO_CARD_DATA",
    "_MIMO_AUDIO_CONFIG",
    "_MINIMAX_M2_CARD_DATA",
    "_MINIMAX_M2_CONFIG",
    "_MISTRAL_CARD_DATA",
    "_MISTRAL_CONFIG",
    "_MISTRAL_TOKENIZER_CONFIG",
    "_MLX_GEMMA4_CARD_DATA",
    "_MLX_GEMMA4_CONFIG",
    "_MMADA_CARD_DATA",
    "_MMADA_CONFIG",
    "_MOIRAI_CARD_DATA",
    "_MOIRAI_CONFIG",
    "_NLLB_CONFIG",
    "_NLLB_TOKENIZER_CONFIG",
    "_NOMIC_GGUF_CARD_DATA",
    "_OCCIGLOT_CARD_DATA",
    "_OCCIGLOT_CONFIG",
    "_OCCIGLOT_TOKENIZER_SENTINEL",
    "_ONNX_GEMMA4_CARD_DATA",
    "_ONNX_GEMMA4_CONFIG",
    "_OPENELM_270M_CARD_DATA",
    "_OPENELM_270M_CONFIG",
    "_OPENEUROLLM_CARD_DATA",
    "_OPENEUROLLM_CONFIG",
    "_OPENTHAIGPT_CARD_DATA",
    "_OPENTHAIGPT_CONFIG",
    "_OPENVINO_MIXTRAL_CARD_DATA",
    "_OPENVINO_MIXTRAL_CONFIG",
    "_PHARIA_ALIGNED_CARD_DATA",
    "_PHARIA_CONTROL_CARD_DATA",
    "_QWEN35_27B_CARD_DATA",
    "_QWEN35_27B_CONFIG",
    "_QWEN3_235B_CARD_DATA",
    "_QWEN3_235B_CONFIG",
    "_QWEN3_235B_GENERATION_CONFIG",
    "_RTDETR_COCO_CARD_DATA",
    "_RTDETR_COCO_O365_CARD_DATA",
    "_RTDETR_COCO_O365_CONFIG",
    "_RURI_CARD_DATA",
    "_RURI_CONFIG",
    "_SAILOR2_20B_CARD_DATA",
    "_SAILOR2_20B_CONFIG",
    "_SAP_RPT_CARD_DATA",
    "_SEALION_CARD_DATA",
    "_SEALLMS_CARD_DATA",
    "_SEALLMS_CONFIG",
    "_SENSENOVA_CARD_DATA",
    "_SENSENOVA_CONFIG",
    "_SERENGETI_CONFIG",
    "_SERENGETI_TOKENIZER_CONFIG",
    "_SHAP_E_CARD_DATA",
    "_SONOISA_CARD_DATA",
    "_SONOISA_CONFIG",
    "_STABLE_ZERO123_CARD_DATA",
    "_STANZA_DE_CARD_DATA",
    "_STANZA_FI_CARD_DATA",
    "_STARCODER2_CARD_DATA",
    "_STARCODER2_CONFIG",
    "_SUGOI_CARD_DATA",
    "_TALKIE_CARD_DATA",
    "_TILDEOPEN_30B_64K_CARD_DATA",
    "_TILDEOPEN_30B_64K_CONFIG",
    "_TILDEOPEN_30B_CARD_DATA",
    "_TILDEOPEN_30B_CONFIG",
    "_TILDEOPEN_TOKENIZER_SENTINEL",
    "_TIMELENS_CARD_DATA",
    "_TIMELENS_CONFIG",
    "_TRADEPULSE_CARD_DATA",
    "_TRADEPULSE_CONFIG",
    "_TYPHOON_CARD_DATA",
    "_TYPHOON_CONFIG",
    "_VNTL_CARD_DATA",
    "_VOXTRAL_MINI_CARD_DATA",
    "_VOXTRAL_MINI_CONFIG",
    "_WANGCHANX_LEGAL_CARD_DATA",
    "_WANGCHANX_LEGAL_CONFIG",
    "_WAV2VEC2_JP_CARD_DATA",
    "_WAV2VEC2_JP_CONFIG",
    "_WAV2VEC2_JP_MODEL_INDEX",
    "_WHISPER_CARD_DATA",
    "_WHISPER_CONFIG",
    "_WHISPER_LANGUAGES",
    "_WINDOWSEAT_CARD_DATA",
    "_make_card_data",
    "_patch_aion",
    "_patch_apple_sharp",
    "_patch_arabic_legal_ocr",
    "_patch_aspect_finnlp_th",
    "_patch_aya_vision",
    "_patch_bagel",
    "_patch_bert_turkish",
    "_patch_blenderllm",
    "_patch_blenderllm_gguf",
    "_patch_blip_vqa",
    "_patch_bloom",
    "_patch_bloomz_7b1",
    "_patch_boba_food_gguf",
    "_patch_chinda",
    "_patch_chinda_gguf",
    "_patch_clip_japanese_v2",
    "_patch_codeberta",
    "_patch_cohere_aya_23",
    "_patch_cross_encoder",
    "_patch_crow_9b",
    "_patch_darwin_kr_legal",
    "_patch_deberta_human_value",
    "_patch_deepseek",
    "_patch_deplot",
    "_patch_depth_pro",
    "_patch_dinov2",
    "_patch_distilbert_multilingual",
    "_patch_donut",
    "_patch_ernie_image_turbo",
    "_patch_eurollm_1b7",
    "_patch_exaone45_33b",
    "_patch_exaone45_33b_awq",
    "_patch_exaone45_33b_fp8",
    "_patch_exaone45_33b_gguf",
    "_patch_exaone_path",
    "_patch_falconsai",
    "_patch_fibo_edit",
    "_patch_fineweb_edu",
    "_patch_firered_vad",
    "_patch_flood_image_detect",
    "_patch_fujitsu_llm",
    "_patch_gabert",
    "_patch_gemma",
    "_patch_glm45_air_reap",
    "_patch_gpt_neo_2_7b",
    "_patch_gpt_neox_jp",
    "_patch_granite_4_1_8b",
    "_patch_granite_embed",
    "_patch_granite_geo_flood",
    "_patch_granite_speech",
    "_patch_groot",
    "_patch_gte_modernbert",
    "_patch_gte_reranker",
    "_patch_hermes_3_llama_3b",
    "_patch_hf_calls",
    "_patch_hrnetpose",
    "_patch_hunyuan_mt",
    "_patch_hunyuan_mt7b",
    "_patch_hy_motion",
    "_patch_hy_mt_gguf",
    "_patch_ii_medical",
    "_patch_indic_conformer",
    "_patch_inkubalm",
    "_patch_ipa_whisper",
    "_patch_jina_v4",
    "_patch_kanana_15v",
    "_patch_kimi",
    "_patch_kokoro",
    "_patch_laguna",
    "_patch_laion_clip",
    "_patch_layoutlm",
    "_patch_legal_embed_ita",
    "_patch_lightglue",
    "_patch_line_distilbert",
    "_patch_llada2_moe",
    "_patch_llama",
    "_patch_llama_3_2_3b",
    "_patch_llama_3_2_3b_instruct",
    "_patch_llasa_3b",
    "_patch_llava_video",
    "_patch_llmjp",
    "_patch_mallam",
    "_patch_marigold",
    "_patch_mimo_asr_gguf",
    "_patch_mimo_audio",
    "_patch_minimax_m2",
    "_patch_mistral_medium",
    "_patch_mlx_gemma4",
    "_patch_mmada",
    "_patch_moirai",
    "_patch_nemotron",
    "_patch_nllb",
    "_patch_nomic_gguf",
    "_patch_occiglot",
    "_patch_omnivoice",
    "_patch_omnivoice_bf16",
    "_patch_onnx_gemma4",
    "_patch_openelm_270m",
    "_patch_openeurollm",
    "_patch_openthaigpt",
    "_patch_openvino_mixtral",
    "_patch_openvla",
    "_patch_opt_2_7b",
    "_patch_opt_iml",
    "_patch_opus_mt_th_en",
    "_patch_pharia_aligned",
    "_patch_pharia_control",
    "_patch_phi2",
    "_patch_pi05",
    "_patch_privacy_filter",
    "_patch_protonx_legal",
    "_patch_pyannote_diar",
    "_patch_qwen35_27b",
    "_patch_qwen3_235b",
    "_patch_qwen3_reap",
    "_patch_qwen3_swallow",
    "_patch_rad_dino",
    "_patch_resnet18",
    "_patch_rmbg14",
    "_patch_rmbg20",
    "_patch_rtdetr_coco",
    "_patch_rtdetr_coco_o365",
    "_patch_ruri",
    "_patch_sailor2_20b",
    "_patch_sap_rpt",
    "_patch_sealion_27b_it",
    "_patch_sealion_gguf",
    "_patch_sealion_vl",
    "_patch_seallms",
    "_patch_seamless_m4t",
    "_patch_sensenova",
    "_patch_serengeti",
    "_patch_shap_e",
    "_patch_sonoisa",
    "_patch_stable_zero123",
    "_patch_stablelm_zephyr",
    "_patch_stanza_de",
    "_patch_stanza_fi",
    "_patch_starcoder2",
    "_patch_streetclip",
    "_patch_sugoi",
    "_patch_swin",
    "_patch_talkie",
    "_patch_tapas",
    "_patch_tildeopen_30b",
    "_patch_tildeopen_30b_64k",
    "_patch_timelens",
    "_patch_timm_convnext",
    "_patch_tinyllama_chat",
    "_patch_tradepulse",
    "_patch_typhoon",
    "_patch_uni2",
    "_patch_vibevoice_asr",
    "_patch_vilt_vqa",
    "_patch_vitpose",
    "_patch_vntl",
    "_patch_voxtral_mini",
    "_patch_wangchanglm",
    "_patch_wangchanx_legal",
    "_patch_wav2vec2_id_jv_su",
    "_patch_wav2vec2_jp",
    "_patch_whisper",
    "_patch_windowseat",
    "_patch_wmt22_cometkiwi",
    "_patch_xlm_roberta_base",
    "annotations",
    "patch",
]
