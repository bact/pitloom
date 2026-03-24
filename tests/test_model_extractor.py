# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for AI model metadata extraction."""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=too-many-lines
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from loom.extractors.model import (
    ModelFormat,
    ModelMetadata,
    detect_model_format,
    extract_metadata_from_gguf,
    extract_metadata_from_model,
    extract_metadata_from_onnx,
    extract_metadata_from_safetensors,
)

# ---------------------------------------------------------------------------
# detect_model_format
# ---------------------------------------------------------------------------


def test_detect_format_onnx() -> None:
    assert detect_model_format(Path("model.onnx")) == ModelFormat.ONNX


def test_detect_format_safetensors() -> None:
    assert detect_model_format(Path("weights.safetensors")) == ModelFormat.SAFETENSORS


def test_detect_format_gguf() -> None:
    assert detect_model_format(Path("llama.gguf")) == ModelFormat.GGUF


def test_detect_format_unknown() -> None:
    assert detect_model_format(Path("model.pt")) == ModelFormat.UNKNOWN


def test_detect_format_case_insensitive() -> None:
    assert detect_model_format(Path("MODEL.ONNX")) == ModelFormat.ONNX


# ---------------------------------------------------------------------------
# extract_metadata_from_model — dispatch
# ---------------------------------------------------------------------------


def test_extract_metadata_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        extract_metadata_from_model(Path("/nonexistent/model.onnx"))


def test_extract_metadata_unsupported_format(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt"
    model_file.write_bytes(b"fake pytorch")
    with pytest.raises(ValueError, match="Unsupported model format"):
        extract_metadata_from_model(model_file)


# ---------------------------------------------------------------------------
# ONNX extractor (mocked)
# ---------------------------------------------------------------------------


def _make_onnx_mock(
    graph_name: str = "TestGraph",
    doc_string: str = "A test model",
    model_version: int = 1,
    domain: str = "ai.onnx",
    metadata_props: dict[str, str] | None = None,
    opset_versions: dict[str, int] | None = None,
    inputs: list[MagicMock] | None = None,
    outputs: list[MagicMock] | None = None,
) -> MagicMock:
    """Build a minimal mock of an onnx.ModelProto."""
    model = MagicMock()
    model.graph.name = graph_name
    model.doc_string = doc_string
    model.model_version = model_version
    model.domain = domain

    # metadata_props
    props = []
    for k, v in (metadata_props or {}).items():
        p = MagicMock()
        p.key = k
        p.value = v
        props.append(p)
    model.metadata_props = props

    # opset_import
    opsets = []
    for dom, ver in (opset_versions or {"": 17}).items():
        o = MagicMock()
        o.domain = dom
        o.version = ver
        opsets.append(o)
    model.opset_import = opsets

    # graph inputs / outputs
    def _make_vi(
        name: str, dtype: int = 1, shape: list[int | str] | None = None
    ) -> MagicMock:
        vi = MagicMock()
        vi.name = name
        vi.type.tensor_type.elem_type = dtype
        vi.type.tensor_type.HasField.return_value = True
        dims = []
        for d in shape or []:
            dim = MagicMock()
            if isinstance(d, int):
                dim.HasField.side_effect = lambda f: f == "dim_value"
                dim.dim_value = d
                dim.dim_param = ""
            else:
                dim.HasField.side_effect = lambda f: f == "dim_param"
                dim.dim_value = 0
                dim.dim_param = d
            dims.append(dim)
        vi.type.tensor_type.shape.dim = dims
        return vi

    model.graph.input = [_make_vi("input", shape=["batch", 3, 224, 224])]
    model.graph.output = [_make_vi("output", shape=["batch", 1000])]

    if inputs is not None:
        model.graph.input = inputs
    if outputs is not None:
        model.graph.output = outputs

    return model


def test_onnx_missing_library(tmp_path: Path) -> None:
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"fake onnx")
    with patch.dict("sys.modules", {"onnx": None}):
        with pytest.raises(ImportError, match="onnx"):
            extract_metadata_from_onnx(model_file)


def test_onnx_basic_extraction(tmp_path: Path) -> None:
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"fake")

    mock_model = _make_onnx_mock(
        graph_name="ResNet50",
        doc_string="Image classification model",
        model_version=2,
        domain="ai.onnx",
        metadata_props={"author": "test", "task": "classification"},
        opset_versions={"": 17, "com.microsoft": 1},
    )

    mock_onnx = MagicMock()
    mock_onnx.load.return_value = mock_model

    with patch.dict("sys.modules", {"onnx": mock_onnx}):
        meta = extract_metadata_from_onnx(model_file)

    assert meta.format == ModelFormat.ONNX
    assert meta.name == "ResNet50"
    assert meta.description == "Image classification model"
    assert meta.version == "2"
    assert meta.type_of_model == "ai.onnx"
    assert meta.properties["author"] == "test"
    assert meta.properties["task"] == "classification"
    assert meta.properties["domain"] == "ai.onnx"
    assert "opset.ai.onnx" in meta.properties
    assert meta.properties["opset.ai.onnx"] == "17"
    assert len(meta.inputs) == 1
    assert meta.inputs[0]["name"] == "input"
    assert meta.inputs[0]["shape"] == ["batch", 3, 224, 224]
    assert len(meta.outputs) == 1
    assert meta.outputs[0]["name"] == "output"
    assert "name" in meta.provenance
    assert "description" in meta.provenance
    assert "version" in meta.provenance


