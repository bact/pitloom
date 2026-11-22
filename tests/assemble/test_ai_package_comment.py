# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``ai_AIPackage`` comment lines: the tool that wrote the model file
and the known biases, after the parameter-count note.

See also: :mod:`tests.assemble.test_ai_parameter_count` (the note and the
provenance after these lines).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble.spdx3._ai_package_comment import (
    package_comment,
    writing_tool_line,
)
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import (
    MAX_MODEL_NAME_CHARS,
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
)
from pitloom.core.creation import CreationMetadata
from pitloom.core.model_parameters import PARAMETER_COUNT_NOTE
from pitloom.core.provenance import ProvenanceConfig
from pitloom.extract.ai_model.onnx import read_onnx

_CREATION = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")


@pytest.mark.parametrize(
    ("tool", "version", "line"),
    [
        ("tf2onnx", "1.16.1", "Model file written by: tf2onnx 1.16.1"),
        ("mytool", None, "Model file written by: mytool"),
        (None, "2.0", "Model file written by: 2.0"),
        (" my\n tool ", "1\t0", "Model file written by: my tool 1 0"),
        (None, None, None),
        ("  ", "", None),
    ],
    ids=["both", "no-version", "version-only", "one-line", "none", "blank"],
)
def test_the_writing_tool_line(
    tool: str | None, version: str | None, line: str | None
) -> None:
    info = AiModelFormatInfo(writing_tool=tool, writing_tool_version=version)
    assert writing_tool_line(info) == line


def test_a_long_writing_tool_is_capped_as_a_model_name() -> None:
    line = writing_tool_line(AiModelFormatInfo(writing_tool="x" * 5000))
    assert line is not None
    assert len(line.removeprefix("Model file written by: ")) == MAX_MODEL_NAME_CHARS


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (False, "Model file written by: t 1\nKnown biases: b1; b2"),
        (
            True,
            f"{PARAMETER_COUNT_NOTE}\nModel file written by: t 1\nKnown biases: b1; b2",
        ),
    ],
    ids=["no-count", "count"],
)
def test_the_lines_keep_their_order(count: bool, expected: str) -> None:
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(writing_tool="t", writing_tool_version="1")
    )
    model.usage.known_biases = ["b1", "b2"]
    assert package_comment(model, count) == expected


def test_no_line_is_no_comment() -> None:
    assert package_comment(AiModelMetadata(), False) is None


def _onnx_package(path: Path, **producer: str) -> dict[str, Any]:
    onnx = pytest.importorskip("onnx")
    helper = onnx.helper
    graph = helper.make_graph(
        [helper.make_node("Identity", ["x"], ["y"])],
        "g",
        [helper.make_tensor_value_info("x", onnx.TensorProto.FLOAT, [1])],
        [helper.make_tensor_value_info("y", onnx.TensorProto.FLOAT, [1])],
    )
    model = helper.make_model(graph, **producer)
    onnx.save(model, str(path))
    meta = read_onnx(path)
    assert meta.format_info.model_format is AiModelFormat.ONNX
    exporter = build_model(meta, _CREATION, provenance=ProvenanceConfig("both"))
    graph_out: list[dict[str, Any]] = json.loads(exporter.to_json())["@graph"]
    (package,) = [e for e in graph_out if e["type"] == "ai_AIPackage"]
    return package


def test_an_onnx_producer_is_written_as_the_writing_tool(tmp_path: Path) -> None:
    package = _onnx_package(
        tmp_path / "m.onnx", producer_name="mytool", producer_version="1.0"
    )
    lines = package["comment"].split("\n")
    assert "Model file written by: mytool 1.0" in lines
    # cited, as the field it is: not the framework, nor the producer
    assert "writing_tool: Source: m.onnx | Field: producer_name" in package["comment"]
    assert "originatedBy" not in package


def test_an_onnx_file_naming_no_producer_has_no_line(tmp_path: Path) -> None:
    package = _onnx_package(tmp_path / "m.onnx", producer_name="")
    assert "written by" not in package.get("comment", "")
