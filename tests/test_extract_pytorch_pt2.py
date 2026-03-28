# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the PyTorch PT2 Archive metadata extractor (.pt2).

Covers mocked and integration tests.
"""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import io as _io
import json as _json
import zipfile as _zipfile
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import read_pytorch_pt2

# ---------------------------------------------------------------------------
# PT2 Archive extractor (mocked / stdlib ZIP)
# ---------------------------------------------------------------------------

_PT2_DIR = Path(__file__).parent / "fixtures" / "pytorch"


def _make_pt2_zip(
    files: dict[str, bytes] | None = None,
) -> bytes:
    """Build a minimal in-memory ZIP archive for PT2 Archive testing."""
    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        for name, data in (files or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_read_pytorch_pt2_format(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"version": b"2\n"}))
    meta = read_pytorch_pt2(model_file)
    assert meta.format == AiModelFormat.PYTORCH_PT2


def test_read_pytorch_pt2_version_file(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"version": b"2\n"}))
    meta = read_pytorch_pt2(model_file)
    assert meta.version == "2"
    assert "version" in meta.provenance


def test_read_pytorch_pt2_archive_contents_in_properties(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"version": b"2", "model.pte": b"\x00" * 8}))
    meta = read_pytorch_pt2(model_file)
    assert "archive_contents" in meta.properties
    assert "version" in meta.properties["archive_contents"]


def test_read_pytorch_pt2_metadata_json_name(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    metadata = _json.dumps({"name": "my_pt2_model"}).encode()
    model_file.write_bytes(_make_pt2_zip({"version": b"2", "METADATA.json": metadata}))
    meta = read_pytorch_pt2(model_file)
    assert meta.name == "my_pt2_model"
    assert "name" in meta.provenance


def test_read_pytorch_pt2_metadata_json_model_name_fallback(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    metadata = _json.dumps({"model_name": "fallback_name"}).encode()
    model_file.write_bytes(_make_pt2_zip({"version": b"2", "METADATA.json": metadata}))
    meta = read_pytorch_pt2(model_file)
    assert meta.name == "fallback_name"


def test_read_pytorch_pt2_no_metadata_json_name_is_none(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"version": b"2"}))
    meta = read_pytorch_pt2(model_file)
    assert meta.name is None


def test_read_pytorch_pt2_no_version_file(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"model.pte": b"\x00" * 4}))
    meta = read_pytorch_pt2(model_file)
    assert meta.version is None


def test_read_pytorch_pt2_not_a_zip_raises(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(b"not a zip file")
    with pytest.raises(ValueError, match="PT2 Archive must be a ZIP"):
        read_pytorch_pt2(model_file)


def test_read_pytorch_pt2_no_type_of_model(tmp_path: Path) -> None:
    # PT2 Archive does not inspect pickle; type_of_model is always None.
    model_file = tmp_path / "model.pt2"
    model_file.write_bytes(_make_pt2_zip({"version": b"2"}))
    meta = read_pytorch_pt2(model_file)
    assert meta.type_of_model is None


# ---------------------------------------------------------------------------
# Integration tests — PT2 Archive fixtures (pytorch/*.pt2)
# Require: fixture files present
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pt2_fixture() -> Any:
    pt2_files = list(_PT2_DIR.glob("*.pt2"))
    if not pt2_files:
        pytest.skip("No .pt2 fixture files found in tests/fixtures/pytorch/")
    return read_pytorch_pt2(pt2_files[0])


def test_pt2_fixture_format(pt2_fixture: Any) -> None:
    assert pt2_fixture.format == AiModelFormat.PYTORCH_PT2
