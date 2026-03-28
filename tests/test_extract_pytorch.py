# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the classic PyTorch metadata extractor (.pt, .pth).

Covers mocked and integration tests.
"""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import io as _io
import zipfile as _zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import read_pytorch

# ---------------------------------------------------------------------------
# Classic PyTorch extractor (mocked / stdlib ZIP)
# ---------------------------------------------------------------------------

_PYTORCH_DIR = Path(__file__).parent / "fixtures" / "pytorch"


def _make_pytorch_zip(
    files: dict[str, bytes] | None = None,
) -> bytes:
    """Build a minimal in-memory ZIP archive for PyTorch model testing."""
    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        for name, data in (files or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_read_pytorch_format(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt"
    model_file.write_bytes(
        _make_pytorch_zip({"archive/data.pkl": b"\x80\x04\x95\x00\x00\x00\x00."})
    )
    with patch.dict("sys.modules", {"fickling": None, "fickling.pickle": None}):
        meta = read_pytorch(model_file)
    assert meta.format == AiModelFormat.PYTORCH


def test_read_pytorch_archive_contents_in_properties(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt"
    model_file.write_bytes(
        _make_pytorch_zip(
            {
                "archive/data.pkl": b"\x80\x02.",
                "archive/version": b"1",
            }
        )
    )
    with patch.dict("sys.modules", {"fickling": None, "fickling.pickle": None}):
        meta = read_pytorch(model_file)
    assert "archive_contents" in meta.properties
    assert "archive/data.pkl" in meta.properties["archive_contents"]


def test_read_pytorch_pth_format(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pth"
    model_file.write_bytes(_make_pytorch_zip({"archive/data.pkl": b"\x80\x02."}))
    with patch.dict("sys.modules", {"fickling": None, "fickling.pickle": None}):
        meta = read_pytorch(model_file)
    assert meta.format == AiModelFormat.PYTORCH


def test_read_pytorch_raw_pickle_format_detail(tmp_path: Path) -> None:
    # A file that is NOT a ZIP is treated as raw pickle.
    model_file = tmp_path / "model.pt"
    model_file.write_bytes(b"\x80\x02}q\x00.")  # minimal raw pickle (empty dict)
    with patch.dict("sys.modules", {"fickling": None, "fickling.pickle": None}):
        meta = read_pytorch(model_file)
    assert meta.format == AiModelFormat.PYTORCH
    assert meta.properties.get("format_detail") == "raw pickle"


def test_read_pytorch_no_fickling_type_of_model_is_none(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt"
    model_file.write_bytes(_make_pytorch_zip({"archive/data.pkl": b"\x80\x02."}))
    with patch.dict("sys.modules", {"fickling": None, "fickling.pickle": None}):
        meta = read_pytorch(model_file)
    assert meta.type_of_model is None


def test_read_pytorch_no_name_version(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt"
    model_file.write_bytes(_make_pytorch_zip({"archive/data.pkl": b"\x80\x02."}))
    with patch.dict("sys.modules", {"fickling": None, "fickling.pickle": None}):
        meta = read_pytorch(model_file)
    assert meta.name is None
    assert meta.version is None


# ---------------------------------------------------------------------------
# Integration tests — classic PyTorch fixtures (pytorch/*.pt, *.pth)
# Require: fixture files present (fickling optional for class name extraction)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pytorch_fixture() -> Any:
    pt_files = list(_PYTORCH_DIR.glob("*.pt")) + list(_PYTORCH_DIR.glob("*.pth"))
    if not pt_files:
        pytest.skip("No .pt/.pth fixture files found in tests/fixtures/pytorch/")
    return read_pytorch(pt_files[0])


def test_pytorch_fixture_format(pytorch_fixture: Any) -> None:
    assert pytorch_fixture.format == AiModelFormat.PYTORCH
