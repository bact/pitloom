# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The JSON members of a ``.keras`` archive: what ``compile_config``,
``metadata.json`` and the model config give, what a member that does not
parse costs (one warning, the other member kept), and the drift guard
between the Keras and the HDF5 parsing of one config.

See also: test_keras.py (the reader and the fixture) and
test_hdf5_parsing.py (the HDF5 side of the shared parsing).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.provenance import provenance_source
from pitloom.extract.ai_model.hdf5_config import parse_model_config
from pitloom.extract.ai_model.keras import read_keras
from pitloom.extract.ai_model.keras_training_config import parse_training_config
from tests.extract.ai_model.zip_builders import dated_zip

_SOURCE = "Source: m.keras | Field: "
_META = {"keras_version": "3.5.0", "date_saved": "2026-01-01@00:00:00"}
_MODEL = {"class_name": "Sequential", "config": {"name": "m", "units": 2}}
_ADAM = {
    "module": "keras.optimizers",
    "class_name": "Adam",
    "config": {"name": "adam", "learning_rate": 0.001},
    "registered_name": None,
}
_MODEL_FIELDS = (
    "type_of_model, name, hyperparameters, inputs, properties.layer_count, "
    "properties.optimizer, properties.loss, properties.metrics"
)
_DEEP = 100_000  # deeper than the JSON parser's stack


def _body(value: Any) -> bytes:
    return value if isinstance(value, bytes) else json.dumps(value).encode()


def _read(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    config: Any = None,
    metadata: Any = None,
) -> tuple[AiModelMetadata, list[str]]:
    """Read a ``.keras`` archive of the members given (``None``: absent), and
    the warnings it logged."""
    files = {
        name: _body(value)
        for name, value in (("metadata.json", metadata), ("config.json", config))
        if value is not None
    }
    path = tmp_path / "m.keras"
    path.write_bytes(dated_zip(files))
    with caplog.at_level(logging.WARNING):
        meta = read_keras(path)
    return meta, [r.getMessage() for r in caplog.records]


# ---------------------------------------------------------------------------
# compile_config
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("compile_config", "expected", "field"),
    [
        (
            {"optimizer": _ADAM, "loss": "binary_crossentropy", "metrics": ["acc"]},
            {"optimizer": "Adam", "loss": "binary_crossentropy", "metrics": '["acc"]'},
            "optimizer.class_name",
        ),
        (
            {"optimizer": "adam", "loss": "mse"},
            {"optimizer": "adam", "loss": "mse"},
            "optimizer",
        ),
        (None, {}, None),
        ({}, {}, None),
        ({"optimizer": None, "loss": None, "metrics": []}, {}, None),
        ({"optimizer": "", "metrics": None}, {}, None),
    ],
    ids=["object", "string", "null", "empty", "nulls", "empty-values"],
)
def test_compile_config_gives_optimizer_loss_and_metrics(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    compile_config: Any,
    expected: dict[str, str],
    field: str | None,
) -> None:
    """An optimizer object gives its class name, a string itself (Keras 3
    keeps what ``compile()`` was given); absent, ``null`` and empty values
    give nothing, quietly. The optimizer's own config is not read."""
    meta, messages = _read(
        tmp_path, caplog, {**_MODEL, "compile_config": compile_config}
    )
    assert messages == []
    keys = ("optimizer", "loss", "metrics")
    assert {k: meta.properties[k] for k in keys if k in meta.properties} == expected
    assert "learning_rate" not in json.dumps(meta.properties)
    if field is not None:
        assert meta.provenance["properties.optimizer"] == (
            f"{_SOURCE}config.compile_config.{field}"
        )
    assert meta.type_of_model == "Sequential"  # the model config is read too


def test_compile_config_absent_is_quiet(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    meta, messages = _read(tmp_path, caplog, _MODEL)
    assert messages == []
    assert not {"optimizer", "loss", "metrics"} & set(meta.properties)


@pytest.mark.parametrize(
    ("compile_config", "problem", "kept"),
    [
        ({"optimizer": 3, "loss": "mse"}, "optimizer is not an object or a string", 1),
        ({"optimizer": ["adam"], "loss": "mse"}, "optimizer is not an object or", 1),
        ({"optimizer": {"class_name": 5}, "loss": "mse"}, "class_name is not a s", 1),
        ("adam", "compile_config is not an object", 0),
        ([{"loss": "mse"}], "compile_config is not an object", 0),
        ([], "compile_config is not an object", 0),
    ],
    ids=["int", "list", "class-int", "config-string", "config-list", "config-[]"],
)
def test_a_compile_config_part_of_the_wrong_type_warns_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    compile_config: Any,
    problem: str,
    kept: int,
) -> None:
    """One warning; the loss after a bad optimizer is kept, and so is the
    model config. An empty list is no object either, as for an HDF5
    ``training_config``."""
    meta, messages = _read(
        tmp_path, caplog, {**_MODEL, "compile_config": compile_config}
    )
    if compile_config == []:
        hdf5 = parse_training_config("[]", "S", {}, {})
        assert hdf5 is not None and hdf5.error == "is not a JSON object"
    (message,) = messages
    assert message.startswith("config.compile_config")
    assert problem in message
    assert "; reading stopped there | Field(s) affected (skipped): " in message
    assert ("loss" in meta.properties) == bool(kept)
    assert "optimizer" not in meta.properties
    assert (meta.type_of_model, meta.name) == ("Sequential", "m")


