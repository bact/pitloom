# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for instruction-tuned text-generation models.

See also: test_huggingface_embeddings.py, test_huggingface_gated_access.py,
test_huggingface_gated_metadata.py, test_huggingface_granite_misc.py,
test_huggingface_multimodal.py, test_huggingface_omni_modal.py,
test_huggingface_speech_misc.py, test_huggingface_structured_text.py,
test_huggingface_text_generation_pretrained.py, test_huggingface_text_misc.py,
test_huggingface_vision.py, test_huggingface_vision_robotics.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .hf_patches._hf_patches_text_generation_instruct import (
    _patch_bloomz_7b1,
    _patch_crow_9b,
    _patch_glm45_air_reap,
    _patch_llama_3_2_3b_instruct,
    _patch_minimax_m2,
    _patch_occiglot,
    _patch_openvino_mixtral,
    _patch_pharia_aligned,
    _patch_pharia_control,
    _patch_qwen3_reap,
    _patch_stablelm_zephyr,
    _patch_tinyllama_chat,
)


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


def test_llama_3_2_3b_instruct_base_model_finetune() -> None:
    with _patch_llama_3_2_3b_instruct():
        meta = read_huggingface("meta-llama/Llama-3.2-3B-Instruct")
    assert meta.extra_data.get("hf.base_model") == "meta-llama/Llama-3.2-3B"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


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


def test_minimax_m2_type_of_model() -> None:
    with _patch_minimax_m2():
        meta = read_huggingface("MiniMaxAI/MiniMax-M2.7")
    assert meta.type_of_model == "minimax_m2"


def test_minimax_m2_architecture() -> None:
    with _patch_minimax_m2():
        meta = read_huggingface("MiniMaxAI/MiniMax-M2.7")
    assert meta.architecture == "MiniMaxM2ForCausalLM"


def test_minimax_m2_very_long_context() -> None:
    # max_position_embeddings=1_000_000 -> captured
    with _patch_minimax_m2():
        meta = read_huggingface("MiniMaxAI/MiniMax-M2.7")
    assert meta.hyperparameters.get("max_position_embeddings") == 1_000_000


def test_openvino_mixtral_type_of_model() -> None:
    # Config accessible despite OpenVINO quantization -> model_type extractable
    with _patch_openvino_mixtral():
        meta = read_huggingface("OpenVINO/Mixtral-8x7B-Instruct-v0.1-int8-ov")
    assert meta.type_of_model == "mixtral"


def test_openvino_mixtral_int8_dtype_captured() -> None:
    # torch_dtype="int8" is in _HYPER_KEYS -> captured even for quantized model
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
