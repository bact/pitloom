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

# Magic prefix b'\x93NUMPY' (6 bytes) + major (1 byte) + minor (1 byte).
_NPY_MAGIC = b"\x93NUMPY"


def _make_npy_bytes(major: int = 1, minor: int = 0) -> bytes:
    """Minimal .npy file bytes with correct magic and version header."""
    return _NPY_MAGIC + bytes([major, minor]) + b"\x00" * 20


def test_read_numpy_missing_library(tmp_path: Path) -> None:
    model_file = tmp_path / "array.npy"
    model_file.write_bytes(_make_npy_bytes())
    with patch.dict("sys.modules", {"numpy": None}):
        with pytest.raises(ImportError, match="numpy"):
            read_numpy(model_file)


def test_read_numpy_npy_format(tmp_path: Path) -> None:
    model_file = tmp_path / "array.npy"
    model_file.write_bytes(_make_npy_bytes())
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
    model_file.write_bytes(_make_npy_bytes())
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
    model_file.write_bytes(_make_npy_bytes())
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
    model_file.write_bytes(_make_npy_bytes())
    mock_arr = MagicMock()
    mock_arr.shape = (10,)
    mock_arr.dtype = MagicMock(__str__=lambda _: "float32")
    mock_np = MagicMock()
    mock_np.load.return_value = mock_arr
    with patch.dict("sys.modules", {"numpy": mock_np}):
        meta = read_numpy(model_file)
    assert meta.type_of_model == "numpy array"


# ---------------------------------------------------------------------------
# NPY format version detection
# ---------------------------------------------------------------------------


def test_read_numpy_npy_v1_version(tmp_path: Path) -> None:
    model_file = tmp_path / "array.npy"
    model_file.write_bytes(_make_npy_bytes(major=1, minor=0))
    mock_arr = MagicMock()
    mock_arr.shape = (10,)
    mock_arr.dtype = MagicMock(__str__=lambda _: "float32")
    mock_np = MagicMock()
    mock_np.load.return_value = mock_arr
    with patch.dict("sys.modules", {"numpy": mock_np}):
        meta = read_numpy(model_file)
    assert meta.format_version == "1.0"
    assert meta.properties["header_encoding"] == "latin1"
    assert "npy_format_version" not in meta.properties


def test_read_numpy_npy_v2_version(tmp_path: Path) -> None:
    model_file = tmp_path / "array.npy"
    model_file.write_bytes(_make_npy_bytes(major=2, minor=0))
    mock_arr = MagicMock()
    mock_arr.shape = (10,)
    mock_arr.dtype = MagicMock(__str__=lambda _: "float32")
    mock_np = MagicMock()
    mock_np.load.return_value = mock_arr
    with patch.dict("sys.modules", {"numpy": mock_np}):
        meta = read_numpy(model_file)
    assert meta.format_version == "2.0"
    assert meta.properties["header_encoding"] == "latin1"
    assert "npy_format_version" not in meta.properties


def test_read_numpy_npy_v3_version(tmp_path: Path) -> None:
    model_file = tmp_path / "array.npy"
    model_file.write_bytes(_make_npy_bytes(major=3, minor=0))
    mock_arr = MagicMock()
    mock_arr.shape = (10,)
    mock_arr.dtype = MagicMock(__str__=lambda _: "float32")
    mock_np = MagicMock()
    mock_np.load.return_value = mock_arr
    with patch.dict("sys.modules", {"numpy": mock_np}):
        meta = read_numpy(model_file)
    assert meta.format_version == "3.0"
    assert meta.properties["header_encoding"] == "utf-8"
    assert "npy_format_version" not in meta.properties


def test_read_numpy_npy_framework(tmp_path: Path) -> None:
    model_file = tmp_path / "array.npy"
    model_file.write_bytes(_make_npy_bytes())
    mock_arr = MagicMock()
    mock_arr.shape = (10,)
    mock_arr.dtype = MagicMock(__str__=lambda _: "float32")
    mock_np = MagicMock()
    mock_np.load.return_value = mock_arr
    with patch.dict("sys.modules", {"numpy": mock_np}):
        meta = read_numpy(model_file)
    assert meta.framework == "numpy"


def test_read_numpy_npy_version_in_provenance(tmp_path: Path) -> None:
    model_file = tmp_path / "array.npy"
    model_file.write_bytes(_make_npy_bytes())
    mock_arr = MagicMock()
    mock_arr.shape = (10,)
    mock_arr.dtype = MagicMock(__str__=lambda _: "float32")
    mock_np = MagicMock()
    mock_np.load.return_value = mock_arr
    with patch.dict("sys.modules", {"numpy": mock_np}):
        meta = read_numpy(model_file)
    assert "format_version" in meta.provenance


