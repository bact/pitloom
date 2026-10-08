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
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model.onnx import _onnx_tensor_specs, read_onnx

_ONNX = Path(__file__).parent.parent.parent / "fixtures" / "aimodels" / "onnx"

# ONNX elem_type 1 = FLOAT  (TensorProto.FLOAT)
_ONNX_FLOAT = 1

# The onnx.ModelProto fields read_onnx() reads; a spec keeps a misspelt
# field from passing as an auto-created mock attribute
_MODEL_PROTO_FIELDS = [
    "doc_string",
    "domain",
    "graph",
    "ir_version",
    "metadata_props",
    "model_version",
    "opset_import",
    "producer_name",
    "producer_version",
]

_VALUE_INFO_FIELDS = ["name", "type"]
_DIMENSION_FIELDS = ["HasField", "dim_param", "dim_value"]


def _mock_onnx_module(model: MagicMock | None = None) -> MagicMock:
    """A mock ``onnx`` module whose ``load()`` returns *model*."""
    mock_onnx = MagicMock(spec=["load"])
    mock_onnx.load.return_value = model
    return mock_onnx


# pylint: disable-next=too-many-arguments,too-many-positional-arguments,too-many-locals
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
    model = MagicMock(spec=_MODEL_PROTO_FIELDS)
    model.graph.name = graph_name
    model.doc_string = doc_string
    model.model_version = model_version
    model.domain = domain

    # metadata_props
    props = []
    for k, v in (metadata_props or {}).items():
        p = MagicMock(spec=["key", "value"])
        p.key = k
        p.value = v
        props.append(p)
    model.metadata_props = props

    # opset_import
    opsets = []
    for dom, ver in (opset_versions or {"": 17}).items():
        o = MagicMock(spec=["domain", "version"])
        o.domain = dom
        o.version = ver
        opsets.append(o)
    model.opset_import = opsets

    # graph inputs / outputs
    def _make_vi(
        name: str, dtype: int = 1, shape: list[int | str] | None = None
    ) -> MagicMock:
        vi = MagicMock(spec=_VALUE_INFO_FIELDS)
        vi.name = name
        vi.type.tensor_type.elem_type = dtype
        vi.type.tensor_type.HasField.return_value = True
        dims = []
        for d in shape or []:
            dim = MagicMock(spec=_DIMENSION_FIELDS)
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
        domain="org.example",
        metadata_props={"author": "test", "task": "classification"},
        opset_versions={"": 17, "com.microsoft": 1},
    )

    mock_onnx = _mock_onnx_module(mock_model)

    with patch.dict("sys.modules", {"onnx": mock_onnx}):
        meta = read_onnx(model_file)

    assert meta.format_info.model_format == AiModelFormat.ONNX
    assert meta.name == "ResNet50"
    assert meta.description == "Image classification model"
    assert meta.version == "2"
    # domain is the owner's namespace, not a model type
    assert meta.type_of_model == "neural network"
    assert meta.properties["metadata_props.author"] == "test"
    assert meta.properties["metadata_props.task"] == "classification"
    assert meta.properties["domain"] == "org.example"
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

    mock_onnx = _mock_onnx_module(mock_model)

    with patch.dict("sys.modules", {"onnx": mock_onnx}):
        meta = read_onnx(model_file)

    assert meta.name is None
    assert "name" not in meta.provenance
    assert meta.description is None
    assert meta.version is None
    assert meta.license is None
    assert "license" not in meta.provenance
    assert meta.format_info.model_format == AiModelFormat.ONNX


def _read_mock(tmp_path: Path, **kwargs: Any) -> Any:
    """Run read_onnx() on a mocked ModelProto built from *kwargs*."""
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"fake")
    mock_onnx = _mock_onnx_module(_make_onnx_mock(**kwargs))
    with patch.dict("sys.modules", {"onnx": mock_onnx}):
        return read_onnx(model_file)


