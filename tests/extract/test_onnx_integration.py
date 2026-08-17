# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for the ONNX metadata extractor against real ONNX
model fixtures (encoder-model-q4f16, gpt2-tiny-decoder, light-inception-v2,
resnet-tiny-beans, squeezenet1.1-7).

See also: test_onnx_mocked.py for the mocked onnx.ModelProto unit tests.
"""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.extract.ai_model import read_onnx

_ONNX = Path(__file__).parent.parent / "fixtures" / "aimodels" / "onnx"

# ONNX elem_type 1 = FLOAT  (TensorProto.FLOAT)
_ONNX_FLOAT = 1


# ---------------------------------------------------------------------------
# Integration tests -- real ONNX file (encoder-model-q4f16.onnx)
# Source: onnx-community/whisper-tiny-ONNX (~6.3 MB)
# Whisper tiny speech encoder, quantised Q4F16, two opset domains
# Require: onnx installed AND
#          tests/fixtures/aimodels/onnx/encoder-model-q4f16.onnx present
# ---------------------------------------------------------------------------

WHISPER_ENCODER_FIXTURE = _ONNX / "encoder-model-q4f16.onnx"


@pytest.fixture(scope="module")
def whisper_encoder_metadata() -> AiModelMetadata:
    """Extract metadata from the encoder-model-q4f16.onnx fixture once per session."""
    pytest.importorskip("onnx")
    if not WHISPER_ENCODER_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {WHISPER_ENCODER_FIXTURE}")
    return read_onnx(WHISPER_ENCODER_FIXTURE)


def test_whisper_encoder_format(whisper_encoder_metadata: AiModelMetadata) -> None:
    assert whisper_encoder_metadata.format_info.model_format == AiModelFormat.ONNX


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
# Integration tests -- real ONNX file (gpt2-tiny-decoder.onnx)
# Source: fxmarty/gpt2-tiny-onnx (~1.0 MB)
# GPT-2 causal LM decoder with KV-cache outputs; opset 13
# Require: onnx installed AND
#          tests/fixtures/aimodels/onnx/gpt2-tiny-decoder.onnx present
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
    assert gpt2_decoder_metadata.format_info.model_format == AiModelFormat.ONNX


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
# Integration tests -- real ONNX file (light-inception-v2.onnx)
# Source: onnx/onnx GitHub (onnx/backend/test/data/light/light_inception_v2.onnx)
# Lightweight InceptionV2, opset 9; weight initializers listed as graph inputs
# Require: onnx installed AND
#          tests/fixtures/aimodels/onnx/light-inception-v2.onnx present
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
    assert inception_v2_metadata.format_info.model_format == AiModelFormat.ONNX


def test_inception_v2_name(inception_v2_metadata: AiModelMetadata) -> None:
    assert inception_v2_metadata.name == "inception_v2"
    assert "graph.name" in inception_v2_metadata.provenance["name"]


def test_inception_v2_type_of_model(inception_v2_metadata: AiModelMetadata) -> None:
    # Empty domain falls back to "neural network"
    assert inception_v2_metadata.type_of_model == "neural network"


def test_inception_v2_opset(inception_v2_metadata: AiModelMetadata) -> None:
    # Opset 9 -- oldest opset in the test fixtures
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
# Integration tests -- real ONNX file (resnet-tiny-beans.onnx)
# Source: fxmarty/resnet-tiny-beans (~761 KB)
# ResNet fine-tuned for 3-class bean disease classification; opset 11
# Require: onnx installed AND
#          tests/fixtures/aimodels/onnx/resnet-tiny-beans.onnx present
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
    assert resnet_beans_metadata.format_info.model_format == AiModelFormat.ONNX


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
# Integration tests -- real ONNX file (squeezenet1.1-7.onnx)
# Require: onnx installed AND
#          tests/fixtures/aimodels/onnx/squeezenet1.1-7.onnx present
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
    assert squeezenet_metadata.format_info.model_format == AiModelFormat.ONNX


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