def test_onnx_no_graph_name_falls_back(tmp_path: Path) -> None:
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"fake")

    mock_model = _make_onnx_mock(
        graph_name="", doc_string="", model_version=0, domain=""
    )
    mock_model.metadata_props = []
    mock_model.opset_import = []
    mock_model.graph.input = []
    mock_model.graph.output = []

    mock_onnx = MagicMock()
    mock_onnx.load.return_value = mock_model

    with patch.dict("sys.modules", {"onnx": mock_onnx}):
        meta = extract_metadata_from_onnx(model_file)

    assert meta.name is None
    assert meta.description is None
    assert meta.version is None
    assert meta.format == ModelFormat.ONNX


def test_onnx_load_failure(tmp_path: Path) -> None:
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"corrupt")

    mock_onnx = MagicMock()
    mock_onnx.load.side_effect = RuntimeError("bad protobuf")

    with patch.dict("sys.modules", {"onnx": mock_onnx}):
        with pytest.raises(ValueError, match="Failed to load ONNX model"):
            extract_metadata_from_onnx(model_file)


# ---------------------------------------------------------------------------
# Safetensors extractor (mocked)
# ---------------------------------------------------------------------------


def test_safetensors_missing_library(tmp_path: Path) -> None:
    model_file = tmp_path / "weights.safetensors"
    model_file.write_bytes(b"fake")
    with patch.dict("sys.modules", {"safetensors": None}):
        with pytest.raises(ImportError, match="safetensors"):
            extract_metadata_from_safetensors(model_file)


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
        meta = extract_metadata_from_safetensors(model_file)

    assert meta.format == ModelFormat.SAFETENSORS
    assert meta.name == "My Diffusion Model"
    assert meta.description == "A latent diffusion model"
    assert meta.version == "1.0"
    assert meta.type_of_model == "stable-diffusion-xl-v1"
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
        meta = extract_metadata_from_safetensors(model_file)

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
        meta = extract_metadata_from_safetensors(model_file)

    assert meta.name == "Fallback Name"
    assert meta.description == "Fallback description"
    assert meta.version == "0.1"
    assert meta.type_of_model == "llama"


def test_safetensors_read_failure(tmp_path: Path) -> None:
    model_file = tmp_path / "model.safetensors"
    model_file.write_bytes(b"corrupt")

    mock_safetensors = MagicMock()
    mock_safetensors.safe_open.side_effect = OSError("bad file")

    with patch.dict("sys.modules", {"safetensors": mock_safetensors}):
        with pytest.raises(ValueError, match="Failed to read Safetensors"):
            extract_metadata_from_safetensors(model_file)


# ---------------------------------------------------------------------------
# GGUF extractor (mocked)
# ---------------------------------------------------------------------------


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
            extract_metadata_from_gguf(model_file)


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
        meta = extract_metadata_from_gguf(model_file)

    assert meta.format == ModelFormat.GGUF
    assert meta.name == "LLaMA-3-8B"
    assert meta.description == "Meta LLaMA 3 8B"
    assert meta.version == "3.0"
    assert meta.type_of_model == "llama"
    assert meta.hyperparameters["llama.context_length"] == 8192
    assert meta.hyperparameters["llama.embedding_length"] == 4096
    assert meta.hyperparameters["llama.attention.head_count"] == 32
    assert meta.hyperparameters["llama.block_count"] == 32
    # Non-hyperparam key goes to properties
    assert "tokenizer.ggml.model" in meta.properties
    assert "hyperparameters" in meta.provenance
    assert "type_of_model" in meta.provenance


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
        meta = extract_metadata_from_gguf(model_file)

    assert meta.type_of_model == "mistral"
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
            extract_metadata_from_gguf(model_file)


# ---------------------------------------------------------------------------
# ModelMetadata dataclass
# ---------------------------------------------------------------------------


def test_model_metadata_defaults() -> None:
    meta = ModelMetadata()
    assert meta.format == ModelFormat.UNKNOWN
    assert meta.name is None
    assert meta.hyperparameters == {}
    assert meta.properties == {}
    assert meta.inputs == []
    assert meta.outputs == []
    assert meta.provenance == {}


def test_model_metadata_construction() -> None:
    meta = ModelMetadata(
        format=ModelFormat.ONNX,
        name="MyModel",
        version="1.0",
        type_of_model="transformer",
        hyperparameters={"num_heads": 12},
        provenance={"name": "Source: model.onnx | Field: graph.name"},
    )
    assert meta.format == ModelFormat.ONNX
    assert meta.name == "MyModel"
    assert meta.hyperparameters["num_heads"] == 12
    assert "name" in meta.provenance


# ---------------------------------------------------------------------------
# Integration tests — real ONNX file (squeezenet1.1-7.onnx)
# Require: onnx installed AND tests/fixtures/squeezenet1.1-7.onnx present
# ---------------------------------------------------------------------------

# ONNX elem_type 1 = FLOAT  (TensorProto.FLOAT)
_ONNX_FLOAT = 1

SQUEEZENET_FIXTURE = Path(__file__).parent / "fixtures" / "squeezenet1.1-7.onnx"


@pytest.fixture(scope="module")
def squeezenet_metadata() -> ModelMetadata:
    """Extract metadata from the squeezenet1.1-7.onnx fixture once per session."""
    pytest.importorskip("onnx")
    if not SQUEEZENET_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {SQUEEZENET_FIXTURE}")
    return extract_metadata_from_onnx(SQUEEZENET_FIXTURE)


def test_onnx_integration_format(squeezenet_metadata: ModelMetadata) -> None:
    assert squeezenet_metadata.format == ModelFormat.ONNX


def test_onnx_integration_name(squeezenet_metadata: ModelMetadata) -> None:
    # squeezenet1.1-7.onnx graph name is 'main'
    assert squeezenet_metadata.name == "main"
    assert "name" in squeezenet_metadata.provenance
    assert "graph.name" in squeezenet_metadata.provenance["name"]


