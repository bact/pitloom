# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model's producer (``originatedBy``) and parameter count (``parameters``)
on every route that reads a model: a project directory (``project`` and
``generate``, the library API, the Hatchling build hook's real
``initialize()``), a built wheel (``wheel``, ``wheel --embed``,
``embed-wheel``, the library API), ``loom model`` per file, an ONNX file
and a Hugging Face repository.

Each gives the same Agents, in the same order, the same count text and the
count's comment note. Only the Hugging Face route has a ``suppliedBy``, the
repository owner, the same element as its originator; no model file format
gives one.

See also: tests/assemble/test_ai_originators.py and
tests/assemble/test_ai_parameter_count.py (assembly),
tests/test_author_surfaces.py (the main package's authors).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import io
import json
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from pitloom import __main__
from pitloom.assemble import (
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.core.model_parameters import PARAMETER_COUNT_KEY, PARAMETER_COUNT_NOTE
from pitloom.embed import embed_wheel_sbom
from pitloom.extract.ai_model.reader import read_ai_model
from tests._author_routes import CREATED, hook_sbom, isolate
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.extract.ai_model.gguf_builders import STRING, gguf_with_tensors, kv, string
from tests.extract.remote.hf_patches._hf_patches_base import _patch_hf_calls
from tests.warning_helpers import stderr_warnings

_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0.0"
"""
#: Five elements: one tensor of ``1 + 4`` values.
_ELEMENTS = "5"
_BIDI = "Al\u202eice"
_BIDI_ESCAPED = "Al\\u202eice"
_NAME_LABEL = "model originator name"


class _Summary(NamedTuple):
    """What a route says of one ``ai_AIPackage``."""

    agents: list[str]  # the ``originatedBy`` names, in order
    parameters: str | None  # the ``parameters`` entry's text
    supplier: str | None = None  # the ``suppliedBy`` name


#: Package (its file's stem) -> what every route must say of it.
_EXPECTED = {
    "alice": _Summary(["Alice"], None),
    "weights": _Summary([], _ELEMENTS),
}
#: A route: build the SBOM from a fresh directory, with this author for the
#: PT2 model.
_Route = Callable[[Path, pytest.MonkeyPatch, str], str]


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolate(tmp_path, monkeypatch)


def _models(author: str) -> dict[str, bytes]:
    """A PT2 Archive by *author* and a Safetensors file of 5 elements."""
    pt2 = io.BytesIO()
    with zipfile.ZipFile(pt2, "w") as archive:
        archive.writestr("mdl/extra/author", author)
    return {
        "alice.pt2": pt2.getvalue(),
        "weights.safetensors": safetensors_bytes(extra=4),
    }


def _project(base: Path, author: str) -> Path:
    project = base / "demo"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_bytes(b"")
    (project / "pyproject.toml").write_bytes(_PYPROJECT.encode())
    for name, data in _models(author).items():
        (project / "demo" / name).write_bytes(data)
    return project


def _wheel(base: Path, author: str) -> Path:
    members = {f"demo/{n}": d for n, d in _models(author).items()}
    return write_model_wheel(base / "dist", members)


def _embedded(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        (name,) = [n for n in archive.namelist() if "/sboms/" in n]
        return archive.read(name).decode("utf-8")


def _run(mp: pytest.MonkeyPatch, base: Path, *args: str | Path) -> str:
    """The SBOM the CLI writes for ``loom *args*``."""
    out = base / "out.json"
    mp.setattr(sys, "argv", ["loom", *map(str, args), "-o", str(out)])
    assert __main__.main() == 0
    return out.read_text(encoding="utf-8")


def _cli_project(base: Path, mp: pytest.MonkeyPatch, author: str) -> str:
    return _run(mp, base, "project", _project(base, author), "--offline")


def _cli_generate(base: Path, mp: pytest.MonkeyPatch, author: str) -> str:
    return _run(mp, base, "generate", _project(base, author), "--offline")


def _cli_wheel(base: Path, mp: pytest.MonkeyPatch, author: str) -> str:
    return _run(mp, base, "wheel", _wheel(base, author), "--offline")


def _cli_wheel_embed(base: Path, mp: pytest.MonkeyPatch, author: str) -> str:
    wheel = _wheel(base, author)
    _run(mp, base, "wheel", wheel, "--embed", "--offline")
    return _embedded(wheel)


def _cli_embed_wheel(base: Path, mp: pytest.MonkeyPatch, author: str) -> str:
    wheel = _wheel(base, author)
    _run(mp, base, "embed-wheel", wheel, "--offline")
    return _embedded(wheel)


def _lib_project(base: Path, _mp: pytest.MonkeyPatch, author: str) -> str:
    return generate_project_sbom(
        _project(base, author), creation_metadata=CREATED, offline=True
    )


def _lib_wheel(base: Path, _mp: pytest.MonkeyPatch, author: str) -> str:
    return generate_wheel_sbom(_wheel(base, author), creation_metadata=CREATED)


def _lib_embed(base: Path, _mp: pytest.MonkeyPatch, author: str) -> str:
    wheel = _wheel(base, author)
    embed_wheel_sbom(wheel, creation_metadata=CREATED)
    return _embedded(wheel)


def _hook(base: Path, _mp: pytest.MonkeyPatch, author: str) -> str:
    return hook_sbom(_project(base, author))


def _model_route(file_name: str) -> _Route:
    def run(base: Path, mp: pytest.MonkeyPatch, author: str) -> str:
        path = base / file_name
        path.write_bytes(_models(author)[file_name])
        return _run(mp, base, "model", path)

    return run


#: route -> (build the SBOM, the packages it lists)
_ROUTES: dict[str, tuple[_Route, tuple[str, ...]]] = {
    "cli-project": (_cli_project, ("alice", "weights")),
    "cli-generate": (_cli_generate, ("alice", "weights")),
    "cli-wheel": (_cli_wheel, ("alice", "weights")),
    "cli-wheel-embed": (_cli_wheel_embed, ("alice", "weights")),
    "cli-embed-wheel": (_cli_embed_wheel, ("alice", "weights")),
    "lib-project": (_lib_project, ("alice", "weights")),
    "lib-wheel": (_lib_wheel, ("alice", "weights")),
    "lib-embed": (_lib_embed, ("alice", "weights")),
    "hook": (_hook, ("alice", "weights")),
    "model-pt2": (_model_route("alice.pt2"), ("alice",)),
    "model-st": (_model_route("weights.safetensors"), ("weights",)),
}


def _graph(sbom: str) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    return graph


def _summaries(sbom: str) -> dict[str, _Summary]:
    """Each ``ai_AIPackage`` by name, after checking what holds for every
    package: its originators and supplier are ``Agent``s, and the count's
    comment note exactly when there is a count."""
    graph = _graph(sbom)
    by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
    found: dict[str, _Summary] = {}
    for package in (e for e in graph if e["type"] == "ai_AIPackage"):
        agents = [by_id[i] for i in package.get("originatedBy", [])]
        supplier = by_id.get(package.get("suppliedBy", ""))
        named = agents + ([supplier] if supplier else [])
        assert {a["type"] for a in named} <= {"Agent"}
        counts = [
            h["value"]
            for h in package.get("ai_hyperparameter", [])
            if h["key"] == PARAMETER_COUNT_KEY
        ]
        assert (PARAMETER_COUNT_NOTE in package.get("comment", "")) == bool(counts)
        found[package["name"]] = _Summary(
            [a["name"] for a in agents],
            counts[0] if counts else None,
            supplier["name"] if supplier else None,
        )
    return found


@pytest.mark.parametrize("route", _ROUTES)
def test_producer_and_count_on_every_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    pytest.importorskip("safetensors")
    run, packages = _ROUTES[route]
    summaries = _summaries(run(tmp_path, monkeypatch, "Alice"))
    assert summaries == {name: _EXPECTED[name] for name in packages}


@pytest.mark.parametrize("route", ["cli-project", "cli-wheel", "hook"])
def test_a_route_is_byte_identical_when_run_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    pytest.importorskip("safetensors")
    run = _ROUTES[route][0]
    runs = []
    for label in ("first", "second"):
        base = tmp_path / label
        base.mkdir()
        runs.append(run(base, monkeypatch, "Alice"))
    assert "Alice" in runs[0]  # not vacuous: the SBOM names the model's author
    assert runs[0] == runs[1]


@pytest.mark.parametrize("route", [r for r in _ROUTES if r != "model-st"])
def test_an_originator_with_a_bidi_control_is_escaped_with_one_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    route: str,
) -> None:
    pytest.importorskip("safetensors")
    sbom = _ROUTES[route][0](tmp_path, monkeypatch, _BIDI)
    named = [w for w in stderr_warnings(capsys.readouterr().err) if _NAME_LABEL in w]
    assert len(named) == 1
    assert _summaries(sbom)["alice"].agents == [_BIDI_ESCAPED]


def _onnx_model(path: Path) -> None:
    onnx: Any = pytest.importorskip("onnx")
    initializers = [
        onnx.TensorProto(name="a", data_type=onnx.TensorProto.FLOAT, dims=[2, 3]),
        onnx.TensorProto(name="b", data_type=onnx.TensorProto.FLOAT, dims=[4]),
    ]
    graph = onnx.helper.make_graph([], "net", [], [], initializers)
    model = onnx.helper.make_model(graph)
    entry = model.metadata_props.add()
    entry.key, entry.value = "model_author", "Alice, Bob"
    path.write_bytes(model.SerializeToString())


def _onnx_model_route(base: Path, mp: pytest.MonkeyPatch) -> str:
    _onnx_model(base / "net.onnx")
    return _run(mp, base, "model", base / "net.onnx")


def _onnx_project_route(base: Path, mp: pytest.MonkeyPatch) -> str:
    pytest.importorskip("safetensors")
    project = _project(base, "Alice")
    _onnx_model(project / "demo" / "net.onnx")
    return _run(mp, base, "project", project, "--offline")


@pytest.mark.parametrize(
    "route",
    [_onnx_model_route, _onnx_project_route],
    ids=["model", "project"],
)
def test_onnx_author_list_gives_two_agents_and_the_initializer_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    route: Callable[[Path, pytest.MonkeyPatch], str],
) -> None:
    summaries = _summaries(route(tmp_path, monkeypatch))
    assert summaries["net"] == _Summary(["Alice", "Bob"], "10")


@pytest.mark.parametrize("cli", [False, True], ids=["library", "cli"])
def test_hugging_face_owner_and_stated_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli: bool
) -> None:
    with _patch_hf_calls(hub_info={"author": "acme", "safetensors_total": 7}):
        if cli:
            sbom = _run(monkeypatch, tmp_path, "model", "acme/model")
        else:
            sbom = generate_model_sbom("acme/model", creation_metadata=CREATED)
    assert list(_summaries(sbom).values()) == [_Summary(["acme"], "7", "acme")]
    (package,) = [e for e in _graph(sbom) if e["type"] == "ai_AIPackage"]
    assert package["originatedBy"] == [package["suppliedBy"]]  # one element


def _gguf_file(path: Path, author: str) -> None:
    pytest.importorskip("gguf")
    pair = kv(b"general.author", STRING, string(author))
    path.write_bytes(gguf_with_tensors([], 1, pair))


def _onnx_file(path: Path, _author: str) -> None:
    _onnx_model(path)  # by "Alice, Bob"


def _pt2_file(path: Path, author: str) -> None:
    path.write_bytes(_models(author)["alice.pt2"])


def _safetensors_file(path: Path, author: str) -> None:
    pytest.importorskip("safetensors")
    path.write_bytes(safetensors_bytes(metadata={"modelspec.author": author}))


#: Model file format -> (its suffix, a writer of a file whose author is
#: ``Alice``).
_AUTHORED_FILES: dict[str, tuple[str, Callable[[Path, str], None]]] = {
    "gguf": (".gguf", _gguf_file),
    "onnx": (".onnx", _onnx_file),
    "pt2": (".pt2", _pt2_file),
    "safetensors": (".safetensors", _safetensors_file),
}


@pytest.mark.parametrize("fmt", _AUTHORED_FILES)
def test_no_model_file_format_gives_a_supplier(tmp_path: Path, fmt: str) -> None:
    """Drift guard: a file-declared author is an originator only; the
    reader keeps no supplier and the package has no ``suppliedBy``."""
    suffix, write = _AUTHORED_FILES[fmt]
    path = tmp_path / f"m{suffix}"
    write(path, "Alice")
    meta = read_ai_model(path)
    assert meta.originators[0] == "Alice"  # not vacuous: an author was read
    assert meta.supplier is None
    sbom = generate_model_sbom(path, creation_metadata=CREATED)
    summaries = list(_summaries(sbom).values())
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.agents[0] == "Alice"
    assert summary.supplier is None
