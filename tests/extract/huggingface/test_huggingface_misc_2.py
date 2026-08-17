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
    _patch_chinda,
    _patch_chinda_gguf,
    _patch_depth_pro,
    _patch_dinov2,
    _patch_donut,
    _patch_fibo_edit,
    _patch_jina_v4,
    _patch_laion_clip,
    _patch_layoutlm,
    _patch_llava_video,
    _patch_marigold,
    _patch_nllb,
    _patch_nomic_gguf,
    _patch_resnet18,
    _patch_rmbg14,
    _patch_rmbg20,
    _patch_ruri,
    _patch_sonoisa,
    _patch_streetclip,
    _patch_sugoi,
    _patch_swin,
    _patch_talkie,
    _patch_tapas,
    _patch_vitpose,
    _patch_vntl,
    _patch_wangchanx_legal,
    _patch_wav2vec2_jp,
)


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


def test_wav2vec2_jp_language_scalar_normalised() -> None:
    with _patch_wav2vec2_jp():
        meta = read_huggingface("jonatasgrosman/wav2vec2-large-xlsr-53-japanese")
    assert meta.extra_lists.get("hf.language") == ["ja"]


def test_wav2vec2_jp_doi_extracted() -> None:
    with _patch_wav2vec2_jp():
        meta = read_huggingface("jonatasgrosman/wav2vec2-large-xlsr-53-japanese")
    assert meta.extra_data.get("hf.doi") == "10.57967/hf/3568"


def test_wav2vec2_jp_model_index_in_extra_data() -> None:
    with _patch_wav2vec2_jp():
        meta = read_huggingface("jonatasgrosman/wav2vec2-large-xlsr-53-japanese")
    assert meta.extra_data.get("hf.model_index") is not None


def test_wav2vec2_jp_asr_domain() -> None:
    with _patch_wav2vec2_jp():
        meta = read_huggingface("jonatasgrosman/wav2vec2-large-xlsr-53-japanese")
    assert "automatic-speech-recognition" in meta.usage.domains


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


def test_chinda_base_model_and_relation() -> None:
    with _patch_chinda():
        meta = read_huggingface("iapp/chinda-qwen3-4b")
    assert meta.extra_data.get("hf.base_model") == "Qwen/Qwen3-4B"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_chinda_doi_extracted() -> None:
    with _patch_chinda():
        meta = read_huggingface("iapp/chinda-qwen3-4b")
    assert meta.extra_data.get("hf.doi") == "10.57967/hf/5709"


def test_chinda_qwen3_architecture() -> None:
    with _patch_chinda():
        meta = read_huggingface("iapp/chinda-qwen3-4b")
    assert meta.type_of_model == "qwen3"
    assert meta.architecture == "Qwen3ForCausalLM"


def test_chinda_gguf_base_model_string_form() -> None:
    # base_model as a scalar string (not a list) must still be extracted.
    with _patch_chinda_gguf():
        meta = read_huggingface("iapp/chinda-qwen3-4b-gguf")
    assert meta.extra_data.get("hf.base_model") == "iapp/chinda-qwen3-4b"


def test_chinda_gguf_quantized_relation() -> None:
    with _patch_chinda_gguf():
        meta = read_huggingface("iapp/chinda-qwen3-4b-gguf")
    assert meta.extra_data.get("hf.base_model_relation") == "quantized"


def test_chinda_gguf_no_architecture_without_config() -> None:
    with _patch_chinda_gguf():
        meta = read_huggingface("iapp/chinda-qwen3-4b-gguf")
    assert meta.type_of_model is None


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


def test_talkie_no_config_base_model_finetune() -> None:
    with _patch_talkie():
        meta = read_huggingface("talkie-lm/talkie-1930-13b-it")
    assert meta.extra_data.get("hf.base_model") == "talkie-lm/talkie-1930-13b-base"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"
    assert meta.type_of_model is None  # no config.json


def test_depth_pro_depth_estimation_domain() -> None:
    with _patch_depth_pro():
        meta = read_huggingface("apple/DepthPro-hf")
    assert "depth-estimation" in meta.usage.domains


def test_depth_pro_architecture() -> None:
    with _patch_depth_pro():
        meta = read_huggingface("apple/DepthPro-hf")
    assert meta.type_of_model == "depth_pro"
    assert meta.architecture == "DepthProForDepthEstimation"


def test_marigold_depth_estimation_domain() -> None:
    with _patch_marigold():
        meta = read_huggingface("prs-eth/marigold-depth-v1-0")
    assert "depth-estimation" in meta.usage.domains


def test_marigold_diffusers_library() -> None:
    with _patch_marigold():
        meta = read_huggingface("prs-eth/marigold-depth-v1-0")
    assert meta.extra_data.get("hf.library_name") == "diffusers"


def test_vitpose_keypoint_detection_domain() -> None:
    with _patch_vitpose():
        meta = read_huggingface("usyd-community/vitpose-plus-huge")
    assert "keypoint-detection" in meta.usage.domains


def test_vitpose_architecture() -> None:
    with _patch_vitpose():
        meta = read_huggingface("usyd-community/vitpose-plus-huge")
    assert meta.type_of_model == "vitpose"


def test_jina_v4_visual_document_retrieval_domain() -> None:
    with _patch_jina_v4():
        meta = read_huggingface("jinaai/jina-embeddings-v4")
    assert "visual-document-retrieval" in meta.usage.domains


def test_jina_v4_multilingual_language() -> None:
    # "multilingual" is not an ISO code but a valid language keyword
    # - preserved.
    with _patch_jina_v4():
        meta = read_huggingface("jinaai/jina-embeddings-v4")
    assert "multilingual" in meta.extra_lists.get("hf.language", [])


