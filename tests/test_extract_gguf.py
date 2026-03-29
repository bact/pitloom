# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GGUF metadata extractor (mocked and integration)."""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.extract.ai_model import read_gguf

# ---------------------------------------------------------------------------
# GGUF extractor (mocked)
# ---------------------------------------------------------------------------

_GGUF = Path(__file__).parent / "fixtures" / "gguf"


def _make_gguf_field(value: int | str) -> MagicMock:
    """Create a mock GGUFReader field with a single scalar value."""
    field = MagicMock()
    arr = MagicMock()
    arr.tolist.return_value = [value]
    field.parts = [arr]
    return field


def test_gguf_missing_library(tmp_path: Path) -> None:
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake")
    with patch.dict("sys.modules", {"gguf": None}):
        with pytest.raises(ImportError, match="gguf"):
            read_gguf(model_file)


def test_gguf_basic_extraction(tmp_path: Path) -> None:
    model_file = tmp_path / "llama.gguf"
    model_file.write_bytes(b"fake")

    mock_fields = {
        "general.architecture": _make_gguf_field("llama"),
        "general.name": _make_gguf_field("LLaMA-3-8B"),
        "general.description": _make_gguf_field("Meta LLaMA 3 8B"),
        "general.version": _make_gguf_field("3.0"),
        "llama.context_length": _make_gguf_field(8192),
        "llama.embedding_length": _make_gguf_field(4096),
        "llama.attention.head_count": _make_gguf_field(32),
        "llama.block_count": _make_gguf_field(32),
        "tokenizer.ggml.model": _make_gguf_field("llama"),
    }

    mock_reader = MagicMock()
    mock_reader.fields = mock_fields

    mock_gguf = MagicMock()
    mock_gguf.GGUFReader.return_value = mock_reader

    with patch.dict("sys.modules", {"gguf": mock_gguf}):
        meta = read_gguf(model_file)

    assert meta.format_info.model_format == AiModelFormat.GGUF
    assert meta.name == "LLaMA-3-8B"
    assert meta.description == "Meta LLaMA 3 8B"
    assert meta.version == "3.0"
    assert meta.architecture == "llama"
    assert meta.hyperparameters["llama.context_length"] == 8192
    assert meta.hyperparameters["llama.embedding_length"] == 4096
    assert meta.hyperparameters["llama.attention.head_count"] == 32
    assert meta.hyperparameters["llama.block_count"] == 32
    # Non-hyperparam key goes to properties
    assert "tokenizer.ggml.model" in meta.properties
    assert "hyperparameters" in meta.provenance
    assert "architecture" in meta.provenance


def test_gguf_minimal_fields(tmp_path: Path) -> None:
    """Only architecture, no name or description."""
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake")

    mock_fields = {
        "general.architecture": _make_gguf_field("mistral"),
    }

    mock_reader = MagicMock()
    mock_reader.fields = mock_fields

    mock_gguf = MagicMock()
    mock_gguf.GGUFReader.return_value = mock_reader

    with patch.dict("sys.modules", {"gguf": mock_gguf}):
        meta = read_gguf(model_file)

    assert meta.architecture == "mistral"
    assert meta.name is None
    assert meta.description is None
    assert meta.version is None


def test_gguf_load_failure(tmp_path: Path) -> None:
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"corrupt")

    mock_gguf = MagicMock()
    mock_gguf.GGUFReader.side_effect = ValueError("bad magic")

    with patch.dict("sys.modules", {"gguf": mock_gguf}):
        with pytest.raises(ValueError, match="Failed to read GGUF"):
            read_gguf(model_file)


# ---------------------------------------------------------------------------
# Integration tests — real GGUF file (ggml-vocab-bert-bge.gguf)
# Source: ggerganov/llama.cpp GitHub (models/ggml-vocab-bert-bge.gguf)
# Vocabulary-only GGUF for the BGE BERT tokenizer; zero model tensors
# Require: gguf installed AND tests/fixtures/gguf/ggml-vocab-bert-bge.gguf present
# ---------------------------------------------------------------------------

VOCAB_BERT_BGE_FIXTURE = _GGUF / "ggml-vocab-bert-bge.gguf"


@pytest.fixture(scope="module")
def vocab_bert_bge_metadata() -> AiModelMetadata:
    """Extract metadata from the ggml-vocab-bert-bge.gguf fixture once per session."""
    pytest.importorskip("gguf")
    if not VOCAB_BERT_BGE_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {VOCAB_BERT_BGE_FIXTURE}")
    return read_gguf(VOCAB_BERT_BGE_FIXTURE)


def test_vocab_bert_bge_format(vocab_bert_bge_metadata: AiModelMetadata) -> None:
    assert vocab_bert_bge_metadata.format_info.model_format == AiModelFormat.GGUF