@pytest.mark.parametrize(
    ("graph_name", "expected"),
    [
        # Exporter defaults name the tool, not the model
        ("torch-jit-export", None),
        ("torch_jit", None),
        ("main_graph", None),
        ("tf2onnx", None),
        # Exact match only: a real name that merely contains a default stays
        ("torch_jit_resnet", "torch_jit_resnet"),
        ("Torch_JIT", "Torch_JIT"),
        # Blank is no name; padding is not part of one
        ("   ", None),
        ("\t\n", None),
        ("  ResNet  ", "ResNet"),
        (" torch_jit ", None),
    ],
)
def test_onnx_exporter_default_graph_name_is_not_a_name(
    tmp_path: Path, graph_name: str, expected: str | None
) -> None:
    meta = _read_mock(tmp_path, graph_name=graph_name)
    assert meta.name == expected
    if expected is None:
        assert "name" not in meta.provenance
    else:
        assert meta.provenance["name"].endswith("Field: graph.name")


@pytest.mark.parametrize(
    ("metadata_props", "expected"),
    [
        ({"model_license": "Apache-2.0"}, "Apache-2.0"),
        ({"model_license": "  CC-BY-4.0\n"}, "CC-BY-4.0"),
        ({"model_license": "https://example.org/l"}, "https://example.org/l"),
        # Present but empty is no statement
        ({"model_license": ""}, None),
        ({"model_license": "   "}, None),
        # Only the ONNX IR standard key is read, not ad-hoc spellings
        ({"license": "MIT"}, None),
        ({}, None),
    ],
)
def test_onnx_model_license(
    tmp_path: Path, metadata_props: dict[str, str], expected: str | None
) -> None:
    meta = _read_mock(tmp_path, metadata_props=metadata_props)
    assert meta.license == expected
    if expected is None:
        assert "license" not in meta.provenance
    else:
        assert meta.provenance["license"].endswith(
            "Field: metadata_props.model_license"
        )
    # The verbatim property is kept alongside the promoted licence
    assert (
        meta.properties.items()
        >= {f"metadata_props.{k}": v for k, v in metadata_props.items()}.items()
    )


def test_onnx_tensor_specs_missing_dtype_shape_and_dim() -> None:
    """_onnx_tensor_specs handles a missing elem_type, a falsy shape, and a
    dimension with neither dim_value nor dim_param set."""
    vi_no_dtype_no_shape = MagicMock(spec=_VALUE_INFO_FIELDS)
    vi_no_dtype_no_shape.name = "no_dtype"
    vi_no_dtype_no_shape.type.tensor_type.HasField.return_value = False
    vi_no_dtype_no_shape.type.tensor_type.shape = None

    dim_no_field = MagicMock(spec=_DIMENSION_FIELDS)
    dim_no_field.HasField.return_value = False

    vi_unknown_dim = MagicMock(spec=_VALUE_INFO_FIELDS)
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

    mock_onnx = _mock_onnx_module(mock_model)

    with patch.dict("sys.modules", {"onnx": mock_onnx}):
        meta = read_onnx(model_file)

    assert meta.format_info.format_version is None
    assert "format_version" not in meta.provenance


def test_onnx_load_failure(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"corrupt")

    mock_onnx = _mock_onnx_module()
    mock_onnx.load.side_effect = RuntimeError("bad protobuf")

    with patch.dict("sys.modules", {"onnx": mock_onnx}):
        with caplog.at_level(logging.DEBUG, logger="pitloom.extract.ai_model.onnx"):
            with pytest.raises(ValueError, match="Failed to load ONNX model"):
                read_onnx(model_file)

    # Load failure is now logged at debug level before being re-raised.
    assert any("model.onnx" in r.message for r in caplog.records)


