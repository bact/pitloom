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

from pitloom.extract.ai_model import _hdf5_warnings, fasttext, onnx, pytorch
from pitloom.extract.ai_model import pytorch_pt2 as pt2
from pitloom.extract.ai_model.hdf5_config import (
    ConfigProblem,
    ConfigShapeError,
    parse_training_config,
)
from pitloom.extract.ai_model.unrecordable import UNRECORDABLE, log_unrecordable
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    FIELD_NOT_RECORDABLE,
    MODEL_FIELD_CONFLICT,
    MODEL_FIELD_UNREADABLE,
    RELAY_FRAME,
    Line,
    relay_extra,
    trusted_message,
)
from pitloom.messages._model_field import ENTRIES
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
        lambda _: _hdf5_warnings.log_model_config_problem(_PROBLEM, "{}", True, ""),
        "u",
    ),
    "config-raw-cut": (
        lambda _: _hdf5_warnings.log_model_config_problem(
            _PROBLEM, "x" * 501, True, ""
        ),
        "u",
    ),
    "config-kept": (
        lambda _: _hdf5_warnings.log_model_config_problem(_PROBLEM, "{}", False, ""),
        "u",
    ),
    "training-config": (
        lambda _: _hdf5_warnings.log_training_config_problem(
            parse_training_config("[]", "", {}, {})
        ),
        "u",
    ),
    "raw-config-cap": (
        lambda _: _hdf5_warnings.log_model_config_problem(None, "x" * 501, True, "m"),
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

    monkeypatch.setattr("pitloom.extract.ai_model.hdf5_config.canonical_json", too_deep)
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
