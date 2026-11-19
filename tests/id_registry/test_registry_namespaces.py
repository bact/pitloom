# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Namespaces in one SBOM, as ``docs/id-registry.md#namespaces`` states: an
id the registry holds keeps the registry's namespace, every other id is minted
in the document's ``https://spdx.org/spdxdocs/<name>-<uuid>``; without a
registry every id is in the document's. On every surface that reads a
registry.

See also: _surfaces_path_keys_shared.py (the project and runners),
test_surfaces_path_keys.py (the id reuse guard).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core.iri import SPDX_DOCS_BASE
from tests.id_registry._surfaces_path_keys_shared import (
    REGISTRY,
    SURFACES,
    held_files,
    src_project,
)
from tests.id_registry.surfaces_base import _run_cli

pytestmark = [pytest.mark.usefixtures("fixed_epoch"), pytest.mark.platform]

_NAMESPACE = "https://ids.example/ns"


def _namespaces(sbom: str) -> set[str]:
    """The namespace (the id before ``#``) of every element with an id."""
    return {
        node["spdxId"].split("#")[0]
        for node in json.loads(sbom)["@graph"]
        if "spdxId" in node
    }


def _document_id(sbom: str) -> str:
    (ids,) = [
        node["spdxId"]
        for node in json.loads(sbom)["@graph"]
        if node["type"] == "SpdxDocument"
    ]
    return str(ids)


@pytest.mark.parametrize("surface", list(SURFACES))
def test_registry_namespace_beside_document_namespace(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = src_project(tmp_path / "proj")
    registry = project / REGISTRY
    argv = ["id", "generate", str(project / "src"), "--project-dir", str(project)]
    argv += ["-o", str(registry), "--namespace", _NAMESPACE]
    assert _run_cli(monkeypatch, argv) == 0
    held = set(held_files(registry).values())
    assert held  # non-vacuous: the registry holds files
    assert all(spdx_id.startswith(f"{_NAMESPACE}#") for spdx_id in held)

    scratch = tmp_path / "run"
    scratch.mkdir()
    sbom = SURFACES[surface].run(project, registry, scratch, monkeypatch)

    ids = {node.get("spdxId") for node in json.loads(sbom)["@graph"]}
    assert held <= ids  # a held id keeps the registry's namespace
    namespaces = _namespaces(sbom)
    assert _NAMESPACE in namespaces
    assert _document_id(sbom).startswith(SPDX_DOCS_BASE)  # never the registry's
    assert len(namespaces - {_NAMESPACE}) == 1  # one document namespace


def test_no_registry_one_namespace(tmp_path: Path) -> None:
    project = src_project(tmp_path / "proj")
    (project / "pyproject.toml").write_text(
        (project / "pyproject.toml")
        .read_text(encoding="utf-8")
        .split("[tool.pitloom]")[0],
        encoding="utf-8",
    )
    namespaces = _namespaces(generate_project_sbom(project, creation_metadata=None))
    (only,) = namespaces
    assert only.startswith(SPDX_DOCS_BASE)
