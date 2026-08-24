# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for text and multilingual embedding/reranker models.

See also: test_huggingface_gated_access.py, test_huggingface_gated_metadata.py,
test_huggingface_granite_misc.py, test_huggingface_multimodal.py,
test_huggingface_omni_modal.py, test_huggingface_speech_misc.py,
test_huggingface_structured_text.py,
test_huggingface_text_generation_instruct.py,
test_huggingface_text_generation_pretrained.py, test_huggingface_text_misc.py,
test_huggingface_vision.py, test_huggingface_vision_robotics.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .hf_patches._hf_patches_embeddings import (
    _patch_clip_japanese_v2,
    _patch_codeberta,
    _patch_cross_encoder,
    _patch_dinov2,
    _patch_distilbert_multilingual,
    _patch_gte_modernbert,
    _patch_gte_reranker,
    _patch_line_distilbert,
    _patch_nomic_gguf,
    _patch_ruri,
    _patch_sonoisa,
    _patch_wangchanx_legal,
    _patch_xlm_roberta_base,
)


def test_sonoisa_language_scalar_string_normalised() -> None:
    # "ja" as a scalar must be stored as ["ja"], not as individual chars ["j","a"].
    with _patch_sonoisa():
        meta = read_huggingface("sonoisa/sentence-bert-base-ja-mean-tokens")
    assert meta.extra_lists.get("hf.language") == ["ja"]


def test_sonoisa_feature_extraction_domain() -> None:
    with _patch_sonoisa():
        meta = read_huggingface("sonoisa/sentence-bert-base-ja-mean-tokens")
    assert "feature-extraction" in meta.usage.domains


def test_sonoisa_sentence_bert_tags_in_extra_lists() -> None:
    # "sentence-bert" is not a domain tag -> extra_lists["hf.tags"]
    with _patch_sonoisa():
        meta = read_huggingface("sonoisa/sentence-bert-base-ja-mean-tokens")
    assert "sentence-bert" in meta.extra_lists.get("hf.tags", [])


def test_wangchanx_legal_base_model_extracted() -> None:
    with _patch_wangchanx_legal():
        meta = read_huggingface("airesearch/WangchanX-Legal-ThaiCCL-Retriever")
    assert meta.extra_data.get("hf.base_model") == "BAAI/bge-m3"


def test_wangchanx_legal_base_model_relation_finetune() -> None:
    with _patch_wangchanx_legal():
        meta = read_huggingface("airesearch/WangchanX-Legal-ThaiCCL-Retriever")
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_wangchanx_legal_xlm_roberta_architecture() -> None:
    with _patch_wangchanx_legal():
        meta = read_huggingface("airesearch/WangchanX-Legal-ThaiCCL-Retriever")
    assert meta.type_of_model == "xlm-roberta"
    assert meta.architecture == "XLMRobertaModel"


def test_wangchanx_legal_dataset_reference() -> None:
    with _patch_wangchanx_legal():
        meta = read_huggingface("airesearch/WangchanX-Legal-ThaiCCL-Retriever")
    assert any("WangchanX-Legal-ThaiCCL-RAG" in d.metadata.name for d in meta.datasets)


def test_ruri_arxiv_extracted() -> None:
    with _patch_ruri():
        meta = read_huggingface("cl-nagoya/ruri-v3-310m")
    assert "2409.07737" in meta.extra_lists.get("hf.arxiv", [])


def test_ruri_base_model_and_relation() -> None:
    with _patch_ruri():
        meta = read_huggingface("cl-nagoya/ruri-v3-310m")
    assert meta.extra_data.get("hf.base_model") == "cl-nagoya/ruri-v3-pt-310m"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_ruri_modernbert_architecture() -> None:
    with _patch_ruri():
        meta = read_huggingface("cl-nagoya/ruri-v3-310m")
    assert meta.type_of_model == "modernbert"


def test_nomic_gguf_base_model_quantized() -> None:
    with _patch_nomic_gguf():
        meta = read_huggingface("nomic-ai/nomic-embed-text-v1.5-GGUF")
    assert meta.extra_data.get("hf.base_model") == "nomic-ai/nomic-embed-text-v1.5"
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"


def test_dinov2_image_feature_extraction_domain() -> None:
    with _patch_dinov2():
        meta = read_huggingface("facebook/dinov2-small")
    assert "image-feature-extraction" in meta.usage.domains


def test_dinov2_architecture() -> None:
    with _patch_dinov2():
        meta = read_huggingface("facebook/dinov2-small")
    assert meta.type_of_model == "dinov2"
    assert meta.architecture == "Dinov2Model"


def test_xlm_roberta_fill_mask_domain_and_languages() -> None:
    with _patch_xlm_roberta_base():
        meta = read_huggingface("FacebookAI/xlm-roberta-base")
    assert "fill-mask" in meta.usage.domains
    langs = meta.extra_lists.get("hf.language", [])
    assert "hi" in langs and "ar" in langs and "zh" in langs


def test_distilbert_multilingual_fill_mask_and_6_layers() -> None:
    # DistilBERT halves BERT's 12 layers to 6.
    with _patch_distilbert_multilingual():
        meta = read_huggingface("distilbert/distilbert-base-multilingual-cased")
    assert "fill-mask" in meta.usage.domains
    assert meta.type_of_model == "distilbert"
    assert meta.hyperparameters.get("num_hidden_layers") == 6


def test_line_distilbert_type_of_model() -> None:
    with _patch_line_distilbert():
        meta = read_huggingface("line-corporation/line-distilbert-base-japanese")
    assert meta.type_of_model == "distilbert"


def test_line_distilbert_architecture() -> None:
    with _patch_line_distilbert():
        meta = read_huggingface("line-corporation/line-distilbert-base-japanese")
    assert meta.architecture == "DistilBertForMaskedLM"


def test_line_distilbert_six_layers() -> None:
    # DistilBERT halves BERT's 12 layers -> 6 layers
    with _patch_line_distilbert():
        meta = read_huggingface("line-corporation/line-distilbert-base-japanese")
    assert meta.hyperparameters.get("num_hidden_layers") == 6


def test_line_distilbert_fill_mask_domain() -> None:
    with _patch_line_distilbert():
        meta = read_huggingface("line-corporation/line-distilbert-base-japanese")
    assert "fill-mask" in meta.usage.domains


def test_clip_japanese_v2_type_of_model() -> None:
    # Custom "clyp" model_type stored as-is
    with _patch_clip_japanese_v2():
        meta = read_huggingface("line-corporation/clip-japanese-base-v2")
    assert meta.type_of_model == "clyp"


def test_clip_japanese_v2_architecture() -> None:
    with _patch_clip_japanese_v2():
        meta = read_huggingface("line-corporation/clip-japanese-base-v2")
    assert meta.architecture == "CLYPModel"


def test_clip_japanese_v2_feature_extraction_domain() -> None:
    with _patch_clip_japanese_v2():
        meta = read_huggingface("line-corporation/clip-japanese-base-v2")
    assert "feature-extraction" in meta.usage.domains


def test_clip_japanese_v2_hidden_size() -> None:
    with _patch_clip_japanese_v2():
        meta = read_huggingface("line-corporation/clip-japanese-base-v2")
    assert meta.hyperparameters.get("hidden_size") == 768


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
