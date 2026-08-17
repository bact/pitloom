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
    _make_card_data,
    _patch_blip_vqa,
    _patch_deplot,
    _patch_falconsai,
    _patch_gpt_neox_jp,
    _patch_granite_4_1_8b,
    _patch_granite_embed,
    _patch_granite_geo_flood,
    _patch_granite_speech,
    _patch_groot,
    _patch_hf_calls,
    _patch_hunyuan_mt,
    _patch_hunyuan_mt7b,
    _patch_hy_mt_gguf,
    _patch_ii_medical,
    _patch_indic_conformer,
    _patch_ipa_whisper,
    _patch_laguna,
    _patch_llmjp,
    _patch_mallam,
    _patch_mimo_asr_gguf,
    _patch_mistral_medium,
    _patch_nemotron,
    _patch_omnivoice,
    _patch_omnivoice_bf16,
    _patch_openvla,
    _patch_opus_mt_th_en,
    _patch_pi05,
    _patch_privacy_filter,
    _patch_pyannote_diar,
    _patch_rad_dino,
    _patch_sealion_vl,
    _patch_seamless_m4t,
    _patch_timm_convnext,
    _patch_uni2,
    _patch_vibevoice_asr,
    _patch_vilt_vqa,
    _patch_wangchanglm,
    _patch_wav2vec2_id_jv_su,
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


def test_nemotron_any_to_any_domain() -> None:
    with _patch_nemotron():
        meta = read_huggingface("nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16")
    assert "any-to-any" in meta.usage.domains


def test_nemotron_dataset_from_card_yaml() -> None:
    with _patch_nemotron():
        meta = read_huggingface("nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16")
    assert any("Nemotron-Image-Training" in d.metadata.name for d in meta.datasets)


def test_wangchanglm_architecture() -> None:
    with _patch_wangchanglm():
        meta = read_huggingface("pythainlp/wangchanglm-7.5B-sft-enth")
    assert meta.type_of_model == "xglm"


def test_wangchanglm_multiple_datasets() -> None:
    with _patch_wangchanglm():
        meta = read_huggingface("pythainlp/wangchanglm-7.5B-sft-enth")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "laion/OIG" in ds_names
    assert "Hello-SimpleAI/HC3" in ds_names


def test_wangchanglm_unlimited_tokenizer_filtered() -> None:
    with _patch_wangchanglm():
        meta = read_huggingface("pythainlp/wangchanglm-7.5B-sft-enth")
    assert "hf.tokenizer_max_length" not in meta.extra_data


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


def test_mallam_malay_language() -> None:
    with _patch_mallam():
        meta = read_huggingface("mesolitica/mallam-1.1B-4096")
    assert meta.extra_lists.get("hf.language") == ["ms"]


def test_llmjp_llama_architecture_large_vocab() -> None:
    # 99 584-token vocab designed for Japanese tokenization
    with _patch_llmjp():
        meta = read_huggingface("llm-jp/llm-jp-3-1.8b")
    assert meta.type_of_model == "llama"
    assert meta.hyperparameters.get("vocab_size") == 99584


def test_privacy_filter_token_classification_domain() -> None:
    with _patch_privacy_filter():
        meta = read_huggingface("openai/privacy-filter")
    assert "token-classification" in meta.usage.domains


def test_privacy_filter_tokenizer_max_length() -> None:
    with _patch_privacy_filter():
        meta = read_huggingface("openai/privacy-filter")
    assert meta.extra_data.get("hf.tokenizer_max_length") == 128000


def test_mistral_medium_no_pipeline_tag_empty_domain() -> None:
    with _patch_mistral_medium():
        meta = read_huggingface("mistralai/Mistral-Medium-3.5-128B")
    assert not meta.usage.domains


def test_mistral_medium_many_languages() -> None:
    with _patch_mistral_medium():
        meta = read_huggingface("mistralai/Mistral-Medium-3.5-128B")
    langs = meta.extra_lists.get("hf.language", [])
    assert "ja" in langs and "ar" in langs and "hi" in langs


def test_laguna_custom_architecture() -> None:
    with _patch_laguna():
        meta = read_huggingface("poolside/Laguna-XS.2")
    assert meta.type_of_model == "laguna"
    assert meta.architecture == "LagunaForCausalLM"


def test_laguna_custom_tags_in_extra_lists() -> None:
    with _patch_laguna():
        meta = read_huggingface("poolside/Laguna-XS.2")
    assert "laguna-xs.2" in meta.extra_lists.get("hf.tags", [])


def test_gpt_neox_jp_language_scalar() -> None:
    with _patch_gpt_neox_jp():
        meta = read_huggingface("abeja/gpt-neox-japanese-2.7b")
    assert meta.extra_lists.get("hf.language") == ["ja"]


def test_gpt_neox_jp_datasets() -> None:
    with _patch_gpt_neox_jp():
        meta = read_huggingface("abeja/gpt-neox-japanese-2.7b")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "cc100" in ds_names and "wikipedia" in ds_names


