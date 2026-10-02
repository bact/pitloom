# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``read_hdf5()`` on root attributes that are not what Keras writes.

A part of the wrong type, JSON nested too deeply, or a string array is one
``WARNING:`` per attribute naming the fields lost; what was read before it
is kept, and the SBOM still builds.

See also: test_hdf5_mocked.py (the same function on well-formed attributes)
and test_hdf5_parsing.py (the helpers directly).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import sys
import tracemalloc
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.extract.ai_model import hdf5
from pitloom.extract.ai_model.hdf5 import _decode_h5_attr, read_hdf5
from tests.warning_helpers import logged_warnings

_FIELDS = "type_of_model, name, hyperparameters, inputs, properties.layer_count"
_NO_NAME = "name, hyperparameters, inputs, properties.layer_count"
# Deep enough for RecursionError on every version: 3.14's json decoder
# checks the real stack and parses 100 000 levels as plain invalid JSON.
_DEEP = "[" * 1_000_000


def _model(config: dict[str, Any]) -> str:
    return json.dumps({"class_name": "Sequential", "config": config})


def _read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, **attrs: Any
) -> tuple[AiModelMetadata, list[str]]:
    return _read_attrs(tmp_path, caplog, attrs)


def _read_attrs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, attrs: dict[str, Any]
) -> tuple[AiModelMetadata, list[str]]:
    model_file = tmp_path / "model.h5"
    model_file.write_bytes(b"fake")
    hf = MagicMock()
    hf.__enter__ = MagicMock(return_value=hf)
    hf.__exit__ = MagicMock(return_value=False)
    hf.attrs = attrs
    h5py = MagicMock()
    h5py.File.return_value = hf
    with (
        caplog.at_level(logging.WARNING),
        patch.dict("sys.modules", {"h5py": h5py}),
    ):
        meta = read_hdf5(model_file)
    return meta, logged_warnings(caplog)


@pytest.mark.parametrize(
    ("config", "problem", "affected"),
    [
        # nothing but the raw text can stand in for it
        (json.dumps({"class_name": 5}), "class_name is not a string", None),
        (json.dumps({"class_name": ["S"]}), "class_name is not a string", None),
        # what was read before the problem is kept; the rest is skipped
        (_model({"name": 7}), "config.name is not a string", _NO_NAME),
        (_model({"name": "m", "model_name": []}), None, None),  # name wins
        (
            _model({"name": "", "model_name": {}}),
            "model_name is not a string",
            _NO_NAME,
        ),
        (_model("x"), "config is not an object", _NO_NAME),  # type: ignore[arg-type]
        (_model(None), None, None),  # type: ignore[arg-type]  # null = absent
        (
            _model({"units": 4, "layers": {}}),
            "layers is not a list",
            "inputs, properties.layer_count",
        ),
        (_model({"layers": None}), None, None),  # null = absent
        (_model({"layers": [None]}), "layers[0] is not an object", "inputs"),
        (
            _model({"layers": [{"class_name": "InputLayer", "config": []}]}),
            "layers[0].config is not an object",
            "inputs",
        ),
        (
            _model({"layers": [{"class_name": "Dense", "build_config": "x"}]}),
            "layers[0].build_config is not an object",
            "inputs",
        ),
        (
            json.dumps({"class_name": "Sequential", "config": {}, "build_config": "x"}),
            "model_config.build_config is not an object",
            "inputs",
        ),
        pytest.param(  # over-long digits: a ValueError, not a decode error
            '{"class_name": ' + "1" * 5000 + "}",
            "is not valid JSON",
            None,
            marks=pytest.mark.skipif(
                not hasattr(sys, "get_int_max_str_digits"), reason="no digit limit"
            ),
        ),
        (_DEEP, "nested too deeply", None),
        ('{"class_name": ' + _DEEP, "nested too deeply", None),
    ],
)
def test_a_model_config_part_of_the_wrong_type_warns_once_naming_what_is_lost(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    config: str,
    problem: str | None,
    affected: str | None,
) -> None:
    meta, messages = _read(tmp_path, caplog, model_config=config)
    assert len(messages) == (problem is not None)
    if problem is None:
        return
    assert problem in messages[0]
    if affected is None:  # the raw text is kept in place of everything
        assert "model_config_raw" in meta.properties
        assert messages[0].count("Field(s) affected") == 1
        assert messages[0].endswith(f"(skipped): {_FIELDS}")  # lost with it
        assert meta.type_of_model is None and meta.name is None
    else:
        assert messages[0].endswith(f"(skipped): {affected}")
        assert "model_config_raw" not in meta.properties
        assert meta.type_of_model == "Sequential"
    # SBOM-bound text fields are strings or absent, never another type
    assert meta.type_of_model is None or isinstance(meta.type_of_model, str)
    assert meta.name is None or isinstance(meta.name, str)


