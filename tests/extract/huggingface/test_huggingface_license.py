# ruff: noqa: F403, F405
from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pitloom.extract._huggingface import (
    _detect_license_from_hf_files,
    _list_license_files_in_repo,
    read_huggingface,
)

from .conftest import (
    _make_card_data,
    _patch_apple_sharp,
    _patch_arabic_legal_ocr,
    _patch_aspect_finnlp_th,
    _patch_aya_vision,
    _patch_blip_vqa,
    _patch_bloom,
    _patch_bloomz_7b1,
    _patch_clip_japanese_v2,
    _patch_codeberta,
    _patch_cohere_aya_23,
    _patch_deberta_human_value,
    _patch_deepseek,
    _patch_depth_pro,
    _patch_exaone45_33b,
    _patch_exaone45_33b_awq,
    _patch_exaone45_33b_fp8,
    _patch_exaone45_33b_gguf,
    _patch_exaone_path,
    _patch_firered_vad,
    _patch_fujitsu_llm,
    _patch_gabert,
    _patch_gemma,
    _patch_glm45_air_reap,
    _patch_groot,
    _patch_gte_reranker,
    _patch_hermes_3_llama_3b,
    _patch_hf_calls,
    _patch_hrnetpose,
    _patch_hunyuan_mt,
    _patch_hy_motion,
    _patch_inkubalm,
    _patch_jina_v4,
    _patch_kanana_15v,
    _patch_kimi,
    _patch_kokoro,
    _patch_legal_embed_ita,
    _patch_lightglue,
    _patch_line_distilbert,
    _patch_llada2_moe,
    _patch_llama,
    _patch_llasa_3b,
    _patch_mallam,
    _patch_minimax_m2,
    _patch_mistral_medium,
    _patch_moirai,
    _patch_opt_2_7b,
    _patch_opt_iml,
    _patch_pharia_aligned,
    _patch_pharia_control,
    _patch_phi2,
    _patch_pi05,
    _patch_protonx_legal,
    _patch_qwen3_235b,
    _patch_qwen35_27b,
    _patch_rad_dino,
    _patch_rmbg14,
    _patch_sealion_27b_it,
    _patch_sealion_gguf,
    _patch_seallms,
    _patch_seamless_m4t,
    _patch_serengeti,
    _patch_shap_e,
    _patch_stable_zero123,
    _patch_starcoder2,
    _patch_tildeopen_30b_64k,
    _patch_timelens,
    _patch_timm_convnext,
    _patch_typhoon,
    _patch_uni2,
    _patch_windowseat,
    _patch_wmt22_cometkiwi,
)


def test_read_huggingface_license_from_card() -> None:
    with _patch_hf_calls():
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert meta.license == "Apache-2.0"


def test_license_from_file_when_card_has_none() -> None:
    # When model card has no license field, license files are checked.
    card_data = _make_card_data(license=None, pipeline_tag="text-generation")
    with _patch_hf_calls(card_data=card_data):
        with patch(
            "pitloom.extract._huggingface._detect_license_from_hf_files",
            return_value=(
                "Apache-2.0",
                "Source: Hugging Face Hub "
                "| File: LICENSE "
                "| Method: licenseid_detection",
            ),
        ):
            meta = read_huggingface("org/model")
    assert meta.license == "Apache-2.0"
    assert "licenseid_detection" in (meta.provenance.get("license") or "")


def test_license_from_file_when_card_says_other() -> None:
    # "other" triggers file detection; detected value replaces the vague sentinel.
    card_data = _make_card_data(license="other")
    with _patch_hf_calls(card_data=card_data):
        with patch(
            "pitloom.extract._huggingface._detect_license_from_hf_files",
            return_value=(
                "MIT",
                "Source: Hugging Face Hub "
                "| File: LICENSE "
                "| Method: licenseid_detection",
            ),
        ):
            meta = read_huggingface("org/model")
    assert meta.license == "MIT"
    # Raw vague value still stored for transparency
    assert meta.extra_data.get("hf.license_raw") == "other"


def test_vague_license_raw_not_stored_when_card_has_real_spdx_id() -> None:
    # A proper SPDX License ID in the card YAML should NOT create hf.license_raw.
    with _patch_hf_calls():  # uses apache-2.0 card data
        meta = read_huggingface("mistralai/Mistral-7B-v0.1")
    assert "hf.license_raw" not in meta.extra_data


