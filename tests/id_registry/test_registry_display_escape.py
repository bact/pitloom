# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model whose name holds a bidi control keeps its id on every surface:
``loom model``/``loom enrich`` the id ``loom id import`` took from an earlier
SBOM, which holds the name escaped; a project scan the id its file's raw
path key was harvested under.

Each test changes the document identity between the two runs (the project's
version, or the surface), so a re-minted id would differ: the registry hit
is what keeps it. The model's bytes stay: its lookup is gated by their
SHA-256.

See also: test_registry_crfsuite_ids.py (``id generate`` ids) and
:mod:`tests.assemble.test_display_text_escape` (the escape).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom.id_registry import AI_PACKAGE_TYPE, IdRegistry
from tests.extract.ai_model.gguf_builders import STRING, gguf_file, kv, string
from tests.id_registry.surfaces_base import _run_cli, demo_project

_RLO = "\u202e"


def _gguf(*pairs: tuple[str, str]) -> bytes:
    body = b"".join(kv(key.encode(), STRING, string(value)) for key, value in pairs)
    return gguf_file(0, len(pairs), body)


def _ids(sbom: Path, type_name: str = "ai_AIPackage") -> list[str]:
    graph = json.loads(sbom.read_text(encoding="utf-8"))["@graph"]
    return [e["spdxId"] for e in graph if e["type"] == type_name]


def _import(monkeypatch: pytest.MonkeyPatch, sbom: Path, registry: Path) -> str:
    assert _run_cli(monkeypatch, ["id", "import", str(sbom), "-o", str(registry)]) == 0
    (registered,) = _ids(sbom)
    return registered


@pytest.mark.parametrize("named_by", ["own-name", "file-stem"])
def test_a_project_model_keeps_its_harvested_id(
    named_by: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = demo_project(tmp_path)
    if named_by == "own-name":
        model = root / "demo" / "m.gguf"
        model.write_bytes(_gguf(("general.name", f"evil{_RLO}txt.exe")))
    else:
        model = root / "demo" / f"evil{_RLO}txt.gguf"
        model.write_bytes(_gguf(("general.description", "x")))
    registry = tmp_path / "registry.json"
    IdRegistry.new("demo").save(registry)
    first, out = tmp_path / "first.json", tmp_path / "out.json"
    argv = ["project", str(root), "--id-registry", str(registry), "-o"]
    assert _run_cli(monkeypatch, [*argv, str(first)]) == 0
    (registered,) = _ids(first)
    # Held under its file's raw path from the root, never escaped.
    key = f"proj/demo/{model.name}"
    assert IdRegistry.load(registry).lookup(AI_PACKAGE_TYPE, [key]) == registered

    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    pyproject.write_text(text.replace('version = "1.0.0"', 'version = "2.0.0"'))
    assert _run_cli(monkeypatch, [*argv, str(out)]) == 0
    assert _ids(out, "SpdxDocument") != _ids(first, "SpdxDocument")  # non-vacuous
    assert _ids(out) == [registered]


@pytest.mark.parametrize("command", ["model", "enrich"])
def test_a_model_file_keeps_its_imported_id(
    command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``loom model`` and ``loom enrich`` look a model below the registry's
    root (the import's current directory) up by its file's key, here the id
    a project SBOM's model (hashed) was imported with under its file's
    name."""
    root = demo_project(tmp_path)
    model = root / "demo" / f"evil{_RLO}txt.gguf"
    model.write_bytes(_gguf(("general.version", "1")))
    monkeypatch.chdir(root)  # the import's root
    first, registry = tmp_path / "first.json", tmp_path / "registry.json"
    argv = ["project", str(root), "-o", str(first)]
    assert _run_cli(monkeypatch, argv) == 0
    registered = _import(monkeypatch, first, registry)
    # Held under its file's raw name, never the model's escaped one.
    key = f"demo/evil{_RLO}txt.gguf"
    assert IdRegistry.load(registry).lookup(AI_PACKAGE_TYPE, [key]) == registered

    readme = model.parent / "README.md"
    readme.write_text("---\nlicense: mit\n---\n", encoding="utf-8")
    out = tmp_path / "out.json"
    argv = [command, str(model), "-o", str(out), "--id-registry", str(registry)]
    assert _run_cli(monkeypatch, argv) == 0
    graph = json.loads(out.read_text(encoding="utf-8"))["@graph"]
    if command == "model":
        assert _ids(out, "SpdxDocument") != _ids(first, "SpdxDocument")
        assert _ids(out) == [registered]
    else:  # the fragment names the model by its id
        assert graph, "the fragment enriched nothing"
        assert registered in json.dumps(graph)
