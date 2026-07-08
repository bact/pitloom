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
import logging
import zipfile as _zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract._pytorch import _fickling_get_top_class, _read_pytorch_zip
from pitloom.extract.ai_model import read_pytorch

# ---------------------------------------------------------------------------
# Classic PyTorch extractor (mocked / stdlib ZIP)
# ---------------------------------------------------------------------------

_PYTORCH_DIR = Path(__file__).parent / "fixtures" / "aimodels" / "pytorch"


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
    assert meta.format_info.model_format == AiModelFormat.PYTORCH


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
    assert meta.format_info.model_format == AiModelFormat.PYTORCH


def test_read_pytorch_raw_pickle_format_detail(tmp_path: Path) -> None:
    # A file that is NOT a ZIP is treated as raw pickle.
    model_file = tmp_path / "model.pt"
    model_file.write_bytes(b"\x80\x02}q\x00.")  # minimal raw pickle (empty dict)
    with patch.dict("sys.modules", {"fickling": None, "fickling.pickle": None}):
        meta = read_pytorch(model_file)
    assert meta.format_info.model_format == AiModelFormat.PYTORCH
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
# Malformed input -- exceptions are caught, logged at debug level, and
# degrade gracefully (behaviour unchanged; only visibility was added).
# ---------------------------------------------------------------------------


def test_fickling_get_top_class_malformed_pickle_logs_and_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pytest.importorskip("fickling")

    # b"\x80\x99" starts a pickle stream (protocol opcode) but is truncated
    # before a STOP opcode, so fickling's AST parser raises.
    with caplog.at_level(logging.DEBUG, logger="pitloom.extract._pytorch"):
        result = _fickling_get_top_class(b"\x80\x99")

    assert result is None
    assert any(
        "fickling failed to parse pickle bytes" in r.message for r in caplog.records
    )


def test_read_pytorch_zip_inspect_failure_logs_and_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A ZIP entry that exists in the file list but fails to read (e.g. a
    corrupt/encrypted archive member) is caught, logged, and the function
    still returns its normal (type_of_model=None) result rather than
    raising."""
    mock_zf = MagicMock()
    mock_zf.namelist.return_value = ["archive/data.pkl"]
    mock_zf.read.side_effect = RuntimeError("bad CRC-32")

    with caplog.at_level(logging.DEBUG, logger="pitloom.extract._pytorch"):
        type_of_model, properties, provenance = _read_pytorch_zip(
            mock_zf, "Source: model.pt"
        )

    assert type_of_model is None
    assert "type_of_model" not in provenance
    assert "archive_contents" in properties
    assert any("archive/data.pkl" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Integration tests -- classic PyTorch fixtures (pytorch/*.pt, *.pth)
# Require: fixture files present (fickling optional for class name extraction)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pytorch_fixture() -> Any:
    pt_files = list(_PYTORCH_DIR.glob("*.pt")) + list(_PYTORCH_DIR.glob("*.pth"))
    if not pt_files:
        pytest.skip("No .pt/.pth fixture files found in tests/fixtures/pytorch/")
    return read_pytorch(pt_files[0])


def test_pytorch_fixture_format(pytorch_fixture: Any) -> None:
    assert pytorch_fixture.format_info.model_format == AiModelFormat.PYTORCH