def test_license_detection_not_called_when_card_has_real_spdx_id() -> None:
    # File detection must be skipped entirely when card YAML already has a valid ID.
    mock_detect = MagicMock(return_value=(None, None))
    with _patch_hf_calls():
        with patch(
            "pitloom.extract._huggingface._detect_license_from_hf_files", mock_detect
        ):
            read_huggingface("mistralai/Mistral-7B-v0.1")
    mock_detect.assert_not_called()


def test_license_remains_none_when_file_detection_also_fails() -> None:
    # Neither card YAML nor file detection -> license is None (not a vague string).
    card_data = _make_card_data(license=None)
    with _patch_hf_calls(card_data=card_data):
        # _detect_license_from_hf_files already mocked to (None, None) in base helper
        meta = read_huggingface("org/model")
    assert meta.license is None


def test_detect_license_from_hf_files_returns_none_on_empty_file(
    tmp_path: Any,
) -> None:
    # Empty licence file should not produce a match.
    with patch(
        "pitloom.extract._huggingface._list_license_files_in_repo",
        return_value=["LICENSE"],
    ):
        empty_file = tmp_path / "LICENSE"
        empty_file.write_text("", encoding="utf-8")
        with patch("huggingface_hub.hf_hub_download", return_value=str(empty_file)):
            detected_id, _ = _detect_license_from_hf_files("org/model")
    assert detected_id is None


def test_list_license_files_in_repo_failure_logs_and_returns_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with patch(
        "huggingface_hub.list_repo_files", side_effect=OSError("listing failed")
    ):
        with caplog.at_level(logging.DEBUG, logger="pitloom.extract._huggingface"):
            result = _list_license_files_in_repo("org/model")
    assert not result
    assert any("org/model" in r.message for r in caplog.records)


def test_detect_license_from_hf_files_download_failure_logs_and_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A license candidate is listed, but downloading/reading it fails --
    # the loop must catch, log, and continue (returning (None, None) since
    # no other candidates exist) rather than raising.
    with patch(
        "pitloom.extract._huggingface._list_license_files_in_repo",
        return_value=["LICENSE"],
    ):
        with patch(
            "huggingface_hub.hf_hub_download",
            side_effect=OSError("download failed"),
        ):
            with caplog.at_level(logging.DEBUG, logger="pitloom.extract._huggingface"):
                detected_id, provenance = _detect_license_from_hf_files("org/model")
    assert detected_id is None
    assert provenance is None
    assert any("LICENSE" in r.message for r in caplog.records)


def test_kokoro_license() -> None:
    with _patch_kokoro():
        meta = read_huggingface("hexgrad/Kokoro-82M")
    assert meta.license == "Apache-2.0"


def test_starcoder2_non_standard_license_passed_through() -> None:
    # "bigcode-openrail-m" is not in _VAGUE_LICENSE_VALUES -> used directly
    with _patch_starcoder2():
        meta = read_huggingface("bigcode/starcoder2-3b")
    assert meta.license == "bigcode-openrail-m"


def test_kimi_vague_license_triggers_file_detection() -> None:
    detected_mock = MagicMock(
        return_value=(
            "MIT",
            "Source: Hugging Face Hub | File: LICENSE | Method: licenseid_detection",
        )
    )
    with _patch_kimi():
        with patch(
            "pitloom.extract._huggingface._detect_license_from_hf_files", detected_mock
        ):
            meta = read_huggingface("moonshotai/Kimi-K2.6")
    detected_mock.assert_called_once_with("moonshotai/Kimi-K2.6", revision=None)
    assert meta.license == "MIT"
    assert meta.extra_data.get("hf.license_raw") == "other"


def test_gemma_proprietary_license_used_directly() -> None:
    # "gemma" is not in _VAGUE_LICENSE_VALUES - used as-is
    with _patch_gemma():
        meta = read_huggingface("google/gemma-2b")
    assert meta.license == "gemma"
    assert "hf.license_raw" not in meta.extra_data


def test_llama_custom_license_used_directly() -> None:
    # "llama3.2" is not in _VAGUE_LICENSE_VALUES, so it is taken from the card.
    # Not recognized by licenseid matcher → _canonicalize_license_id returns
    # it unchanged.
    with _patch_llama():
        meta = read_huggingface("meta-llama/Llama-3.2-1B")
    assert meta.license == "llama3.2"


