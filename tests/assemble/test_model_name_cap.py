# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A 1 MiB model name read from a file is cut to
:data:`~pitloom.core.ai_metadata.MAX_MODEL_NAME_CHARS` code points, with one
``WARNING:``, the same way on every surface and every run.

See also: :mod:`tests.core.test_ai_metadata` (the cut itself) and
:mod:`tests.assemble.test_model_entry_cap` (the entry cap, same warning
path).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import generate_model_sbom
from pitloom.assemble._model_generator import enrich_model
from pitloom.assemble.spdx3._ai_package import _ai_model_entity_candidates
from pitloom.assemble.spdx3._document_model import build_model
from pitloom.core.ai_metadata import (
    MAX_MODEL_NAME_CHARS,
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    cap_model_name,
)
from pitloom.core.creation import CreationMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.project import ProjectFile
from pitloom.extract.scanner_project import scan_project_for_ai_models
from tests._wheel_models import safetensors_bytes
from tests.extract.ai_model.gguf_builders import STRING, gguf_file, kv, string
from tests.id_registry.surfaces_base import demo_project
from tests.warning_helpers import logged_warnings

_LONG = "n" * 2**20
_CUT = (
    _LONG[: MAX_MODEL_NAME_CHARS - 12]
    + "...~"
    + hashlib.sha256(_LONG.encode()).hexdigest()[:8]
)
_WARNING = f"model name of {len(_LONG)} characters cut to {MAX_MODEL_NAME_CHARS}"
_COMMON = ["--creation-datetime", "2026-01-01T00:00:00Z", "--offline"]


def _gguf(_: Path) -> bytes:
    return gguf_file(0, 1, kv(b"general.name", STRING, string(_LONG)))


def _safetensors(_: Path) -> bytes:
    return safetensors_bytes(metadata={"name": _LONG})


def _pt2(_: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("version", b"2")
        zf.writestr("METADATA.json", json.dumps({"name": _LONG}))
    return buf.getvalue()


def _onnx(_: Path) -> bytes:
    onnx = pytest.importorskip("onnx")
    graph = onnx.helper.make_graph([], _LONG, [], [])
    return bytes(onnx.helper.make_model(graph).SerializeToString())


def _hdf5(directory: Path) -> bytes:
    h5py = pytest.importorskip("h5py")
    path = directory / "built.h5"
    config = {"class_name": "Sequential", "config": {"name": _LONG, "layers": []}}
    with h5py.File(path, "w") as h5:
        h5.attrs["model_config"] = json.dumps(config)
    return path.read_bytes()


_BUILDERS: dict[str, tuple[str, Callable[[Path], bytes]]] = {
    "gguf": ("m.gguf", _gguf),
    "safetensors": ("m.safetensors", _safetensors),
    "pt2": ("m.pt2", _pt2),
    "onnx": ("m.onnx", _onnx),
    "hdf5": ("m.h5", _hdf5),
}


def _ai_package(sbom: str) -> dict[str, Any]:
    packages: list[dict[str, Any]] = [
        e for e in json.loads(sbom)["@graph"] if e["type"] == "ai_AIPackage"
    ]
    (package,) = packages
    return package


def _name_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [m for m in logged_warnings(caplog) if "model name of" in m]


@pytest.mark.parametrize("surface", ["model", "project"])
@pytest.mark.parametrize("fmt", _BUILDERS)
def test_a_long_name_is_cut_once_and_the_same_every_run(
    fmt: str,
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    file_name, build = _BUILDERS[fmt]
    data = build(tmp_path)
    if surface == "project":
        target = demo_project(tmp_path)
        (target / "demo" / file_name).write_bytes(data)
    else:
        target = tmp_path / file_name
        target.write_bytes(data)
    runs = []
    for run in range(2):
        caplog.clear()
        out = tmp_path / f"out{run}.json"
        argv = ["loom", surface, str(target), "-o", str(out), *_COMMON]
        monkeypatch.setattr(sys, "argv", argv)
        assert __main__.main() == 0
        (message,) = _name_warnings(caplog)
        assert _WARNING in message
        assert "FILE=" in message
        runs.append(out.read_bytes())
    assert runs[0] == runs[1]
    package = _ai_package(runs[0].decode())
    assert package["name"] == _CUT
    assert len(package["name"]) == MAX_MODEL_NAME_CHARS
    assert len(package["spdxId"]) < 2 * MAX_MODEL_NAME_CHARS + 200


@pytest.mark.parametrize(
    "surface", [generate_model_sbom, enrich_model], ids=["generate", "enrich"]
)
def test_the_library_api_cuts_and_warns_once(
    surface: Callable[..., object],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(_gguf(tmp_path))
    surface(path, output_path=tmp_path / "out.json")
    (message,) = _name_warnings(caplog)
    assert _WARNING in message
    text = (tmp_path / "out.json").read_text(encoding="utf-8")
    names = [e.get("name") for e in json.loads(text)["@graph"]]
    assert _LONG not in names
    if surface is generate_model_sbom:  # an enrich fragment names no package
        assert _CUT in names


def test_the_registry_looks_up_the_cut_name(tmp_path: Path) -> None:
    """Both id paths see one name: the registry candidate is the shown name."""
    (tmp_path / "m.gguf").write_bytes(_gguf(tmp_path))
    # pylint: disable-next=unbalanced-tuple-unpacking
    (model,) = scan_project_for_ai_models(
        tmp_path,
        [ProjectFile(physical_path="m.gguf", distribution_path="m.gguf")],
        scan_usage=False,
        usage_hint=lambda: False,
    )
    assert model.name == _LONG  # the read value stays as read
    assert _ai_model_entity_candidates(model)[0] == model.resolve_name()[0] == _CUT


def test_the_names_a_model_brings_in_are_cut_too(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A base model, a dataset and a dataset creator: each name cut as the
    model's own, said once each in the same words, its id from the cut."""
    model = AiModelMetadata(
        name="m",
        format_info=AiModelFormatInfo(
            file_name="m.gguf", model_format=AiModelFormat.GGUF
        ),
        base_model=f"org/{_LONG}",
        datasets=[
            DatasetReference(
                role="trainedOn",
                metadata=DatasetMetadata(name=_LONG + "d", creator=_LONG + "c"),
            )
        ],
    )
    sbom = build_model(model, CreationMetadata()).to_json()
    graph = json.loads(sbom)["@graph"]
    names = {e["type"]: e["name"] for e in graph if "name" in e and e["name"] != "m"}
    assert {len(names[t]) for t in ("dataset_DatasetPackage", "Agent")} == {
        MAX_MODEL_NAME_CHARS
    }
    base = [e for e in graph if e["type"] == "ai_AIPackage" and e["name"] != "m"]
    assert [e["name"] for e in base] == [cap_model_name(_LONG)]
    assert sorted(m.split(": ", 1)[1] for m in logged_warnings(caplog)) == [
        f"{label} of {length} characters cut to {MAX_MODEL_NAME_CHARS}"
        for label, length in (
            ("base model name", len(_LONG)),
            ("dataset creator name", len(_LONG) + 1),
            ("dataset name", len(_LONG) + 1),
        )
    ]