def test_onnx_integration_no_description(squeezenet_metadata: ModelMetadata) -> None:
    # The model has an empty doc_string
    assert squeezenet_metadata.description is None


def test_onnx_integration_no_version(squeezenet_metadata: ModelMetadata) -> None:
    # model_version is 0 (not set)
    assert squeezenet_metadata.version is None


def test_onnx_integration_type_of_model(squeezenet_metadata: ModelMetadata) -> None:
    # Empty domain falls back to "neural network"
    assert squeezenet_metadata.type_of_model == "neural network"


def test_onnx_integration_opset(squeezenet_metadata: ModelMetadata) -> None:
    # Opset domain '' is normalised to 'ai.onnx'; version 7
    assert squeezenet_metadata.properties.get("opset.ai.onnx") == "7"


def test_onnx_integration_no_domain_property(
    squeezenet_metadata: ModelMetadata,
) -> None:
    # Empty domain string is not stored as a property
    assert "domain" not in squeezenet_metadata.properties


def test_onnx_integration_inputs(squeezenet_metadata: ModelMetadata) -> None:
    # First input is the image tensor 'data' with shape [1, 3, 224, 224]
    inputs = squeezenet_metadata.inputs
    assert len(inputs) > 0
    data_input = inputs[0]
    assert data_input["name"] == "data"
    assert data_input["dtype"] == _ONNX_FLOAT
    assert data_input["shape"] == [1, 3, 224, 224]


def test_onnx_integration_outputs(squeezenet_metadata: ModelMetadata) -> None:
    # Single output with shape [1, 1000] (1000 ImageNet classes)
    outputs = squeezenet_metadata.outputs
    assert len(outputs) == 1
    assert outputs[0]["name"] == "squeezenet0_flatten0_reshape0"
    assert outputs[0]["dtype"] == _ONNX_FLOAT
    assert outputs[0]["shape"] == [1, 1000]


def test_onnx_integration_provenance_fields(squeezenet_metadata: ModelMetadata) -> None:
    assert "inputs" in squeezenet_metadata.provenance
    assert "outputs" in squeezenet_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real GGUF file (stories260K.gguf)
# Source: ggml-org/models tinyllamas/stories260K.gguf (~1.1 MB)
# A 260K-parameter LLaMA model trained on TinyStories (Karpathy / llama2.c)
# Require: gguf installed AND tests/fixtures/stories260K.gguf present
# ---------------------------------------------------------------------------

STORIES260K_FIXTURE = Path(__file__).parent / "fixtures" / "stories260K.gguf"


@pytest.fixture(scope="module")
def stories260k_metadata() -> ModelMetadata:
    """Extract metadata from the stories260K.gguf fixture once per session."""
    pytest.importorskip("gguf")
    if not STORIES260K_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {STORIES260K_FIXTURE}")
    return extract_metadata_from_gguf(STORIES260K_FIXTURE)


def test_gguf_integration_format(stories260k_metadata: ModelMetadata) -> None:
    assert stories260k_metadata.format == ModelFormat.GGUF


def test_gguf_integration_architecture(stories260k_metadata: ModelMetadata) -> None:
    # general.architecture = 'llama'
    assert stories260k_metadata.type_of_model == "llama"
    assert "type_of_model" in stories260k_metadata.provenance
    assert "general.architecture" in stories260k_metadata.provenance["type_of_model"]


def test_gguf_integration_name(stories260k_metadata: ModelMetadata) -> None:
    # general.name = 'llama' (same as architecture in this tiny model)
    assert stories260k_metadata.name == "llama"
    assert "name" in stories260k_metadata.provenance


def test_gguf_integration_no_description(stories260k_metadata: ModelMetadata) -> None:
    # stories260K has no general.description key
    assert stories260k_metadata.description is None


def test_gguf_integration_hyperparameters(stories260k_metadata: ModelMetadata) -> None:
    hp = stories260k_metadata.hyperparameters
    assert hp["llama.context_length"] == 2048
    assert hp["llama.embedding_length"] == 64
    assert hp["llama.block_count"] == 5
    assert hp["llama.attention.head_count"] == 8
    assert hp["llama.attention.head_count_kv"] == 4
    assert hp["llama.feed_forward_length"] == 172
    assert hp["llama.rope.dimension_count"] == 8


def test_gguf_integration_properties(stories260k_metadata: ModelMetadata) -> None:
    props = stories260k_metadata.properties
    # GGUF format metadata keys
    assert props.get("GGUF.version") == "3"
    assert props.get("GGUF.tensor_count") == "48"
    # Architecture string stored as a property too
    assert props.get("general.architecture") == "llama"


def test_gguf_integration_provenance(stories260k_metadata: ModelMetadata) -> None:
    assert "hyperparameters" in stories260k_metadata.provenance
    assert "properties" in stories260k_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real ONNX file (encoder_model_q4f16.onnx)
# Source: onnx-community/whisper-tiny-ONNX (~6.3 MB)
# Whisper tiny speech encoder, quantised Q4F16, two opset domains
# Require: onnx installed AND tests/fixtures/encoder_model_q4f16.onnx present
# ---------------------------------------------------------------------------

WHISPER_ENCODER_FIXTURE = (
    Path(__file__).parent / "fixtures" / "encoder_model_q4f16.onnx"
)


@pytest.fixture(scope="module")
def whisper_encoder_metadata() -> ModelMetadata:
    """Extract metadata from the encoder_model_q4f16.onnx fixture once per session."""
    pytest.importorskip("onnx")
    if not WHISPER_ENCODER_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {WHISPER_ENCODER_FIXTURE}")
    return extract_metadata_from_onnx(WHISPER_ENCODER_FIXTURE)


