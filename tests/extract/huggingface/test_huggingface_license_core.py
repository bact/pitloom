# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pitloom.extract._huggingface import read_huggingface
from pitloom.extract._huggingface_fetch import (
    _detect_license_from_hf_files,
    _list_license_files_in_repo,
)

from .hf_patches._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)
from .hf_patches._hf_patches_embeddings import (
    _patch_rad_dino,
    _patch_timm_convnext,
    _patch_uni2,
)
from .hf_patches._hf_patches_gated_access import (
    _patch_aya_vision,
    _patch_gemma,
    _patch_inkubalm,
    _patch_serengeti,
)
from .hf_patches._hf_patches_gated_metadata import (
    _patch_deepseek,
    _patch_mistral_medium,
    _patch_seallms,
)
from .hf_patches._hf_patches_generative_3d import (
    _patch_groot,
    _patch_pi05,
)
from .hf_patches._hf_patches_multimodal import (
    _patch_jina_v4,
    _patch_kimi,
    _patch_sealion_gguf,
)
from .hf_patches._hf_patches_speech_audio import (
    _patch_kokoro,
)
from .hf_patches._hf_patches_text_generation_pretrained import (
    _patch_llama,
    _patch_starcoder2,
)
from .hf_patches._hf_patches_text_generation_regional import (
    _patch_mallam,
    _patch_typhoon,
)
from .hf_patches._hf_patches_vision import (
    _patch_depth_pro,
    _patch_rmbg14,
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
            "pitloom.extract._huggingface_fetch._detect_license_from_hf_files",
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
            "pitloom.extract._huggingface_fetch._detect_license_from_hf_files",
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
            "pitloom.extract._huggingface_fetch._detect_license_from_hf_files",
            mock_detect,
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
        "pitloom.extract._huggingface_fetch._list_license_files_in_repo",
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
        with caplog.at_level(
            logging.DEBUG, logger="pitloom.extract._huggingface_fetch"
        ):
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
        "pitloom.extract._huggingface_fetch._list_license_files_in_repo",
        return_value=["LICENSE"],
    ):
        with patch(
            "huggingface_hub.hf_hub_download",
            side_effect=OSError("download failed"),
        ):
            with caplog.at_level(
                logging.DEBUG, logger="pitloom.extract._huggingface_fetch"
            ):
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
            "pitloom.extract._huggingface_fetch._detect_license_from_hf_files",
            detected_mock,
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
    # Not recognized by licenseid matcher -> _canonicalize_license_id returns
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
