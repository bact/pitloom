# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The shared rule that a blank text field states nothing: the helper, and
the Safetensors and ONNX readers that use it.

See also: :mod:`tests.extract.ai_model.test_gguf_text_fields` (GGUF).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.extract.ai_model._stated_text import first_stated_text, stated_text
from pitloom.extract.ai_model.onnx import read_onnx
from pitloom.extract.ai_model.safetensors import read_safetensors


@pytest.mark.parametrize(
    ("value", "scalar", "expected"),
    [
        (None, False, None),
        ("", False, None),
        (" \t\n", False, None),
        (" x ", False, "x"),
        (3, False, None),
        (3, True, "3"),
        (1.5, True, "1.5"),
        (True, True, None),
        (["x"], True, None),
    ],
    ids=[
        "none",
        "empty",
        "blank",
        "padded",
        "int",
        "int-scalar",
        "float",
        "bool",
        "list",
    ],
)
def test_stated_text(value: object, scalar: bool, expected: str | None) -> None:
    assert stated_text(value, scalar=scalar) == expected


def test_first_stated_text_skips_a_blank_value_to_the_next_key() -> None:
    fields = {"a": "  ", "b": "", "c": " C ", "d": "D"}
    assert first_stated_text(fields, ("a", "b", "c", "d")) == ("c", "C")
    assert first_stated_text(fields, ("a", "b", "missing")) is None


_ST_KEYS = {
    "name": ("modelspec.title", "name", "ss_base_model_version"),
    "description": ("modelspec.description", "description"),
    "version": ("modelspec.version", "version"),
    "architecture": ("modelspec.architecture", "architecture"),
    "quantization": ("modelspec.precision", "precision"),
}


def _safetensors(path: Path, metadata: dict[str, str]) -> Path:
    numpy = pytest.importorskip("numpy")
    save_file = pytest.importorskip("safetensors.numpy").save_file
    save_file({"w": numpy.zeros(2, dtype="float32")}, str(path), metadata=metadata)
    return path


@pytest.mark.parametrize("blank", ["", "  ", "\t"], ids=["empty", "spaces", "tab"])
@pytest.mark.parametrize("attr", sorted(_ST_KEYS))
def test_safetensors_blank_field_is_absent(
    attr: str, blank: str, tmp_path: Path
) -> None:
    metadata = dict.fromkeys(_ST_KEYS[attr], blank)
    meta = read_safetensors(_safetensors(tmp_path / "m.safetensors", metadata))
    assert getattr(meta, attr) is None
    assert attr not in meta.provenance


@pytest.mark.parametrize("attr", sorted(_ST_KEYS))
def test_safetensors_blank_first_key_gives_way_to_the_next(
    attr: str, tmp_path: Path
) -> None:
    first, second = _ST_KEYS[attr][:2]
    path = _safetensors(tmp_path / "m.safetensors", {first: " ", second: " v "})
    meta = read_safetensors(path)
    assert getattr(meta, attr) == "v"
    assert meta.provenance[attr].endswith("Field: __metadata__")


def _onnx(path: Path, doc_string: str) -> Path:
    helper = pytest.importorskip("onnx.helper")
    onnx = pytest.importorskip("onnx")
    graph = helper.make_graph([], "g", [], [])
    model = helper.make_model(graph, doc_string=doc_string)
    onnx.save(model, str(path))
    return path


@pytest.mark.parametrize(
    ("doc_string", "expected"),
    [("", None), ("   ", None), ("\n\t", None), ("  A model.\n", "A model.")],
    ids=["empty", "spaces", "ws", "padded"],
)
def test_onnx_blank_doc_string_is_no_description(
    doc_string: str, expected: str | None, tmp_path: Path
) -> None:
    meta = read_onnx(_onnx(tmp_path / "m.onnx", doc_string))
    assert meta.description == expected
    assert ("description" in meta.provenance) is (expected is not None)
