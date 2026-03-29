# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Safetensors metadata extractor (mocked and integration)."""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.extract.ai_model import read_safetensors

# ---------------------------------------------------------------------------
# Safetensors extractor (mocked)
# ---------------------------------------------------------------------------

_ST = Path(__file__).parent / "fixtures" / "safetensors"


def test_safetensors_missing_library(tmp_path: Path) -> None:
    model_file = tmp_path / "weights.safetensors"
    model_file.write_bytes(b"fake")
    with patch.dict("sys.modules", {"safetensors": None}):
        with pytest.raises(ImportError, match="safetensors"):
            read_safetensors(model_file)


def test_safetensors_basic_extraction(tmp_path: Path) -> None:
    model_file = tmp_path / "model.safetensors"
    model_file.write_bytes(b"fake")

    raw_metadata = {
        "modelspec.title": "My Diffusion Model",
        "modelspec.description": "A latent diffusion model",
        "modelspec.architecture": "stable-diffusion-xl-v1",
        "modelspec.version": "1.0",
        "custom_key": "custom_value",
    }
    tensor_keys = ["model.embed_tokens.weight", "model.layers.0.weight"]

    mock_file_ctx = MagicMock()
    mock_file_ctx.__enter__ = MagicMock(return_value=mock_file_ctx)
    mock_file_ctx.__exit__ = MagicMock(return_value=False)
    mock_file_ctx.metadata.return_value = raw_metadata
    mock_file_ctx.keys.return_value = tensor_keys

    mock_safetensors = MagicMock()
    mock_safetensors.safe_open.return_value = mock_file_ctx

    with patch.dict("sys.modules", {"safetensors": mock_safetensors}):
        meta = read_safetensors(model_file)

    assert meta.format_info.model_format == AiModelFormat.SAFETENSORS
    assert meta.name == "My Diffusion Model"
    assert meta.description == "A latent diffusion model"
    assert meta.version == "1.0"
    assert meta.architecture == "stable-diffusion-xl-v1"
    assert meta.properties["custom_key"] == "custom_value"
    assert len(meta.inputs) == 2
    assert meta.inputs[0]["name"] == "model.embed_tokens.weight"
    assert "name" in meta.provenance
    assert "inputs" in meta.provenance


def test_safetensors_empty_metadata(tmp_path: Path) -> None:
    model_file = tmp_path / "model.safetensors"
    model_file.write_bytes(b"fake")

    mock_file_ctx = MagicMock()
    mock_file_ctx.__enter__ = MagicMock(return_value=mock_file_ctx)
    mock_file_ctx.__exit__ = MagicMock(return_value=False)
    mock_file_ctx.metadata.return_value = {}
    mock_file_ctx.keys.return_value = []

    mock_safetensors = MagicMock()
    mock_safetensors.safe_open.return_value = mock_file_ctx

    with patch.dict("sys.modules", {"safetensors": mock_safetensors}):
        meta = read_safetensors(model_file)

    assert meta.name is None
    assert meta.description is None
    assert meta.version is None
    assert meta.type_of_model is None
    assert meta.inputs == []


def test_safetensors_fallback_keys(tmp_path: Path) -> None:
    """Verify fallback metadata key resolution."""
    model_file = tmp_path / "model.safetensors"
    model_file.write_bytes(b"fake")

    raw_metadata = {
        "name": "Fallback Name",
        "description": "Fallback description",
        "version": "0.1",
        "architecture": "llama",
    }

    mock_file_ctx = MagicMock()
    mock_file_ctx.__enter__ = MagicMock(return_value=mock_file_ctx)
    mock_file_ctx.__exit__ = MagicMock(return_value=False)
    mock_file_ctx.metadata.return_value = raw_metadata
    mock_file_ctx.keys.return_value = []

    mock_safetensors = MagicMock()
    mock_safetensors.safe_open.return_value = mock_file_ctx

    with patch.dict("sys.modules", {"safetensors": mock_safetensors}):
        meta = read_safetensors(model_file)

    assert meta.name == "Fallback Name"
    assert meta.description == "Fallback description"
    assert meta.version == "0.1"
    assert meta.architecture == "llama"


def test_safetensors_read_failure(tmp_path: Path) -> None:
    model_file = tmp_path / "model.safetensors"
    model_file.write_bytes(b"corrupt")

    mock_safetensors = MagicMock()
    mock_safetensors.safe_open.side_effect = OSError("bad file")

    with patch.dict("sys.modules", {"safetensors": mock_safetensors}):
        with pytest.raises(ValueError, match="Failed to read Safetensors"):
            read_safetensors(model_file)


# ---------------------------------------------------------------------------
# Integration tests — real Safetensors file (marian-tiny-random.safetensors)
# Source: optimum-internal-testing/tiny-random-marian (~690 KB)
# Tiny randomly-initialised MarianMT translation encoder-decoder; 86 tensors, MIT
# Require: safetensors installed AND
#          tests/fixtures/safetensors/marian-tiny-random.safetensors present
# ---------------------------------------------------------------------------

MARIAN_FIXTURE = _ST / "marian-tiny-random.safetensors"


