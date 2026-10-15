# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""ONNX originators (``model_author``) and parameter count (initializers).

See also: test_onnx_integration.py (the other real-file ONNX tests).
"""

# pylint: disable=missing-function-docstring
# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.model_originators import (
    COMMA_LIST_METHOD,
    MAX_ORIGINATOR_PARTS,
    ORIGINATORS_PROVENANCE_KEY,
)
from pitloom.core.model_parameters import PARAMETER_COUNT_PROVENANCE_KEY
from pitloom.extract.ai_model.onnx import read_onnx
from tests.warning_helpers import logged_warnings

onnx: Any = pytest.importorskip("onnx")

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "aimodels" / "onnx"
_FLOAT = onnx.TensorProto.FLOAT
_KEY = "model_author"
_AUTHOR = f"metadata_props.{_KEY}"


def _tensor(name: str, *dims: int) -> Any:
    """An initializer of *dims* with no data: the count reads dims only."""
    return onnx.TensorProto(name=name, data_type=_FLOAT, dims=list(dims))


def _graph(
    initializers: list[Any] | None = None,
    nodes: list[Any] | None = None,
    sparse: list[Any] | None = None,
) -> Any:
    graph = onnx.helper.make_graph(nodes or [], "g", [], [], initializers or [])
    graph.sparse_initializer.extend(sparse or [])
    return graph


def _write(tmp_path: Path, graph: Any, props: tuple[tuple[str, str], ...] = ()) -> Path:
    model = onnx.helper.make_model(graph)
    for key, value in props:
        entry = model.metadata_props.add()
        entry.key, entry.value = key, value
    path = tmp_path / "m.onnx"
    path.write_bytes(model.SerializeToString())
    return path


def _if(then_branch: Any, else_branch: Any) -> Any:
    return onnx.helper.make_node(
        "If", ["c"], ["o"], then_branch=then_branch, else_branch=else_branch
    )


@pytest.mark.parametrize(
    ("fixture", "count"),
    [
        ("encoder-model-q4f16.onnx", 4890637),
        ("gpt2-tiny-decoder.onnx", 404256),
        ("light-inception-v2.onnx", 5417),
        ("resnet-tiny-beans.onnx", 189347),
        ("squeezenet1.1-7.onnx", 1235498),
    ],
    ids=lambda value: str(value)[:8],
)
def test_fixture_counts(fixture: str, count: int) -> None:
    meta = read_onnx(_FIXTURES / fixture)
    assert meta.parameter_count == count
    assert meta.originators == []  # no fixture carries an author


def test_fixture_provenance_exact() -> None:
    meta = read_onnx(_FIXTURES / "squeezenet1.1-7.onnx")
    assert meta.provenance[PARAMETER_COUNT_PROVENANCE_KEY] == (
        "Source: squeezenet1.1-7.onnx"
        " | Field: graph.initializer, graph.sparse_initializer"
        " | Method: tensor_element_sum"
    )
    assert ORIGINATORS_PROVENANCE_KEY not in meta.provenance


def test_provenance_keys_are_field_names(tmp_path: Path) -> None:
    """The keys are the ``AiModelMetadata`` field names, as every other
    model provenance key is (literal: the constants must not drift)."""
    path = _write(tmp_path, _graph([_tensor("w", 2, 3)]), ((_KEY, "Alice"),))
    provenance = read_onnx(path).provenance
    assert {"originators", "parameter_count"} <= provenance.keys()
    assert not {"originatedBy", "hyperparameters.parameters"} & provenance.keys()


def _sparse_graph() -> Any:
    values, indices = (
        _tensor("v", 2),
        onnx.TensorProto(name="i", data_type=onnx.TensorProto.INT64, dims=[2]),
    )
    return _graph(sparse=[onnx.helper.make_sparse_tensor(values, indices, [4, 5])])


def _if_graph() -> Any:
    then_branch = _graph([_tensor("t", 3, 3)])
    return _graph([_tensor("w", 2)], [_if(then_branch, _graph())])


def _both_branches_graph() -> Any:
    return _graph(
        nodes=[_if(_graph([_tensor("a", 5)]), _graph([_tensor("b", 7)]))],
    )


def _graphs_attribute_graph() -> Any:
    node = onnx.helper.make_node("Scan", ["x"], ["y"])
    node.attribute.append(
        onnx.helper.make_attribute("bodies", [_graph([_tensor("a", 4)])] * 2)
    )
    assert node.attribute[0].type == onnx.AttributeProto.GRAPHS
    return _graph(nodes=[node])


def _nested_graph() -> Any:
    inner = _graph([_tensor("c", 1)])
    for _ in range(30):  # one node per level: a recursive walk would add frames
        inner = _graph([_tensor("c", 1)], [_if(inner, _graph())])
    return inner


def _external_graph() -> Any:
    tensor = _tensor("e", 6, 7)
    tensor.data_location = onnx.TensorProto.EXTERNAL
    entry = tensor.external_data.add()
    entry.key, entry.value = "location", "absent.bin"  # the file does not exist
    return _graph([tensor])


def _constant_graph() -> Any:
    node = onnx.helper.make_node(
        "Constant", [], ["k"], value=_tensor("k", 99)
    )  # not a weight: not counted
    return _graph([_tensor("w", 2)], [node])


@pytest.mark.parametrize(
    ("build", "count"),
    [
        (_sparse_graph, 20),  # the dense dims, not the 2 stored values
        (_if_graph, 11),
        (_both_branches_graph, 12),
        (_graphs_attribute_graph, 8),  # GRAPHS: two bodies of 4
        (_nested_graph, 31),
        (_external_graph, 42),
        (_constant_graph, 2),
        (lambda: _graph([_tensor("a", 2, 3), _tensor("s")]), 7),  # scalar: 1
    ],
    ids=[
        "sparse",
        "if",
        "branches",
        "graphs",
        "nested",
        "external",
        "constant",
        "scalar",
    ],
)
def test_counted_initializers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, build: Any, count: int
) -> None:
    with caplog.at_level(logging.WARNING):
        meta = read_onnx(_write(tmp_path, build()))
    assert meta.parameter_count == count
    assert PARAMETER_COUNT_PROVENANCE_KEY in meta.provenance
    assert logged_warnings(caplog) == []


@pytest.mark.parametrize(
    ("dims", "needle"),
    [
        ([-1, 4], "not a non-negative integer"),
        ([10**8, 10**8], "parameter-count cap"),
    ],
    ids=["negative", "cap"],
)
def test_rejected_dims_warn_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, dims: list[int], needle: str
) -> None:
    graph = _graph([_tensor("ok", 3), _tensor("bad", *dims)])
    with caplog.at_level(logging.WARNING):
        meta = read_onnx(_write(tmp_path, graph))
    assert meta.parameter_count is None  # never the partial sum 3
    assert PARAMETER_COUNT_PROVENANCE_KEY not in meta.provenance
    [message] = logged_warnings(caplog)
    assert needle in message


@pytest.mark.parametrize(
    "build",
    [_graph, lambda: _graph([_tensor("z", 0, 5)])],
    ids=["none", "zero-size"],
)
def test_no_elements_is_silent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, build: Any
) -> None:
    with caplog.at_level(logging.WARNING):
        meta = read_onnx(_write(tmp_path, build()))
    assert meta.parameter_count is None
    assert PARAMETER_COUNT_PROVENANCE_KEY not in meta.provenance
    assert logged_warnings(caplog) == []


_SOURCE = "Source: m.onnx | Field: " + _AUTHOR


@pytest.mark.parametrize(
    ("props", "names", "provenance"),
    [
        ((), [], None),
        (((_KEY, ""),), [], None),
        (((_KEY, "   "),), [], None),
        (((_KEY, " , ,"),), [], None),
        (((_KEY, "Alice"),), ["Alice"], _SOURCE),
        (
            ((_KEY, "Alice, Bob,,Alice"),),
            ["Alice", "Bob"],
            _SOURCE + COMMA_LIST_METHOD,
        ),
        # Known caveat: a name with a comma is split ("Doe, Jane", "Foo, Inc.")
        (((_KEY, "Doe, Jane"),), ["Doe", "Jane"], _SOURCE + COMMA_LIST_METHOD),
        # Repeated key: the last value wins, as for every metadata_props key
        (
            ((_KEY, "Alice"), (_KEY, "Bob")),
            ["Bob"],
            _SOURCE,
        ),
    ],
    ids=[
        "absent",
        "empty",
        "blank",
        "commas",
        "one",
        "list",
        "doe-jane",
        "repeated",
    ],
)
def test_model_author(
    tmp_path: Path,
    props: tuple[tuple[str, str], ...],
    names: list[str],
    provenance: str | None,
) -> None:
    meta = read_onnx(_write(tmp_path, _graph(), props))
    assert meta.originators == names
    assert meta.provenance.get(ORIGINATORS_PROVENANCE_KEY) == provenance
    if props:  # properties stay as read
        assert meta.properties[_AUTHOR] == props[-1][1]


def test_model_author_unusual_characters(tmp_path: Path) -> None:
    """The name is kept as read (the assembler escapes it); the provenance
    holds only the literal field name, never text from the file."""
    name = "Zo\N{LATIN SMALL LETTER E WITH DIAERESIS} \N{RIGHT-TO-LEFT OVERRIDE}x\x07"
    meta = read_onnx(_write(tmp_path, _graph(), ((_KEY, f"{name}, Bob"),)))
    assert meta.originators == [name, "Bob"]
    assert meta.provenance[ORIGINATORS_PROVENANCE_KEY] == _SOURCE + COMMA_LIST_METHOD
    assert meta.provenance[ORIGINATORS_PROVENANCE_KEY].isascii()


_BOUND = MAX_ORIGINATOR_PARTS


@pytest.mark.parametrize(
    ("author", "names", "cut"),
    [
        (" ," * _BOUND + "Real Author", [], True),
        ("Acme, " * _BOUND + "Real Author", ["Acme"], True),
        ("Acme, " * (_BOUND - 1) + "Real Author", ["Acme", "Real Author"], False),
        (" ," * (_BOUND - 1) + "Real Author", ["Real Author"], False),
        ("," * 10**5 + "Real Author", ["Real Author"], False),
    ],
    ids=["blank-parts", "repeats", "exact-end", "exact-end-blank", "empty-pieces"],
)
def test_model_author_parts_bound_warns_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    author: str,
    names: list[str],
    cut: bool,
) -> None:
    """Names past the parts bound are not read, and the reader says so once;
    a bound met exactly at the end, or empty pieces, are no cut."""
    with caplog.at_level(logging.WARNING):
        meta = read_onnx(_write(tmp_path, _graph(), ((_KEY, author),)))
    assert meta.originators == names
    expected = [
        f"FILE={tmp_path / 'm.onnx'}: larger than the {_BOUND}-part model-author"
        " cap; rest of model_author not read"
    ]
    assert logged_warnings(caplog) == (expected if cut else [])