def test_whisper_encoder_format(whisper_encoder_metadata: ModelMetadata) -> None:
    assert whisper_encoder_metadata.format == ModelFormat.ONNX


def test_whisper_encoder_name(whisper_encoder_metadata: ModelMetadata) -> None:
    assert whisper_encoder_metadata.name == "main_graph"
    assert "graph.name" in whisper_encoder_metadata.provenance["name"]


def test_whisper_encoder_opsets(whisper_encoder_metadata: ModelMetadata) -> None:
    # Uses both the standard ai.onnx opset and com.microsoft extensions
    props = whisper_encoder_metadata.properties
    assert props.get("opset.ai.onnx") == "14"
    assert props.get("opset.com.microsoft") == "1"


def test_whisper_encoder_input(whisper_encoder_metadata: ModelMetadata) -> None:
    inputs = whisper_encoder_metadata.inputs
    assert len(inputs) > 0
    inp = inputs[0]
    assert inp["name"] == "input_features"
    assert inp["dtype"] == _ONNX_FLOAT
    # Shape: [batch_size, 80, 3000]  (batch is dynamic)
    assert inp["shape"][1] == 80
    assert inp["shape"][2] == 3000


def test_whisper_encoder_output(whisper_encoder_metadata: ModelMetadata) -> None:
    outputs = whisper_encoder_metadata.outputs
    assert len(outputs) > 0
    out = outputs[0]
    assert out["name"] == "last_hidden_state"
    assert out["dtype"] == _ONNX_FLOAT
    # Shape: [batch_size, 1500, 384]
    assert out["shape"][1] == 1500
    assert out["shape"][2] == 384


def test_whisper_encoder_provenance(whisper_encoder_metadata: ModelMetadata) -> None:
    assert "inputs" in whisper_encoder_metadata.provenance
    assert "outputs" in whisper_encoder_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real GGUF file (mmproj-tinygemma3.gguf)
# Source: ggml-org/tinygemma3-GGUF (~1.0 MB)
# CLIP vision multimodal projector for tinygemma3; architecture = "clip"
# Require: gguf installed AND tests/fixtures/mmproj-tinygemma3.gguf present
# ---------------------------------------------------------------------------

MMPROJ_FIXTURE = Path(__file__).parent / "fixtures" / "mmproj-tinygemma3.gguf"


@pytest.fixture(scope="module")
def mmproj_metadata() -> ModelMetadata:
    """Extract metadata from the mmproj-tinygemma3.gguf fixture once per session."""
    pytest.importorskip("gguf")
    if not MMPROJ_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {MMPROJ_FIXTURE}")
    return extract_metadata_from_gguf(MMPROJ_FIXTURE)


def test_mmproj_format(mmproj_metadata: ModelMetadata) -> None:
    assert mmproj_metadata.format == ModelFormat.GGUF


def test_mmproj_architecture(mmproj_metadata: ModelMetadata) -> None:
    # Multimodal projector uses the "clip" architecture
    assert mmproj_metadata.type_of_model == "clip"
    assert "general.architecture" in mmproj_metadata.provenance["type_of_model"]


def test_mmproj_no_name(mmproj_metadata: ModelMetadata) -> None:
    # mmproj files don't carry a general.name
    assert mmproj_metadata.name is None
    assert mmproj_metadata.description is None
    assert mmproj_metadata.version is None


def test_mmproj_hyperparameters(mmproj_metadata: ModelMetadata) -> None:
    hp = mmproj_metadata.hyperparameters
    assert hp["clip.vision.embedding_length"] == 128
    assert hp["clip.vision.feed_forward_length"] == 512
    assert hp["clip.vision.block_count"] == 4
    assert hp["clip.vision.attention.head_count"] == 4


def test_mmproj_properties(mmproj_metadata: ModelMetadata) -> None:
    props = mmproj_metadata.properties
    assert props.get("GGUF.version") == "3"
    assert props.get("GGUF.tensor_count") == "71"
    assert props.get("general.architecture") == "clip"
    assert props.get("general.type") == "clip-vision"
    assert props.get("clip.vision.image_size") == "32"
    assert props.get("clip.vision.patch_size") == "2"
    assert props.get("clip.projector_type") == "gemma3"


def test_mmproj_provenance(mmproj_metadata: ModelMetadata) -> None:
    assert "hyperparameters" in mmproj_metadata.provenance
    assert "properties" in mmproj_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real GGUF file (ggml-vocab-bert-bge.gguf)
# Source: ggerganov/llama.cpp GitHub (models/ggml-vocab-bert-bge.gguf)
# Vocabulary-only GGUF for the BGE BERT tokenizer; zero model tensors
# Require: gguf installed AND tests/fixtures/ggml-vocab-bert-bge.gguf present
# ---------------------------------------------------------------------------

VOCAB_BERT_BGE_FIXTURE = Path(__file__).parent / "fixtures" / "ggml-vocab-bert-bge.gguf"


@pytest.fixture(scope="module")
def vocab_bert_bge_metadata() -> ModelMetadata:
    """Extract metadata from the ggml-vocab-bert-bge.gguf fixture once per session."""
    pytest.importorskip("gguf")
    if not VOCAB_BERT_BGE_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {VOCAB_BERT_BGE_FIXTURE}")
    return extract_metadata_from_gguf(VOCAB_BERT_BGE_FIXTURE)


def test_vocab_bert_bge_format(vocab_bert_bge_metadata: ModelMetadata) -> None:
    assert vocab_bert_bge_metadata.format == ModelFormat.GGUF


