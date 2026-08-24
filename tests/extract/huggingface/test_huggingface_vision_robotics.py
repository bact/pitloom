# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for vision, robotics, and vision-language models: image feature
extraction, pathology tags, robotic control, and visual question
answering.

See also: test_huggingface_embeddings.py, test_huggingface_gated_access.py,
test_huggingface_gated_metadata.py, test_huggingface_granite_misc.py,
test_huggingface_multimodal.py, test_huggingface_omni_modal.py,
test_huggingface_speech_misc.py, test_huggingface_structured_text.py,
test_huggingface_text_generation_instruct.py,
test_huggingface_text_generation_pretrained.py, test_huggingface_text_misc.py,
test_huggingface_vision.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .hf_patches._hf_patches_embeddings import (
    _patch_rad_dino,
    _patch_timm_convnext,
    _patch_uni2,
)
from .hf_patches._hf_patches_generative_3d import (
    _patch_apple_sharp,
    _patch_blenderllm,
    _patch_blenderllm_gguf,
    _patch_ernie_image_turbo,
    _patch_groot,
    _patch_hy_motion,
    _patch_openvla,
    _patch_pi05,
    _patch_shap_e,
    _patch_stable_zero123,
)
from .hf_patches._hf_patches_multimodal import (
    _patch_blip_vqa,
    _patch_deplot,
    _patch_sealion_vl,
    _patch_vilt_vqa,
)


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


def test_ernie_image_turbo_text_to_image_domain_diffusers() -> None:
    with _patch_ernie_image_turbo():
        meta = read_huggingface("baidu/ERNIE-Image-Turbo")
    assert "text-to-image" in meta.usage.domains
    assert meta.extra_data.get("hf.library_name") == "diffusers"


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
