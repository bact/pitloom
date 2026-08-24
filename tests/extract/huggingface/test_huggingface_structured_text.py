# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for tabular, time-series, and other structured-text models.

See also: test_huggingface_embeddings.py, test_huggingface_gated_access.py,
test_huggingface_gated_metadata.py, test_huggingface_granite_misc.py,
test_huggingface_multimodal.py, test_huggingface_omni_modal.py,
test_huggingface_speech_misc.py, test_huggingface_text_generation_instruct.py,
test_huggingface_text_generation_pretrained.py, test_huggingface_text_misc.py,
test_huggingface_vision.py, test_huggingface_vision_robotics.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .hf_patches._hf_patches_structured_text import (
    _patch_fineweb_edu,
    _patch_moirai,
    _patch_sap_rpt,
    _patch_sugoi,
    _patch_tapas,
    _patch_tradepulse,
    _patch_vntl,
)


def test_vntl_quantized_translation_gguf() -> None:
    with _patch_vntl():
        meta = read_huggingface("lmg-anon/vntl-llama3-8b-v2-gguf")
    assert meta.license == "llama3"
    assert meta.extra_data.get("hf.base_model") == "rinna/llama-3-youko-8b"
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"
    assert "translation" in meta.usage.domains


def test_sugoi_gguf_base_model_list_form() -> None:
    # base_model as a list ["sugoitoolkit/Sugoi-14B-Ultra-HF"]
    # - primary entry extracted.
    with _patch_sugoi():
        meta = read_huggingface("sugoitoolkit/Sugoi-14B-Ultra-GGUF")
    assert meta.extra_data.get("hf.base_model") == "sugoitoolkit/Sugoi-14B-Ultra-HF"
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"


def test_tapas_table_question_answering_domain() -> None:
    with _patch_tapas():
        meta = read_huggingface("google/tapas-large-finetuned-wtq")
    assert "table-question-answering" in meta.usage.domains


def test_tapas_language_scalar_string() -> None:
    with _patch_tapas():
        meta = read_huggingface("google/tapas-large-finetuned-wtq")
    assert meta.extra_lists.get("hf.language") == ["en"]


def test_tapas_dataset_reference() -> None:
    with _patch_tapas():
        meta = read_huggingface("google/tapas-large-finetuned-wtq")
    assert any("wikitablequestions" in d.metadata.name for d in meta.datasets)


def test_fineweb_edu_text_classification_and_base_model() -> None:
    with _patch_fineweb_edu():
        meta = read_huggingface("HuggingFaceFW/fineweb-edu-classifier")
    assert "text-classification" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "Snowflake/snowflake-arctic-embed-m"


def test_moirai_no_type_of_model() -> None:
    # Config has no "model_type" key -> type_of_model=None
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert meta.type_of_model is None


def test_moirai_no_architecture() -> None:
    # Config has no "architectures" key -> architecture=None
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert meta.architecture is None


def test_moirai_empty_hyperparameters() -> None:
    # Custom config keys (patch_sizes, d_model, etc.) not in _HYPER_KEYS
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert not meta.hyperparameters


def test_moirai_time_series_forecasting_domain() -> None:
    # "time-series-forecasting" added to _DOMAIN_TAGS -> captured as domain
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert "time-series-forecasting" in meta.usage.domains


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
