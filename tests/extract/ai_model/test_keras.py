# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Keras v3 native format metadata extractor (mocked and integration)."""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model.keras import read_keras
from tests.extract.ai_model.zip_builders import dated_zip

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KERAS_DIR = Path(__file__).parent.parent.parent / "fixtures" / "aimodels" / "keras"


def _make_keras_zip(
    metadata: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> bytes:
    """Build a minimal in-memory .keras ZIP archive (no clock read)."""
    files = {}
    if metadata is not None:
        files["metadata.json"] = json.dumps(metadata).encode()
    if config is not None:
        files["config.json"] = json.dumps(config).encode()
    return dated_zip(files)


# ---------------------------------------------------------------------------
# Keras extractor (mocked via tmp_path)
# ---------------------------------------------------------------------------


def test_read_keras_format(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip())
    assert read_keras(f).format_info.model_format == AiModelFormat.KERAS


def test_read_keras_framework_version_from_metadata(tmp_path: Path) -> None:
    # keras_version is the Keras library version -> framework_version.
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip(metadata={"keras_version": "3.5.0"}))
    meta = read_keras(f)
    assert meta.format_info.framework_version == "3.5.0"
    assert meta.version is None


def test_read_keras_framework_version_in_provenance(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip(metadata={"keras_version": "3.5.0"}))
    assert "framework_version" in read_keras(f).provenance


def test_read_keras_format_version(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip())
    assert read_keras(f).format_info.format_version == "v3"


def test_read_keras_framework(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip())
    assert read_keras(f).format_info.framework == "keras"


def test_read_keras_date_saved_in_properties(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip(metadata={"date_saved": "2026-01-01@00:00:00"}))
    assert read_keras(f).properties.get("date_saved") == "2026-01-01@00:00:00"


def test_read_keras_no_metadata_file(tmp_path: Path) -> None:
    # No metadata.json -- framework_version should be None, no crash.
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip(metadata=None))
    meta = read_keras(f)
    assert meta.format_info.framework_version is None


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


