# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""ONNX inputs, outputs and type of model on small graphs built with
``onnx.helper``: dtype names, initializers listed as inputs, ONNX-ML.

See also: test_onnx_integration.py (the real fixtures) and
test_onnx_mocked.py (a mocked ``onnx.ModelProto``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pitloom.extract.ai_model.onnx import read_onnx

onnx = pytest.importorskip("onnx")
helper = onnx.helper
TensorProto = onnx.TensorProto


def _save(
    path: Path,
    graph_inputs: list[Any],
    *,
    initializers: tuple[str, ...] = (),
    sparse: tuple[str, ...] = (),
    opsets: tuple[tuple[str, int], ...] = (("", 13),),
    out_type: int = TensorProto.FLOAT,
) -> Path:
    """An Identity graph from the first input, *initializers* (dense) and
    *sparse* (sparse) weights named as given, IR version 3 so weights may
    also be listed as inputs."""
    first = graph_inputs[0].name
    weights = [
        helper.make_tensor(name, TensorProto.FLOAT, [1], [1.0]) for name in initializers
    ]
    sparse_weights = [
        helper.make_sparse_tensor(
            helper.make_tensor(name, TensorProto.FLOAT, [1], [1.0]),
            helper.make_tensor(name + "_i", TensorProto.INT64, [1], [0]),
            [1],
        )
        for name in sparse
    ]
    graph = helper.make_graph(
        [helper.make_node("Identity", [first], ["y"])],
        "main",
        graph_inputs,
        [helper.make_tensor_value_info("y", out_type, ["N"])],
        weights,
        sparse_initializer=sparse_weights,
    )
    model = helper.make_model(
        graph, opset_imports=[helper.make_opsetid(d, v) for d, v in opsets]
    )
    model.ir_version = 3
    onnx.save(model, str(path))
    return path


def _value_info(name: str, elem_type: int = TensorProto.FLOAT) -> Any:
    return helper.make_tensor_value_info(name, elem_type, ["N"])


def test_every_element_type_is_a_name_never_its_number(tmp_path: Path) -> None:
    """Regression: dtype was the raw TensorProto enum (1, 7). Each name is
    NumPy's where NumPy has the type, else ONNX's own, lowercased."""
    values = [v for _, v in TensorProto.DataType.items() if v]
    inputs = [_value_info(f"x{v}", v) for v in values]
    meta = read_onnx(_save(tmp_path / "m.onnx", inputs))
    dtypes = {spec["name"]: spec["dtype"] for spec in meta.inputs}
    assert len(dtypes) == len(values)
    for value in values:
        dtype = dtypes[f"x{value}"]
        assert isinstance(dtype, str)
        numpy_dtype = helper.tensor_dtype_to_np_dtype(value)
        # NumPy's own type (not ml_dtypes' bfloat16, float8, ...; not object)
        if numpy_dtype.type.__module__ == "numpy" and numpy_dtype.kind != "O":
            assert dtype == numpy_dtype.name
        else:
            assert dtype == TensorProto.DataType.Name(value).lower()
    assert dtypes[f"x{TensorProto.FLOAT}"] == "float32"
    assert dtypes[f"x{TensorProto.STRING}"] == "string"
    assert dtypes[f"x{TensorProto.BFLOAT16}"] == "bfloat16"
    assert meta.outputs == [{"name": "y", "dtype": "float32", "shape": ["N"]}]


def test_initializers_listed_as_inputs_are_not_inputs(tmp_path: Path) -> None:
    """Regression: an IR version 3 graph lists its weights in graph.input."""
    inputs = [_value_info("x"), _value_info("w"), _value_info("s")]
    path = _save(tmp_path / "m.onnx", inputs, initializers=("w",), sparse=("s",))
    meta = read_onnx(path)
    assert meta.inputs == [{"name": "x", "dtype": "float32", "shape": ["N"]}]
    assert meta.provenance["inputs"] == "Source: m.onnx | Field: graph.input"


@pytest.mark.parametrize(
    ("opsets", "expected"),
    [
        ((("", 13),), "neural network"),
        ((("", 13), ("com.microsoft", 1)), "neural network"),
        ((("", 13), ("ai.onnx.ml", 3)), None),
        ((("ai.onnx.ml", 3),), None),
    ],
    ids=["onnx", "contrib", "onnx-and-ml", "ml-only"],
)
def test_an_onnx_ml_model_has_no_type_of_model(
    tmp_path: Path, opsets: tuple[tuple[str, int], ...], expected: str | None
) -> None:
    """ONNX-ML operators (trees, linear models, SVMs) are not a neural
    network, and the file does not say which: left unset, silently."""
    meta = read_onnx(_save(tmp_path / "m.onnx", [_value_info("x")], opsets=opsets))
    assert meta.type_of_model == expected
    assert meta.name == "main"  # a user's graph name, not an exporter default
