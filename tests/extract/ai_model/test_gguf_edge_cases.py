# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for GGUF metadata extraction edge cases and helper routines.

See also:
- :mod:`tests.extract.ai_model.test_gguf` for main GGUF extraction and parser tests.
"""

from __future__ import annotations

import collections
import struct
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pitloom.extract.ai_model.gguf import (
    _categorize_gguf_fields,
    _field_value,
    _resolve_quantization,
    read_gguf,
)
from tests.extract.ai_model.gguf_builders import (
    BOOL,
    FLOAT32,
    STRING,
    UINT32,
    gguf_file,
    kv,
    string,
)


@pytest.mark.parametrize("value", [None, "invalid_number", "7", True, False, 7.0, 1024])
def test_resolve_quantization_needs_a_stated_integer(value: Any) -> None:
    """Only a non-bool integer names a quantization; 1024 is ``GUESSED``
    (llama.cpp's "not stated")."""
    assert _resolve_quantization(value) is None


def test_resolve_quantization_unknown_integer() -> None:
    """An integer the enum does not know falls back to its text."""
    result = _resolve_quantization(999999)
    assert result == "999999"


@pytest.mark.parametrize(
    ("file_type", "name"),
    [(0, "F32"), (1, "F16"), (7, "Q8_0"), (15, "Q4_K_M"), (4, "4")],
)
def test_file_type_is_a_llama_file_type(file_type: int, name: str) -> None:
    """Regression: 7 was read as ``GGMLQuantizationType`` (``Q5_1``); 4 is a
    retired ``LlamaFileType`` value, kept as its number."""
    pytest.importorskip("gguf")
    assert _resolve_quantization(file_type) == name


@pytest.mark.parametrize("endian", ["<", ">"], ids=["little", "big"])
def test_format_version_is_read_in_the_files_byte_order(
    tmp_path: Path, endian: str
) -> None:
    """Regression: a big-endian version 3 was read as ``<I``, 50331648."""
    pytest.importorskip("gguf")
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 0, endian=endian))
    meta = read_gguf(path)
    assert meta.format_info.format_version == "3"
    assert meta.provenance["format_version"] == "Source: m.gguf | Field: GGUF.version"


@pytest.mark.parametrize(
    ("key", "vtype", "value", "field"),
    [
        (b"general.file_type", BOOL, b"\x01", "quantization"),
        (b"general.file_type", STRING, string("7"), "quantization"),
        (b"general.file_type", FLOAT32, struct.pack("<f", 7.0), "quantization"),
        (b"general.file_type", UINT32, struct.pack("<I", 1024), "quantization"),
        (b"general.version", STRING, string(""), "version"),
        (b"general.version", STRING, string(" \t "), "version"),
        (b"general.version", BOOL, b"\x01", "version"),
        (b"general.license", UINT32, struct.pack("<I", 1), "license"),
        (b"general.license", BOOL, b"\x01", "license"),
        (b"general.license", STRING, string("  "), "license"),
    ],
    ids=[
        "file-type-bool",
        "file-type-string",
        "file-type-float",
        "file-type-guessed",
        "version-empty",
        "version-blank",
        "version-bool",
        "license-uint32",
        "license-bool",
        "license-blank",
    ],
)
def test_a_value_that_states_nothing_leaves_the_field_absent(
    tmp_path: Path, key: bytes, vtype: int, value: bytes, field: str
) -> None:
    """Silently absent, no provenance; the value stays in properties."""
    pytest.importorskip("gguf")
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 1, kv(key, vtype, value)))
    meta = read_gguf(path)
    assert getattr(meta, field) is None
    assert field not in meta.provenance
    assert key.decode() in meta.properties


@pytest.mark.parametrize(
    ("key", "vtype", "value", "field", "expected"),
    [
        (b"general.file_type", UINT32, struct.pack("<I", 7), "quantization", "Q8_0"),
        (b"general.version", STRING, string(" 1.2 "), "version", "1.2"),
        (b"general.version", UINT32, struct.pack("<I", 2), "version", "2"),
        (b"general.license", STRING, string(" MIT "), "license", "MIT"),
    ],
    ids=["file-type", "version-string", "version-number", "license"],
)
def test_a_stated_value_is_read(
    tmp_path: Path, key: bytes, vtype: int, value: bytes, field: str, expected: str
) -> None:
    pytest.importorskip("gguf")
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 1, kv(key, vtype, value)))
    meta = read_gguf(path)
    assert getattr(meta, field) == expected
    assert meta.provenance[field] == f"Source: m.gguf | Field: {key.decode()}"


def test_field_value_empty_parts_and_raw_objects() -> None:
    """_field_value handles empty parts and non-list / non-string parts."""
    # 1. Empty parts
    field_empty = MagicMock()
    field_empty.parts = []
    assert _field_value(field_empty) is None

    # 2. String parts with STRING type name
    type_tuple = collections.namedtuple("type_tuple", ["name"])
    type_obj = type_tuple("STRING")
    part_mock = MagicMock()
    part_mock.tobytes.return_value = b"hello world"
    field_str = MagicMock()
    field_str.parts = [part_mock]
    field_str.types = [type_obj]
    assert _field_value(field_str) == "hello world"

    # 3. Raw scalar object without tolist()
    field_scalar = MagicMock()
    field_scalar.parts = [42]
    field_scalar.types = []
    assert _field_value(field_scalar) == 42


def test_categorize_gguf_fields_skips_none_values() -> None:
    """_categorize_gguf_fields ignores fields where the value is None."""
    fields = {
        "llama.context_length": 4096,
        "general.author": "Someone",
        "general.empty_key": None,
    }
    prov: dict[str, str] = {}
    hyperparams, properties = _categorize_gguf_fields(fields, "Source: test", prov, {})

    assert "llama.context_length" in hyperparams
    assert "general.author" in properties
    assert "general.empty_key" not in properties
    assert "general.empty_key" not in hyperparams
