# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The model-field entries (``model-field-unreadable``, ``model-field-conflict``,
``field-not-recordable``): their lines, read back after the scan's frame,
the values they refuse, and every reader site that says one.

See also: tests/test_model_field_surfaces.py (the surfaces) and
tests/messages/test_model_stub.py (a model not read at all).
"""

# pylint: disable=protected-access

from __future__ import annotations

import io
import logging
import pickle  # nosec B403
import struct
import zipfile
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import _hdf5_warnings, fasttext, onnx, pytorch
from pitloom.extract.ai_model import pytorch_pt2 as pt2
from pitloom.extract.ai_model.hdf5 import read_hdf5
from pitloom.extract.ai_model.hdf5_config import ConfigProblem, ConfigShapeError
from pitloom.extract.ai_model.keras import read_keras
from pitloom.extract.ai_model.keras_training_config import parse_training_config
from pitloom.extract.ai_model.unrecordable import UNRECORDABLE, log_unrecordable
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    RELAY_FRAME,
    Line,
    relay_extra,
    trusted_message,
)
from pitloom.messages._model_field import ENTRIES
from pitloom.messages.model_fields import (
    FIELD_NOT_RECORDABLE,
    MODEL_FIELD_CONFLICT,
    MODEL_FIELD_UNREADABLE,
)
from tests._message_drift import SAMPLES
from tests.extract.ai_model.gguf_builders import UINT8, UINT32, array, gguf_file, kv
from tests.extract.ai_model.zip_builders import dated_zip

_LINES = [(m, ln) for m in ENTRIES for ln in m.lines]


def test_the_entries() -> None:
    assert [m.code for m in ENTRIES] == [
        "model-field-unreadable",
        "model-field-conflict",
        "field-not-recordable",
    ]
    assert {m.since for m in ENTRIES} == {"0.23.0"}
    assert [(m.effect, m.actor) for m in ENTRIES] == [
        ("thinner", "user"),
        ("none", "none"),
        ("weaker", "none"),
    ]
    assert FIELD_NOT_RECORDABLE.levels == {"INFO"}


@pytest.mark.parametrize(
    ("message", "line"), _LINES, ids=[ln.template[:30] for _, ln in _LINES]
)
def test_a_line_keeps_its_code_through_the_scans_frame(
    message: Any, line: Line
) -> None:
    """A reader's line is said again after ``FORMAT=... FILE=...: `` (a
    ``WARNING``); an error holding a line break is escaped first."""
    values = {name: SAMPLES[name] for name in line.fields}
    if "error" in values:
        values["error"] = "bad\nINFO: forged"
    text = line.render(values)
    assert "\n" not in text
    if line.level == "WARNING":
        text = RELAY_FRAME.render({"format": "hdf5", "file": "d/m.h5"}) + text
    assert relay_extra(message.code, line.level, text) == {CODE_ATTR: message.code}
    assert trusted_message(f"{line.level}: {text} [{message.code}]") is message


@pytest.mark.parametrize(
    ("values", "line"),
    [
        ({"fields": "type_of_model"}, None),
        ({"fields": ()}, None),
        ({"fields": ("type_of_model [x]",)}, None),
        ({"part": "model config"}, MODEL_FIELD_UNREADABLE.lines[10]),
        ({"number": -1}, MODEL_FIELD_CONFLICT.lines[1]),
        ({"elements": ("model-architecture",)}, FIELD_NOT_RECORDABLE.lines[0]),
    ],
    ids=["fields-text", "fields-empty", "fields-forged", "part", "number", "elements"],
)
def test_a_value_out_of_shape_is_refused(
    values: dict[str, object], line: Line | None
) -> None:
    shape = line or MODEL_FIELD_UNREADABLE.lines[0]
    given = {name: SAMPLES[name] for name in shape.fields} | values
    with pytest.raises(ValueError):
        shape.render(given)


def _raise() -> None:
    raise RuntimeError("binding")


#: A fastText model whose binding raises on every call.
_BROKEN = SimpleNamespace(f=SimpleNamespace(getArgs=_raise), get_labels=_raise)


def _zip(files: dict[str, bytes]) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(dated_zip(files)))


def _pt2(tmp_path: Path, files: dict[str, bytes]) -> None:
    path = tmp_path / "m.pt2"
    path.write_bytes(dated_zip(files))
    pt2.read_pytorch_pt2(path)


def _fickling_walk(_: Path) -> None:
    pytest.importorskip("fickling")
    with mock.patch.object(pytorch, "_top_class", side_effect=RuntimeError("walk")):
        pytorch._fickling_get_top_class(io.BytesIO(pickle.dumps(1)))


def _pickle_member(_: Path) -> None:
    broken = mock.patch.object(
        pytorch, "_fickling_get_top_class", side_effect=OSError("bad")
    )
    with broken, _zip({"archive/data.pkl": b""}) as zf:
        pytorch._read_pytorch_zip(zf, "Source: m.pt")


def _gguf(tmp_path: Path) -> None:
    pytest.importorskip("gguf")
    body = array(UINT8, 2, b"\0\0", key=b"x") + kv(
        b"x.length", UINT32, struct.pack("<I", 99)
    )
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 2, body))
    from pitloom.extract.ai_model.gguf import (  # pylint: disable=C0415
        read_gguf,
    )

    read_gguf(path)


def _keras_member(tmp_path: Path) -> None:
    path = tmp_path / "m.keras"
    path.write_bytes(dated_zip({"metadata.json": b"{", "config.json": b"{}"}))
    read_keras(path)


_H5 = AiModelFormat.HDF5
_PROBLEM = ConfigProblem("model_config.config", "is not an object", ("name",))

#: Each reader site: how to reach it, and the code its one record carries.
_SITES: dict[str, tuple[Callable[[Path], object], str]] = {
    "fasttext-args": (lambda _: fasttext._extract_fasttext_args(_BROKEN), "u"),
    "fasttext-labels": (lambda _: fasttext._extract_fasttext_labels(_BROKEN), "u"),
    "fickling-parse": (lambda _: pytorch._bounded_pickle(io.BytesIO(b"x")), "u"),
    "fickling-walk": (_fickling_walk, "u"),
    "pickle-member": (_pickle_member, "u"),
    "pt2-meta": (lambda p: _pt2(p, {"METADATA.json": b"{bad"}), "u"),
    "pt2-extra": (lambda _: pt2._read_pt2_text(_zip({}), "extra/name", "name"), "u"),
    "pt2-tags": (lambda p: _pt2(p, {"mdl/extra/tags": b"not json"}), "u"),
    "pt2-graph": (lambda p: _pt2(p, {"v": b"", "models/model.json": b"{"}), "u"),
    "pt2-version": (
        lambda _: pt2._read_pt2_format_version(_zip({}), "", ["archive_version"], ""),
        "u",
    ),
    "attribute": (
        lambda _: _hdf5_warnings.log_attribute_problem("backend", OSError("x")),
        "u",
    ),
    "config-raw": (
        lambda _: _hdf5_warnings.log_model_config_problem(
            _PROBLEM, "{}", True, _H5, ""
        ),
        "u",
    ),
    "config-raw-cut": (
        lambda _: _hdf5_warnings.log_model_config_problem(
            _PROBLEM, "x" * 501, True, _H5, ""
        ),
        "u",
    ),
    "config-kept": (
        lambda _: _hdf5_warnings.log_model_config_problem(
            _PROBLEM, "{}", False, _H5, ""
        ),
        "u",
    ),
    "training-config": (
        lambda _: _hdf5_warnings.log_training_config_problem(
            parse_training_config("[]", "", {}, {})
        ),
        "u",
    ),
    "keras-member": (_keras_member, "u"),
    "raw-config-cap": (
        lambda _: _hdf5_warnings.log_model_config_problem(
            None, "x" * 501, True, _H5, "m"
        ),
        "over-cap",
    ),
    "gguf-length": (_gguf, "c"),
    "onnx-repeated": (lambda _: onnx._warn_repeated_keys(list("abcd")), "c"),
    "not-recordable": (lambda _: log_unrecordable("gguf", "m", UNRECORDABLE), "n"),
}
_CODES = {
    "u": MODEL_FIELD_UNREADABLE.code,
    "c": MODEL_FIELD_CONFLICT.code,
    "n": FIELD_NOT_RECORDABLE.code,
}


@pytest.mark.parametrize("site", _SITES)
def test_each_reader_site_says_its_code(
    site: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """One coded record per site (the autouse drift check holds its text to
    the catalogue)."""
    reach, code = _SITES[site]
    with caplog.at_level(logging.INFO, logger="pitloom"):
        reach(tmp_path)
    coded = [getattr(r, CODE_ATTR) for r in caplog.records if hasattr(r, CODE_ATTR)]
    assert coded == [_CODES.get(code, code)]


def test_the_onnx_line_names_the_first_keys_and_how_many(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        onnx._warn_repeated_keys(list("abcd"))
    assert [r.getMessage() for r in caplog.records] == [
        "ONNX metadata_props: 4 key(s) appear more than once; kept the last value "
        "of each: a, b, c, ..."
    ]


def test_a_config_problem_names_its_first_part_then_every_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def too_deep(_: object) -> str:
        raise RecursionError

    monkeypatch.setattr(
        "pitloom.extract.ai_model.keras_training_config.canonical_json", too_deep
    )
    raw = '{"optimizer": 1, "loss": ["x"]}'
    problem = parse_training_config(raw, "", {}, {})
    assert problem is not None
    assert problem == ConfigProblem(
        "training_config.optimizer",
        "is not an object; training_config.loss is nested too deeply",
        ("properties.optimizer", "properties.loss"),
    )
    assert problem.text == f"{problem.part} {problem.error}"


def test_a_config_shape_error_keeps_its_part_through_a_pickle() -> None:
    error = ConfigShapeError("layers[0]", "is not an object")
    copied = pickle.loads(pickle.dumps(error))  # nosec B301
    assert (copied.part, copied.reason, str(copied)) == (
        "layers[0]",
        "is not an object",
        "layers[0] is not an object",
    )


@pytest.mark.parametrize(
    ("raw", "kept"),
    [
        ("x" * 501, ", the first 500 of 501 characters"),
        ("x" * 500, ""),
    ],
    ids=["cut", "whole"],
)
def test_a_kept_raw_config_says_whether_it_was_cut(
    raw: str, kept: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        _hdf5_warnings.log_model_config_problem(_PROBLEM, raw, True, _H5, "")
    (record,) = caplog.records
    assert record.getMessage() == (
        "model_config.config is not an object; kept as "
        f"properties.model_config_raw{kept} | Field(s) affected (skipped): name"
    )


def test_an_error_without_text_is_named_by_its_class(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A reader's line never fails to print: an exception with no message
    gives its class name, one with a line break one line."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        pt2._read_pt2_text(_zip({"extra/name": b""}), "extra/name\n", "name")
        with mock.patch.object(pt2, "read_archive_member", side_effect=OSError()):
            pt2._read_pt2_text(_zip({}), "extra/name", "name")
    assert [r.getMessage() for r in caplog.records] == [
        "Failed to read PT2 extra file 'extra/name\\n': \"There is no item named "
        "'extra/name\\\\n' in the archive\" | Field(s) affected (skipped): name",
        "Failed to read PT2 extra file extra/name: OSError | Field(s) affected "
        "(skipped): name",
    ]


@pytest.mark.parametrize(
    ("keras_version", "fmt"), [(None, "hdf5"), ("2.15.0", "keras")], ids=str
)
def test_the_raw_config_cap_names_the_model_as_its_siblings_do(
    keras_version: str | None,
    fmt: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Read on its own, not through a scan, the cut names the format the
    reader found (Keras when the file states a Keras version) and the file."""
    h5py = pytest.importorskip("h5py")
    path = tmp_path / "m.h5"
    config = '{"pad": "' + "x" * 600 + '"}'
    with h5py.File(path, "w") as hf:
        hf.attrs["model_config"] = config
        if keras_version is not None:
            hf.attrs["keras_version"] = keras_version
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read_hdf5(path)
    assert [r.getMessage() for r in caplog.records] == [
        f"FORMAT={fmt} FILE={path}: larger than the 500-character "
        f"raw-model-config cap; the first 500 of {len(config)} characters kept "
        "in properties.model_config_raw"
    ]