@pytest.mark.parametrize(
    ("key", "value", "text"),
    [
        ("loss", "mse", "mse"),
        (
            "loss",
            {"class_name": "Huber", "config": {}},
            '{"class_name":"Huber","config":{}}',
        ),
        ("loss", ["mse", "mae"], '["mse","mae"]'),
        ("metrics", ["accuracy"], '["accuracy"]'),
        ("metrics", [], None),
        ("metrics", None, None),
        ("loss", "", None),
        ("metrics", "", None),
    ],
    ids=[
        "loss-str",
        "loss-dict",
        "loss-list",
        "metrics",
        "metrics-empty",
        "null",
        "loss-empty-str",
        "metrics-empty-str",
    ],
)
def test_loss_and_metrics_as_stated(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, key: str, value: Any, text: Any
) -> None:
    """A string as is, a collection as its JSON text and, in the raw
    metadata, as read; empty metrics and an empty loss string are absent,
    as an empty optimizer string is."""
    meta, _ = _read(tmp_path, caplog, {**_MODEL, "compile_config": {key: value}})
    assert meta.properties.get(key) == text
    assert meta.raw_metadata.get(key) == (value if text is not None else None)
    if text is not None:
        assert meta.provenance[f"properties.{key}"] == (
            f"{_SOURCE}config.compile_config.{key}"
        )