def test_vocab_bert_bge_name(vocab_bert_bge_metadata: AiModelMetadata) -> None:
    assert vocab_bert_bge_metadata.name == "bert-bge"
    assert "general.name" in vocab_bert_bge_metadata.provenance["name"]


def test_vocab_bert_bge_architecture(vocab_bert_bge_metadata: AiModelMetadata) -> None:
    assert vocab_bert_bge_metadata.architecture == "bert"
    assert "general.architecture" in vocab_bert_bge_metadata.provenance["architecture"]


def test_vocab_bert_bge_hyperparameters(
    vocab_bert_bge_metadata: AiModelMetadata,
) -> None:
    hp = vocab_bert_bge_metadata.hyperparameters
    assert hp["bert.block_count"] == 12
    assert hp["bert.context_length"] == 512
    assert hp["bert.embedding_length"] == 384
    assert hp["bert.feed_forward_length"] == 1536
    assert hp["bert.attention.head_count"] == 12


def test_vocab_bert_bge_zero_tensors(vocab_bert_bge_metadata: AiModelMetadata) -> None:
    # Vocabulary-only GGUF — no model weight tensors
    assert vocab_bert_bge_metadata.properties.get("GGUF.tensor_count") == "0"


def test_vocab_bert_bge_properties(vocab_bert_bge_metadata: AiModelMetadata) -> None:
    props = vocab_bert_bge_metadata.properties
    assert props.get("GGUF.version") == "3"
    assert props.get("general.architecture") == "bert"
    assert props.get("tokenizer.ggml.model") == "bert"
    assert props.get("tokenizer.ggml.pre") == "bert-bge"


def test_vocab_bert_bge_provenance(vocab_bert_bge_metadata: AiModelMetadata) -> None:
    assert "hyperparameters" in vocab_bert_bge_metadata.provenance
    assert "properties" in vocab_bert_bge_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real GGUF file (ggml-vocab-phi-3.gguf)
# Source: ggerganov/llama.cpp GitHub (models/ggml-vocab-phi-3.gguf)
# Vocabulary-only GGUF for the Phi-3 tokenizer (LLaMA BPE, RoPE architecture)
# Require: gguf installed AND tests/fixtures/gguf/ggml-vocab-phi-3.gguf present
# ---------------------------------------------------------------------------

VOCAB_PHI3_FIXTURE = _GGUF / "ggml-vocab-phi-3.gguf"


@pytest.fixture(scope="module")
def vocab_phi3_metadata() -> AiModelMetadata:
    """Extract metadata from the ggml-vocab-phi-3.gguf fixture once per session."""
    pytest.importorskip("gguf")
    if not VOCAB_PHI3_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {VOCAB_PHI3_FIXTURE}")
    return read_gguf(VOCAB_PHI3_FIXTURE)


def test_vocab_phi3_format(vocab_phi3_metadata: AiModelMetadata) -> None:
    assert vocab_phi3_metadata.format_info.model_format == AiModelFormat.GGUF


def test_vocab_phi3_name(vocab_phi3_metadata: AiModelMetadata) -> None:
    assert vocab_phi3_metadata.name == "Phi3"
    assert "general.name" in vocab_phi3_metadata.provenance["name"]


def test_vocab_phi3_architecture(vocab_phi3_metadata: AiModelMetadata) -> None:
    assert vocab_phi3_metadata.architecture == "phi3"


def test_vocab_phi3_hyperparameters(vocab_phi3_metadata: AiModelMetadata) -> None:
    hp = vocab_phi3_metadata.hyperparameters
    assert hp["phi3.context_length"] == 4096
    assert hp["phi3.embedding_length"] == 3072
    assert hp["phi3.block_count"] == 32
    assert hp["phi3.attention.head_count"] == 32
    assert hp["phi3.rope.dimension_count"] == 96


def test_vocab_phi3_zero_tensors(vocab_phi3_metadata: AiModelMetadata) -> None:
    assert vocab_phi3_metadata.properties.get("GGUF.tensor_count") == "0"


def test_vocab_phi3_tokenizer(vocab_phi3_metadata: AiModelMetadata) -> None:
    props = vocab_phi3_metadata.properties
    # Phi-3 uses a LLaMA-family BPE tokenizer (not BERT WordPiece)
    assert props.get("tokenizer.ggml.model") == "llama"
    assert props.get("general.architecture") == "phi3"


def test_vocab_phi3_provenance(vocab_phi3_metadata: AiModelMetadata) -> None:
    assert "hyperparameters" in vocab_phi3_metadata.provenance
    assert "properties" in vocab_phi3_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real GGUF file (mmproj-tinygemma3.gguf)
# Source: ggml-org/tinygemma3-GGUF (~1.0 MB)
# CLIP vision multimodal projector for tinygemma3; architecture = "clip"
# Require: gguf installed AND
#          tests/fixtures/gguf/mmproj-tinygemma3.gguf present
# ---------------------------------------------------------------------------

