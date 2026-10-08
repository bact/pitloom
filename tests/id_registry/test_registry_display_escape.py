# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model whose name holds a bidi control keeps the id ``loom id import``
took from an earlier SBOM, which holds the name escaped, on every surface.

Each test changes the document identity between the import and the re-run
(the project's or the model's version), so a re-minted id would differ: the
registry hit is what keeps it.

See also: test_registry_crfsuite_ids.py (``id generate`` ids) and
:mod:`tests.assemble.test_display_text_escape` (the escape).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom.id_registry import IdRegistry
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
def test_a_project_model_keeps_its_imported_id(
    named_by: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = demo_project(tmp_path)
    if named_by == "own-name":
        model = root / "demo" / "m.gguf"
        model.write_bytes(_gguf(("general.name", f"evil{_RLO}txt.exe")))
    else:
        model = root / "demo" / f"evil{_RLO}txt.gguf"
        model.write_bytes(_gguf(("general.description", "x")))
    first, registry = tmp_path / "first.json", tmp_path / "registry.json"
    assert _run_cli(monkeypatch, ["project", str(root), "-o", str(first)]) == 0
    registered = _import(monkeypatch, first, registry)

    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    pyproject.write_text(text.replace('version = "1.0.0"', 'version = "2.0.0"'))
    out = tmp_path / "out.json"
    argv = ["project", str(root), "-o", str(out), "--id-registry", str(registry)]
    assert _run_cli(monkeypatch, argv) == 0
    assert _ids(out, "SpdxDocument") != _ids(first, "SpdxDocument")  # non-vacuous
    assert _ids(out) == [registered]


@pytest.mark.parametrize("command", ["model", "enrich"])
def test_a_model_file_keeps_its_imported_id(
    command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``loom model`` and ``loom enrich`` look a model up by its file stem."""
    model = tmp_path / f"evil{_RLO}txt.gguf"
    model.write_bytes(_gguf(("general.version", "1")))
    first, registry = tmp_path / "first.json", tmp_path / "registry.json"
    assert _run_cli(monkeypatch, ["model", str(model), "-o", str(first)]) == 0
    registered = _import(monkeypatch, first, registry)
    # The registry holds the name as the SBOM shows it, escaped.
    stored = IdRegistry.load(registry).lookup_entity("evil\\u202etxt", "ai_AIPackage")
    assert stored == registered

    model.write_bytes(_gguf(("general.version", "2")))
    (tmp_path / "README.md").write_text("---\nlicense: mit\n---\n", encoding="utf-8")
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
