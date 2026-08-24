# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Direct unit tests for the lower-level ``pitloom.extract._hdf5`` parsing
helpers: ``_decode_h5_attr``, ``_extract_input_from_layers``,
``_parse_model_config``, and ``_parse_training_config``.

See also: test_hdf5_mocked.py (tests for ``read_hdf5()`` against a mocked
``h5py`` file, exercising these helpers through the full pipeline) and
test_hdf5_integration.py (tests against a real HDF5 fixture file).
"""

# pylint: disable=missing-function-docstring
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import json as _json
from typing import Any
from unittest.mock import MagicMock

from pitloom.extract._hdf5 import (
    _decode_h5_attr,
    _extract_input_from_layers,
    _parse_model_config,
    _parse_training_config,
)

# ---------------------------------------------------------------------------
# _decode_h5_attr -- direct unit tests
# ---------------------------------------------------------------------------


def test_decode_h5_attr_bytes() -> None:
    assert _decode_h5_attr(b"2.15.0") == "2.15.0"


def test_decode_h5_attr_numpy_like_tobytes() -> None:
    # numpy.bytes_ (and similar) expose .tobytes() rather than being a
    # plain `bytes` instance.
    fake_numpy_bytes = MagicMock()
    fake_numpy_bytes.tobytes.return_value = b"tensorflow"
    assert _decode_h5_attr(fake_numpy_bytes) == "tensorflow"


def test_decode_h5_attr_plain_str() -> None:
    assert _decode_h5_attr("already-a-str") == "already-a-str"


def test_decode_h5_attr_none() -> None:
    assert _decode_h5_attr(None) is None


# ---------------------------------------------------------------------------
# _extract_input_from_layers -- direct unit tests
# ---------------------------------------------------------------------------


def test_extract_input_from_layers_non_input_layer_build_config() -> None:
    # A non-InputLayer entry with a build_config.input_shape is used as a
    # fallback source for the input shape.
    layers = [{"class_name": "Dense", "build_config": {"input_shape": [None, 32]}}]
    inputs, prov = _extract_input_from_layers(layers, "Source: model.h5")
    assert inputs == [{"shape": [None, 32]}]
    assert "layers[0].build_config.input_shape" in prov


def test_extract_input_from_layers_skips_unmatching_then_matches() -> None:
    # First layer (Dense, no build_config) yields nothing; loop continues to
    # the second layer (InputLayer) which does.
    layers = [
        {"class_name": "Dense"},
        {"class_name": "InputLayer", "config": {"batch_shape": [None, 10]}},
    ]
    inputs, prov = _extract_input_from_layers(layers, "Source: model.h5")
    assert inputs == [{"shape": [None, 10]}]
    assert "InputLayer" in prov


def test_extract_input_from_layers_input_layer_missing_batch_shape_continues() -> None:
    # An InputLayer entry with no config.batch_shape yields nothing from
    # that layer; the loop continues to the next layer instead of stopping.
    layers = [
        {"class_name": "InputLayer", "config": {}},
        {"class_name": "Dense", "build_config": {"input_shape": [None, 16]}},
    ]
    inputs, prov = _extract_input_from_layers(layers, "Source: model.h5")
    assert inputs == [{"shape": [None, 16]}]
    assert "layers[1].build_config.input_shape" in prov


def test_extract_input_from_layers_no_match_returns_empty() -> None:
    layers = [{"class_name": "Dense"}, {"class_name": "Activation"}]
    inputs, prov = _extract_input_from_layers(layers, "Source: model.h5")
    assert inputs == []
    assert prov == ""


# ---------------------------------------------------------------------------
# _parse_model_config -- direct unit tests
# ---------------------------------------------------------------------------


def test_parse_model_config_no_class_name_skips_provenance() -> None:
    hyperparameters: dict[str, Any] = {}
    inputs: list[dict[str, Any]] = []
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}
    raw = _json.dumps({"config": {"name": "my_model"}})

    type_of_model, name = _parse_model_config(
        raw, "Source: m.h5", hyperparameters, inputs, properties, provenance
    )

    assert type_of_model is None
    assert name == "my_model"
    assert "type_of_model" not in provenance


def test_parse_model_config_no_name_skips_name_provenance() -> None:
    hyperparameters: dict[str, Any] = {}
    inputs: list[dict[str, Any]] = []
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}
    raw = _json.dumps({"class_name": "Sequential", "config": {"trainable": True}})

    type_of_model, name = _parse_model_config(
        raw, "Source: m.h5", hyperparameters, inputs, properties, provenance
    )

    assert type_of_model == "Sequential"
    assert name is None
    assert "name" not in provenance


def test_parse_model_config_config_not_a_dict_is_ignored() -> None:
    # A malformed model_config where "config" isn't a dict must not raise --
    # the whole `if isinstance(config, dict)` block is skipped.
    hyperparameters: dict[str, Any] = {}
    inputs: list[dict[str, Any]] = []
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}
    raw = _json.dumps({"class_name": "Sequential", "config": "not-a-dict"})

    type_of_model, name = _parse_model_config(
        raw, "Source: m.h5", hyperparameters, inputs, properties, provenance
    )

    assert type_of_model == "Sequential"
    assert name is None
    assert hyperparameters == {}


def test_parse_model_config_top_level_build_config_fallback() -> None:
    # No layers give a shape (there are none), so the top-level
    # build_config.input_shape is used as a fallback.
    hyperparameters: dict[str, Any] = {}
    inputs: list[dict[str, Any]] = []
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}
    raw = _json.dumps(
        {
            "class_name": "Sequential",
            "config": {"name": "m"},
            "build_config": {"input_shape": [None, 4]},
        }
    )

    _parse_model_config(
        raw, "Source: m.h5", hyperparameters, inputs, properties, provenance
    )

    assert inputs == [{"shape": [None, 4]}]
    assert provenance["inputs"] == (
        "Source: m.h5 | Field: model_config.build_config.input_shape"
    )


def test_parse_model_config_invalid_json_returns_none_none() -> None:
    hyperparameters: dict[str, Any] = {}
    inputs: list[dict[str, Any]] = []
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}

    type_of_model, name = _parse_model_config(
        "not valid json",
        "Source: m.h5",
        hyperparameters,
        inputs,
        properties,
        provenance,
    )

    assert type_of_model is None
    assert name is None
    assert provenance == {}


# ---------------------------------------------------------------------------
# _parse_training_config -- direct unit tests
# ---------------------------------------------------------------------------


def test_parse_training_config_empty_dict_populates_nothing() -> None:
    # No optimizer/loss/metrics keys at all -- every guard's false branch.
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}

    _parse_training_config(_json.dumps({}), "Source: m.h5", properties, provenance)

    assert properties == {}
    assert provenance == {}


def test_parse_training_config_optimizer_without_class_name() -> None:
    # optimizer is a dict but has no (or an empty) class_name.
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}
    raw = _json.dumps({"optimizer": {}})

    _parse_training_config(raw, "Source: m.h5", properties, provenance)

    assert "optimizer" not in properties


def test_parse_training_config_invalid_json_is_ignored() -> None:
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}

    _parse_training_config("not valid json", "Source: m.h5", properties, provenance)

    assert properties == {}
    assert provenance == {}