def test_deepseek_mit_license() -> None:
    with _patch_deepseek():
        meta = read_huggingface("deepseek-ai/DeepSeek-R1")
    assert meta.license == "MIT"


def test_sealion_gguf_gemma_license() -> None:
    with _patch_sealion_gguf():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-4B-VL-GGUF")
    assert meta.license == "gemma"


def test_seallms_vague_license_not_propagated() -> None:
    with _patch_seallms():
        meta = read_huggingface("SeaLLMs/SeaLLMs-v3-7B-Chat")
    assert meta.license is None
    assert meta.extra_data.get("hf.license_raw") == "other"


def test_typhoon_license() -> None:
    with _patch_typhoon():
        meta = read_huggingface("typhoon-ai/typhoon-7b")
    assert meta.license == "Apache-2.0"


def test_serengeti_no_license_when_no_card_and_no_file() -> None:
    # No card license + file detection mock returns nothing -> license is None.
    with _patch_serengeti():
        meta = read_huggingface("UBC-NLP/serengeti-E250")
    assert meta.license is None


def test_aya_vision_no_license_when_gated() -> None:
    # model_info reports license="cc-by-nc-4.0" but the extractor reads
    # license from card YAML -> absent card -> license is None.
    # This test documents a known gap: license is only captured when the
    # model card YAML is accessible or a license file can be downloaded.
    with _patch_aya_vision():
        meta = read_huggingface("CohereLabs/aya-vision-8b")
    assert meta.license is None


def test_inkubalm_no_license_when_gated() -> None:
    # model_info reports cc-by-nc-4.0 but the extractor reads license from
    # card YAML only - absent card -> license is None.
    with _patch_inkubalm():
        meta = read_huggingface("lelapa/InkubaLM-0.4B")
    assert meta.license is None


def test_depth_pro_non_standard_license() -> None:
    # "apple-amlr" is not in _VAGUE_LICENSE_VALUES - passed through as-is.
    with _patch_depth_pro():
        meta = read_huggingface("apple/DepthPro-hf")
    assert meta.license == "apple-amlr"


def test_jina_v4_no_license() -> None:
    with _patch_jina_v4():
        meta = read_huggingface("jinaai/jina-embeddings-v4")
    assert meta.license is None


def test_rmbg14_vague_license_not_propagated() -> None:
    with _patch_rmbg14():
        meta = read_huggingface("briaai/RMBG-1.4")
    assert meta.license is None
    assert meta.extra_data.get("hf.license_raw") == "other"


def test_rad_dino_no_license() -> None:
    with _patch_rad_dino():
        meta = read_huggingface("microsoft/rad-dino")
    assert meta.license is None


def test_uni2_nc_nd_license() -> None:
    with _patch_uni2():
        meta = read_huggingface("MahmoodLab/UNI2-h")
    assert meta.license == "CC-BY-NC-ND-4.0"


def test_timm_convnext_vague_license() -> None:
    with _patch_timm_convnext():
        meta = read_huggingface("timm/convnext_large.dinov3_lvd1689m")
    assert meta.license is None
    assert meta.extra_data.get("hf.license_raw") == "other"


def test_groot_no_license() -> None:
    with _patch_groot():
        meta = read_huggingface("nvidia/GR00T-N1.7-3B")
    assert meta.license is None


def test_pi05_robotics_domain_gemma_license() -> None:
    with _patch_pi05():
        meta = read_huggingface("lerobot/pi05_base")
    assert "robotics" in meta.usage.domains
    assert meta.license == "gemma"


def test_mallam_no_license() -> None:
    with _patch_mallam():
        meta = read_huggingface("mesolitica/mallam-1.1B-4096")
    assert meta.license is None


def test_mistral_medium_vague_license() -> None:
    with _patch_mistral_medium():
        meta = read_huggingface("mistralai/Mistral-Medium-3.5-128B")
    assert meta.license is None
    assert meta.extra_data.get("hf.license_raw") == "other"


def test_hunyuan_mt_no_license() -> None:
    with _patch_hunyuan_mt():
        meta = read_huggingface("tencent/HY-MT1.5-1.8B")
    assert meta.license is None