def test_falconsai_t5_summarization() -> None:
    with _patch_falconsai():
        meta = read_huggingface("Falconsai/medical_summarization")
    assert meta.type_of_model == "t5"
    assert "summarization" in meta.usage.domains


def test_falconsai_tokenizer_max_length() -> None:
    with _patch_falconsai():
        meta = read_huggingface("Falconsai/medical_summarization")
    assert meta.extra_data.get("hf.tokenizer_max_length") == 512


def test_opus_mt_translation_domain_from_tag() -> None:
    # pipeline_tag absent; "translation" is a domain tag in card tags.
    with _patch_opus_mt_th_en():
        meta = read_huggingface("Helsinki-NLP/opus-mt-th-en")
    assert "translation" in meta.usage.domains


def test_opus_mt_marian_architecture() -> None:
    with _patch_opus_mt_th_en():
        meta = read_huggingface("Helsinki-NLP/opus-mt-th-en")
    assert meta.type_of_model == "marian"


def test_hunyuan_mt_translation_from_tag() -> None:
    with _patch_hunyuan_mt():
        meta = read_huggingface("tencent/HY-MT1.5-1.8B")
    assert "translation" in meta.usage.domains


def test_hy_mt_gguf_multilingual_keyword_preserved() -> None:
    with _patch_hy_mt_gguf():
        meta = read_huggingface("tencent/Hy-MT1.5-1.8B-2bit-GGUF")
    assert "multilingual" in meta.extra_lists.get("hf.language", [])


def test_hy_mt_gguf_base_model_quantized() -> None:
    with _patch_hy_mt_gguf():
        meta = read_huggingface("tencent/Hy-MT1.5-1.8B-2bit-GGUF")
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"


def test_hunyuan_mt7b_translation_from_tag_no_pipeline() -> None:
    with _patch_hunyuan_mt7b():
        meta = read_huggingface("tencent/Hunyuan-MT-7B")
    assert "translation" in meta.usage.domains
    assert meta.license is None


def test_ii_medical_qwen3_architecture() -> None:
    with _patch_ii_medical():
        meta = read_huggingface("Intelligent-Internet/II-Medical-8B")
    assert meta.type_of_model == "qwen3"
    assert meta.hyperparameters.get("hidden_size") == 4096


def test_dataset_card_yaml_takes_priority_over_info_tags() -> None:
    # When card_data has datasets, model_info tags are ignored for datasets.
    card = _make_card_data(
        license="cc-by-sa-4.0",
        pipeline_tag="text-generation",
        datasets=["from-card-dataset"],
    )
    with _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=card,
        hub_info={"tags": ["dataset:from-info-tag"]},
    ):
        meta = read_huggingface("pythainlp/wangchanglm-7.5B-sft-enth")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "from-card-dataset" in ds_names
    assert "from-info-tag" not in ds_names


def test_dataset_info_tag_fallback_when_no_card_datasets() -> None:
    # When card has no datasets, model_info tags with dataset: prefix are used.
    card = _make_card_data(license="mit", pipeline_tag="text-generation")
    with _patch_hf_calls(
        config=None,
        tokenizer_config=None,
        card_data=card,
        hub_info={"tags": ["dataset:fallback-dataset"]},
    ):
        meta = read_huggingface("pythainlp/wangchanglm-7.5B-sft-enth")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "fallback-dataset" in ds_names


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


def test_omnivoice_text_to_speech_domain() -> None:
    with _patch_omnivoice():
        meta = read_huggingface("k2-fsa/OmniVoice")
    assert "text-to-speech" in meta.usage.domains


def test_omnivoice_arxiv_and_base_model() -> None:
    with _patch_omnivoice():
        meta = read_huggingface("k2-fsa/OmniVoice")
    assert "2604.00688" in meta.extra_lists.get("hf.arxiv", [])
    assert meta.extra_data.get("hf.base_model") == "Qwen/Qwen3-0.6B"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_omnivoice_bf16_tts_domain_and_base_model() -> None:
    with _patch_omnivoice_bf16():
        meta = read_huggingface("drbaph/OmniVoice-bf16")
    assert "text-to-speech" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "k2-fsa/OmniVoice"


def test_pyannote_speaker_diarization_domain() -> None:
    with _patch_pyannote_diar():
        meta = read_huggingface("pyannote/speaker-diarization-community-1")
    assert "speaker-diarization" in meta.usage.domains


def test_pyannote_library_name() -> None:
    with _patch_pyannote_diar():
        meta = read_huggingface("pyannote/speaker-diarization-community-1")
    assert meta.extra_data.get("hf.library_name") == "pyannote.audio"


def test_seamless_asr_domain_from_pipeline_tag() -> None:
    with _patch_seamless_m4t():
        meta = read_huggingface("facebook/seamless-m4t-v2-large")
    assert "automatic-speech-recognition" in meta.usage.domains


