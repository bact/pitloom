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
    _patch_bert_turkish,
    _patch_codeberta,
    _patch_cross_encoder,
    _patch_gte_modernbert,
    _patch_hrnetpose,
    _patch_onnx_gemma4,
    _patch_rtdetr_coco,
    _patch_rtdetr_coco_o365,
    _patch_sailor2_20b,
    _patch_sap_rpt,
    _patch_timelens,
    _patch_tradepulse,
)


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
    # object-detection is in _DOMAIN_TAGS -- captured as domain
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
    # Config 401 -> no type_of_model or architecture
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
    # All LM numeric keys are inside text_config -> not captured by _HYPER_KEYS
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
    # architectures key absent from config -> architecture=None
    with _patch_bert_turkish():
        meta = read_huggingface("dbmdz/bert-base-turkish-cased")
    assert meta.architecture is None


def test_bert_turkish_no_pipeline_tag_empty_domains() -> None:
    # No pipeline_tag in card -> empty usage.domains
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
    # hidden_size=384 -- half of standard BERT-base
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
