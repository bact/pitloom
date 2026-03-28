# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ONNX metadata extractor (mocked and integration)."""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.extract.ai_model import read_onnx

# ---------------------------------------------------------------------------
# ONNX extractor (mocked)
# ---------------------------------------------------------------------------

_ONNX = Path(__file__).parent / "fixtures" / "onnx"

# ONNX elem_type 1 = FLOAT  (TensorProto.FLOAT)
_ONNX_FLOAT = 1


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
            read_onnx(model_file)


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
        meta = read_onnx(model_file)

    assert meta.format == AiModelFormat.ONNX
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
        meta = read_onnx(model_file)

    assert meta.name is None
    assert meta.description is None
    assert meta.version is None
    assert meta.format == AiModelFormat.ONNX


def test_onnx_load_failure(tmp_path: Path) -> None:
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"corrupt")

    mock_onnx = MagicMock()
    mock_onnx.load.side_effect = RuntimeError("bad protobuf")

    with patch.dict("sys.modules", {"onnx": mock_onnx}):
        with pytest.raises(ValueError, match="Failed to load ONNX model"):
            read_onnx(model_file)


# ---------------------------------------------------------------------------
# Integration tests — real ONNX file (encoder_model_q4f16.onnx)
# Source: onnx-community/whisper-tiny-ONNX (~6.3 MB)
# Whisper tiny speech encoder, quantised Q4F16, two opset domains
# Require: onnx installed AND
#          tests/fixtures/onnx/encoder_model_q4f16.onnx present
# ---------------------------------------------------------------------------

WHISPER_ENCODER_FIXTURE = _ONNX / "encoder_model_q4f16.onnx"


@pytest.fixture(scope="module")
def whisper_encoder_metadata() -> AiModelMetadata:
    """Extract metadata from the encoder_model_q4f16.onnx fixture once per session."""
    pytest.importorskip("onnx")
    if not WHISPER_ENCODER_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {WHISPER_ENCODER_FIXTURE}")
    return read_onnx(WHISPER_ENCODER_FIXTURE)


def test_whisper_encoder_format(whisper_encoder_metadata: AiModelMetadata) -> None:
    assert whisper_encoder_metadata.format == AiModelFormat.ONNX


def test_whisper_encoder_name(whisper_encoder_metadata: AiModelMetadata) -> None:
    assert whisper_encoder_metadata.name == "main_graph"
    assert "graph.name" in whisper_encoder_metadata.provenance["name"]


def test_whisper_encoder_opsets(whisper_encoder_metadata: AiModelMetadata) -> None:
    # Uses both the standard ai.onnx opset and com.microsoft extensions
    props = whisper_encoder_metadata.properties
    assert props.get("opset.ai.onnx") == "14"
    assert props.get("opset.com.microsoft") == "1"


def test_whisper_encoder_input(whisper_encoder_metadata: AiModelMetadata) -> None:
    inputs = whisper_encoder_metadata.inputs
    assert len(inputs) > 0
    inp = inputs[0]
    assert inp["name"] == "input_features"
    assert inp["dtype"] == _ONNX_FLOAT
    # Shape: [batch_size, 80, 3000]  (batch is dynamic)
    assert inp["shape"][1] == 80
    assert inp["shape"][2] == 3000


def test_whisper_encoder_output(whisper_encoder_metadata: AiModelMetadata) -> None:
    outputs = whisper_encoder_metadata.outputs
    assert len(outputs) > 0
    out = outputs[0]
    assert out["name"] == "last_hidden_state"
    assert out["dtype"] == _ONNX_FLOAT
    # Shape: [batch_size, 1500, 384]
    assert out["shape"][1] == 1500
    assert out["shape"][2] == 384


def test_whisper_encoder_provenance(whisper_encoder_metadata: AiModelMetadata) -> None:
    assert "inputs" in whisper_encoder_metadata.provenance
    assert "outputs" in whisper_encoder_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real ONNX file (gpt2-tiny-decoder.onnx)
# Source: fxmarty/gpt2-tiny-onnx (~1.0 MB)
# GPT-2 causal LM decoder with KV-cache outputs; opset 13
# Require: onnx installed AND tests/fixtures/onnx/gpt2-tiny-decoder.onnx present
# ---------------------------------------------------------------------------

GPT2_DECODER_FIXTURE = _ONNX / "gpt2-tiny-decoder.onnx"


@pytest.fixture(scope="module")
def gpt2_decoder_metadata() -> AiModelMetadata:
    """Extract metadata from the gpt2-tiny-decoder.onnx fixture once per session."""
    pytest.importorskip("onnx")
    if not GPT2_DECODER_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {GPT2_DECODER_FIXTURE}")
    return read_onnx(GPT2_DECODER_FIXTURE)


def test_gpt2_decoder_format(gpt2_decoder_metadata: AiModelMetadata) -> None:
    assert gpt2_decoder_metadata.format == AiModelFormat.ONNX


