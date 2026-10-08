# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Invisible and bidi controls read from a model file are escaped in the
AI package's display text, with one ``WARNING:`` naming the properties, and
kept as read in the artifact-metadata annotation.

See also: :mod:`tests.core.test_untrusted_text` (the escape itself).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom import __main__
from pitloom.assemble import generate_model_sbom, generate_project_sbom
from pitloom.assemble.spdx3.ai import finish_ai_package
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.extract.ai_model import crfsuite
from pitloom.extract.ai_model.formats import Limits
from pitloom.extract.ai_model.formats.crfsuite import (
    read_crfsuite as read_crfsuite_header,
)
from tests._network import assert_spdx3_validate_ok
from tests.extract.ai_model.gguf_builders import STRING, gguf_file, kv, string
from tests.id_registry.surfaces_base import demo_project
from tests.warning_helpers import logged_warnings

_CRFSUITE = Path(__file__).parents[1] / "fixtures" / "aimodels" / "crfsuite"
_RLO = "\u202e"
_COMMON = ["--creation-datetime", "2026-01-01T00:00:00Z", "--offline"]


def _gguf(*pairs: tuple[str, str]) -> bytes:
    body = b"".join(kv(key.encode(), STRING, string(value)) for key, value in pairs)
    return gguf_file(0, len(pairs), body)


def _onnx_named(name: str) -> bytes:
    onnx = pytest.importorskip("onnx")
    return bytes(
        onnx.helper.make_model(
            onnx.helper.make_graph([], name, [], [])
        ).SerializeToString()
    )


def _onnx_input(name: str) -> bytes:
    onnx = pytest.importorskip("onnx")
    tensor = onnx.helper.make_tensor_value_info(name, onnx.TensorProto.FLOAT, [1])
    graph = onnx.helper.make_graph([], "g", [tensor], [])
    return bytes(onnx.helper.make_model(graph).SerializeToString())


def _crfsuite_labelled(monkeypatch: pytest.MonkeyPatch, label: str) -> bytes:
    with (_CRFSUITE / "complete.crfsuite").open("rb") as handle:
        model = read_crfsuite_header(handle, Limits())
    patched = model._replace(labels=(label, *model.labels[1:]))
    monkeypatch.setattr(crfsuite, "read_crfsuite_header", lambda *_a, **_k: patched)
    return (_CRFSUITE / "complete.crfsuite").read_bytes()


def _ai_package(sbom: str) -> dict[str, Any]:
    graph = json.loads(sbom)["@graph"]
    packages: list[dict[str, Any]] = [e for e in graph if e["type"] == "ai_AIPackage"]
    (package,) = packages
    return package


def _shown(sbom: str) -> dict[str, Any]:
    """The AI package, with its licence element under ``@license``."""
    graph = json.loads(sbom)["@graph"]
    licences = {e["spdxId"]: e for e in graph if e["type"].startswith("simplelic")}
    targets = [
        t
        for e in graph
        if e["type"] == "Relationship"
        for t in e.get("to", [])
        if t in licences
    ]
    return {**_ai_package(sbom), "@license": [licences[t] for t in targets]}


def _escape_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [m for m in logged_warnings(caplog) if "bidi control" in m]


_Case = tuple[
    str,
    Callable[[pytest.MonkeyPatch], bytes],
    Callable[[dict[str, Any]], Any],
    Any,
    str,
]
_CASES: dict[str, _Case] = {
    "gguf-name": (
        "m.gguf",
        lambda _: _gguf(("general.name", f"evil{_RLO}txt.exe")),
        lambda p: p["name"],
        "evil\\u202etxt.exe",
        "name",
    ),
    "gguf-description": (
        "m.gguf",
        lambda _: _gguf(("general.description", "\ufeffabout")),
        lambda p: p["description"],
        "\\ufeffabout",
        "description",
    ),
    "gguf-hyperparameter": (
        "m.gguf",
        lambda _: _gguf((f"x{_RLO}.context_length", f"8{_RLO}")),
        lambda p: [(e["key"], e["value"]) for e in p["ai_hyperparameter"]],
        [("x\\u202e.context_length", "8\\u202e")],
        "ai_hyperparameter, comment",
    ),
    "gguf-license": (
        "m.gguf",
        lambda _: _gguf(("general.license", f"mine{_RLO}")),
        lambda p: [
            (e["name"], e["simplelicensing_licenseText"]) for e in p["@license"]
        ],
        [("mine\\u202e", "mine\\u202e")],
        "license name, license simplelicensing_licenseText",
    ),
    "onnx-name": (
        "m.onnx",
        lambda _: _onnx_named(f"a{_RLO}b"),
        lambda p: p["name"],
        "a\\u202eb",
        "name",
    ),
    "onnx-input": (
        "m.onnx",
        lambda _: _onnx_input(f"in{_RLO}"),
        lambda p: json.loads(p["ai_informationAboutApplication"])["inputs"][0]["name"],
        "in\\u202e",
        "ai_informationAboutApplication",
    ),
    "crfsuite-label": (
        "m.crfsuite",
        lambda mp: _crfsuite_labelled(mp, f"B{_RLO}LOC"),
        lambda p: p["description"].split(": ", 1)[1].split(", ")[0],
        "B\\u202eLOC",
        "description",
    ),
}


