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
    _patch_aion,
    _patch_apple_sharp,
    _patch_bagel,
    _patch_blenderllm,
    _patch_blenderllm_gguf,
    _patch_firered_vad,
    _patch_gte_reranker,
    _patch_hy_motion,
    _patch_lightglue,
    _patch_llada2_moe,
    _patch_mimo_audio,
    _patch_minimax_m2,
    _patch_mlx_gemma4,
    _patch_mmada,
    _patch_openelm_270m,
    _patch_openvino_mixtral,
    _patch_sensenova,
    _patch_shap_e,
    _patch_stanza_de,
    _patch_stanza_fi,
)


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
