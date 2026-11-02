# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""GGUF text fields: invalid UTF-8 reads as a lone surrogate (one warning, no
failure; read as a scan does, which escapes it), a blank value reads as
absent, and the hyperparameter keys.

See also: :mod:`tests.extract.ai_model.test_stated_text` (the shared rule)
and :mod:`tests.extract.ai_model.test_gguf_scalar_text`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import struct
from pathlib import Path

import pytest

from pitloom.extract.ai_model import read_ai_model
from pitloom.extract.scanner import read_model_candidate
from pitloom.extract.scanner_project import local_model_candidate
from tests.extract.ai_model.gguf_builders import (
    FLOAT32,
    STRING,
    UINT32,
    gguf_file,
    kv,
    string,
)

pytest.importorskip("gguf")


def _raw_string(data: bytes) -> bytes:
    """A GGUF string value holding *data* as it is, valid UTF-8 or not."""
    return struct.pack("<Q", len(data)) + data


@pytest.mark.parametrize(
    ("key", "attr", "data", "expected"),
    [
        ("general.name", "name", b"A\xffB", "A\\udcffB"),
        ("general.description", "description", b"\xc3(", "\\udcc3("),
        ("general.architecture", "architecture", b"l\xe2\x82a", "l\\udce2\\udc82a"),
        ("general.version", "version", b"1.\xff", "1.\\udcff"),
    ],
    ids=["name", "description-truncated-sequence", "architecture", "version"],
)
def test_invalid_utf8_is_a_lone_surrogate_with_one_warning(
    key: str,
    attr: str,
    data: bytes,
    expected: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 1, kv(key.encode(), STRING, _raw_string(data))))
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        meta = read_model_candidate(local_model_candidate(path))
    assert getattr(meta, attr) == expected
    messages = [r.getMessage() for r in caplog.records]
    (said,) = [m for m in messages if "lone surrogates" in m]
    assert said.startswith("FORMAT=gguf FILE=")
    assert said.endswith("lone surrogates written as \\uXXXX")
    assert not [m for m in messages if "failed to extract" in m]


def test_valid_utf8_string_raises_no_surrogate_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "m.gguf"
    body = kv(b"general.name", STRING, string("café モデル"))
    path.write_bytes(gguf_file(0, 1, body))
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        meta = read_model_candidate(local_model_candidate(path))
    assert meta.name == "café モデル"
    assert not caplog.records


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"], ids=["empty", "spaces", "ws"])
@pytest.mark.parametrize(
    ("key", "attr"),
    [
        ("general.name", "name"),
        ("general.description", "description"),
        ("general.architecture", "architecture"),
        ("general.version", "version"),
    ],
)
def test_blank_core_field_reads_as_absent(
    key: str, attr: str, blank: str, tmp_path: Path
) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 1, kv(key.encode(), STRING, string(blank))))
    meta = read_ai_model(path)
    assert meta.properties[key] == blank  # the file's value stays a property
    if attr == "name":  # the shown name falls back to the file name
        assert meta.name != blank
    else:
        assert getattr(meta, attr) is None
    assert attr not in meta.provenance


def test_padded_core_field_is_stripped_with_provenance(tmp_path: Path) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 1, kv(b"general.name", STRING, string("  M  "))))
    meta = read_ai_model(path)
    assert meta.name == "M"
    assert meta.provenance["name"].endswith("Field: general.name")


@pytest.mark.parametrize(
    ("key", "vtype", "value"),
    [
        ("llama.attention.layer_norm_epsilon", FLOAT32, struct.pack("<f", 0.5)),
        ("llama.expert_count", UINT32, struct.pack("<I", 8)),
        ("llama.expert_used_count", UINT32, struct.pack("<I", 2)),
        ("llama.rope.scaling.type", STRING, string("yarn")),
        ("llama.rope.scaling.factor", FLOAT32, struct.pack("<f", 4.0)),
        (
            "llama.rope.scaling.original_context_length",
            UINT32,
            struct.pack("<I", 4096),
        ),
    ],
    ids=["epsilon", "experts", "experts-used", "rope-type", "rope-factor", "rope-ctx"],
)
def test_hyperparameter_keys_of_the_gguf_spec(
    key: str, vtype: int, value: bytes, tmp_path: Path
) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 1, kv(key.encode(), vtype, value)))
    meta = read_ai_model(path)
    assert list(meta.hyperparameters) == [key]
    assert key not in meta.properties
    assert meta.provenance["hyperparameters." + key].endswith(f"Field: {key}")
