# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``compile_config`` of a ``.keras`` archive: what it gives (optimiser,
loss, metrics), what a part of the wrong type costs (one warning, the rest
kept), and a lone surrogate in a training collection, which HDF5 and Keras
share the code for.

See also: test_keras.py (the reader and the fixture),
test_keras_config_members.py (``metadata.json`` and the model config),
test_keras_config_parse_failure.py (a member that does not parse) and
test_hdf5_parsing.py (the HDF5 side of the shared parsing).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pitloom.extract.ai_model.keras_training_config import parse_training_config
from tests.extract.ai_model._keras_helpers import ADAM, MODEL, SOURCE, read


@pytest.mark.parametrize(
    ("compile_config", "expected", "field"),
    [
        (
            {"optimizer": ADAM, "loss": "binary_crossentropy", "metrics": ["acc"]},
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
    meta, messages = read(tmp_path, caplog, {**MODEL, "compile_config": compile_config})
    assert messages == []
    keys = ("optimizer", "loss", "metrics")
    assert {k: meta.properties[k] for k in keys if k in meta.properties} == expected
    assert "learning_rate" not in json.dumps(meta.properties)
    if field is not None:
        assert meta.provenance["properties.optimizer"] == (
            f"{SOURCE}config.compile_config.{field}"
        )
    assert meta.type_of_model == "Sequential"  # the model config is read too


def test_compile_config_absent_is_quiet(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    meta, messages = read(tmp_path, caplog, MODEL)
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
    meta, messages = read(tmp_path, caplog, {**MODEL, "compile_config": compile_config})
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
    metadata, as read. Empty metrics (``[]``) and an empty loss string
    (``""``) are absent, as an empty optimiser string is: a blank value is not
    a claim, the decision of note 11 in docs/ai-model-formats.md (a ``null``
    or ``""`` value is left out, and so are empty metrics)."""
    meta, _ = read(tmp_path, caplog, {**MODEL, "compile_config": {key: value}})
    assert meta.properties.get(key) == text
    assert meta.raw_metadata.get(key) == (value if text is not None else None)
    if text is not None:
        assert meta.provenance[f"properties.{key}"] == (
            f"{SOURCE}config.compile_config.{key}"
        )


_SURROGATE_TRAINING = b'{"loss": ["\\ud800"], "metrics": {"\\udc00": 1}}'


def test_a_lone_surrogate_in_a_compile_config_keeps_the_model(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """RFC 8785 cannot write it: the text is written escaped, the value kept
    as read, and the rest of the model is read."""
    body = b'{"class_name": "S", "compile_config": ' + _SURROGATE_TRAINING + b"}"
    meta, messages = read(tmp_path, caplog, body)
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
