# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The model licence of a Safetensors file: ``modelspec.license`` of its
``__metadata__`` (ModelSpec, as stable-diffusion-xl-base-1.0 and
stable-cascade write it: a licence name, not an SPDX expression).

See also: :mod:`tests.extract.ai_model.test_safetensors`.
"""

from __future__ import annotations

import json
import logging
import struct
from pathlib import Path

import pytest

from pitloom.extract.ai_model.safetensors import read_safetensors


def _file(path: Path, metadata: dict[str, object] | None) -> Path:
    """A valid Safetensors file of one tensor with *metadata*."""
    table: dict[str, object] = (
        {"__metadata__": metadata} if metadata is not None else {}
    )
    table["t"] = {"dtype": "U8", "shape": [1], "data_offsets": [0, 1]}
    header = json.dumps(table).encode()
    path.write_bytes(struct.pack("<Q", len(header)) + header + b"\0")
    return path


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CreativeML Open RAIL++-M License", "CreativeML Open RAIL++-M License"),
        ("  Apache-2.0\n", "Apache-2.0"),
        ("MIT OR Apache-2.0", "MIT OR Apache-2.0"),
    ],
    ids=["name", "trimmed", "expression"],
)
def test_modelspec_license_is_the_model_licence(
    tmp_path: Path, value: str, expected: str
) -> None:
    meta = read_safetensors(
        _file(tmp_path / "m.safetensors", {"modelspec.license": value})
    )

    assert meta.license == expected
    assert meta.provenance["license"].endswith("Field: __metadata__.modelspec.license")
    # the key stays a property and in the verbatim metadata either way
    assert meta.properties["modelspec.license"] == value


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {"format": "pt"},
        {"modelspec.license": ""},
        {"modelspec.license": "   "},
        {"license": "MIT"},
    ],
    ids=["no-metadata", "no-key", "empty", "blank", "other-key-not-mapped"],
)
def test_an_absent_or_blank_licence_stays_absent_and_quiet(
    tmp_path: Path, metadata: dict[str, object] | None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        meta = read_safetensors(_file(tmp_path / "m.safetensors", metadata))

    assert meta.license is None
    assert "license" not in meta.provenance
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_a_licence_name_is_text_without_the_spdx_only_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The key holds free text, so a name that is no SPDX expression is not a
    broken expression (GGUF ``general.license`` is expression-only)."""
    path = _file(tmp_path / "m.safetensors", {"modelspec.license": "Some Terms v2"})

    with caplog.at_level(logging.WARNING):
        meta = read_safetensors(path)

    assert meta.license == "Some Terms v2"
    assert not caplog.records