def test_read_numpy_npy_invalid_magic(tmp_path: Path) -> None:
    model_file = tmp_path / "array.npy"
    model_file.write_bytes(b"not a numpy file at all")
    mock_np = MagicMock()
    with patch.dict("sys.modules", {"numpy": mock_np}):
        with pytest.raises(ValueError, match="Failed to read NumPy"):
            read_numpy(model_file)


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


def test_read_numpy_npz_no_format_version(tmp_path: Path) -> None:
    # .npz archives do not expose a per-file NPY format version.
    model_file = tmp_path / "arrays.npz"
    model_file.write_bytes(b"fake")

    mock_npz = MagicMock()
    mock_npz.__enter__ = MagicMock(return_value=mock_npz)
    mock_npz.__exit__ = MagicMock(return_value=False)
    mock_npz.files = []

    mock_np = MagicMock()
    mock_np.load.return_value = mock_npz
    with patch.dict("sys.modules", {"numpy": mock_np}):
        meta = read_numpy(model_file)
    assert meta.format_version is None


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


def _load_fixture(filename: str) -> Any:
    """Skip if numpy is not installed or the fixture file is absent."""
    pytest.importorskip("numpy")
    path = _NPY_DIR / filename
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    return read_numpy(path)


@pytest.fixture(scope="module")
def fixture_v1() -> Any:
    return _load_fixture("example-model-v1.npy")


@pytest.fixture(scope="module")
def fixture_v2() -> Any:
    return _load_fixture("example-model-v2.npy")


@pytest.fixture(scope="module")
def fixture_v3() -> Any:
    return _load_fixture("example-model-v3.npy")


@pytest.fixture(scope="module")
def fixture_bundle() -> Any:
    return _load_fixture("example-model-bundle.npz")


# --- example-model-v1.npy ---


def test_numpy_v1_format(fixture_v1: Any) -> None:
    assert fixture_v1.format == AiModelFormat.NUMPY


def test_numpy_v1_format_version(fixture_v1: Any) -> None:
    assert fixture_v1.format_version == "1.0"


def test_numpy_v1_encoding(fixture_v1: Any) -> None:
    assert fixture_v1.properties["header_encoding"] == "latin1"


def test_numpy_v1_shape(fixture_v1: Any) -> None:
    assert fixture_v1.inputs[0]["shape"] == [2, 2]


def test_numpy_v1_dtype(fixture_v1: Any) -> None:
    assert fixture_v1.inputs[0]["dtype"] == "float32"


# --- example-model-v2.npy ---


def test_numpy_v2_format(fixture_v2: Any) -> None:
    assert fixture_v2.format == AiModelFormat.NUMPY


def test_numpy_v2_format_version(fixture_v2: Any) -> None:
    assert fixture_v2.format_version == "2.0"


def test_numpy_v2_encoding(fixture_v2: Any) -> None:
    assert fixture_v2.properties["header_encoding"] == "latin1"


def test_numpy_v2_shape(fixture_v2: Any) -> None:
    assert fixture_v2.inputs[0]["shape"] == [2, 2]


def test_numpy_v2_dtype(fixture_v2: Any) -> None:
    assert fixture_v2.inputs[0]["dtype"] == "float32"


# --- example-model-v3.npy (structured dtype with Unicode field name) ---


def test_numpy_v3_format(fixture_v3: Any) -> None:
    assert fixture_v3.format == AiModelFormat.NUMPY


def test_numpy_v3_format_version(fixture_v3: Any) -> None:
    assert fixture_v3.format_version == "3.0"


def test_numpy_v3_encoding(fixture_v3: Any) -> None:
    assert fixture_v3.properties["header_encoding"] == "utf-8"


def test_numpy_v3_shape(fixture_v3: Any) -> None:
    assert fixture_v3.inputs[0]["shape"] == [2]


def test_numpy_v3_dtype_contains_unicode_field(fixture_v3: Any) -> None:
    assert "π_weights" in fixture_v3.inputs[0]["dtype"]


# --- example-model-bundle.npz ---


def test_numpy_bundle_format(fixture_bundle: Any) -> None:
    assert fixture_bundle.format == AiModelFormat.NUMPY


def test_numpy_bundle_array_count(fixture_bundle: Any) -> None:
    assert len(fixture_bundle.inputs) == 1


def test_numpy_bundle_weights_name(fixture_bundle: Any) -> None:
    assert fixture_bundle.inputs[0]["name"] == "weights"


def test_numpy_bundle_weights_shape(fixture_bundle: Any) -> None:
    assert fixture_bundle.inputs[0]["shape"] == [2, 2]


def test_numpy_bundle_weights_dtype(fixture_bundle: Any) -> None:
    assert fixture_bundle.inputs[0]["dtype"] == "float32"


def test_numpy_bundle_no_format_version(fixture_bundle: Any) -> None:
    # .npz archives don't have a per-file NPY format version.
    assert fixture_bundle.format_version is None
