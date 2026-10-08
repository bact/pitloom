# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``loom id generate`` and ``loom project --id-registry`` give a CRFsuite
``.model`` the same id.

See also: test_registry_generate.py (what ``id generate`` registers) and
test_surfaces_same_ids.py (the other elements).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.id_registry import IdRegistry
from tests.id_registry.surfaces_base import _run_cli, demo_project

_MINIMAL = (
    Path(__file__).parents[1] / "fixtures" / "aimodels" / "crfsuite" / "minimal.model"
)


def test_a_crfsuite_model_keeps_the_id_id_generate_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = demo_project(tmp_path)
    (root / "demo" / "tagger.model").write_bytes(_MINIMAL.read_bytes())
    registry_path = tmp_path / "registry.json"

    argv = ["id", "generate", str(root / "demo"), "--project-dir", str(root)]
    assert _run_cli(monkeypatch, [*argv, "-o", str(registry_path)]) == 0
    registered = IdRegistry.load(registry_path).lookup_entity("tagger", "ai_AIPackage")
    assert registered is not None  # non-vacuous: the model got an entity

    out = tmp_path / "out.json"
    argv = ["project", str(root), "-o", str(out), "--id-registry", str(registry_path)]
    assert _run_cli(monkeypatch, argv) == 0
    cli_ids = [
        e["spdxId"]
        for e in json.loads(out.read_text(encoding="utf-8"))["@graph"]
        if e["type"] == "ai_AIPackage"
    ]
    assert cli_ids == [registered]

    library = generate_project_sbom(root, id_registry=registry_path, offline=True)
    assert [
        e["spdxId"]
        for e in json.loads(library)["@graph"]
        if e["type"] == "ai_AIPackage"
    ] == [registered]