def test_gpt2_decoder_name(gpt2_decoder_metadata: AiModelMetadata) -> None:
    assert gpt2_decoder_metadata.name == "torch_jit"


def test_gpt2_decoder_opset(gpt2_decoder_metadata: AiModelMetadata) -> None:
    assert gpt2_decoder_metadata.properties.get("opset.ai.onnx") == "13"


def test_gpt2_decoder_inputs(gpt2_decoder_metadata: AiModelMetadata) -> None:
    input_names = {i["name"] for i in gpt2_decoder_metadata.inputs}
    assert "input_ids" in input_names
    assert "attention_mask" in input_names


def test_gpt2_decoder_logits_output(gpt2_decoder_metadata: AiModelMetadata) -> None:
    output_names = {o["name"] for o in gpt2_decoder_metadata.outputs}
    assert "logits" in output_names


def test_gpt2_decoder_kv_cache_outputs(gpt2_decoder_metadata: AiModelMetadata) -> None:
    # Decoder produces past key/value tensors for each transformer layer
    output_names = {o["name"] for o in gpt2_decoder_metadata.outputs}
    assert "present.0.key" in output_names
    assert "present.0.value" in output_names


def test_gpt2_decoder_provenance(gpt2_decoder_metadata: AiModelMetadata) -> None:
    assert "inputs" in gpt2_decoder_metadata.provenance
    assert "outputs" in gpt2_decoder_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real ONNX file (light-inception-v2.onnx)
# Source: onnx/onnx GitHub (onnx/backend/test/data/light/light_inception_v2.onnx)
# Lightweight InceptionV2, opset 9; weight initializers listed as graph inputs
# Require: onnx installed AND tests/fixtures/onnx/light-inception-v2.onnx present
# ---------------------------------------------------------------------------

INCEPTION_V2_FIXTURE = _ONNX / "light-inception-v2.onnx"


@pytest.fixture(scope="module")
def inception_v2_metadata() -> AiModelMetadata:
    """Extract metadata from the light-inception-v2.onnx fixture once per session."""
    pytest.importorskip("onnx")
    if not INCEPTION_V2_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {INCEPTION_V2_FIXTURE}")
    return read_onnx(INCEPTION_V2_FIXTURE)


def test_inception_v2_format(inception_v2_metadata: AiModelMetadata) -> None:
    assert inception_v2_metadata.format == AiModelFormat.ONNX


def test_inception_v2_name(inception_v2_metadata: AiModelMetadata) -> None:
    assert inception_v2_metadata.name == "inception_v2"
    assert "graph.name" in inception_v2_metadata.provenance["name"]


def test_inception_v2_type_of_model(inception_v2_metadata: AiModelMetadata) -> None:
    # Empty domain falls back to "neural network"
    assert inception_v2_metadata.type_of_model == "neural network"


def test_inception_v2_opset(inception_v2_metadata: AiModelMetadata) -> None:
    # Opset 9 — oldest opset in the test fixtures
    assert inception_v2_metadata.properties.get("opset.ai.onnx") == "9"


def test_inception_v2_data_input(inception_v2_metadata: AiModelMetadata) -> None:
    # First input is the image tensor; remaining inputs are weight initializers
    # (older ONNX format included initializers in graph.input)
    inputs = inception_v2_metadata.inputs
    assert len(inputs) > 1  # data + weight initializers
    data_in = inputs[0]
    assert data_in["name"] == "data_0"
    assert data_in["dtype"] == _ONNX_FLOAT
    assert data_in["shape"] == [1, 3, 224, 224]


def test_inception_v2_output(inception_v2_metadata: AiModelMetadata) -> None:
    outputs = inception_v2_metadata.outputs
    assert len(outputs) == 1
    out = outputs[0]
    assert out["name"] == "prob_1"
    assert out["dtype"] == _ONNX_FLOAT
    assert out["shape"] == [1, 1000]


def test_inception_v2_provenance(inception_v2_metadata: AiModelMetadata) -> None:
    assert "inputs" in inception_v2_metadata.provenance
    assert "outputs" in inception_v2_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real ONNX file (resnet-tiny-beans.onnx)
# Source: fxmarty/resnet-tiny-beans (~761 KB)
# ResNet fine-tuned for 3-class bean disease classification; opset 11
# Require: onnx installed AND tests/fixtures/onnx/resnet-tiny-beans.onnx present
# ---------------------------------------------------------------------------

RESNET_BEANS_FIXTURE = _ONNX / "resnet-tiny-beans.onnx"


@pytest.fixture(scope="module")
def resnet_beans_metadata() -> AiModelMetadata:
    """Extract metadata from the resnet-tiny-beans.onnx fixture once per session."""
    pytest.importorskip("onnx")
    if not RESNET_BEANS_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {RESNET_BEANS_FIXTURE}")
    return read_onnx(RESNET_BEANS_FIXTURE)


