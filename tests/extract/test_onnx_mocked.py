# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ONNX metadata extractor (mocked onnx.ModelProto).

See also: test_onnx_integration.py for the real-fixture integration tests.
"""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract._onnx import _onnx_tensor_specs
from pitloom.extract.ai_model import read_onnx

_ONNX = Path(__file__).parent.parent / "fixtures" / "aimodels" / "onnx"

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

    assert meta.format_info.model_format == AiModelFormat.ONNX
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
    assert meta.format_info.model_format == AiModelFormat.ONNX


def test_onnx_tensor_specs_missing_dtype_shape_and_dim() -> None:
    """_onnx_tensor_specs handles a missing elem_type, a falsy shape, and a
    dimension with neither dim_value nor dim_param set."""
    vi_no_dtype_no_shape = MagicMock()
    vi_no_dtype_no_shape.name = "no_dtype"
    vi_no_dtype_no_shape.type.tensor_type.HasField.return_value = False
    vi_no_dtype_no_shape.type.tensor_type.shape = None

    dim_no_field = MagicMock()
    dim_no_field.HasField.return_value = False

    vi_unknown_dim = MagicMock()
    vi_unknown_dim.name = "unknown_dim"
    vi_unknown_dim.type.tensor_type.HasField.return_value = True
    vi_unknown_dim.type.tensor_type.elem_type = _ONNX_FLOAT
    vi_unknown_dim.type.tensor_type.shape.dim = [dim_no_field]

    specs = _onnx_tensor_specs([vi_no_dtype_no_shape, vi_unknown_dim])

    assert specs[0] == {"name": "no_dtype"}
    assert "dtype" not in specs[0]
    assert "shape" not in specs[0]
    assert specs[1]["shape"] == [None]


def test_onnx_zero_ir_version_skips_format_version(tmp_path: Path) -> None:
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"fake")

    mock_model = _make_onnx_mock()
    mock_model.ir_version = 0
    mock_model.graph.input = []
    mock_model.graph.output = []

    mock_onnx = MagicMock()
    mock_onnx.load.return_value = mock_model

    with patch.dict("sys.modules", {"onnx": mock_onnx}):
        meta = read_onnx(model_file)

    assert meta.format_info.format_version is None
    assert "format_version" not in meta.provenance


def test_onnx_load_failure(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"corrupt")

    mock_onnx = MagicMock()
    mock_onnx.load.side_effect = RuntimeError("bad protobuf")

    with patch.dict("sys.modules", {"onnx": mock_onnx}):
        with caplog.at_level(logging.DEBUG, logger="pitloom.extract._onnx"):
            with pytest.raises(ValueError, match="Failed to load ONNX model"):
                read_onnx(model_file)

    # Load failure is now logged at debug level before being re-raised.
    assert any("model.onnx" in r.message for r in caplog.records)