def test_blip_vqa_bsd_license_normalized() -> None:
    # bsd-3-clause not in _VAGUE_LICENSE_VALUES; _canonicalize_license_id maps
    # it to the canonical SPDX License ID BSD-3-Clause via licenseid matcher.
    with _patch_blip_vqa():
        meta = read_huggingface("Salesforce/blip-vqa-base")
    assert meta.license == "BSD-3-Clause"


def test_seamless_nc_license() -> None:
    with _patch_seamless_m4t():
        meta = read_huggingface("facebook/seamless-m4t-v2-large")
    assert meta.license == "CC-BY-NC-4.0"


def test_gabert_fill_mask_irish_no_license() -> None:
    with _patch_gabert():
        meta = read_huggingface("DCU-NLP/bert-base-irish-cased-v1")
    assert "fill-mask" in meta.usage.domains
    assert meta.extra_lists.get("hf.language") == ["ga"]
    assert meta.license is None


def test_opt_2_7b_vague_license_and_opt_arch() -> None:
    with _patch_opt_2_7b():
        meta = read_huggingface("facebook/opt-2.7b")
    assert meta.license is None
    assert meta.extra_data.get("hf.license_raw") == "other"
    assert meta.type_of_model == "opt"


def test_opt_iml_arxiv_and_vague_license() -> None:
    with _patch_opt_iml():
        meta = read_huggingface("facebook/opt-iml-max-1.3b")
    assert "2212.12017" in meta.extra_lists.get("hf.arxiv", [])
    assert meta.license is None
    assert meta.extra_data.get("hf.license_raw") == "other"


def test_phi2_phi_architecture_mit_license() -> None:
    with _patch_phi2():
        meta = read_huggingface("microsoft/phi-2")
    assert meta.type_of_model == "phi"
    assert meta.license == "MIT"


def test_hermes_3_llama_3b_finetune_and_license() -> None:
    with _patch_hermes_3_llama_3b():
        meta = read_huggingface("NousResearch/Hermes-3-Llama-3.2-3B")
    assert meta.license == "llama3"
    assert meta.extra_data.get("hf.base_model") == "meta-llama/Llama-3.2-3B"
    assert meta.extra_data.get("hf.base_model_relation") == "finetune"


def test_deberta_human_value_openrail_license() -> None:
    # openrail++ is not in _VAGUE_LICENSE_VALUES -- passed through as-is.
    with _patch_deberta_human_value():
        meta = read_huggingface("tum-nlp/Deberta_Human_Value_Detector")
    assert meta.license == "openrail++"
    assert "text-classification" in meta.usage.domains


def test_aspect_finnlp_th_camembert_no_license() -> None:
    with _patch_aspect_finnlp_th():
        meta = read_huggingface("nlp-chula/aspect-finnlp-th")
    assert meta.type_of_model == "camembert"
    assert meta.license is None
    assert "text-classification" in meta.usage.domains


def test_protonx_legal_vietnamese_nc_license() -> None:
    # Proprietary NC license → "other" in card → hf.license_raw.
    with _patch_protonx_legal():
        meta = read_huggingface("protonx-models/protonx-legal-tc")
    assert meta.license is None
    assert meta.extra_data.get("hf.license_raw") == "other"
    assert "text2text-generation" in meta.usage.domains
    assert meta.extra_lists.get("hf.language") == ["vi"]


def test_legal_embed_ita_nc_license_italian() -> None:
    with _patch_legal_embed_ita():
        meta = read_huggingface("ReDiX/Legal-Embedding-ita-0.6B")
    assert meta.license == "CC-BY-NC-4.0"
    assert meta.extra_lists.get("hf.language") == ["it"]
    assert "sentence-similarity" in meta.usage.domains


def test_arabic_legal_ocr_domain_and_gemma_license() -> None:
    with _patch_arabic_legal_ocr():
        meta = read_huggingface("bakrianoo/arabic-legal-documents-ocr-1.0")
    assert "image-text-to-text" in meta.usage.domains
    assert meta.license == "gemma"
    assert "ar" in meta.extra_lists.get("hf.language", [])