def test_vocab_bert_bge_name(vocab_bert_bge_metadata: ModelMetadata) -> None:
    assert vocab_bert_bge_metadata.name == "bert-bge"
    assert "general.name" in vocab_bert_bge_metadata.provenance["name"]


def test_vocab_bert_bge_architecture(vocab_bert_bge_metadata: ModelMetadata) -> None:
    assert vocab_bert_bge_metadata.type_of_model == "bert"
    assert "general.architecture" in vocab_bert_bge_metadata.provenance["type_of_model"]


def test_vocab_bert_bge_hyperparameters(vocab_bert_bge_metadata: ModelMetadata) -> None:
    hp = vocab_bert_bge_metadata.hyperparameters
    assert hp["bert.block_count"] == 12
    assert hp["bert.context_length"] == 512
    assert hp["bert.embedding_length"] == 384
    assert hp["bert.feed_forward_length"] == 1536
    assert hp["bert.attention.head_count"] == 12


def test_vocab_bert_bge_zero_tensors(vocab_bert_bge_metadata: ModelMetadata) -> None:
    # Vocabulary-only GGUF — no model weight tensors
    assert vocab_bert_bge_metadata.properties.get("GGUF.tensor_count") == "0"


def test_vocab_bert_bge_properties(vocab_bert_bge_metadata: ModelMetadata) -> None:
    props = vocab_bert_bge_metadata.properties
    assert props.get("GGUF.version") == "3"
    assert props.get("general.architecture") == "bert"
    assert props.get("tokenizer.ggml.model") == "bert"
    assert props.get("tokenizer.ggml.pre") == "bert-bge"


def test_vocab_bert_bge_provenance(vocab_bert_bge_metadata: ModelMetadata) -> None:
    assert "hyperparameters" in vocab_bert_bge_metadata.provenance
    assert "properties" in vocab_bert_bge_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real ONNX file (light-inception-v2.onnx)
# Source: onnx/onnx GitHub (onnx/backend/test/data/light/light_inception_v2.onnx)
# Lightweight InceptionV2, opset 9; weight initializers listed as graph inputs
# Require: onnx installed AND tests/fixtures/light-inception-v2.onnx present
# ---------------------------------------------------------------------------

INCEPTION_V2_FIXTURE = Path(__file__).parent / "fixtures" / "light-inception-v2.onnx"


@pytest.fixture(scope="module")
def inception_v2_metadata() -> ModelMetadata:
    """Extract metadata from the light-inception-v2.onnx fixture once per session."""
    pytest.importorskip("onnx")
    if not INCEPTION_V2_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {INCEPTION_V2_FIXTURE}")
    return extract_metadata_from_onnx(INCEPTION_V2_FIXTURE)


def test_inception_v2_format(inception_v2_metadata: ModelMetadata) -> None:
    assert inception_v2_metadata.format == ModelFormat.ONNX


def test_inception_v2_name(inception_v2_metadata: ModelMetadata) -> None:
    assert inception_v2_metadata.name == "inception_v2"
    assert "graph.name" in inception_v2_metadata.provenance["name"]


def test_inception_v2_type_of_model(inception_v2_metadata: ModelMetadata) -> None:
    # Empty domain falls back to "neural network"
    assert inception_v2_metadata.type_of_model == "neural network"


def test_inception_v2_opset(inception_v2_metadata: ModelMetadata) -> None:
    # Opset 9 — oldest opset in the test fixtures
    assert inception_v2_metadata.properties.get("opset.ai.onnx") == "9"


def test_inception_v2_data_input(inception_v2_metadata: ModelMetadata) -> None:
    # First input is the image tensor; remaining inputs are weight initializers
    # (older ONNX format included initializers in graph.input)
    inputs = inception_v2_metadata.inputs
    assert len(inputs) > 1  # data + weight initializers
    data_in = inputs[0]
    assert data_in["name"] == "data_0"
    assert data_in["dtype"] == _ONNX_FLOAT
    assert data_in["shape"] == [1, 3, 224, 224]


def test_inception_v2_output(inception_v2_metadata: ModelMetadata) -> None:
    outputs = inception_v2_metadata.outputs
    assert len(outputs) == 1
    out = outputs[0]
    assert out["name"] == "prob_1"
    assert out["dtype"] == _ONNX_FLOAT
    assert out["shape"] == [1, 1000]


def test_inception_v2_provenance(inception_v2_metadata: ModelMetadata) -> None:
    assert "inputs" in inception_v2_metadata.provenance
    assert "outputs" in inception_v2_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real ONNX file (resnet-tiny-beans.onnx)
# Source: fxmarty/resnet-tiny-beans (~761 KB)
# ResNet fine-tuned for 3-class bean disease classification; opset 11
# Require: onnx installed AND tests/fixtures/resnet-tiny-beans.onnx present
# ---------------------------------------------------------------------------

RESNET_BEANS_FIXTURE = Path(__file__).parent / "fixtures" / "resnet-tiny-beans.onnx"


@pytest.fixture(scope="module")
def resnet_beans_metadata() -> ModelMetadata:
    """Extract metadata from the resnet-tiny-beans.onnx fixture once per session."""
    pytest.importorskip("onnx")
    if not RESNET_BEANS_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {RESNET_BEANS_FIXTURE}")
    return extract_metadata_from_onnx(RESNET_BEANS_FIXTURE)


def test_resnet_beans_format(resnet_beans_metadata: ModelMetadata) -> None:
    assert resnet_beans_metadata.format == ModelFormat.ONNX


def test_resnet_beans_name(resnet_beans_metadata: ModelMetadata) -> None:
    # PyTorch JIT ONNX exports use "torch_jit" as the graph name
    assert resnet_beans_metadata.name == "torch_jit"


