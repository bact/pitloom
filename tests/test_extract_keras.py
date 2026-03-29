# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Keras v3 native format metadata extractor (mocked and integration)."""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import read_keras

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KERAS_DIR = Path(__file__).parent / "fixtures" / "keras"


def _make_keras_zip(
    metadata: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> bytes:
    """Build a minimal in-memory .keras ZIP archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if metadata is not None:
            zf.writestr("metadata.json", json.dumps(metadata))
        if config is not None:
            zf.writestr("config.json", json.dumps(config))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Keras extractor (mocked via tmp_path)
# ---------------------------------------------------------------------------


def test_read_keras_format(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip())
    assert read_keras(f).format == AiModelFormat.KERAS


def test_read_keras_framework_version_from_metadata(tmp_path: Path) -> None:
    # keras_version is the Keras library version → framework_version.
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip(metadata={"keras_version": "3.5.0"}))
    meta = read_keras(f)
    assert meta.framework_version == "3.5.0"
    assert meta.version is None


def test_read_keras_framework_version_in_provenance(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip(metadata={"keras_version": "3.5.0"}))
    assert "framework_version" in read_keras(f).provenance


def test_read_keras_format_version(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip())
    assert read_keras(f).format_version == "v3"


def test_read_keras_framework(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip())
    assert read_keras(f).framework == "keras"


def test_read_keras_date_saved_in_properties(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip(metadata={"date_saved": "2026-01-01@00:00:00"}))
    assert read_keras(f).properties.get("date_saved") == "2026-01-01@00:00:00"


def test_read_keras_no_metadata_file(tmp_path: Path) -> None:
    # No metadata.json — framework_version should be None, no crash.
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip(metadata=None))
    meta = read_keras(f)
    assert meta.framework_version is None


def test_read_keras_type_of_model_from_config(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip(config={"class_name": "Sequential", "config": {}}))
    assert read_keras(f).type_of_model == "Sequential"


def test_read_keras_name_from_config(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(
        _make_keras_zip(
            config={"class_name": "Sequential", "config": {"name": "my_model"}}
        )
    )
    assert read_keras(f).name == "my_model"


def test_read_keras_scalar_hyperparameters(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(
        _make_keras_zip(
            config={
                "class_name": "Sequential",
                "config": {
                    "name": "m",
                    "trainable": True,
                    "layers": [],  # non-scalar, excluded
                },
            }
        )
    )
    meta = read_keras(f)
    assert meta.hyperparameters.get("trainable") is True
    assert "layers" not in meta.hyperparameters


def test_read_keras_input_shape_from_build_config(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(
        _make_keras_zip(
            config={
                "class_name": "Sequential",
                "config": {"name": "m"},
                "build_config": {"input_shape": [None, 4]},
            }
        )
    )
    meta = read_keras(f)
    assert len(meta.inputs) == 1
    assert meta.inputs[0]["shape"] == [None, 4]


def test_read_keras_no_inputs_when_no_build_config(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip(config={"class_name": "Sequential", "config": {}}))
    assert read_keras(f).inputs == []


def test_read_keras_bad_zip_raises_value_error(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(b"not a zip file at all")
    with pytest.raises(ValueError, match="not a valid ZIP archive"):
        read_keras(f)


def test_read_keras_no_name_description_license(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip())
    meta = read_keras(f)
    assert meta.name is None
    assert meta.description is None
    assert meta.license is None


# ---------------------------------------------------------------------------
# Integration tests — Keras fixture (keras/example-model.keras)
# No optional dependency required (uses stdlib zipfile + json).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fixture_keras() -> Any:
    path = _KERAS_DIR / "example-model.keras"
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    return read_keras(path)


def test_keras_fixture_format(fixture_keras: Any) -> None:
    assert fixture_keras.format == AiModelFormat.KERAS


def test_keras_fixture_framework_version(fixture_keras: Any) -> None:
    assert fixture_keras.framework_version == "3.13.2"


def test_keras_fixture_format_version(fixture_keras: Any) -> None:
    assert fixture_keras.format_version == "v3"


def test_keras_fixture_framework(fixture_keras: Any) -> None:
    assert fixture_keras.framework == "keras"


def test_keras_fixture_version_is_none(fixture_keras: Any) -> None:
    assert fixture_keras.version is None


def test_keras_fixture_type_of_model(fixture_keras: Any) -> None:
    assert fixture_keras.type_of_model == "Sequential"


def test_keras_fixture_name(fixture_keras: Any) -> None:
    assert fixture_keras.name == "Binary_Classifier_v1"


def test_keras_fixture_trainable_hyperparameter(fixture_keras: Any) -> None:
    assert fixture_keras.hyperparameters.get("trainable") is True


def test_keras_fixture_input_shape(fixture_keras: Any) -> None:
    assert len(fixture_keras.inputs) == 1
    assert fixture_keras.inputs[0]["shape"] == [None, 10]


def test_keras_fixture_date_saved_in_properties(fixture_keras: Any) -> None:
    assert "date_saved" in fixture_keras.properties


def test_keras_fixture_provenance_has_framework_version(fixture_keras: Any) -> None:
    assert "framework_version" in fixture_keras.provenance


def test_keras_fixture_provenance_has_name(fixture_keras: Any) -> None:
    assert "name" in fixture_keras.provenance