MMPROJ_FIXTURE = _GGUF / "mmproj-tinygemma3.gguf"


@pytest.fixture(scope="module")
def mmproj_metadata() -> AiModelMetadata:
    """Extract metadata from the mmproj-tinygemma3.gguf fixture once per session."""
    pytest.importorskip("gguf")
    if not MMPROJ_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {MMPROJ_FIXTURE}")
    return read_gguf(MMPROJ_FIXTURE)


def test_mmproj_format(mmproj_metadata: AiModelMetadata) -> None:
    assert mmproj_metadata.format_info.model_format == AiModelFormat.GGUF


def test_mmproj_architecture(mmproj_metadata: AiModelMetadata) -> None:
    # Multimodal projector uses the "clip" architecture
    assert mmproj_metadata.architecture == "clip"
    assert "general.architecture" in mmproj_metadata.provenance["architecture"]


def test_mmproj_no_name(mmproj_metadata: AiModelMetadata) -> None:
    # mmproj files don't carry a general.name
    assert mmproj_metadata.name is None
    assert mmproj_metadata.description is None
    assert mmproj_metadata.version is None


def test_mmproj_hyperparameters(mmproj_metadata: AiModelMetadata) -> None:
    hp = mmproj_metadata.hyperparameters
    assert hp["clip.vision.embedding_length"] == 128
    assert hp["clip.vision.feed_forward_length"] == 512
    assert hp["clip.vision.block_count"] == 4
    assert hp["clip.vision.attention.head_count"] == 4


def test_mmproj_properties(mmproj_metadata: AiModelMetadata) -> None:
    props = mmproj_metadata.properties
    assert props.get("GGUF.version") == "3"
    assert props.get("GGUF.tensor_count") == "71"
    assert props.get("general.architecture") == "clip"
    assert props.get("general.type") == "clip-vision"
    assert props.get("clip.vision.image_size") == "32"
    assert props.get("clip.vision.patch_size") == "2"
    assert props.get("clip.projector_type") == "gemma3"


def test_mmproj_provenance(mmproj_metadata: AiModelMetadata) -> None:
    assert "hyperparameters" in mmproj_metadata.provenance
    assert "properties" in mmproj_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real GGUF file (stories260K.gguf)
# Source: ggml-org/models tinyllamas/stories260K.gguf (~1.1 MB)
# A 260K-parameter LLaMA model trained on TinyStories (Karpathy / llama2.c)
# Require: gguf installed AND tests/fixtures/gguf/stories260K.gguf present
# ---------------------------------------------------------------------------

STORIES260K_FIXTURE = _GGUF / "stories260K.gguf"


@pytest.fixture(scope="module")
def stories260k_metadata() -> AiModelMetadata:
    """Extract metadata from the stories260K.gguf fixture once per session."""
    pytest.importorskip("gguf")
    if not STORIES260K_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {STORIES260K_FIXTURE}")
    return read_gguf(STORIES260K_FIXTURE)


def test_gguf_integration_format(stories260k_metadata: AiModelMetadata) -> None:
    assert stories260k_metadata.format_info.model_format == AiModelFormat.GGUF


def test_gguf_integration_architecture(stories260k_metadata: AiModelMetadata) -> None:
    # general.architecture = 'llama'
    assert stories260k_metadata.architecture == "llama"
    assert "architecture" in stories260k_metadata.provenance
    assert "general.architecture" in stories260k_metadata.provenance["architecture"]


def test_gguf_integration_name(stories260k_metadata: AiModelMetadata) -> None:
    # general.name = 'llama' (same as architecture in this tiny model)
    assert stories260k_metadata.name == "llama"
    assert "name" in stories260k_metadata.provenance


def test_gguf_integration_no_description(stories260k_metadata: AiModelMetadata) -> None:
    # stories260K has no general.description key
    assert stories260k_metadata.description is None


def test_gguf_integration_hyperparameters(
    stories260k_metadata: AiModelMetadata,
) -> None:
    hp = stories260k_metadata.hyperparameters
    assert hp["llama.context_length"] == 2048
    assert hp["llama.embedding_length"] == 64
    assert hp["llama.block_count"] == 5
    assert hp["llama.attention.head_count"] == 8
    assert hp["llama.attention.head_count_kv"] == 4
    assert hp["llama.feed_forward_length"] == 172
    assert hp["llama.rope.dimension_count"] == 8


def test_gguf_integration_properties(stories260k_metadata: AiModelMetadata) -> None:
    props = stories260k_metadata.properties
    # GGUF format metadata keys
    assert props.get("GGUF.version") == "3"
    assert props.get("GGUF.tensor_count") == "48"
    # Architecture string stored as a property too
    assert props.get("general.architecture") == "llama"


def test_gguf_integration_provenance(stories260k_metadata: AiModelMetadata) -> None:
    assert "hyperparameters" in stories260k_metadata.provenance
    assert "properties" in stories260k_metadata.provenance