def test_resnet_beans_opset(resnet_beans_metadata: ModelMetadata) -> None:
    assert resnet_beans_metadata.properties.get("opset.ai.onnx") == "11"


def test_resnet_beans_input(resnet_beans_metadata: ModelMetadata) -> None:
    inputs = resnet_beans_metadata.inputs
    assert len(inputs) > 0
    inp = inputs[0]
    assert inp["name"] == "pixel_values"
    assert inp["dtype"] == _ONNX_FLOAT
    # Spatial dimensions 224×224 are fixed; batch and channels are dynamic
    assert inp["shape"][2] == 224
    assert inp["shape"][3] == 224


def test_resnet_beans_output(resnet_beans_metadata: ModelMetadata) -> None:
    outputs = resnet_beans_metadata.outputs
    assert len(outputs) == 1
    assert outputs[0]["name"] == "logits"
    assert outputs[0]["dtype"] == _ONNX_FLOAT


def test_resnet_beans_provenance(resnet_beans_metadata: ModelMetadata) -> None:
    assert "inputs" in resnet_beans_metadata.provenance
    assert "outputs" in resnet_beans_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real ONNX file (gpt2-tiny-decoder.onnx)
# Source: fxmarty/gpt2-tiny-onnx (~1.0 MB)
# GPT-2 causal LM decoder with KV-cache outputs; opset 13
# Require: onnx installed AND tests/fixtures/gpt2-tiny-decoder.onnx present
# ---------------------------------------------------------------------------

GPT2_DECODER_FIXTURE = Path(__file__).parent / "fixtures" / "gpt2-tiny-decoder.onnx"


@pytest.fixture(scope="module")
def gpt2_decoder_metadata() -> ModelMetadata:
    """Extract metadata from the gpt2-tiny-decoder.onnx fixture once per session."""
    pytest.importorskip("onnx")
    if not GPT2_DECODER_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {GPT2_DECODER_FIXTURE}")
    return extract_metadata_from_onnx(GPT2_DECODER_FIXTURE)


def test_gpt2_decoder_format(gpt2_decoder_metadata: ModelMetadata) -> None:
    assert gpt2_decoder_metadata.format == ModelFormat.ONNX


def test_gpt2_decoder_name(gpt2_decoder_metadata: ModelMetadata) -> None:
    assert gpt2_decoder_metadata.name == "torch_jit"


def test_gpt2_decoder_opset(gpt2_decoder_metadata: ModelMetadata) -> None:
    assert gpt2_decoder_metadata.properties.get("opset.ai.onnx") == "13"


def test_gpt2_decoder_inputs(gpt2_decoder_metadata: ModelMetadata) -> None:
    input_names = {i["name"] for i in gpt2_decoder_metadata.inputs}
    assert "input_ids" in input_names
    assert "attention_mask" in input_names


def test_gpt2_decoder_logits_output(gpt2_decoder_metadata: ModelMetadata) -> None:
    output_names = {o["name"] for o in gpt2_decoder_metadata.outputs}
    assert "logits" in output_names


def test_gpt2_decoder_kv_cache_outputs(gpt2_decoder_metadata: ModelMetadata) -> None:
    # Decoder produces past key/value tensors for each transformer layer
    output_names = {o["name"] for o in gpt2_decoder_metadata.outputs}
    assert "present.0.key" in output_names
    assert "present.0.value" in output_names


def test_gpt2_decoder_provenance(gpt2_decoder_metadata: ModelMetadata) -> None:
    assert "inputs" in gpt2_decoder_metadata.provenance
    assert "outputs" in gpt2_decoder_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real Safetensors file (vits-tiny-random.safetensors)
# Source: echarlaix/tiny-random-vits (~344 KB)
# Randomly initialised VITS text-to-speech model; 438 tensors
# Require: safetensors installed AND tests/fixtures/vits-tiny-random.safetensors present
# ---------------------------------------------------------------------------

VITS_FIXTURE = Path(__file__).parent / "fixtures" / "vits-tiny-random.safetensors"


@pytest.fixture(scope="module")
def vits_metadata() -> ModelMetadata:
    """Extract metadata from the vits-tiny-random fixture once per session."""
    pytest.importorskip("safetensors")
    if not VITS_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {VITS_FIXTURE}")
    return extract_metadata_from_safetensors(VITS_FIXTURE)


def test_vits_format(vits_metadata: ModelMetadata) -> None:
    assert vits_metadata.format == ModelFormat.SAFETENSORS


def test_vits_no_model_metadata(vits_metadata: ModelMetadata) -> None:
    assert vits_metadata.name is None
    assert vits_metadata.description is None
    assert vits_metadata.version is None
    assert vits_metadata.type_of_model is None


def test_vits_format_property(vits_metadata: ModelMetadata) -> None:
    assert vits_metadata.properties.get("format") == "pt"


def test_vits_tensor_count(vits_metadata: ModelMetadata) -> None:
    # VITS has many sub-networks (text encoder, decoder, flow, posterior encoder)
    assert len(vits_metadata.inputs) == 438


def test_vits_tensor_names(vits_metadata: ModelMetadata) -> None:
    names = {t["name"] for t in vits_metadata.inputs}
    # Key sub-modules of a VITS TTS model
    assert any(n.startswith("decoder.") for n in names)
    assert any(n.startswith("text_encoder.") for n in names)
    assert "text_encoder.project.weight" in names


def test_vits_provenance(vits_metadata: ModelMetadata) -> None:
    assert "inputs" in vits_metadata.provenance
    assert "properties" in vits_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real Safetensors file (whisper-tiny-random.safetensors)
