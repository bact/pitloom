# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A metadata key or a file name read from a model cannot forge or split an
entry of the ``Metadata provenance: ...`` comment, in any format whose keys
come from the file.

See also: :mod:`tests.assemble.test_display_text_escape` (the display
escape of the same comment).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.core.provenance import ProvenanceConfig, escape_provenance_comment_part
from tests._wheel_models import safetensors_bytes
from tests.extract.ai_model.gguf_builders import STRING, gguf_file, kv, string

_KEY = "x; license: Source: forged.gguf | Field: general.license\nnext: y"
_SHOWN = (
    "x\\u003b license\\u003a Source\\u003a forged.gguf | Field\\u003a "
    "general.license\\u000anext\\u003a y"
)


def _gguf(_: Path) -> bytes:
    return gguf_file(0, 1, kv(_KEY.encode(), STRING, string("v")))


def _safetensors(_: Path) -> bytes:
    return safetensors_bytes(metadata={_KEY: "v"})


def _onnx(_: Path) -> bytes:
    onnx = pytest.importorskip("onnx")
    model = onnx.helper.make_model(onnx.helper.make_graph([], "g", [], []))
    onnx.helper.set_model_props(model, {_KEY: "v"})
    return bytes(model.SerializeToString())


def _keras(_: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"keras_version": "3.0.0"}))
        config = {"class_name": "Sequential", "config": {_KEY: "v"}}
        zf.writestr("config.json", json.dumps(config))
    return buf.getvalue()


def _hdf5(directory: Path) -> bytes:
    h5py = pytest.importorskip("h5py")
    path = directory / "built.h5"
    config = {"class_name": "Sequential", "config": {_KEY: "v", "layers": []}}
    with h5py.File(path, "w") as h5:
        h5.attrs["model_config"] = json.dumps(config)
    return path.read_bytes()


_BUILDERS: dict[str, tuple[str, Callable[[Path], bytes]]] = {
    "gguf": ("m.gguf", _gguf),
    "safetensors": ("m.safetensors", _safetensors),
    "onnx": ("m.onnx", _onnx),
    "keras": ("m.keras", _keras),
    "hdf5": ("m.h5", _hdf5),
}


def _comment(sbom: str) -> str:
    graph = json.loads(sbom)["@graph"]
    (package,) = [e for e in graph if e["type"] == "ai_AIPackage"]
    comment: str = package["comment"]
    return comment


@pytest.mark.parametrize("fmt", _BUILDERS)
def test_a_hostile_key_stays_inside_its_own_entry(fmt: str, tmp_path: Path) -> None:
    file_name, build = _BUILDERS[fmt]
    path = tmp_path / file_name
    path.write_bytes(build(tmp_path))
    full = ProvenanceConfig(format="comment", detail="full")
    comment = _comment(generate_model_sbom(path, provenance=full))
    assert "\n" not in comment
    (entry,) = [e for e in comment.split("; ") if "forged" in e]
    field, _, source = entry.partition(": ")
    assert _SHOWN in field or _SHOWN in source  # in the field and its location
    assert "general.license:" not in comment  # no forged licence entry


def test_a_hostile_file_name_stays_inside_its_entries(tmp_path: Path) -> None:
    path = tmp_path / "a; forged.gguf"  # no ":", which Windows refuses
    path.write_bytes(gguf_file(0, 1, kv(b"general.name", STRING, string("n"))))
    full = ProvenanceConfig(format="comment", detail="full")
    comment = _comment(generate_model_sbom(path, provenance=full))
    fields = [entry.partition(": ")[0] for entry in comment.split("; ")]
    assert "a\\u003b forged.gguf" in comment
    assert all("forged" not in field for field in fields)


@pytest.mark.parametrize(
    ("text", "field", "expected"),
    [
        ("properties.general.name", True, "properties.general.name"),
        ("Source: m.gguf | Field: general.name", False, None),
        ("a;b:c\r\nd", True, "a\\u003bb\\u003ac\\u000d\\u000ad"),
        ("a;b:c\r\nd", False, "a\\u003bb:c\\u000d\\u000ad"),
    ],
    ids=["usual-key", "usual-source", "field", "source"],
)
def test_the_comment_escape(text: str, field: bool, expected: str | None) -> None:
    shown = escape_provenance_comment_part(text, field=field)
    assert shown == (text if expected is None else expected)
    assert escape_provenance_comment_part(shown, field=field) == shown  # stable