def test_jina_v4_tokenizer_max_length() -> None:
    with _patch_jina_v4():
        meta = read_huggingface("jinaai/jina-embeddings-v4")
    assert meta.extra_data.get("hf.tokenizer_max_length") == 131072


def test_llava_video_text_to_text_domain() -> None:
    with _patch_llava_video():
        meta = read_huggingface("llava-hf/LLaVA-NeXT-Video-7B-hf")
    assert "video-text-to-text" in meta.usage.domains


def test_llava_image_text_tag_also_domain() -> None:
    # "image-text-to-text" in tags list is also a domain tag -> usage.domains
    with _patch_llava_video():
        meta = read_huggingface("llava-hf/LLaVA-NeXT-Video-7B-hf")
    assert "image-text-to-text" in meta.usage.domains


def test_llava_dataset_reference() -> None:
    with _patch_llava_video():
        meta = read_huggingface("llava-hf/LLaVA-NeXT-Video-7B-hf")
    assert any("VideoChatGPT" in d.metadata.name for d in meta.datasets)


def test_donut_document_question_answering_domain() -> None:
    with _patch_donut():
        meta = read_huggingface("naver-clova-ix/donut-base-finetuned-docvqa")
    assert "document-question-answering" in meta.usage.domains


def test_donut_image_to_text_also_domain() -> None:
    with _patch_donut():
        meta = read_huggingface("naver-clova-ix/donut-base-finetuned-docvqa")
    assert "image-to-text" in meta.usage.domains


def test_layoutlm_document_question_answering() -> None:
    with _patch_layoutlm():
        meta = read_huggingface("impira/layoutlm-document-qa")
    assert "document-question-answering" in meta.usage.domains


def test_layoutlm_language_scalar_string() -> None:
    with _patch_layoutlm():
        meta = read_huggingface("impira/layoutlm-document-qa")
    assert meta.extra_lists.get("hf.language") == ["en"]


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


def test_rmbg14_image_segmentation_domain() -> None:
    with _patch_rmbg14():
        meta = read_huggingface("briaai/RMBG-1.4")
    assert "image-segmentation" in meta.usage.domains


def test_rmbg14_custom_tags_in_extra_lists() -> None:
    with _patch_rmbg14():
        meta = read_huggingface("briaai/RMBG-1.4")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "remove background" in tags
    assert "legal liability" in tags


def test_rmbg20_gated_still_has_domain_from_card() -> None:
    # Pipeline tag is in card YAML, so domain is captured even without config.
    with _patch_rmbg20():
        meta = read_huggingface("briaai/RMBG-2.0")
    assert "image-segmentation" in meta.usage.domains
    assert meta.type_of_model is None


def test_fibo_edit_image_to_image_domain() -> None:
    with _patch_fibo_edit():
        meta = read_huggingface("briaai/Fibo-Edit-RMBG")
    assert "image-to-image" in meta.usage.domains


def test_fibo_edit_arxiv_extracted() -> None:
    with _patch_fibo_edit():
        meta = read_huggingface("briaai/Fibo-Edit-RMBG")
    assert "2511.06876" in meta.extra_lists.get("hf.arxiv", [])


def test_fibo_edit_base_model_relation() -> None:
    with _patch_fibo_edit():
        meta = read_huggingface("briaai/Fibo-Edit-RMBG")
    assert meta.extra_data.get("hf.base_model") == "briaai/Fibo-Edit"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_laion_clip_zero_shot_image_classification_domain() -> None:
    with _patch_laion_clip():
        meta = read_huggingface("laion/CLIP-convnext_base_w-laion2B-s13B-b82K-augreg")
    assert "zero-shot-image-classification" in meta.usage.domains


def test_laion_clip_no_config_no_architecture() -> None:
    with _patch_laion_clip():
        meta = read_huggingface("laion/CLIP-convnext_base_w-laion2B-s13B-b82K-augreg")
    assert meta.type_of_model is None


def test_streetclip_zero_shot_classification_domain() -> None:
    with _patch_streetclip():
        meta = read_huggingface("geolocal/StreetCLIP")
    assert "zero-shot-image-classification" in meta.usage.domains


def test_streetclip_clip_architecture() -> None:
    with _patch_streetclip():
        meta = read_huggingface("geolocal/StreetCLIP")
    assert meta.type_of_model == "clip"


def test_streetclip_geo_tags_in_extra_lists() -> None:
    with _patch_streetclip():
        meta = read_huggingface("geolocal/StreetCLIP")
    tags = meta.extra_lists.get("hf.tags", [])
    assert "geolocalization" in tags


def test_swin_no_pipeline_tag_but_image_classification_from_tags() -> None:
    with _patch_swin():
        meta = read_huggingface("microsoft/swin-tiny-patch4-window7-224")
    # pipeline_tag absent in card -> domain comes from card tags
    assert "image-classification" in meta.usage.domains


def test_swin_imagenet_dataset() -> None:
    with _patch_swin():
        meta = read_huggingface("microsoft/swin-tiny-patch4-window7-224")
    assert any("imagenet-1k" in d.metadata.name for d in meta.datasets)


def test_resnet18_architecture() -> None:
    with _patch_resnet18():
        meta = read_huggingface("microsoft/resnet-18")
    assert meta.type_of_model == "resnet"
    assert meta.architecture == "ResNetForImageClassification"


def test_dinov2_image_feature_extraction_domain() -> None:
    with _patch_dinov2():
        meta = read_huggingface("facebook/dinov2-small")
    assert "image-feature-extraction" in meta.usage.domains


def test_dinov2_architecture() -> None:
    with _patch_dinov2():
        meta = read_huggingface("facebook/dinov2-small")
    assert meta.type_of_model == "dinov2"
    assert meta.architecture == "Dinov2Model"