def test_the_raw_config_is_kept_and_the_fields_after_the_problem_are_lost(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: the kept-raw line named the raw text as the one field
    affected, not the ones the problem stopped from being read."""
    config = json.dumps({"class_name": "", "config": {"layers": {}}})
    meta, messages = _read(tmp_path, caplog, model_config=config)
    (message,) = messages
    assert (
        "model_config_raw" in meta.properties and "layer_count" not in meta.properties
    )
    assert message.count("Field(s) affected") == 1
    assert message.endswith("(skipped): inputs, properties.layer_count")


def test_what_is_read_before_a_bad_model_config_part_is_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = _model({"name": "m", "units": 4, "layers": [{}, None]})
    meta, messages = _read(tmp_path, caplog, model_config=config)
    assert len(messages) == 1
    assert (meta.name, meta.hyperparameters) == ("m", {"units": 4})
    assert meta.properties["layer_count"] == "2"
    assert "layers[1] is not an object" in messages[0]


@pytest.mark.parametrize(
    ("training", "problem", "affected", "loss"),
    [
        (
            {"optimizer_config": {"class_name": 5}, "loss": "mse"},
            "is not a string",
            1,
            "mse",
        ),
        ({"optimizer": {"class_name": {}}, "loss": "mse"}, "is not a string", 1, "mse"),
        ({"optimizer_config": "adam", "loss": "mse"}, "is not an object", 1, "mse"),
        ({"optimizer_config": {"class_name": "Adam"}, "loss": "mse"}, None, 0, "mse"),
    ],
)
def test_a_training_config_optimizer_of_the_wrong_type_warns_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    training: dict[str, Any],
    problem: str | None,
    affected: int,
    loss: str,
) -> None:
    meta, messages = _read(tmp_path, caplog, training_config=json.dumps(training))
    assert len(messages) == affected
    assert meta.properties["loss"] == loss  # read before the optimizer
    assert ("optimizer" in meta.properties) is (problem is None)
    if problem:
        assert problem in messages[0]
        assert messages[0].endswith("(skipped): properties.optimizer")


@pytest.mark.parametrize("name", ["training_config", "model_config"])
def test_json_nested_too_deeply_loses_only_its_own_attribute(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, name: str
) -> None:
    """Regression: a ``RecursionError`` from ``json.loads`` escaped the
    reader and failed the whole file (a stub, nothing of it read)."""
    other = "training_config" if name == "model_config" else "model_config"
    good = (
        json.dumps({"loss": "mse"})
        if other == "training_config"
        else _model({"name": "m"})
    )
    meta, messages = _read(
        tmp_path, caplog, **{name: _DEEP, other: good, "backend": "tensorflow"}
    )
    assert len(messages) == 1 and "nested too deeply" in messages[0]
    assert meta.properties["backend"] == "tensorflow"
    assert ("loss" in meta.properties) is (name == "model_config")
    assert (meta.name == "m") is (name == "training_config")


@pytest.mark.parametrize(
    ("make", "expected"),
    [
        (lambda np: np.array(['{"a": 1}'], dtype=object), '{"a": 1}'),
        (lambda np: np.array([b"tf"], dtype=object), "tf"),
        (lambda np: np.array([["a", "b"], ["c", "d"]], dtype=object), "a\nb\nc\nd"),
        (lambda np: np.array(["x", "yz"], dtype="U2"), "x\nyz"),
        (lambda np: np.array([b"x", b"yz"], dtype="S2"), "x\nyz"),
        (lambda np: np.array([], dtype=object), ""),
        (lambda np: np.array([b"a\0", b"\xffb", b"\0"], dtype="S2"), "a\n\ufffdb\n"),
        (lambda np: np.array([["a", "b"], ["c", "d"]], dtype="U1"), "a\nb\nc\nd"),
    ],
    ids=[
        "object",
        "object-bytes",
        "object-2d",
        "unicode",
        "bytes",
        "empty",
        "nul-padding-invalid-utf8",
        "unicode-2d",
    ],
)
def test_a_string_array_attribute_is_decoded_per_element(
    make: Any, expected: str
) -> None:
    """Regression: ``tobytes()`` of an object array is its pointers, so the
    decoded text differed from run to run."""
    numpy = pytest.importorskip("numpy")
    value = make(numpy)
    assert _decode_h5_attr(value) == expected
    assert _decode_h5_attr(value) == expected  # and again
    with patch.object(hdf5, "_DECODE_BLOCK", 2):  # several blocks: the same text
        assert _decode_h5_attr(value) == expected


def test_a_large_fixed_length_string_array_is_decoded_in_bounded_memory() -> None:
    """Regression: decoding each element into its own Python object cost
    ~160 bytes per element: 1 M distinct short strings reached 120 MB."""
    numpy = pytest.importorskip("numpy")
    count = 1_000_000
    value = numpy.arange(count).astype("S7")  # distinct, so none interned
    tracemalloc.start()
    try:
        text = _decode_h5_attr(value)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert text == "\n".join(map(str, range(count)))
    assert peak < 48_000_000, peak


_COMPOUND = [("a", "O"), ("b", "i4")]  # a string field, as h5py reads vlen text


def test_a_compound_attribute_with_a_string_field_is_unsupported() -> None:
    """Regression: its ``tobytes()`` held the string's pointer, so the text
    differed from run to run."""
    numpy = pytest.importorskip("numpy")
    with pytest.raises(ValueError, match="compound"):
        _decode_h5_attr(numpy.array([("x", 1)], dtype=_COMPOUND))
    plain = numpy.array([(b"x", 1)], dtype=[("a", "S1"), ("b", "i4")])
    assert _decode_h5_attr(plain) == _decode_h5_attr(plain.copy())  # no object


class _RaisingBackend(dict[str, Any]):
    """Root attributes whose ``backend`` cannot be converted, as in h5py."""

    def __init__(self, error: Exception, **attrs: Any) -> None:
        super().__init__(attrs)
        self.error = error

    def get(self, key: str, default: Any = None) -> Any:
        if key == "backend":
            raise self.error
        return super().get(key, default)


@pytest.mark.parametrize(
    "error", [TypeError("no NumPy equivalent"), OSError("no conversion path")]
)
def test_an_attribute_h5py_cannot_convert_loses_only_itself(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, error: Exception
) -> None:
    """Regression: the error escaped ``read_hdf5`` and the whole file read
    as failed."""
    attrs = _RaisingBackend(error, keras_version="2.15.0")
    meta, messages = _read_attrs(tmp_path, caplog, attrs)
    (message,) = messages
    assert "backend attribute cannot be read; " in message
    assert message.endswith("(skipped): properties.backend")
    assert "backend" not in meta.properties
    assert meta.format_info.framework_version == "2.15.0"


def test_a_real_file_with_unreadable_attributes_reads_the_same_twice(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An opaque attribute and a compound one with a string field: one
    warning each, and no pointer bytes, so two reads are equal."""
    h5py = pytest.importorskip("h5py")
    numpy = pytest.importorskip("numpy")
    path = tmp_path / "m.h5"
    with h5py.File(path, "w") as hf:
        opaque = h5py.h5t.create(h5py.h5t.OPAQUE, 4)
        opaque.set_tag(b"x")
        h5py.h5a.create(hf.id, b"backend", opaque, h5py.h5s.create(h5py.h5s.SCALAR))
        compound = numpy.array(
            [("x", 1)], dtype=[("a", h5py.string_dtype()), ("b", "i4")]
        )
        hf.attrs.create("model_config", compound)
        hf.attrs["keras_version"] = "2.15.0"
    first, second = read_hdf5(path), read_hdf5(path)
    assert first == second
    assert first.format_info.framework_version == "2.15.0"
    assert not first.properties and first.name is None
    messages = logged_warnings(caplog)
    assert [m.split(" attribute", 1)[0] for m in messages] == (
        ["model_config", "backend", "model_config", "backend"]
    )


def test_a_real_file_with_string_array_attributes_reads_the_same_twice(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    h5py = pytest.importorskip("h5py")
    numpy = pytest.importorskip("numpy")
    path = tmp_path / "m.h5"
    with h5py.File(path, "w") as hf:
        hf.attrs.create(
            "model_config",
            numpy.array([_model({"name": "m"})], dtype=h5py.string_dtype()),
        )
        hf.attrs.create(
            "backend", numpy.array(["tensorflow"], dtype=h5py.string_dtype())
        )
    first, second = read_hdf5(path), read_hdf5(path)
    assert (first.type_of_model, first.name) == ("Sequential", "m")
    assert first.properties["backend"] == "tensorflow"
    assert first == second
    assert not logged_warnings(caplog)


@pytest.mark.parametrize(
    "config",
    [{"class_name": 5, "config": {"name": 6}}, json.loads(_model({"name": 7}))],
)
def test_the_sbom_builds_for_a_file_with_non_string_names(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, config: dict[str, Any]
) -> None:
    """Regression: a ``class_name`` or ``name`` that is not a string reached
    the SBOM builder, which raised."""
    h5py = pytest.importorskip("h5py")
    path = tmp_path / "m.h5"
    with h5py.File(path, "w") as hf:
        hf.attrs["model_config"] = json.dumps(config)
    sbom = json.loads(generate_model_sbom(path))
    packages = [e for e in sbom["@graph"] if e["type"] == "ai_AIPackage"]
    assert len(packages) == 1 and isinstance(packages[0]["name"], str)
    assert len(logged_warnings(caplog)) == 1


@pytest.mark.parametrize("dtype", ["S10", "string"])
def test_an_attribute_with_an_empty_dataspace_is_absent_not_a_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, dtype: str
) -> None:
    """Regression: ``h5py.Empty`` has a dtype and no data (no ``reshape``), so
    reading it raised ``AttributeError``, outside what an attribute read
    catches, and the whole read became a stub."""
    h5py = pytest.importorskip("h5py")
    path = tmp_path / "m.h5"
    empty = h5py.Empty(h5py.string_dtype() if dtype == "string" else dtype)
    with h5py.File(path, "w") as hf:
        hf.attrs["keras_version"] = empty
        hf.attrs["backend"] = empty
        hf.attrs["model_config"] = _model({"name": "m"})
    meta = read_hdf5(path)
    assert (meta.type_of_model, meta.name) == ("Sequential", "m")
    assert meta.format_info.framework_version is None
    assert "backend" not in meta.properties
    assert not logged_warnings(caplog)