@pytest.fixture(scope="module")
def marian_metadata() -> AiModelMetadata:
    """Extract metadata from the marian-tiny-random fixture once per session."""
    pytest.importorskip("safetensors")
    if not MARIAN_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {MARIAN_FIXTURE}")
    return read_safetensors(MARIAN_FIXTURE)


def test_marian_format(marian_metadata: AiModelMetadata) -> None:
    assert marian_metadata.format_info.model_format == AiModelFormat.SAFETENSORS


def test_marian_no_model_metadata(marian_metadata: AiModelMetadata) -> None:
    # Only __metadata__ entry is 'format': 'pt'; no modelspec keys
    assert marian_metadata.name is None
    assert marian_metadata.description is None
    assert marian_metadata.version is None
    assert marian_metadata.type_of_model is None


def test_marian_format_property(marian_metadata: AiModelMetadata) -> None:
    assert marian_metadata.properties.get("format") == "pt"


def test_marian_tensor_count(marian_metadata: AiModelMetadata) -> None:
    # MarianMT encoder-decoder: embedding, 2 encoder + 2 decoder layers, bias
    assert len(marian_metadata.inputs) == 86


def test_marian_tensor_names(marian_metadata: AiModelMetadata) -> None:
    names = {t["name"] for t in marian_metadata.inputs}
    # MarianMT has both encoder and decoder sub-modules plus shared embedding
    assert any(n.startswith("model.encoder.") for n in names)
    assert any(n.startswith("model.decoder.") for n in names)
    assert "model.shared.weight" in names


def test_marian_provenance(marian_metadata: AiModelMetadata) -> None:
    assert "inputs" in marian_metadata.provenance
    assert "properties" in marian_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real Safetensors file (phi-tiny-random.safetensors)
# Source: echarlaix/tiny-random-PhiForCausalLM (~316 KB)
# Tiny randomly-initialised Phi causal language model; 33 tensors, Apache-2.0
# Require: safetensors installed AND
#          tests/fixtures/safetensors/phi-tiny-random.safetensors present
# ---------------------------------------------------------------------------

PHI_FIXTURE = _ST / "phi-tiny-random.safetensors"


@pytest.fixture(scope="module")
def phi_metadata() -> AiModelMetadata:
    """Extract metadata from the phi-tiny-random fixture once per session."""
    pytest.importorskip("safetensors")
    if not PHI_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {PHI_FIXTURE}")
    return read_safetensors(PHI_FIXTURE)


def test_phi_format(phi_metadata: AiModelMetadata) -> None:
    assert phi_metadata.format_info.model_format == AiModelFormat.SAFETENSORS


def test_phi_no_model_metadata(phi_metadata: AiModelMetadata) -> None:
    # Only __metadata__ entry is 'format': 'pt'; no modelspec keys
    assert phi_metadata.name is None
    assert phi_metadata.description is None
    assert phi_metadata.version is None
    assert phi_metadata.type_of_model is None


def test_phi_format_property(phi_metadata: AiModelMetadata) -> None:
    assert phi_metadata.properties.get("format") == "pt"


def test_phi_tensor_count(phi_metadata: AiModelMetadata) -> None:
    # 2-layer Phi model: embeddings + 2 × attention blocks + head
    assert len(phi_metadata.inputs) == 33


def test_phi_tensor_names(phi_metadata: AiModelMetadata) -> None:
    names = {t["name"] for t in phi_metadata.inputs}
    # Phi uses standard transformer naming: embed_tokens, layers, lm_head
    assert "model.embed_tokens.weight" in names
    assert "lm_head.weight" in names
    assert any(n.startswith("model.layers.") for n in names)


def test_phi_provenance(phi_metadata: AiModelMetadata) -> None:
    assert "inputs" in phi_metadata.provenance
    assert "properties" in phi_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real Safetensors file (speech2text-tiny-random.safetensors)
# Source: optimum-internal-testing/tiny-random-Speech2TextModel (~689 KB)
# Tiny randomly-initialised Speech2Text ASR encoder-decoder; 93 tensors, Apache-2.0
# Require: safetensors installed AND
#          tests/fixtures/safetensors/speech2text-tiny-random.safetensors present
# ---------------------------------------------------------------------------

SPEECH2TEXT_FIXTURE = _ST / "speech2text-tiny-random.safetensors"


@pytest.fixture(scope="module")
def speech2text_metadata() -> AiModelMetadata:
    """Extract metadata from the speech2text-tiny-random fixture once per session."""
    pytest.importorskip("safetensors")
    if not SPEECH2TEXT_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {SPEECH2TEXT_FIXTURE}")
    return read_safetensors(SPEECH2TEXT_FIXTURE)


def test_speech2text_format(speech2text_metadata: AiModelMetadata) -> None:
    assert speech2text_metadata.format_info.model_format == AiModelFormat.SAFETENSORS


def test_speech2text_no_model_metadata(speech2text_metadata: AiModelMetadata) -> None:
    # Only __metadata__ entry is 'format': 'pt'; no modelspec keys
    assert speech2text_metadata.name is None
    assert speech2text_metadata.description is None
    assert speech2text_metadata.version is None
    assert speech2text_metadata.type_of_model is None


