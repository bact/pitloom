# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the HDF5/Keras metadata extractor (mocked and integration)."""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import read_hdf5

# ---------------------------------------------------------------------------
# HDF5/Keras extractor (mocked)
# ---------------------------------------------------------------------------

_HDF5_DIR = Path(__file__).parent / "fixtures" / "hdf5"


def _make_hdf5_file(
    model_config: dict[str, Any] | None = None,
    training_config: dict[str, Any] | None = None,
    keras_version: str | None = "2.12.0",
    backend: str | None = "tensorflow",
) -> MagicMock:
    attrs: dict[str, Any] = {}
    if model_config is not None:
        attrs["model_config"] = _json.dumps(model_config)
    if training_config is not None:
        attrs["training_config"] = _json.dumps(training_config)
    if keras_version is not None:
        attrs["keras_version"] = keras_version
    if backend is not None:
        attrs["backend"] = backend

    mock_hf = MagicMock()
    mock_hf.__enter__ = MagicMock(return_value=mock_hf)
    mock_hf.__exit__ = MagicMock(return_value=False)
    mock_hf.attrs = attrs
    return mock_hf


def test_read_hdf5_missing_library(tmp_path: Path) -> None:
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    with patch.dict("sys.modules", {"h5py": None}):
        with pytest.raises(ImportError, match="h5py"):
            read_hdf5(model_file)


def test_read_hdf5_format(tmp_path: Path) -> None:
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file()
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.format == AiModelFormat.HDF5


def test_read_hdf5_keras_version(tmp_path: Path) -> None:
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file(keras_version="2.15.0")
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.version == "2.15.0"
    assert "version" in meta.provenance


def test_read_hdf5_type_of_model_from_model_config(tmp_path: Path) -> None:
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file(
        model_config={"class_name": "Sequential", "config": {"name": "my_seq"}}
    )
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.type_of_model == "Sequential"
    assert "type_of_model" in meta.provenance


def test_read_hdf5_name_from_model_config(tmp_path: Path) -> None:
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file(
        model_config={
            "class_name": "Sequential",
            "config": {"name": "sentiment_model", "trainable": True},
        }
    )
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.name == "sentiment_model"
    assert "name" in meta.provenance


def test_read_hdf5_scalar_hyperparameters(tmp_path: Path) -> None:
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file(
        model_config={
            "class_name": "Sequential",
            "config": {
                "name": "my_model",
                "trainable": True,
                "dtype": "float32",
                "layers": [],  # non-scalar, should be excluded
            },
        }
    )
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.hyperparameters.get("trainable") is True
    assert meta.hyperparameters.get("dtype") == "float32"
    assert "layers" not in meta.hyperparameters


def test_read_hdf5_training_config_optimizer_and_loss(tmp_path: Path) -> None:
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file(
        training_config={
            "optimizer_config": {"class_name": "Adam", "config": {"lr": 0.001}},
            "loss": "sparse_categorical_crossentropy",
            "metrics": ["accuracy"],
        }
    )
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.properties.get("optimizer") == "Adam"
    assert meta.properties.get("loss") == "sparse_categorical_crossentropy"
    assert "accuracy" in meta.properties.get("metrics", "")


def test_read_hdf5_backend_in_properties(tmp_path: Path) -> None:
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file(backend="tensorflow")
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.properties.get("backend") == "tensorflow"


def test_read_hdf5_no_keras_attrs(tmp_path: Path) -> None:
    # Plain HDF5 without Keras metadata.
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file(
        model_config=None, training_config=None, keras_version=None, backend=None
    )
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.name is None
    assert meta.type_of_model is None
    assert meta.version is None
    assert meta.hyperparameters == {}


# ---------------------------------------------------------------------------
# Integration tests — HDF5/Keras fixtures (hdf5/*.h5, *.hdf5)
# Require: h5py installed AND fixture files present
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def hdf5_fixture() -> Any:
    pytest.importorskip("h5py")
    h5_files = list(_HDF5_DIR.glob("*.h5")) + list(_HDF5_DIR.glob("*.hdf5"))
    if not h5_files:
        pytest.skip("No .h5/.hdf5 fixture files found in tests/fixtures/hdf5/")
    return read_hdf5(h5_files[0])


def test_hdf5_fixture_format(hdf5_fixture: Any) -> None:
    assert hdf5_fixture.format == AiModelFormat.HDF5