# Source: optimum-internal-testing/tiny-random-whisper (~872 KB)
# Randomly initialised Whisper ASR encoder-decoder; 50 tensors
# Require: safetensors installed AND
#          tests/fixtures/whisper-tiny-random.safetensors present
# ---------------------------------------------------------------------------

WHISPER_ST_FIXTURE = (
    Path(__file__).parent / "fixtures" / "whisper-tiny-random.safetensors"
)


@pytest.fixture(scope="module")
def whisper_st_metadata() -> ModelMetadata:
    """Extract metadata from the whisper-tiny-random safetensors fixture."""
    pytest.importorskip("safetensors")
    if not WHISPER_ST_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {WHISPER_ST_FIXTURE}")
    return extract_metadata_from_safetensors(WHISPER_ST_FIXTURE)


def test_whisper_st_format(whisper_st_metadata: ModelMetadata) -> None:
    assert whisper_st_metadata.format == ModelFormat.SAFETENSORS


def test_whisper_st_no_model_metadata(whisper_st_metadata: ModelMetadata) -> None:
    assert whisper_st_metadata.name is None
    assert whisper_st_metadata.type_of_model is None


def test_whisper_st_format_property(whisper_st_metadata: ModelMetadata) -> None:
    assert whisper_st_metadata.properties.get("format") == "pt"


def test_whisper_st_tensor_count(whisper_st_metadata: ModelMetadata) -> None:
    assert len(whisper_st_metadata.inputs) == 50


def test_whisper_st_tensor_names(whisper_st_metadata: ModelMetadata) -> None:
    names = {t["name"] for t in whisper_st_metadata.inputs}
    # Whisper has both encoder and decoder sub-modules
    assert any(n.startswith("model.encoder.") for n in names)
    assert any(n.startswith("model.decoder.") for n in names)


def test_whisper_st_provenance(whisper_st_metadata: ModelMetadata) -> None:
    assert "inputs" in whisper_st_metadata.provenance
    assert "properties" in whisper_st_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real GGUF file (ggml-vocab-phi-3.gguf)
# Source: ggerganov/llama.cpp GitHub (models/ggml-vocab-phi-3.gguf)
# Vocabulary-only GGUF for the Phi-3 tokenizer (LLaMA BPE, RoPE architecture)
# Require: gguf installed AND tests/fixtures/ggml-vocab-phi-3.gguf present
# ---------------------------------------------------------------------------

VOCAB_PHI3_FIXTURE = Path(__file__).parent / "fixtures" / "ggml-vocab-phi-3.gguf"


@pytest.fixture(scope="module")
def vocab_phi3_metadata() -> ModelMetadata:
    """Extract metadata from the ggml-vocab-phi-3.gguf fixture once per session."""
    pytest.importorskip("gguf")
    if not VOCAB_PHI3_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {VOCAB_PHI3_FIXTURE}")
    return extract_metadata_from_gguf(VOCAB_PHI3_FIXTURE)


def test_vocab_phi3_format(vocab_phi3_metadata: ModelMetadata) -> None:
    assert vocab_phi3_metadata.format == ModelFormat.GGUF


def test_vocab_phi3_name(vocab_phi3_metadata: ModelMetadata) -> None:
    assert vocab_phi3_metadata.name == "Phi3"
    assert "general.name" in vocab_phi3_metadata.provenance["name"]


def test_vocab_phi3_architecture(vocab_phi3_metadata: ModelMetadata) -> None:
    assert vocab_phi3_metadata.type_of_model == "phi3"


def test_vocab_phi3_hyperparameters(vocab_phi3_metadata: ModelMetadata) -> None:
    hp = vocab_phi3_metadata.hyperparameters
    assert hp["phi3.context_length"] == 4096
    assert hp["phi3.embedding_length"] == 3072
    assert hp["phi3.block_count"] == 32
    assert hp["phi3.attention.head_count"] == 32
    assert hp["phi3.rope.dimension_count"] == 96


def test_vocab_phi3_zero_tensors(vocab_phi3_metadata: ModelMetadata) -> None:
    assert vocab_phi3_metadata.properties.get("GGUF.tensor_count") == "0"


def test_vocab_phi3_tokenizer(vocab_phi3_metadata: ModelMetadata) -> None:
    props = vocab_phi3_metadata.properties
    # Phi-3 uses a LLaMA-family BPE tokenizer (not BERT WordPiece)
    assert props.get("tokenizer.ggml.model") == "llama"
    assert props.get("general.architecture") == "phi3"


def test_vocab_phi3_provenance(vocab_phi3_metadata: ModelMetadata) -> None:
    assert "hyperparameters" in vocab_phi3_metadata.provenance
    assert "properties" in vocab_phi3_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real Safetensors file (phi-tiny-random.safetensors)
# Source: echarlaix/tiny-random-PhiForCausalLM (~316 KB)
# Tiny randomly-initialised Phi causal language model; 33 tensors, Apache-2.0
# Require: safetensors installed AND
#          tests/fixtures/phi-tiny-random.safetensors present
# ---------------------------------------------------------------------------

PHI_FIXTURE = Path(__file__).parent / "fixtures" / "phi-tiny-random.safetensors"


@pytest.fixture(scope="module")
def phi_metadata() -> ModelMetadata:
    """Extract metadata from the phi-tiny-random fixture once per session."""
    pytest.importorskip("safetensors")
    if not PHI_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {PHI_FIXTURE}")
    return extract_metadata_from_safetensors(PHI_FIXTURE)


def test_phi_format(phi_metadata: ModelMetadata) -> None:
    assert phi_metadata.format == ModelFormat.SAFETENSORS


