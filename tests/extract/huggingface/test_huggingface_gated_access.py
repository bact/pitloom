# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for models that are gated or otherwise access-restricted on the Hub.

See also: test_huggingface_embeddings.py, test_huggingface_gated_metadata.py,
test_huggingface_granite_misc.py, test_huggingface_multimodal.py,
test_huggingface_omni_modal.py, test_huggingface_speech_misc.py,
test_huggingface_structured_text.py,
test_huggingface_text_generation_instruct.py,
test_huggingface_text_generation_pretrained.py, test_huggingface_text_misc.py,
test_huggingface_vision.py, test_huggingface_vision_robotics.py.
"""

from __future__ import annotations

from pitloom.extract._huggingface import read_huggingface

from .hf_patches._hf_patches_gated_access import (
    _patch_aya_vision,
    _patch_cohere_aya_23,
    _patch_gemma,
    _patch_inkubalm,
    _patch_nllb,
    _patch_serengeti,
    _patch_stanza_de,
    _patch_stanza_fi,
    _patch_talkie,
    _patch_wmt22_cometkiwi,
)


def test_gemma_name() -> None:
    with _patch_gemma():
        meta = read_huggingface("google/gemma-2b")
    assert meta.name == "gemma-2b"


def test_gemma_no_architecture_when_gated_config() -> None:
    with _patch_gemma():
        meta = read_huggingface("google/gemma-2b")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_gemma_no_domain_when_no_pipeline_tag() -> None:
    with _patch_gemma():
        meta = read_huggingface("google/gemma-2b")
    assert not meta.usage.domains


def test_serengeti_name() -> None:
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert meta.name == "serengeti-E250"


def test_serengeti_electra_type_and_architecture() -> None:
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert meta.type_of_model == "electra"
    assert meta.architecture == "ElectraModel"


def test_serengeti_large_multilingual_vocab() -> None:
    # 250 000-token vocabulary designed for African-language coverage
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert meta.hyperparameters.get("vocab_size") == 250000


def test_serengeti_no_domain_when_no_card() -> None:
    # pipeline_tag="fill-mask" exists in model_info.tags but the extractor
    # reads it from card YAML - absent card -> empty domains.
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert not meta.usage.domains


def test_serengeti_no_language_when_no_card() -> None:
    # 26 African ISO language codes are in model_info.tags but are not
    # extracted when there is no model card.
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert "hf.language" not in meta.extra_lists


def test_serengeti_tokenizer_class_from_tokenizer_config() -> None:
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert meta.extra_data.get("hf.tokenizer_class") == "ElectraTokenizer"


def test_serengeti_unlimited_tokenizer_max_length_filtered() -> None:
    # The sentinel value (1e30) must NOT appear in extra_data.
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert "hf.tokenizer_max_length" not in meta.extra_data


def test_aya_vision_name() -> None:
    with _patch_aya_vision():
        meta = read_huggingface("CohereLabs/aya-vision-8b")
    assert meta.name == "aya-vision-8b"


def test_aya_vision_no_architecture_when_gated() -> None:
    with _patch_aya_vision():
        meta = read_huggingface("CohereLabs/aya-vision-8b")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_aya_vision_no_domain_when_gated() -> None:
    # pipeline_tag="image-text-to-text" is in model_info but not extracted
    # when the card is inaccessible.
    with _patch_aya_vision():
        meta = read_huggingface("CohereLabs/aya-vision-8b")
    assert not meta.usage.domains


def test_aya_vision_no_language_when_gated() -> None:
    # 23 languages are listed in model_info.card_data.language but are
    # not captured when the card is inaccessible.
    with _patch_aya_vision():
        meta = read_huggingface("CohereLabs/aya-vision-8b")
    assert "hf.language" not in meta.extra_lists


def test_aya_vision_extra_data_has_hf_url() -> None:
    # Even for fully gated models, the HF URL is always populated.
    with _patch_aya_vision():
        meta = read_huggingface("CohereLabs/aya-vision-8b")
    assert (
        meta.extra_data.get("hf.url")
        == "https://huggingface.co/CohereLabs/aya-vision-8b"
    )
    assert meta.extra_data.get("hf.model_id") == "CohereLabs/aya-vision-8b"


def test_inkubalm_name() -> None:
    with _patch_inkubalm():
        meta = read_huggingface("lelapa/InkubaLM-0.4B")
    assert meta.name == "InkubaLM-0.4B"


def test_inkubalm_no_architecture_when_gated() -> None:
    with _patch_inkubalm():
        meta = read_huggingface("lelapa/InkubaLM-0.4B")
    assert meta.type_of_model is None
    assert meta.architecture is None


def test_inkubalm_no_african_languages_when_gated() -> None:
    # model_info reports ["en", "sw", "zu", "xh", "ha", "yo"] but they are
    # not captured when the card is inaccessible (language codes appear in
    # model_info.tags but are not extracted - only language: field from card YAML is).
    with _patch_inkubalm():
        meta = read_huggingface("lelapa/InkubaLM-0.4B")
    assert "hf.language" not in meta.extra_lists


def test_inkubalm_dataset_from_model_info_tags() -> None:
    # Even when the card is gated, the extractor falls back to "dataset:*"
    # prefix tags in model_info to populate datasets.
    with _patch_inkubalm():
        meta = read_huggingface("lelapa/InkubaLM-0.4B")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "lelapa/Inkuba-Mono" in ds_names


def test_nllb_m2m100_architecture() -> None:
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert meta.type_of_model == "m2m_100"
    assert meta.architecture == "M2M100ForConditionalGeneration"


def test_nllb_large_multilingual_vocab() -> None:
    # 256 206-token vocabulary for 200-language coverage
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert meta.hyperparameters.get("vocab_size") == 256206


def test_nllb_num_hidden_layers_captured() -> None:
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert meta.hyperparameters.get("num_hidden_layers") == 12


def test_nllb_d_model_not_in_hyperparameters() -> None:
    # "d_model" is the m2m_100 hidden-dimension key but is not in _HYPER_KEYS
    # (which looks for "hidden_size") - silently skipped.
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert "d_model" not in meta.hyperparameters


def test_nllb_tokenizer_real_max_length_captured() -> None:
    # model_max_length=1024 is a real limit (below the unlimited sentinel)
    # and must appear in extra_data - contrast with serengeti's filtered value.
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert meta.extra_data.get("hf.tokenizer_max_length") == 1024
    assert meta.extra_data.get("hf.tokenizer_class") == "NllbTokenizer"


def test_nllb_no_domain_when_no_card() -> None:
    # "translation" and "text2text-generation" are domain tags but live only
    # in model_info.tags - not captured when there is no model card.
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert not meta.usage.domains


def test_nllb_no_language_when_no_card() -> None:
    # 200 language codes are in model_info.tags but not captured without a card.
    with _patch_nllb():
        meta = read_huggingface("facebook/nllb-200-distilled-600M")
    assert "hf.language" not in meta.extra_lists


def test_talkie_no_config_base_model_finetune() -> None:
    with _patch_talkie():
        meta = read_huggingface("talkie-lm/talkie-1930-13b-it")
    assert meta.extra_data.get("hf.base_model") == "talkie-lm/talkie-1930-13b-base"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"
    assert meta.type_of_model is None  # no config.json


def test_cohere_aya_23_no_type_of_model() -> None:
    with _patch_cohere_aya_23():
        meta = read_huggingface("CohereLabs/aya-23-8B")
    assert meta.type_of_model is None


def test_cohere_aya_23_empty_domains() -> None:
    with _patch_cohere_aya_23():
        meta = read_huggingface("CohereLabs/aya-23-8B")
    assert not meta.usage.domains


def test_cohere_aya_23_author_captured_from_hub_info() -> None:
    with _patch_cohere_aya_23():
        meta = read_huggingface("CohereLabs/aya-23-8B")
    assert (meta.extra_data or {}).get("hf.author") == "CohereLabs"


def test_wmt22_cometkiwi_no_type_of_model() -> None:
    with _patch_wmt22_cometkiwi():
        meta = read_huggingface("Unbabel/wmt22-cometkiwi-da")
    assert meta.type_of_model is None


def test_wmt22_cometkiwi_empty_domains() -> None:
    with _patch_wmt22_cometkiwi():
        meta = read_huggingface("Unbabel/wmt22-cometkiwi-da")
    assert not meta.usage.domains


def test_wmt22_cometkiwi_author_from_hub_info() -> None:
    with _patch_wmt22_cometkiwi():
        meta = read_huggingface("Unbabel/wmt22-cometkiwi-da")
    assert (meta.extra_data or {}).get("hf.author") == "Unbabel"


def test_stanza_fi_no_architecture() -> None:
    # Stanza: no config.json -> no type_of_model or architecture
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
    # No pipeline_tag -> empty usage.domains
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