@pytest.mark.parametrize(
    ("model_version", "expected", "semver"),
    [
        (0, None, False),  # no version: nothing recorded
        (1, "1", False),
        (0xFFFF_FFFF, "4294967295", False),  # largest simple number
        (0x0001_0002_0000_0159, "1.2.345", True),  # the spec's example
        (1 << 48, "1.0.0", True),
        (1 << 32, "0.1.0", True),  # lowest SemVer: MINOR alone sets the flag
        (-1, "65535.65535.4294967295", True),  # int64 read as its 64 bits
        (-(2**63), "32768.0.0", True),  # int64 minimum: only the top bit
    ],
)
def test_onnx_model_version_semver_bit_packed(
    tmp_path: Path, model_version: int, expected: str | None, semver: bool
) -> None:
    meta = _read_mock(tmp_path, model_version=model_version)
    assert meta.version == expected
    if expected is None:
        assert "version" not in meta.provenance
        return
    assert meta.provenance["version"] == (
        "Source: model.onnx | Field: model_version"
        + (" | Method: semver_bit_packed" if semver else "")
    )


def test_mocked_model_proto_fields_exist() -> None:
    """The mocks' specs name real ONNX protobuf fields."""
    onnx = pytest.importorskip("onnx")
    for proto, fields in (
        (onnx.ModelProto, _MODEL_PROTO_FIELDS),
        (onnx.ValueInfoProto, _VALUE_INFO_FIELDS),
        (
            onnx.TensorShapeProto.Dimension,
            [f for f in _DIMENSION_FIELDS if f != "HasField"],
        ),
    ):
        assert set(fields) <= set(proto.DESCRIPTOR.fields_by_name), proto


@pytest.mark.parametrize("key", ["domain", "opset.ai.onnx", "metadata_props.x"])
@pytest.mark.parametrize("field_domain", ["org.example", ""])
def test_onnx_metadata_props_never_collide_with_fields(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, key: str, field_domain: str
) -> None:
    """A metadata_props key spelt like a field-derived key, with or without
    that field set, keeps its own entry; the fields keep theirs."""
    with caplog.at_level(logging.WARNING, logger="pitloom.extract.ai_model.onnx"):
        meta = _read_mock(tmp_path, domain=field_domain, metadata_props={key: "NLP"})
    assert meta.properties[f"metadata_props.{key}"] == "NLP"
    assert meta.properties.get("domain") == (field_domain or None)
    assert meta.properties["opset.ai.onnx"] == "17"
    assert len(meta.properties) == 2 + bool(field_domain)
    assert meta.provenance[f"properties.metadata_props.{key}"].endswith(
        f"Field: metadata_props.{key}"
    )
    if field_domain:
        assert meta.provenance["properties.domain"].endswith("Field: domain")
    assert not caplog.records


def _entry(key: str, value: str) -> MagicMock:
    entry = MagicMock(spec=["key", "value"])
    entry.key, entry.value = key, value
    return entry


def test_onnx_repeated_metadata_props_key_warns_once_keeps_last(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Repeated keys (the ONNX checker rejects them) keep the file's last
    value; one bounded warning per file counts them, whatever the file
    holds (a hostile file must not flood the log or fill one line)."""
    long_key = "K" * 100_000
    keys = ["model_license", long_key, "a\nb", "fourth_key", "fifth_key"]
    model = _make_onnx_mock()
    model.metadata_props = [_entry("task", "ner")]
    for value in ("MIT", "BSD-3-Clause", "Apache-2.0"):
        model.metadata_props += [_entry(key, value) for key in keys]
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"fake")
    with patch.dict("sys.modules", {"onnx": _mock_onnx_module(model)}):
        with caplog.at_level(logging.WARNING, logger="pitloom.extract.ai_model.onnx"):
            meta = read_onnx(model_file)
    assert meta.license == "Apache-2.0"
    assert meta.properties["metadata_props.task"] == "ner"
    assert meta.properties[f"metadata_props.{long_key}"] == "Apache-2.0"
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert "5 key(s) appear more than once" in messages[0]
    assert "model_license" in messages[0]
    assert "\n" not in messages[0]
    assert len(messages[0]) < 300
    # The first three keys are named, the rest only counted
    assert "fourth_key" not in messages[0] and "fifth_key" not in messages[0]
    assert messages[0].endswith(", ...")
