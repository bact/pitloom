# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the NumPy metadata extractor (mocked and integration)."""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import read_numpy

# ---------------------------------------------------------------------------
# NumPy extractor (mocked)
# ---------------------------------------------------------------------------

_NPY_DIR = Path(__file__).parent / "fixtures" / "numpy"


def test_read_numpy_missing_library(tmp_path: Path) -> None:
    model_file = tmp_path / "array.npy"
    model_file.write_bytes(b"fake")
    with patch.dict("sys.modules", {"numpy": None}):
        with pytest.raises(ImportError, match="numpy"):
            read_numpy(model_file)


def test_read_numpy_npy_format(tmp_path: Path) -> None:
    model_file = tmp_path / "array.npy"
    model_file.write_bytes(b"fake")
    mock_arr = MagicMock()
    mock_arr.shape = (100, 50)
    mock_arr.dtype = MagicMock(__str__=lambda _: "float32")
    mock_np = MagicMock()
    mock_np.load.return_value = mock_arr
    with patch.dict("sys.modules", {"numpy": mock_np}):
        meta = read_numpy(model_file)
    assert meta.format == AiModelFormat.NUMPY


def test_read_numpy_npy_shape_and_dtype(tmp_path: Path) -> None:
    model_file = tmp_path / "array.npy"
    model_file.write_bytes(b"fake")
    mock_arr = MagicMock()
    mock_arr.shape = (3, 4, 5)
    mock_arr.dtype = MagicMock(__str__=lambda _: "float64")
    mock_np = MagicMock()
    mock_np.load.return_value = mock_arr
    with patch.dict("sys.modules", {"numpy": mock_np}):
        meta = read_numpy(model_file)
    assert len(meta.inputs) == 1
    assert meta.inputs[0]["shape"] == [3, 4, 5]
    assert meta.inputs[0]["dtype"] == "float64"


def test_read_numpy_npy_no_name_description_version(tmp_path: Path) -> None:
    model_file = tmp_path / "array.npy"
    model_file.write_bytes(b"fake")
    mock_arr = MagicMock()
    mock_arr.shape = (10,)
    mock_arr.dtype = MagicMock(__str__=lambda _: "int32")
    mock_np = MagicMock()
    mock_np.load.return_value = mock_arr
    with patch.dict("sys.modules", {"numpy": mock_np}):
        meta = read_numpy(model_file)
    assert meta.name is None
    assert meta.description is None
    assert meta.version is None


def test_read_numpy_npy_type_of_model(tmp_path: Path) -> None:
    model_file = tmp_path / "array.npy"
    model_file.write_bytes(b"fake")
    mock_arr = MagicMock()
    mock_arr.shape = (10,)
    mock_arr.dtype = MagicMock(__str__=lambda _: "float32")
    mock_np = MagicMock()
    mock_np.load.return_value = mock_arr
    with patch.dict("sys.modules", {"numpy": mock_np}):
        meta = read_numpy(model_file)
    assert meta.type_of_model == "numpy array"


def test_read_numpy_npz_multiple_arrays(tmp_path: Path) -> None:
    model_file = tmp_path / "arrays.npz"
    model_file.write_bytes(b"fake")

    mock_arr_a = MagicMock()
    mock_arr_a.shape = (10, 5)
    mock_arr_a.dtype = MagicMock(__str__=lambda _: "float32")
    mock_arr_b = MagicMock()
    mock_arr_b.shape = (5,)
    mock_arr_b.dtype = MagicMock(__str__=lambda _: "float32")

    mock_npz = MagicMock()
    mock_npz.__enter__ = MagicMock(return_value=mock_npz)
    mock_npz.__exit__ = MagicMock(return_value=False)
    mock_npz.files = ["weights", "biases"]
    mock_npz.__getitem__ = lambda self, key: (
        mock_arr_a if key == "weights" else mock_arr_b
    )

    mock_np = MagicMock()
    mock_np.load.return_value = mock_npz
    with patch.dict("sys.modules", {"numpy": mock_np}):
        meta = read_numpy(model_file)

    assert meta.format == AiModelFormat.NUMPY
    assert len(meta.inputs) == 2
    names = [inp["name"] for inp in meta.inputs]
    assert "weights" in names
    assert "biases" in names


def test_read_numpy_invalid_file(tmp_path: Path) -> None:
    model_file = tmp_path / "bad.npy"
    model_file.write_bytes(b"not numpy")
    mock_np = MagicMock()
    mock_np.load.side_effect = ValueError("Invalid npy header")
    with patch.dict("sys.modules", {"numpy": mock_np}):
        with pytest.raises(ValueError, match="Failed to read NumPy"):
            read_numpy(model_file)


# ---------------------------------------------------------------------------
# Integration tests — NumPy fixtures (numpy/*.npy, *.npz)
# Require: numpy installed AND fixture files present
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def numpy_npy_fixture() -> Any:
    pytest.importorskip("numpy")
    npy_files = list(_NPY_DIR.glob("*.npy"))
    if not npy_files:
        pytest.skip("No .npy fixture files found in tests/fixtures/numpy/")
    return read_numpy(npy_files[0])


def test_numpy_npy_fixture_format(numpy_npy_fixture: Any) -> None:
    assert numpy_npy_fixture.format == AiModelFormat.NUMPY


def test_numpy_npy_fixture_has_inputs(numpy_npy_fixture: Any) -> None:
    assert len(numpy_npy_fixture.inputs) >= 1
    assert "shape" in numpy_npy_fixture.inputs[0]
    assert "dtype" in numpy_npy_fixture.inputs[0]