def test_speech2text_format_property(speech2text_metadata: AiModelMetadata) -> None:
    assert speech2text_metadata.properties.get("format") == "pt"


def test_speech2text_tensor_count(speech2text_metadata: AiModelMetadata) -> None:
    # Speech2Text encoder-decoder: conv layers + 2 encoder + 2 decoder layers
    assert len(speech2text_metadata.inputs) == 93


def test_speech2text_tensor_names(speech2text_metadata: AiModelMetadata) -> None:
    names = {t["name"] for t in speech2text_metadata.inputs}
    # Speech2Text has both encoder (with conv) and decoder sub-modules
    assert any(n.startswith("model.encoder.") for n in names)
    assert any(n.startswith("model.decoder.") for n in names)


def test_speech2text_provenance(speech2text_metadata: AiModelMetadata) -> None:
    assert "inputs" in speech2text_metadata.provenance
    assert "properties" in speech2text_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real Safetensors file (vits-tiny-random.safetensors)
# Source: echarlaix/tiny-random-vits (~344 KB)
# Randomly initialised VITS text-to-speech model; 438 tensors
# Require: safetensors installed AND
#          tests/fixtures/safetensors/vits-tiny-random.safetensors present
# ---------------------------------------------------------------------------

VITS_FIXTURE = _ST / "vits-tiny-random.safetensors"


@pytest.fixture(scope="module")
def vits_metadata() -> AiModelMetadata:
    """Extract metadata from the vits-tiny-random fixture once per session."""
    pytest.importorskip("safetensors")
    if not VITS_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {VITS_FIXTURE}")
    return read_safetensors(VITS_FIXTURE)


def test_vits_format(vits_metadata: AiModelMetadata) -> None:
    assert vits_metadata.format_info.model_format == AiModelFormat.SAFETENSORS


def test_vits_no_model_metadata(vits_metadata: AiModelMetadata) -> None:
    assert vits_metadata.name is None
    assert vits_metadata.description is None
    assert vits_metadata.version is None
    assert vits_metadata.type_of_model is None


def test_vits_format_property(vits_metadata: AiModelMetadata) -> None:
    assert vits_metadata.properties.get("format") == "pt"


def test_vits_tensor_count(vits_metadata: AiModelMetadata) -> None:
    # VITS has many sub-networks (text encoder, decoder, flow, posterior encoder)
    assert len(vits_metadata.inputs) == 438


def test_vits_tensor_names(vits_metadata: AiModelMetadata) -> None:
    names = {t["name"] for t in vits_metadata.inputs}
    # Key sub-modules of a VITS TTS model
    assert any(n.startswith("decoder.") for n in names)
    assert any(n.startswith("text_encoder.") for n in names)
    assert "text_encoder.project.weight" in names


def test_vits_provenance(vits_metadata: AiModelMetadata) -> None:
    assert "inputs" in vits_metadata.provenance
    assert "properties" in vits_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real Safetensors file (whisper-tiny-random.safetensors)
# Source: optimum-internal-testing/tiny-random-whisper (~872 KB)
# Randomly initialised Whisper ASR encoder-decoder; 50 tensors
# Require: safetensors installed AND
#          tests/fixtures/safetensors/whisper-tiny-random.safetensors present
# ---------------------------------------------------------------------------

WHISPER_ST_FIXTURE = _ST / "whisper-tiny-random.safetensors"


@pytest.fixture(scope="module")
def whisper_st_metadata() -> AiModelMetadata:
    """Extract metadata from the whisper-tiny-random safetensors fixture."""
    pytest.importorskip("safetensors")
    if not WHISPER_ST_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {WHISPER_ST_FIXTURE}")
    return read_safetensors(WHISPER_ST_FIXTURE)


def test_whisper_st_format(whisper_st_metadata: AiModelMetadata) -> None:
    assert whisper_st_metadata.format_info.model_format == AiModelFormat.SAFETENSORS


def test_whisper_st_no_model_metadata(whisper_st_metadata: AiModelMetadata) -> None:
    assert whisper_st_metadata.name is None
    assert whisper_st_metadata.type_of_model is None


def test_whisper_st_format_property(whisper_st_metadata: AiModelMetadata) -> None:
    assert whisper_st_metadata.properties.get("format") == "pt"


def test_whisper_st_tensor_count(whisper_st_metadata: AiModelMetadata) -> None:
    assert len(whisper_st_metadata.inputs) == 50


def test_whisper_st_tensor_names(whisper_st_metadata: AiModelMetadata) -> None:
    names = {t["name"] for t in whisper_st_metadata.inputs}
    # Whisper has both encoder and decoder sub-modules
    assert any(n.startswith("model.encoder.") for n in names)
    assert any(n.startswith("model.decoder.") for n in names)


def test_whisper_st_provenance(whisper_st_metadata: AiModelMetadata) -> None:
    assert "inputs" in whisper_st_metadata.provenance
    assert "properties" in whisper_st_metadata.provenance