def test_sealion_27b_it_sea_languages_gemma_license() -> None:
    with _patch_sealion_27b_it():
        meta = read_huggingface("aisingapore/Gemma-SEA-LION-v4-27B-IT")
    assert meta.license == "gemma"
    langs = meta.extra_lists.get("hf.language", [])
    assert len(langs) == 11 and "th" in langs and "vi" in langs


def test_qwen3_235b_qwen_license_passthrough() -> None:
    # "qwen" not in _VAGUE_LICENSE_VALUES; not recognized by licenseid matcher →
    # _canonicalize_license_id returns it unchanged
    with _patch_qwen3_235b():
        meta = read_huggingface("Qwen/Qwen3-235B-A22B")
    assert meta.license == "qwen"


def test_qwen35_27b_apache_license() -> None:
    with _patch_qwen35_27b():
        meta = read_huggingface("Qwen/Qwen3.5-27B")
    assert meta.license == "Apache-2.0"


def test_kanana_15v_license_passthrough() -> None:
    # "kanana-license" not in _VAGUE_LICENSE_VALUES; not recognized by
    # licenseid matcher → _canonicalize_license_id returns it unchanged;
    # no file detection triggered
    with _patch_kanana_15v():
        meta = read_huggingface("kakaobank/kanana-1.5-v-3b-instruct")
    assert meta.license == "kanana-license"
    assert "hf.license_raw" not in (meta.extra_data or {})


def test_exaone45_33b_vague_license() -> None:
    # license="other" → vague → detection mock returns (None, None) → license=None
    with _patch_exaone45_33b():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


def test_exaone45_33b_awq_vague_license() -> None:
    with _patch_exaone45_33b_awq():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-AWQ")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


def test_exaone45_33b_fp8_vague_license() -> None:
    with _patch_exaone45_33b_fp8():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-FP8")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


def test_exaone45_33b_gguf_vague_license() -> None:
    with _patch_exaone45_33b_gguf():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-4.5-33B-GGUF")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


def test_exaone_path_vague_license() -> None:
    with _patch_exaone_path():
        meta = read_huggingface("LGAI-EXAONE/EXAONE-Path-2.0-rev-EGFR")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


def test_glm45_air_reap_apache_license() -> None:
    with _patch_glm45_air_reap():
        meta = read_huggingface("THUDM/GLM-4.5-Air-REAP")
    assert meta.license == "Apache-2.0"


def test_line_distilbert_apache_license() -> None:
    with _patch_line_distilbert():
        meta = read_huggingface("line-corporation/line-distilbert-base-japanese")
    assert meta.license == "Apache-2.0"


def test_clip_japanese_v2_apache_license() -> None:
    with _patch_clip_japanese_v2():
        meta = read_huggingface("line-corporation/clip-japanese-base-v2")
    assert meta.license == "Apache-2.0"


def test_fujitsu_llm_apache_license() -> None:
    with _patch_fujitsu_llm():
        meta = read_huggingface("Fujitsu/Fujitsu-LLM-KG-8x7B")
    assert meta.license == "Apache-2.0"


def test_windowseat_apache_license() -> None:
    with _patch_windowseat():
        meta = read_huggingface("windowseat-ai/windowseat-reflection")
    assert meta.license == "Apache-2.0"


def test_moirai_cc_by_nc_license() -> None:
    with _patch_moirai():
        meta = read_huggingface("Salesforce/moirai-2.0-R-small")
    assert meta.license == "CC-BY-NC-4.0"


def test_llasa_3b_cc_by_nc_license() -> None:
    with _patch_llasa_3b():
        meta = read_huggingface("HKUSTAudio/Llasa-3B")
    assert meta.license == "CC-BY-NC-4.0"


def test_tildeopen_30b_64k_cc_by_license() -> None:
    with _patch_tildeopen_30b_64k():
        meta = read_huggingface("TildeAI/TildeOpen-30b-64k")
    assert meta.license == "CC-BY-4.0"


def test_bloom_custom_license_passthrough() -> None:
    # "bigscience-bloom-rail-1.0" not in _VAGUE_LICENSE_VALUES, not a known
    # Not recognized by licenseid matcher → _canonicalize_license_id returns
    # it unchanged.
    with _patch_bloom():
        meta = read_huggingface("bigscience/bloom")
    assert meta.license == "bigscience-bloom-rail-1.0"
    assert "hf.license_raw" not in (meta.extra_data or {})


