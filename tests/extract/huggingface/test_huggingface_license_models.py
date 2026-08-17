# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pitloom.extract._huggingface import (
    read_huggingface,
)

from .conftest import (
    _patch_apple_sharp,
    _patch_arabic_legal_ocr,
    _patch_aspect_finnlp_th,
    _patch_blip_vqa,
    _patch_bloom,
    _patch_bloomz_7b1,
    _patch_clip_japanese_v2,
    _patch_codeberta,
    _patch_cohere_aya_23,
    _patch_deberta_human_value,
    _patch_exaone45_33b,
    _patch_exaone45_33b_awq,
    _patch_exaone45_33b_fp8,
    _patch_exaone45_33b_gguf,
    _patch_exaone_path,
    _patch_firered_vad,
    _patch_fujitsu_llm,
    _patch_gabert,
    _patch_glm45_air_reap,
    _patch_gte_reranker,
    _patch_hermes_3_llama_3b,
    _patch_hrnetpose,
    _patch_hunyuan_mt,
    _patch_hy_motion,
    _patch_kanana_15v,
    _patch_legal_embed_ita,
    _patch_lightglue,
    _patch_line_distilbert,
    _patch_llada2_moe,
    _patch_llasa_3b,
    _patch_minimax_m2,
    _patch_moirai,
    _patch_opt_2_7b,
    _patch_opt_iml,
    _patch_pharia_aligned,
    _patch_pharia_control,
    _patch_phi2,
    _patch_protonx_legal,
    _patch_qwen3_235b,
    _patch_qwen35_27b,
    _patch_sealion_27b_it,
    _patch_seamless_m4t,
    _patch_shap_e,
    _patch_stable_zero123,
    _patch_tildeopen_30b_64k,
    _patch_timelens,
    _patch_windowseat,
    _patch_wmt22_cometkiwi,
)


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