def test_seamless_audio_to_audio_tag_in_domain() -> None:
    # "audio-to-audio" in tags → captured as domain (audio-to-audio domain tag).
    with _patch_seamless_m4t():
        meta = read_huggingface("facebook/seamless-m4t-v2-large")
    assert "audio-to-audio" in meta.usage.domains


def test_granite_speech_asr_domain() -> None:
    with _patch_granite_speech():
        meta = read_huggingface("ibm-granite/granite-speech-4.1-2b")
    assert "automatic-speech-recognition" in meta.usage.domains


def test_granite_speech_base_model_finetune() -> None:
    with _patch_granite_speech():
        meta = read_huggingface("ibm-granite/granite-speech-4.1-2b")
    assert meta.extra_data.get("hf.base_model") == "ibm-granite/granite-4.0-1b-base"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_indic_conformer_22_indian_languages() -> None:
    with _patch_indic_conformer():
        meta = read_huggingface("ai4bharat/indic-conformer-600m-multilingual")
    assert "automatic-speech-recognition" in meta.usage.domains
    langs = meta.extra_lists.get("hf.language", [])
    assert "hi" in langs and "ta" in langs and "te" in langs
    assert len(langs) == 22


def test_mimo_asr_quantized_gguf() -> None:
    with _patch_mimo_asr_gguf():
        meta = read_huggingface("cstr/mimo-asr-GGUF")
    assert "automatic-speech-recognition" in meta.usage.domains
    assert meta.extra_data.get("hf.base_model") == "XiaomiMiMo/MiMo-V2.5-ASR"
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"


def test_vibevoice_asr_domain_and_arxiv() -> None:
    with _patch_vibevoice_asr():
        meta = read_huggingface("microsoft/VibeVoice-ASR")
    assert "automatic-speech-recognition" in meta.usage.domains
    assert "2601.18184" in meta.extra_lists.get("hf.arxiv", [])


def test_ipa_whisper_base_model_finetune() -> None:
    with _patch_ipa_whisper():
        meta = read_huggingface("neurlang/ipa-whisper-medium")
    assert meta.extra_data.get("hf.base_model") == "openai/whisper-medium"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_ipa_whisper_asr_domain() -> None:
    with _patch_ipa_whisper():
        meta = read_huggingface("neurlang/ipa-whisper-medium")
    assert "automatic-speech-recognition" in meta.usage.domains


def test_wav2vec2_id_asr_domain_three_languages() -> None:
    with _patch_wav2vec2_id_jv_su():
        meta = read_huggingface("indonesian-nlp/wav2vec2-indonesian-javanese-sundanese")
    assert "automatic-speech-recognition" in meta.usage.domains
    langs = meta.extra_lists.get("hf.language", [])
    assert "id" in langs and "jv" in langs and "su" in langs


def test_granite_4_1_8b_gqa_and_12_languages() -> None:
    with _patch_granite_4_1_8b():
        meta = read_huggingface("ibm-granite/granite-4.1-8b")
    assert meta.hyperparameters.get("num_key_value_heads") == 8
    langs = meta.extra_lists.get("hf.language", [])
    assert len(langs) == 12 and "ja" in langs and "ar" in langs


def test_granite_4_1_8b_base_model_finetune() -> None:
    with _patch_granite_4_1_8b():
        meta = read_huggingface("ibm-granite/granite-4.1-8b")
    assert meta.extra_data.get("hf.base_model") == "ibm-granite/granite-4.1-8b-base"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_granite_embed_modernbert_arch_and_library() -> None:
    with _patch_granite_embed():
        meta = read_huggingface("ibm-granite/granite-embedding-97m-multilingual-r2")
    assert meta.type_of_model == "modernbert"
    assert meta.extra_data.get("hf.library_name") == "sentence-transformers"


def test_granite_embed_feature_extraction_domain() -> None:
    with _patch_granite_embed():
        meta = read_huggingface("ibm-granite/granite-embedding-97m-multilingual-r2")
    assert "feature-extraction" in meta.usage.domains


def test_granite_geo_flood_image_segmentation_domain() -> None:
    with _patch_granite_geo_flood():
        meta = read_huggingface("ibm-granite/granite-geospatial-uki-flooddetection")
    assert "image-segmentation" in meta.usage.domains


def test_granite_geo_flood_dataset_refs_from_hf_dataset_repos() -> None:
    # Both flood dataset HF IDs captured as DatasetReference objects.
    with _patch_granite_geo_flood():
        meta = read_huggingface("ibm-granite/granite-geospatial-uki-flooddetection")
    ds_names = [d.metadata.name for d in meta.datasets]
    assert "ai-for-good-lab/ai4g-flood-dataset" in ds_names
    assert "blanchon/ETCI-2021-Flood-Detection" in ds_names


def test_granite_geo_flood_terratorch_library_and_base_model() -> None:
    with _patch_granite_geo_flood():
        meta = read_huggingface("ibm-granite/granite-geospatial-uki-flooddetection")
    assert meta.extra_data.get("hf.library_name") == "terratorch"
    assert meta.extra_data.get("hf.base_model") == "ibm-granite/granite-geospatial-uki"
