# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``metadata.json`` and the model config of a ``.keras`` archive: what
they give with their provenance, a value of the wrong type (one warning), an
empty-but-present value, and the drift guard between the Keras and the HDF5
parsing of one config.

See also: test_keras_config.py (``compile_config``),
test_keras_config_parse_failure.py (a member that does not parse) and
test_hdf5_parsing.py (the HDF5 side of the shared parsing).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.provenance import provenance_source
from pitloom.extract.ai_model.hdf5_config import parse_model_config
from pitloom.extract.ai_model.keras_training_config import parse_training_config
from tests.extract.ai_model._keras_helpers import ADAM, META, MODEL, SOURCE, read


@pytest.mark.parametrize(
    ("metadata", "lost", "version", "date"),
    [
        ({**META, "keras_version": 3}, "framework_version", None, True),
        ({**META, "date_saved": ["x"]}, "properties.date_saved", "3.5.0", False),
        (
            {"keras_version": {}, "date_saved": 1},
            "framework_version, properties.date_saved",
            None,
            False,
        ),
    ],
    ids=["version-int", "date-list", "both"],
)
def test_a_metadata_value_of_the_wrong_type_warns_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    metadata: dict[str, Any],
    lost: str,
    version: str | None,
    date: bool,
) -> None:
    meta, messages = read(tmp_path, caplog, MODEL, metadata)
    (message,) = messages
    assert message.startswith("metadata.")
    assert "is not a string" in message
    assert message.endswith(f"(skipped): {lost}")
    assert meta.format_info.framework_version == version
    assert ("date_saved" in meta.properties) == date
    assert ("framework_version" in meta.provenance) == (version is not None)
    assert meta.type_of_model == "Sequential"


def test_an_empty_metadata_text_is_absent_and_quiet(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Declared-but-empty is not the wrong type: ``""`` is a string, so no
    warning, and it is no claim, so no version, no ``date_saved`` property and
    no provenance for them (docs/ai-model-formats.md, note 11: an empty
    string is left out, as for the training config). A white-space-only value
    is not covered here."""
    metadata = {"keras_version": "", "date_saved": ""}
    meta, messages = read(tmp_path, caplog, MODEL, metadata)
    assert messages == []
    assert meta.format_info.framework_version is None
    assert "date_saved" not in meta.properties
    assert not {"framework_version", "properties.date_saved"} & set(meta.provenance)


def test_metadata_fields_and_their_provenance(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``date_saved`` has no time zone: a property, never a release time."""
    meta, _ = read(tmp_path, caplog, metadata=META)
    assert meta.format_info.framework_version == "3.5.0"
    assert meta.properties["date_saved"] == "2026-01-01@00:00:00"
    assert meta.release_time is None
    assert meta.provenance["framework_version"] == (
        f"{SOURCE}metadata.json keras_version"
    )
    assert meta.provenance["properties.date_saved"] == (
        f"{SOURCE}metadata.json date_saved"
    )


def test_layers_not_a_list_keeps_the_hyperparameters(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = {"class_name": "S", "config": {"name": "m", "units": 4, "layers": {}}}
    meta, messages = read(tmp_path, caplog, config)
    (message,) = messages
    assert message.startswith("config.config.layers is not a list;")
    assert message.endswith("(skipped): inputs, properties.layer_count")
    assert meta.hyperparameters == {"units": 4}
    assert "layer_count" not in meta.properties


def test_model_name_is_the_fallback_name(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = {"class_name": "Functional", "config": {"name": "", "model_name": "f"}}
    meta, messages = read(tmp_path, caplog, config)
    assert messages == []
    assert meta.name == "f"
    assert meta.provenance["name"] == f"{SOURCE}config.config.model_name"


def test_dtype_is_no_hyperparameter(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = {"class_name": "S", "config": {"dtype": "float32", "trainable": True}}
    meta, _ = read(tmp_path, caplog, config)
    assert meta.hyperparameters == {"trainable": True}


def test_the_archive_structure_is_recorded(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    meta, _ = read(tmp_path, caplog, MODEL, META)
    assert meta.properties["archive_contents"] == "metadata.json, config.json"
    assert meta.properties["archive_member_count"] == "2"
    assert meta.raw_metadata["archive_contents"] == ["metadata.json", "config.json"]
    assert meta.provenance["properties.archive_contents"] == (
        f"{SOURCE}ZIP archive structure"
    )


_SHARED = {
    "class_name": "Sequential",
    "config": {
        "name": "seq",
        "trainable": True,
        "dtype": "float32",
        "layers": [
            {"class_name": "Dense", "build_config": {"input_shape": [None, 3]}},
            {"class_name": "Dense", "config": {"units": 1}},
        ],
    },
    "build_config": {"input_shape": [None, 9]},
}
_TRAINING = {"optimizer": ADAM, "loss": {"class_name": "Huber"}, "metrics": ["a"]}


def test_hdf5_and_keras_read_one_config_alike(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Equal fields (``dtype`` aside: Keras 3 writes a policy object there);
    provenance differing only by where the config sits."""
    hyper: dict[str, Any] = {}
    inputs: list[dict[str, Any]] = []
    props: dict[str, str] = {}
    prov: dict[str, str] = {}
    source = provenance_source("m.keras")
    type_of_model, name, problem = parse_model_config(
        json.dumps(_SHARED), source, hyper, inputs, props, prov
    )
    assert problem is None
    assert parse_training_config(json.dumps(_TRAINING), source, props, prov) is None
    meta, messages = read(tmp_path, caplog, {**_SHARED, "compile_config": _TRAINING})
    assert messages == []

    assert (meta.type_of_model, meta.name) == (type_of_model, name)
    assert meta.inputs == inputs == [{"shape": [None, 3]}]
    assert hyper.pop("dtype") == "float32"
    del prov["hyperparameters.dtype"]
    assert meta.hyperparameters == hyper
    for key, value in props.items():
        assert meta.properties[key] == value
    assert props["layer_count"] == "2"
    for key, value in prov.items():
        expected = value.replace("Field: model_config.", "Field: config.")
        expected = expected.replace(
            "Field: training_config.", "Field: config.compile_config."
        )
        assert expected != value  # every HDF5 path is renamed
        assert meta.provenance[key] == expected


def test_an_empty_layers_list_is_a_count_of_zero_for_hdf5_and_keras(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``layers: []`` is stated, not absent: a count of 0, with its
    provenance, in an HDF5 ``model_config`` and a ``.keras`` config alike."""
    config = {"class_name": "Sequential", "config": {"name": "m", "layers": []}}
    props: dict[str, str] = {}
    prov: dict[str, str] = {}
    source = provenance_source("m.h5")
    parse_model_config(json.dumps(config), source, {}, [], props, prov)
    meta, messages = read(tmp_path, caplog, config)
    assert messages == []
    assert props["layer_count"] == meta.properties["layer_count"] == "0"
    assert "properties.layer_count" in prov
    assert "properties.layer_count" in meta.provenance