# ONNX's graph name and input names are not in its artifact-metadata
# annotation (known-bugs.md): the original text is not in the SBOM.
_NOT_IN_ANNOTATION = frozenset({"onnx-name", "onnx-input"})


@pytest.mark.parametrize("case", _CASES)
def test_a_control_is_escaped_once_and_kept_in_the_annotation(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    file_name, build, shown, expected, prop = _CASES[case]
    path = tmp_path / file_name
    path.write_bytes(build(monkeypatch))
    sbom = generate_model_sbom(path)
    assert shown(_shown(sbom)) == expected
    (message,) = _escape_warnings(caplog)
    assert message == (
        f"FORMAT={file_name.rsplit('.', 1)[1]} FILE={path}: invisible or bidi "
        f"control characters written as \\uXXXX in {prop}"
    )
    package = _ai_package(sbom)
    assert _RLO not in json.dumps(package, ensure_ascii=False)
    control = "\ufeff" if "ufeff" in str(expected) else _RLO
    (statement,) = [
        e["statement"]
        for e in json.loads(sbom)["@graph"]
        if "artifact-metadata" in e.get("statement", "")
    ]
    # The annotation keeps the text as read, where it holds the field at all.
    assert (control in statement) == (case not in _NOT_IN_ANNOTATION)
    caplog.clear()
    assert generate_model_sbom(path) == sbom  # deterministic


def test_text_without_a_control_is_unchanged_and_quiet(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(_gguf(("general.name", "a\\u202eb"), ("general.description", "x")))
    package = _ai_package(generate_model_sbom(path))
    assert package["name"] == "a\\u202eb"  # literal text: never re-escaped
    assert not _escape_warnings(caplog)


def test_several_properties_give_one_warning_naming_each(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "m.gguf"
    body = _gguf(
        ("general.name", _RLO),
        ("general.description", _RLO),
        ("general.architecture", f"llama{_RLO}"),
    )
    path.write_bytes(body)
    generate_model_sbom(path)
    (message,) = _escape_warnings(caplog)
    assert message.endswith("in ai_typeOfModel, description, name")


@pytest.mark.parametrize("surface", ["model", "project"])
def test_the_cli_escapes_like_the_library(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    data = _gguf(("general.name", f"evil{_RLO}txt.exe"))
    if surface == "project":
        target = demo_project(tmp_path)
        (target / "demo" / "m.gguf").write_bytes(data)
    else:
        target = tmp_path / "m.gguf"
        target.write_bytes(data)
    out = tmp_path / "out.json"
    monkeypatch.setattr(
        sys, "argv", ["loom", surface, str(target), "-o", str(out), *_COMMON]
    )
    assert __main__.main() == 0
    assert _ai_package(out.read_text(encoding="utf-8"))["name"] == "evil\\u202etxt.exe"
    (message,) = _escape_warnings(caplog)
    assert message.endswith(
        ": invisible or bidi control characters written as \\uXXXX in name"
    )


def test_the_library_project_surface_escapes_too(tmp_path: Path) -> None:
    root = demo_project(tmp_path)
    data = _gguf(("general.name", f"a{_RLO}"), ("general.license", f"l{_RLO}"))
    (root / "demo" / "m.gguf").write_bytes(data)
    sbom = generate_project_sbom(root, offline=True)
    shown = _shown(sbom)
    assert shown["name"] == "a\\u202e"
    assert [e["name"] for e in shown["@license"]] == ["l\\u202e"]


@pytest.mark.network
def test_an_escaped_sbom_passes_spdx3_validate(tmp_path: Path) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(_gguf(("general.name", f"evil{_RLO}txt.exe")))
    out = tmp_path / "out.json"
    out.write_text(generate_model_sbom(path), encoding="utf-8")
    assert_spdx3_validate_ok(out)


def test_a_hub_model_is_named_by_its_url(caplog: pytest.LogCaptureFixture) -> None:
    """A Hugging Face model has no file: the warning names its page, with
    the format its annotation and the name-cut warning use."""
    model = AiModelMetadata(
        name="m",
        description=f"a{_RLO}",
        url="https://huggingface.co/o/m",
        extra_data={"hf.sha": "1"},
    )
    package = spdx3.ai_AIPackage(
        spdxId="urn:x", name="m", description=model.description
    )
    finish_ai_package(package, model)
    assert package.description == "a\\u202e"
    assert _escape_warnings(caplog) == [
        "FORMAT=huggingface FILE=https://huggingface.co/o/m: invisible or bidi "
        "control characters written as \\uXXXX in description"
    ]