def test_read_keras_missing_class_name_and_non_dict_config_sections(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No 'class_name' key leaves type_of_model as None (no provenance
    entry); a 'config' section that isn't a dict stops the model config
    there, as in an HDF5 model: one warning names what is not read (no
    name, hyperparameters or inputs)."""
    f = tmp_path / "model.keras"
    f.write_bytes(
        _make_keras_zip(
            config={"config": "not-a-dict", "build_config": ["not-a-dict-either"]}
        )
    )
    with caplog.at_level(logging.WARNING):
        meta = read_keras(f)
    (message,) = [r.getMessage() for r in caplog.records]
    assert message.startswith("config.config is not an object;")
    assert message.endswith(
        "(skipped): name, hyperparameters, inputs, properties.layer_count"
    )
    assert meta.type_of_model is None
    assert "type_of_model" not in meta.provenance
    assert meta.name is None
    assert meta.hyperparameters == {}
    assert meta.inputs == []
    assert "inputs" not in meta.provenance


@pytest.mark.parametrize(
    ("config", "type_of_model", "name", "lost"),
    [
        ({"class_name": {"a": 1}, "config": {"name": "m"}}, None, "m", "type_of_model"),
        ({"class_name": 7, "config": {"name": "m"}}, None, "m", "type_of_model"),
        (
            {"class_name": "Sequential", "config": {"name": 5}},
            "Sequential",
            None,
            "name",
        ),
        (
            {"class_name": "Sequential", "config": {"name": ["x"]}},
            "Sequential",
            None,
            "name",
        ),
        (
            {"class_name": [], "config": {"name": {}}},
            None,
            None,
            "type_of_model, name",
        ),
    ],
    ids=["class-object", "class-int", "name-int", "name-array", "both"],
)
def test_read_keras_non_string_class_name_or_name_warns_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    config: dict[str, Any],
    type_of_model: str | None,
    name: str | None,
    lost: str,
) -> None:
    """A class name or model name that is not a string is not recorded: one
    ``WARNING:`` names what was skipped, the rest of the config is kept."""
    config["config"]["units"] = 3
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip(config=config))
    with caplog.at_level(logging.WARNING):
        meta = read_keras(f)
    assert (meta.type_of_model, meta.name) == (type_of_model, name)
    assert meta.hyperparameters == {"units": 3}
    for field in ("type_of_model", "name"):
        assert (field in meta.provenance) == (field not in lost)
    (message,) = [r.getMessage() for r in caplog.records]
    assert "is not a string" in message
    assert message.endswith(f"Field(s) affected (skipped): {lost}")


@pytest.mark.parametrize(
    "config",
    [
        {"class_name": "Sequential", "config": {"name": "m"}},
        {"config": {}},
        {"class_name": None, "config": {"name": None}},
        {"class_name": "", "config": {"name": ""}},
    ],
    ids=["strings", "absent", "null", "empty"],
)
def test_read_keras_string_absent_null_or_empty_names_are_quiet(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, config: dict[str, Any]
) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip(config=config))
    with caplog.at_level(logging.WARNING):
        read_keras(f)
    assert caplog.records == []


def test_read_keras_bad_zip_raises_value_error(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(b"not a zip file at all")
    with pytest.raises(ValueError, match="not a valid ZIP archive"):
        read_keras(f)


def test_read_keras_member_that_cannot_be_extracted_logs_and_raises(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A valid ZIP whose member cannot be extracted (a compression method
    ``zipfile`` does not support) is a read failure, not data absent: the
    failure is logged at DEBUG and a ValueError is raised. (A member that
    is extracted but is not JSON is a warning: test_keras_config.py.)"""
    data = bytearray(dated_zip({"config.json": b"{}"}))
    for signature, offset in ((b"PK\x03\x04", 8), (b"PK\x01\x02", 10)):
        at = data.find(signature) + offset
        data[at : at + 2] = (99).to_bytes(2, "little")  # compression method
    f = tmp_path / "model.keras"
    f.write_bytes(bytes(data))

    with caplog.at_level(logging.DEBUG, logger="pitloom.extract.ai_model.keras"):
        with pytest.raises(ValueError, match="Failed to read Keras file"):
            read_keras(f)

    assert any("model.keras" in r.message for r in caplog.records)


def test_read_keras_no_name_description_license(tmp_path: Path) -> None:
    f = tmp_path / "model.keras"
    f.write_bytes(_make_keras_zip())
    meta = read_keras(f)
    assert meta.name is None
    assert meta.description is None
    assert meta.license is None


# ---------------------------------------------------------------------------
# Integration tests -- Keras fixture (keras/example-model.keras)
# No optional dependency required (uses stdlib zipfile + json).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fixture_keras() -> Any:
    path = _KERAS_DIR / "example-model.keras"
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    return read_keras(path)


def test_keras_fixture_format(fixture_keras: Any) -> None:
    assert fixture_keras.format_info.model_format == AiModelFormat.KERAS


def test_keras_fixture_framework_version(fixture_keras: Any) -> None:
    assert fixture_keras.format_info.framework_version == "3.13.2"


def test_keras_fixture_format_version(fixture_keras: Any) -> None:
    assert fixture_keras.format_info.format_version == "v3"


def test_keras_fixture_framework(fixture_keras: Any) -> None:
    assert fixture_keras.format_info.framework == "keras"


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


def test_keras_fixture_layers_and_input_layer(fixture_keras: Any) -> None:
    """The three layers (the InputLayer counted, as in HDF5) and the input
    shape the InputLayer states."""
    assert fixture_keras.properties["layer_count"] == "3"
    assert fixture_keras.raw_metadata_types["layer_count"] == "integer"
    assert fixture_keras.provenance["inputs"] == (
        "Source: example-model.keras | Field: "
        "config.config.layers[InputLayer].config.batch_shape"
    )


def test_keras_fixture_archive_structure(fixture_keras: Any) -> None:
    assert fixture_keras.properties["archive_contents"] == (
        "metadata.json, config.json, model.weights.h5"
    )
    assert fixture_keras.properties["archive_member_count"] == "3"


def test_keras_fixture_states_no_compile_settings(fixture_keras: Any) -> None:
    """``compile_config`` is ``{}``; the top-level ``metadata`` object is
    no Keras field: neither gives a value."""
    for key in ("optimizer", "loss", "metrics", "description", "license"):
        assert key not in fixture_keras.properties
    assert (fixture_keras.description, fixture_keras.license) == (None, None)
    assert fixture_keras.version is None