def test_bloomz_7b1_custom_license_passthrough() -> None:
    with _patch_bloomz_7b1():
        meta = read_huggingface("bigscience/bloomz-7b1")
    assert meta.license == "bigscience-bloom-rail-1.0"


def test_cohere_aya_23_no_license() -> None:
    with _patch_cohere_aya_23():
        meta = read_huggingface("CohereLabs/aya-23-8B")
    assert meta.license is None


def test_pharia_control_vague_license_with_license_name() -> None:
    # license=other (vague) → detection triggered → mock returns (None, None)
    # license_name=open-aleph-license stored in extra_data["hf.license_name"]
    with _patch_pharia_control():
        meta = read_huggingface("Aleph-Alpha/Pharia-1-LLM-7B-control")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"
    assert (meta.extra_data or {}).get("hf.license_name") == "open-aleph-license"


def test_pharia_aligned_vague_license_with_license_name() -> None:
    with _patch_pharia_aligned():
        meta = read_huggingface("Aleph-Alpha/Pharia-1-LLM-7B-control-aligned")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_name") == "open-aleph-license"


def test_wmt22_cometkiwi_no_license() -> None:
    with _patch_wmt22_cometkiwi():
        meta = read_huggingface("Unbabel/wmt22-cometkiwi-da")
    assert meta.license is None


def test_stable_zero123_vague_license() -> None:
    with _patch_stable_zero123():
        meta = read_huggingface("stabilityai/stable-zero123")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"
    assert (meta.extra_data or {}).get("hf.license_name") == "sai-nc-community"


def test_shap_e_mit_license() -> None:
    with _patch_shap_e():
        meta = read_huggingface("openai/shap-e")
    assert meta.license == "MIT"


def test_hy_motion_vague_license_with_license_name() -> None:
    # license=other (vague) + license_name=tencent-hunyuan-community
    with _patch_hy_motion():
        meta = read_huggingface("tencent/HY-Motion-1.0")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"
    assert (meta.extra_data or {}).get("hf.license_name") == "tencent-hunyuan-community"


def test_apple_sharp_apple_amlr_license_passthrough() -> None:
    # apple-amlr not in _VAGUE_LICENSE_VALUES; not recognized by licenseid matcher →
    # _canonicalize_license_id returns it unchanged
    with _patch_apple_sharp():
        meta = read_huggingface("apple/Sharp")
    assert meta.license == "apple-amlr"
    assert "hf.license_raw" not in (meta.extra_data or {})


def test_firered_vad_apache_license() -> None:
    with _patch_firered_vad():
        meta = read_huggingface("FireRedTeam/FireRedVAD")
    assert meta.license == "Apache-2.0"


def test_gte_reranker_apache_license() -> None:
    with _patch_gte_reranker():
        meta = read_huggingface("Alibaba-NLP/gte-multilingual-reranker-base")
    assert meta.license == "Apache-2.0"


def test_minimax_m2_vague_license() -> None:
    with _patch_minimax_m2():
        meta = read_huggingface("MiniMaxAI/MiniMax-M2.7")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


def test_llada2_moe_apache_license() -> None:
    with _patch_llada2_moe():
        meta = read_huggingface("inclusionAI/LLaDA2.0-Uni")
    assert meta.license == "Apache-2.0"


def test_lightglue_vague_license() -> None:
    with _patch_lightglue():
        meta = read_huggingface("ETH-CVG/lightglue_superpoint")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


def test_codeberta_no_license() -> None:
    # No license field in card YAML → meta.license=None
    with _patch_codeberta():
        meta = read_huggingface("huggingface/CodeBERTa-small-v1")
    assert meta.license is None
    assert "hf.license_raw" not in (meta.extra_data or {})


def test_hrnetpose_vague_license() -> None:
    with _patch_hrnetpose():
        meta = read_huggingface("qualcomm/HRNetPose")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"


def test_timelens_vague_license_with_spdx_license_name() -> None:
    # license=other (vague) + license_name=bsd-3-clause (an actual SPDX identifier)
    with _patch_timelens():
        meta = read_huggingface("TencentARC/TimeLens-8B")
    assert meta.license is None
    assert (meta.extra_data or {}).get("hf.license_raw") == "other"
    assert (meta.extra_data or {}).get("hf.license_name") == "bsd-3-clause"
