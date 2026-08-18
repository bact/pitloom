# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for GGUF metadata extraction edge cases and helper routines.

See also:
- :mod:`tests.extract.test_gguf` for main GGUF extraction and parser tests.
"""

from __future__ import annotations

import collections
from pathlib import Path
from unittest.mock import MagicMock

from pitloom.extract._gguf import (
    _categorize_gguf_fields,
    _field_value,
    _read_gguf_format_version,
    _resolve_quantization,
)


def test_resolve_quantization_edge_cases() -> None:
    """_resolve_quantization handles None, non-integers, and unknown enum values."""
    assert _resolve_quantization(None) is None
    assert _resolve_quantization("invalid_number") is None

    # Test unknown quantization integer falling back to string representation
    result = _resolve_quantization(999999)
    assert result == "999999"


def test_read_gguf_format_version_oserror() -> None:
    """_read_gguf_format_version handles OSError during open."""
    nonexistent = Path("/tmp/nonexistent_gguf_header_12345.gguf")
    version, prov = _read_gguf_format_version(nonexistent, "Source: test")
    assert version is None
    assert prov == ""


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
    hyperparams, properties = _categorize_gguf_fields(fields, "Source: test", prov)

    assert "llama.context_length" in hyperparams
    assert "general.author" in properties
    assert "general.empty_key" not in properties
    assert "general.empty_key" not in hyperparams