def test_resnet_beans_format(resnet_beans_metadata: AiModelMetadata) -> None:
    assert resnet_beans_metadata.format == AiModelFormat.ONNX


def test_resnet_beans_name(resnet_beans_metadata: AiModelMetadata) -> None:
    # PyTorch JIT ONNX exports use "torch_jit" as the graph name
    assert resnet_beans_metadata.name == "torch_jit"


def test_resnet_beans_opset(resnet_beans_metadata: AiModelMetadata) -> None:
    assert resnet_beans_metadata.properties.get("opset.ai.onnx") == "11"


def test_resnet_beans_input(resnet_beans_metadata: AiModelMetadata) -> None:
    inputs = resnet_beans_metadata.inputs
    assert len(inputs) > 0
    inp = inputs[0]
    assert inp["name"] == "pixel_values"
    assert inp["dtype"] == _ONNX_FLOAT
    # Spatial dimensions 224×224 are fixed; batch and channels are dynamic
    assert inp["shape"][2] == 224
    assert inp["shape"][3] == 224


def test_resnet_beans_output(resnet_beans_metadata: AiModelMetadata) -> None:
    outputs = resnet_beans_metadata.outputs
    assert len(outputs) == 1
    assert outputs[0]["name"] == "logits"
    assert outputs[0]["dtype"] == _ONNX_FLOAT


def test_resnet_beans_provenance(resnet_beans_metadata: AiModelMetadata) -> None:
    assert "inputs" in resnet_beans_metadata.provenance
    assert "outputs" in resnet_beans_metadata.provenance


# ---------------------------------------------------------------------------
# Integration tests — real ONNX file (squeezenet1.1-7.onnx)
# Require: onnx installed AND tests/fixtures/onnx/squeezenet1.1-7.onnx present
# ---------------------------------------------------------------------------

SQUEEZENET_FIXTURE = _ONNX / "squeezenet1.1-7.onnx"


@pytest.fixture(scope="module")
def squeezenet_metadata() -> AiModelMetadata:
    """Extract metadata from the squeezenet1.1-7.onnx fixture once per session."""
    pytest.importorskip("onnx")
    if not SQUEEZENET_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {SQUEEZENET_FIXTURE}")
    return read_onnx(SQUEEZENET_FIXTURE)


def test_onnx_integration_format(squeezenet_metadata: AiModelMetadata) -> None:
    assert squeezenet_metadata.format == AiModelFormat.ONNX


def test_onnx_integration_name(squeezenet_metadata: AiModelMetadata) -> None:
    # squeezenet1.1-7.onnx graph name is 'main'
    assert squeezenet_metadata.name == "main"
    assert "name" in squeezenet_metadata.provenance
    assert "graph.name" in squeezenet_metadata.provenance["name"]


def test_onnx_integration_no_description(squeezenet_metadata: AiModelMetadata) -> None:
    # The model has an empty doc_string
    assert squeezenet_metadata.description is None


def test_onnx_integration_no_version(squeezenet_metadata: AiModelMetadata) -> None:
    # model_version is 0 (not set)
    assert squeezenet_metadata.version is None


def test_onnx_integration_type_of_model(squeezenet_metadata: AiModelMetadata) -> None:
    # Empty domain falls back to "neural network"
    assert squeezenet_metadata.type_of_model == "neural network"


def test_onnx_integration_opset(squeezenet_metadata: AiModelMetadata) -> None:
    # Opset domain '' is normalised to 'ai.onnx'; version 7
    assert squeezenet_metadata.properties.get("opset.ai.onnx") == "7"


def test_onnx_integration_no_domain_property(
    squeezenet_metadata: AiModelMetadata,
) -> None:
    # Empty domain string is not stored as a property
    assert "domain" not in squeezenet_metadata.properties


def test_onnx_integration_inputs(squeezenet_metadata: AiModelMetadata) -> None:
    # First input is the image tensor 'data' with shape [1, 3, 224, 224]
    inputs = squeezenet_metadata.inputs
    assert len(inputs) > 0
    data_input = inputs[0]
    assert data_input["name"] == "data"
    assert data_input["dtype"] == _ONNX_FLOAT
    assert data_input["shape"] == [1, 3, 224, 224]


def test_onnx_integration_outputs(squeezenet_metadata: AiModelMetadata) -> None:
    # Single output with shape [1, 1000] (1000 ImageNet classes)
    outputs = squeezenet_metadata.outputs
    assert len(outputs) == 1
    assert outputs[0]["name"] == "squeezenet0_flatten0_reshape0"
    assert outputs[0]["dtype"] == _ONNX_FLOAT
    assert outputs[0]["shape"] == [1, 1000]


def test_onnx_integration_provenance_fields(
    squeezenet_metadata: AiModelMetadata,
) -> None:
    assert "inputs" in squeezenet_metadata.provenance
    assert "outputs" in squeezenet_metadata.provenance