def test_phi_no_model_metadata(phi_metadata: ModelMetadata) -> None:
    # Only __metadata__ entry is 'format': 'pt'; no modelspec keys
    assert phi_metadata.name is None
    assert phi_metadata.description is None
    assert phi_metadata.version is None
    assert phi_metadata.type_of_model is None


def test_phi_format_property(phi_metadata: ModelMetadata) -> None:
    assert phi_metadata.properties.get("format") == "pt"


def test_phi_tensor_count(phi_metadata: ModelMetadata) -> None:
    # 2-layer Phi model: embeddings + 2 × attention blocks + head
    assert len(phi_metadata.inputs) == 33


def test_phi_tensor_names(phi_metadata: ModelMetadata) -> None:
    names = {t["name"] for t in phi_metadata.inputs}
    # Phi uses standard transformer naming: embed_tokens, layers, lm_head
    assert "model.embed_tokens.weight" in names
    assert "lm_head.weight" in names
    assert any(n.startswith("model.layers.") for n in names)


def test_phi_provenance(phi_metadata: ModelMetadata) -> None:
    assert "inputs" in phi_metadata.provenance
    assert "properties" in phi_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real Safetensors file (marian-tiny-random.safetensors)
# Source: optimum-internal-testing/tiny-random-marian (~690 KB)
# Tiny randomly-initialised MarianMT translation encoder-decoder; 86 tensors, MIT
# Require: safetensors installed AND
#          tests/fixtures/marian-tiny-random.safetensors present
# ---------------------------------------------------------------------------

MARIAN_FIXTURE = Path(__file__).parent / "fixtures" / "marian-tiny-random.safetensors"


@pytest.fixture(scope="module")
def marian_metadata() -> ModelMetadata:
    """Extract metadata from the marian-tiny-random fixture once per session."""
    pytest.importorskip("safetensors")
    if not MARIAN_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {MARIAN_FIXTURE}")
    return extract_metadata_from_safetensors(MARIAN_FIXTURE)


def test_marian_format(marian_metadata: ModelMetadata) -> None:
    assert marian_metadata.format == ModelFormat.SAFETENSORS


def test_marian_no_model_metadata(marian_metadata: ModelMetadata) -> None:
    # Only __metadata__ entry is 'format': 'pt'; no modelspec keys
    assert marian_metadata.name is None
    assert marian_metadata.description is None
    assert marian_metadata.version is None
    assert marian_metadata.type_of_model is None


def test_marian_format_property(marian_metadata: ModelMetadata) -> None:
    assert marian_metadata.properties.get("format") == "pt"


def test_marian_tensor_count(marian_metadata: ModelMetadata) -> None:
    # MarianMT encoder-decoder: embedding, 2 encoder + 2 decoder layers, bias
    assert len(marian_metadata.inputs) == 86


def test_marian_tensor_names(marian_metadata: ModelMetadata) -> None:
    names = {t["name"] for t in marian_metadata.inputs}
    # MarianMT has both encoder and decoder sub-modules plus shared embedding
    assert any(n.startswith("model.encoder.") for n in names)
    assert any(n.startswith("model.decoder.") for n in names)
    assert "model.shared.weight" in names


def test_marian_provenance(marian_metadata: ModelMetadata) -> None:
    assert "inputs" in marian_metadata.provenance
    assert "properties" in marian_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real Safetensors file (speech2text-tiny-random.safetensors)
# Source: optimum-internal-testing/tiny-random-Speech2TextModel (~689 KB)
# Tiny randomly-initialised Speech2Text ASR encoder-decoder; 93 tensors, Apache-2.0
# Require: safetensors installed AND
#          tests/fixtures/speech2text-tiny-random.safetensors present
# ---------------------------------------------------------------------------

SPEECH2TEXT_FIXTURE = (
    Path(__file__).parent / "fixtures" / "speech2text-tiny-random.safetensors"
)


@pytest.fixture(scope="module")
def speech2text_metadata() -> ModelMetadata:
    """Extract metadata from the speech2text-tiny-random fixture once per session."""
    pytest.importorskip("safetensors")
    if not SPEECH2TEXT_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {SPEECH2TEXT_FIXTURE}")
    return extract_metadata_from_safetensors(SPEECH2TEXT_FIXTURE)


def test_speech2text_format(speech2text_metadata: ModelMetadata) -> None:
    assert speech2text_metadata.format == ModelFormat.SAFETENSORS


def test_speech2text_no_model_metadata(speech2text_metadata: ModelMetadata) -> None:
    # Only __metadata__ entry is 'format': 'pt'; no modelspec keys
    assert speech2text_metadata.name is None
    assert speech2text_metadata.description is None
    assert speech2text_metadata.version is None
    assert speech2text_metadata.type_of_model is None


def test_speech2text_format_property(speech2text_metadata: ModelMetadata) -> None:
    assert speech2text_metadata.properties.get("format") == "pt"


def test_speech2text_tensor_count(speech2text_metadata: ModelMetadata) -> None:
    # Speech2Text encoder-decoder: conv layers + 2 encoder + 2 decoder layers
    assert len(speech2text_metadata.inputs) == 93


def test_speech2text_tensor_names(speech2text_metadata: ModelMetadata) -> None:
    names = {t["name"] for t in speech2text_metadata.inputs}
    # Speech2Text has both encoder (with conv) and decoder sub-modules
    assert any(n.startswith("model.encoder.") for n in names)
    assert any(n.startswith("model.decoder.") for n in names)


def test_speech2text_provenance(speech2text_metadata: ModelMetadata) -> None:
    assert "inputs" in speech2text_metadata.provenance
    assert "properties" in speech2text_metadata.provenance
