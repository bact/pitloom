# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Issue #514 on every route that reads a project's or a file's models: a
Gemma-4-sized GGUF tokeniser is read whole, a GGUF header past a bound is
read in part with one ``over-cap`` warning, and an ONNX graph named by its
tool (``merged``) gives the file's stem as the model's name. Routes: the
CLI's ``project``, ``generate`` and ``model``, the library's
``generate_project_sbom`` and ``generate_model_sbom``, and the Hatchling
build hook's real ``initialize()``. The GitHub Action runs the CLI.

See also: tests/extract/ai_model/test_gguf_bounds.py and
tests/test_model_producer_surfaces.py (the same routes, another field).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import struct
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import generate_model_sbom, generate_project_sbom
from tests._author_routes import CREATED, hook_sbom, isolate
from tests.extract.ai_model.gguf_builders import (
    ARRAY,
    STRING,
    UINT8,
    gguf_with_tensors,
    kv,
    string,
    tensor_info,
    tokeniser,
)
from tests.warning_helpers import stderr_warnings

pytestmark = pytest.mark.platform  # model files read from disk

_PYPROJECT = b"""\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0.0"
"""
_GEMMA = "gemma.gguf"
_PARTIAL = "partial.gguf"
_MERGED = "decoder_model_merged.onnx"
#: Five levels of arrays, one past the bound.
_TOO_DEEP = struct.pack("<IQ", ARRAY, 1) * 4 + struct.pack("<IQ", UINT8, 1) + b"\0"
_PARTIAL_WARNING = (
    "larger than the 4-level GGUF-array-nesting cap; deep length as declared; "
    "later fields and the tensor shapes not read [over-cap]"
)


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("gguf")
    pytest.importorskip("onnx")
    isolate(tmp_path, monkeypatch)


def _models() -> dict[str, bytes]:
    onnx: Any = pytest.importorskip("onnx")
    graph = onnx.helper.make_graph([], "merged", [], [])
    merged = onnx.helper.make_model(graph, producer_name="onnx.quantize")
    gemma = (
        kv(b"general.architecture", STRING, string("gemma4"))
        + kv(b"general.name", STRING, string("Gemma shape"))
        + tokeniser(262_144, 514_906)
    )
    partial = (
        kv(b"general.name", STRING, string("Partly read"))
        + kv(b"deep", ARRAY, _TOO_DEEP)
        + kv(b"later", UINT8, b"\0")
    )
    return {
        _GEMMA: gguf_with_tensors([tensor_info("w", (4,))], 6, gemma, data_bytes=16),
        _PARTIAL: gguf_with_tensors([tensor_info("w", (4,))], 3, partial, 16),
        _MERGED: merged.SerializeToString(),
    }


def _project(base: Path) -> Path:
    project = base / "demo"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_bytes(b"")
    (project / "pyproject.toml").write_bytes(_PYPROJECT)
    for name, data in _models().items():
        (project / "demo" / name).write_bytes(data)
    return project


def _run(mp: pytest.MonkeyPatch, base: Path, *args: str | Path) -> list[str]:
    """The SBOMs the CLI writes for ``loom *args*``, one per model file
    when *args* end in files."""
    out = base / "out.json"
    mp.setattr(sys, "argv", ["loom", *map(str, args), "-o", str(out)])
    assert __main__.main() == 0
    return [out.read_text(encoding="utf-8")]


def _cli(command: str) -> Callable[[Path, pytest.MonkeyPatch], list[str]]:
    def run(base: Path, mp: pytest.MonkeyPatch) -> list[str]:
        return _run(mp, base, command, _project(base), "--offline")

    return run


def _cli_model(base: Path, mp: pytest.MonkeyPatch) -> list[str]:
    sboms = []
    for name, data in _models().items():
        path = base / name
        path.write_bytes(data)
        sboms += _run(mp, base, "model", path)
    return sboms


def _lib_project(base: Path, _mp: pytest.MonkeyPatch) -> list[str]:
    return [
        generate_project_sbom(_project(base), creation_metadata=CREATED, offline=True)
    ]


def _lib_model(base: Path, _mp: pytest.MonkeyPatch) -> list[str]:
    sboms = []
    for name, data in _models().items():
        path = base / name
        path.write_bytes(data)
        sboms.append(generate_model_sbom(path, creation_metadata=CREATED))
    return sboms


def _hook(base: Path, _mp: pytest.MonkeyPatch) -> list[str]:
    return [hook_sbom(_project(base))]


_ROUTES = {
    "cli-project": _cli("project"),
    "cli-generate": _cli("generate"),
    "cli-model": _cli_model,
    "lib-project": _lib_project,
    "lib-model": _lib_model,
    "hook": _hook,
}


def _packages(sboms: list[str]) -> dict[str, dict[str, Any]]:
    """Every ``ai_AIPackage`` of *sboms* by name."""
    found = {}
    for sbom in sboms:
        for element in json.loads(sbom)["@graph"]:
            if element["type"] == "ai_AIPackage":
                found[element["name"]] = element
    return found


@pytest.mark.parametrize("route", _ROUTES)
def test_issue_514_on_every_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    route: str,
) -> None:
    sboms = _ROUTES[route](tmp_path, monkeypatch)
    # Each GGUF name is read from its header, the ONNX one is the stem.
    assert set(_packages(sboms)) == {
        "Gemma shape",
        "Partly read",
        "decoder_model_merged",
    }
    warnings = stderr_warnings(capsys.readouterr().err)
    assert [w for w in warnings if "[over-cap]" in w] == [
        w for w in warnings if w.endswith(_PARTIAL_WARNING)
    ]
    assert len([w for w in warnings if w.endswith(_PARTIAL_WARNING)]) == 1
