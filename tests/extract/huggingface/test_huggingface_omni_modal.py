# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for any-to-any omni-modal models.

See also: test_huggingface_embeddings.py, test_huggingface_gated_access.py,
test_huggingface_gated_metadata.py, test_huggingface_granite_misc.py,
test_huggingface_multimodal.py, test_huggingface_speech_misc.py,
test_huggingface_structured_text.py,
test_huggingface_text_generation_instruct.py,
test_huggingface_text_generation_pretrained.py, test_huggingface_text_misc.py,
test_huggingface_vision.py, test_huggingface_vision_robotics.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .hf_patches._hf_patches_omni_modal import (
    _patch_aion,
    _patch_bagel,
    _patch_llada2_moe,
    _patch_mimo_audio,
    _patch_mlx_gemma4,
    _patch_mmada,
    _patch_onnx_gemma4,
    _patch_sensenova,
)


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
    # All numeric keys are nested inside llm_config/vit_config -> not captured
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
    # Numeric keys only in nested llm_config -> not captured by extractor
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
    # ALiBi: no max_position_embeddings in config -> not in hyperparameters
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


def test_mlx_gemma4_type_of_model() -> None:
    # MLX: config.json accessible -> model_type extractable
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