# ---------------------------------------------------------------------------
# metadata.json
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("metadata", "lost", "version", "date"),
    [
        ({**_META, "keras_version": 3}, "framework_version", None, True),
        ({**_META, "date_saved": ["x"]}, "properties.date_saved", "3.5.0", False),
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
    meta, messages = _read(tmp_path, caplog, _MODEL, metadata)
    (message,) = messages
    assert message.startswith("metadata.")
    assert "is not a string" in message
    assert message.endswith(f"(skipped): {lost}")
    assert meta.format_info.framework_version == version
    assert ("date_saved" in meta.properties) == date
    assert ("framework_version" in meta.provenance) == (version is not None)
    assert meta.type_of_model == "Sequential"


def test_metadata_fields_and_their_provenance(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``date_saved`` has no time zone: a property, never a release time."""
    meta, _ = _read(tmp_path, caplog, metadata=_META)
    assert meta.format_info.framework_version == "3.5.0"
    assert meta.properties["date_saved"] == "2026-01-01@00:00:00"
    assert meta.release_time is None
    assert meta.provenance["framework_version"] == (
        f"{_SOURCE}metadata.json keras_version"
    )
    assert meta.provenance["properties.date_saved"] == (
        f"{_SOURCE}metadata.json date_saved"
    )


# ---------------------------------------------------------------------------
# A member that does not parse
# ---------------------------------------------------------------------------

_UNPARSED = [
    pytest.param(b"{not valid json", "is not valid JSON (", id="invalid"),
    pytest.param(b"[1, 2]", "is not a JSON object", id="list"),
    pytest.param(b'{"a": "\xff"}', "is not valid JSON ('utf-8' codec", id="utf8"),
    pytest.param(b"[" * _DEEP, "is not valid JSON (nested too deeply)", id="deep"),
]


@pytest.mark.parametrize(("body", "error"), _UNPARSED)
def test_a_config_that_does_not_parse_keeps_the_metadata(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, body: bytes, error: str
) -> None:
    meta, messages = _read(tmp_path, caplog, body, _META)
    (message,) = messages
    assert message.startswith(f"config.json {error}")
    assert message.endswith(
        f"; the other archive members are read | Field(s) affected (skipped): "
        f"{_MODEL_FIELDS}"
    )
    assert meta.format_info.framework_version == "3.5.0"
    assert meta.properties["date_saved"] == _META["date_saved"]
    assert meta.type_of_model is None and not meta.hyperparameters


@pytest.mark.parametrize(("body", "error"), _UNPARSED)
def test_metadata_that_does_not_parse_keeps_the_config(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, body: bytes, error: str
) -> None:
    meta, messages = _read(tmp_path, caplog, _MODEL, body)
    (message,) = messages
    assert message.startswith(f"metadata.json {error}")
    assert message.endswith("(skipped): framework_version, properties.date_saved")
    assert (meta.type_of_model, meta.name) == ("Sequential", "m")
    assert meta.hyperparameters == {"units": 2}
    assert meta.format_info.framework_version is None


@pytest.mark.parametrize(
    "body",
    [
        b"\xef\xbb\xbf" + json.dumps(_MODEL).encode(),
        json.dumps(_MODEL).encode("utf-16"),
    ],
    ids=["utf-8-bom", "utf-16"],
)
def test_a_config_with_a_byte_order_mark_is_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, body: bytes
) -> None:
    meta, messages = _read(tmp_path, caplog, body)
    assert messages == []
    assert (meta.type_of_model, meta.name) == ("Sequential", "m")


def test_a_null_member_is_no_data(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    meta, messages = _read(tmp_path, caplog, b"null", b"null")
    assert messages == []
    assert meta.type_of_model is None and meta.format_info.framework_version is None


def test_a_config_nested_deeply_is_read_without_a_crash(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Deep values where a scalar or a collection is read: the hyperparameter
    is skipped (not a scalar), the loss kept or named as too deep.

    The depth parses on every supported Python: on 3.10 and 3.11 the json
    module counts nesting against the recursion limit, so 1000 levels fail to
    encode or decode there. A document too deep for the parser is the ``deep``
    case of the member-warning test above."""
    deep: Any = []
    for _ in range(300):
        deep = [deep]
    config = {
        "class_name": "Sequential",
        "config": {"name": "m", "deep": deep, "layers": [deep]},
        "compile_config": {"loss": deep, "metrics": ["acc"]},
    }
    meta, messages = _read(tmp_path, caplog, config)
    assert (meta.type_of_model, meta.name) == ("Sequential", "m")
    assert "deep" not in meta.hyperparameters
    assert meta.properties["metrics"] == '["acc"]'
    assert len(messages) <= 2  # layers[0] not an object; loss maybe too deep


# ---------------------------------------------------------------------------
# The model config
# ---------------------------------------------------------------------------


def test_layers_not_a_list_keeps_the_hyperparameters(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = {"class_name": "S", "config": {"name": "m", "units": 4, "layers": {}}}
    meta, messages = _read(tmp_path, caplog, config)
    (message,) = messages
    assert message.startswith("config.config.layers is not a list;")
    assert message.endswith("(skipped): inputs, properties.layer_count")
    assert meta.hyperparameters == {"units": 4}
    assert "layer_count" not in meta.properties


def test_model_name_is_the_fallback_name(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = {"class_name": "Functional", "config": {"name": "", "model_name": "f"}}
    meta, messages = _read(tmp_path, caplog, config)
    assert messages == []
    assert meta.name == "f"
    assert meta.provenance["name"] == f"{_SOURCE}config.config.model_name"


def test_dtype_is_no_hyperparameter(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = {"class_name": "S", "config": {"dtype": "float32", "trainable": True}}
    meta, _ = _read(tmp_path, caplog, config)
    assert meta.hyperparameters == {"trainable": True}


def test_the_archive_structure_is_recorded(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    meta, _ = _read(tmp_path, caplog, _MODEL, _META)
    assert meta.properties["archive_contents"] == "metadata.json, config.json"
    assert meta.properties["archive_member_count"] == "2"
    assert meta.raw_metadata["archive_contents"] == ["metadata.json", "config.json"]
    assert meta.provenance["properties.archive_contents"] == (
        f"{_SOURCE}ZIP archive structure"
    )


# ---------------------------------------------------------------------------
# Drift guard: one config through the HDF5 and the Keras parsing
# ---------------------------------------------------------------------------

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
_TRAINING = {"optimizer": _ADAM, "loss": {"class_name": "Huber"}, "metrics": ["a"]}


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
    meta, messages = _read(tmp_path, caplog, {**_SHARED, "compile_config": _TRAINING})
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


# ---------------------------------------------------------------------------
# A lone surrogate in a training collection (HDF5 and Keras share the code)
# ---------------------------------------------------------------------------

_SURROGATE_TRAINING = b'{"loss": ["\\ud800"], "metrics": {"\\udc00": 1}}'


def test_a_lone_surrogate_in_a_compile_config_keeps_the_model(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """RFC 8785 cannot write it: the text is written escaped, the value kept
    as read, and the rest of the model is read."""
    body = b'{"class_name": "S", "compile_config": ' + _SURROGATE_TRAINING + b"}"
    meta, messages = _read(tmp_path, caplog, body)
    assert messages == []
    assert meta.type_of_model == "S"
    assert meta.properties["loss"] == '["\\\\ud800"]'
    assert meta.properties["metrics"] == '{"\\\\udc00":1}'
    assert meta.raw_metadata["loss"] == ["\ud800"]


def test_a_lone_surrogate_in_an_hdf5_training_config_is_written_escaped() -> None:
    props: dict[str, str] = {}
    prov: dict[str, str] = {}
    raw = _SURROGATE_TRAINING.decode()
    assert parse_training_config(raw, "S", props, prov) is None
    assert props == {"loss": '["\\\\ud800"]', "metrics": '{"\\\\udc00":1}'}
