# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``read_hdf5()`` against a mocked ``h5py`` file: format
detection (plain HDF5 vs Keras reclassification), version parsing, and
model/training config extraction through the full pipeline.

See also: test_hdf5_parsing.py (direct unit tests for the lower-level
``_hdf5`` parsing helpers) and test_hdf5_integration.py (tests against a
real HDF5 fixture file).
"""

# pylint: disable=missing-function-docstring
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import json as _json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import read_hdf5

# ---------------------------------------------------------------------------
# HDF5 extractor (mocked) -- generic HDF5 with optional Keras legacy attrs
# ---------------------------------------------------------------------------


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


def test_read_hdf5_open_failure_logs_and_raises(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"corrupt")

    mock_h5py = MagicMock()
    mock_h5py.File.side_effect = OSError("unable to open file (bad signature)")

    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        with caplog.at_level(logging.DEBUG, logger="pitloom.extract._hdf5"):
            with pytest.raises(ValueError, match="Failed to read HDF5 file"):
                read_hdf5(model_file)

    # Open failure is now logged at debug level before being re-raised.
    assert any("model.h5" in r.message for r in caplog.records)


def test_read_hdf5_format_plain(tmp_path: Path) -> None:
    # Plain HDF5 without Keras attributes stays as HDF5.
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file(
        model_config=None, training_config=None, keras_version=None, backend=None
    )
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.format_info.model_format == AiModelFormat.HDF5


def test_read_hdf5_format_keras_reclassified(tmp_path: Path) -> None:
    # An HDF5 file with keras_version is reclassified as Keras format.
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file()  # default keras_version="2.12.0"
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.format_info.model_format == AiModelFormat.KERAS


def test_read_hdf5_keras_version_in_framework_version(tmp_path: Path) -> None:
    # keras_version is the Keras library version, stored in framework_version.
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file(keras_version="2.15.0")
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.format_info.framework_version == "2.15.0"
    assert meta.version is None
    assert "framework_version" in meta.provenance


def test_read_hdf5_format_version_v1(tmp_path: Path) -> None:
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file(keras_version="1.2.3")
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.format_info.format_version == "v1"
    assert meta.format_info.framework == "keras"


def test_read_hdf5_format_version_v2(tmp_path: Path) -> None:
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file(keras_version="2.15.0")
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.format_info.format_version == "v2"
    assert meta.format_info.framework == "keras"


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
    assert meta.format_info.framework is None
    assert meta.format_info.framework_version is None
    assert meta.hyperparameters == {}


def test_read_hdf5_unparseable_keras_version_defaults_to_v2(
    tmp_path: Path,
) -> None:
    # A non-numeric keras_version (e.g. corrupted attribute) can't be split
    # into a major version int -- ValueError is caught, defaulting to v2.
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file(keras_version="unknown")
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.format_info.format_version == "v2"


def test_read_hdf5_unparseable_model_config_stores_raw_text(
    tmp_path: Path,
) -> None:
    # model_config present but not valid JSON -> _parse_model_config returns
    # (None, None); the caller then stashes the raw text for inspection
    # instead of silently dropping it.
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    mock_hf = _make_hdf5_file()
    mock_hf.attrs["model_config"] = "not valid json {{{"
    mock_h5py = MagicMock()
    mock_h5py.File.return_value = mock_hf
    with patch.dict("sys.modules", {"h5py": mock_h5py}):
        meta = read_hdf5(model_file)
    assert meta.type_of_model is None
    assert meta.name is None
    assert meta.properties.get("model_config_raw") == "not valid json {{{"
    assert "properties.model_config_raw" in meta.provenance
