# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard: Pitloom's GGUF header reader and the ``gguf`` package's
``GGUFReader`` agree on every fixture and builder shape: the fields as
recorded, the array summaries, the tensor shapes and the ``general.datasets``
strings.

The oracle below is how :mod:`pitloom.extract.ai_model.gguf` read a file
through ``GGUFReader`` before its own reader replaced it.

See also: :mod:`pitloom.extract.ai_model.formats.gguf_header`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import pytest

from pitloom.extract.ai_model._gguf_bounds import load_gguf_header
from pitloom.extract.ai_model._gguf_fields import listed_strings, read_fields
from tests.extract.ai_model.gguf_builders import (
    ARRAY,
    BOOL,
    FLOAT32,
    FLOAT64,
    STRING,
    UINT8,
    UINT32,
    UINT64,
    array,
    gguf_file,
    gguf_with_tensors,
    kv,
    string,
    tensor_info,
)

pytestmark = pytest.mark.platform  # files, a memory map

_GGUF_FIXTURES = Path(__file__).parents[2] / "fixtures" / "aimodels" / "gguf"
_DATASETS = "general.datasets"


def _oracle(path: Path) -> tuple[dict[str, Any], dict[str, Any], list[Any], Any]:
    gguf = pytest.importorskip("gguf")
    numpy = pytest.importorskip("numpy")
    reader = gguf.GGUFReader(str(path), mode="r")
    fields: dict[str, Any] = {}
    raw: dict[str, Any] = {}
    for key, field in reader.fields.items():
        kind = field.types[0].name if field.types else ""
        last = field.parts[-1]
        if kind == "ARRAY":
            summary: dict[str, Any] = {"length": int(field.parts[4][0])}
            try:
                summary["type"] = gguf.GGUFValueType(int(field.parts[3][0])).name
            except ValueError:
                pass
            raw[key] = summary
            fields[key + ".length"] = summary["length"]
            continue
        if kind == "STRING":
            value: Any = last.tobytes().decode("utf-8", errors="surrogateescape")
        elif kind == "FLOAT32":
            value = float(numpy.format_float_scientific(last[0], unique=True))
        else:
            value = last.tolist()[0]
        fields[key] = raw[key] = value
    listed = reader.fields.get(_DATASETS)
    strings = None
    if listed is not None and [t.name for t in listed.types] == ["ARRAY", "STRING"]:
        strings = tuple(
            listed.parts[i].tobytes().decode("utf-8", errors="surrogateescape")
            for i in listed.data
        )
    shapes = [t.shape.tolist() for t in reader.tensors]
    return fields, raw, shapes, strings


def _ours(path: Path) -> tuple[dict[str, Any], dict[str, Any], list[Any], Any]:
    header = load_gguf_header(path, {_DATASETS: 2**63})
    read = read_fields(header)
    assert header.tensors is not None
    shapes = [list(t.shape) for t in header.tensors]
    return read.fields, read.raw_metadata, shapes, listed_strings(header, _DATASETS)


_E = ">"
_SHAPES = {
    "scalars": gguf_file(
        0,
        6,
        kv(b"u8", UINT8, b"\xff")
        + kv(b"b", BOOL, b"\x02")
        + kv(b"u32", UINT32, struct.pack("<I", 2**31))
        + kv(b"u64", UINT64, struct.pack("<Q", 2**63))
        + kv(b"f32", FLOAT32, struct.pack("<f", 1e-6))
        + kv(b"f64", FLOAT64, struct.pack("<d", 0.1)),
    ),
    "strings": gguf_file(
        0,
        2,
        kv(b"s", STRING, string("café ☃"))
        + kv(b"raw", STRING, struct.pack("<Q", 2) + b"\xff\xfe"),
    ),
    "arrays": gguf_file(
        0,
        4,
        array(UINT32, 0, key=b"empty")
        + array(99, 0, key=b"empty-unknown")
        + array(FLOAT32, 2, struct.pack("<ff", 1.5, 2.5), key=b"f")
        + kv(
            b"nested",
            ARRAY,
            struct.pack("<IQ", ARRAY, 2)
            + struct.pack("<IQ", UINT8, 1)
            + b"\x01"
            + struct.pack("<IQ", STRING, 1)
            + string("x"),
        ),
    ),
    "datasets": gguf_file(
        0,
        1,
        array(
            STRING,
            3,
            string("a/b") + string(" c ") + struct.pack("<Q", 1) + b"\xff",
            key=_DATASETS.encode(),
        ),
    ),
    "datasets-not-strings": gguf_file(
        0, 1, array(UINT8, 1, b"\0", key=_DATASETS.encode())
    ),
    "big-endian": gguf_file(
        0,
        3,
        kv(b"n", UINT32, struct.pack(_E + "I", 7), _E)
        + kv(b"f", FLOAT32, struct.pack(_E + "f", 0.1), _E)
        + array(STRING, 1, struct.pack(_E + "Q", 1) + b"z", _E, key=b"a"),
        endian=_E,
    ),
    "tensors": gguf_with_tensors(
        [tensor_info("a", (2, 3)), tensor_info("q", (32, 2), ggml_type=2)],
        1,
        kv(b"general.alignment", UINT32, struct.pack("<I", 64)),
        data_bytes=24 + 36 + 64,
    ),
}


@pytest.mark.parametrize(
    "path",
    [*sorted(_GGUF_FIXTURES.glob("*.gguf")), *_SHAPES],
    ids=lambda p: p.name if isinstance(p, Path) else p,
)
def test_the_reader_agrees_with_the_gguf_package(
    path: Path | str, tmp_path: Path
) -> None:
    if isinstance(path, str):
        data = _SHAPES[path]
        path = tmp_path / "m.gguf"
        path.write_bytes(data)
    assert _ours(path) == _oracle(path)
