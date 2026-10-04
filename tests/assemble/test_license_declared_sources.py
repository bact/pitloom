# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Whose statement a licence is decides the relationship: the package's own
(an AI model file's metadata, an in-package file, its own installed
metadata) is ``hasDeclaredLicense``; a third-party record (PyPI, a
dependency's installed copy) is ``hasConcludedLicense``. Read on each real
surface.

See also: :func:`pitloom.assemble.spdx3.provenance.is_license_concluded` and
:mod:`tests.assemble.test_license_elements_classifier`.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.assemble import (
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.assemble.spdx3._provenance_encoders import THIRD_PARTY_SOURCES
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.creation import CreationMetadata
from tests._license_graph import (
    deployed,
    graph_of,
    hook_metadata,
    license_targets,
    onnx_model,
    project_graph,
)

from .conftest import _make_dummy_wheel

_LICENSE_RELATIONSHIPS = ("hasDeclaredLicense", "hasConcludedLicense")


def _relationships(graph: list[dict[str, Any]], name: str) -> list[tuple[str, str]]:
    """``(relationship type, licence)`` for each licence relationship of the
    package named *name*."""
    ids = {e["spdxId"] for e in graph if e.get("name") == name and "spdxId" in e}
    rels = [
        r
        for r in graph
        if r.get("relationshipType") in _LICENSE_RELATIONSHIPS and r["from"] in ids
    ]
    return [
        (r["relationshipType"], target)
        for r, target in zip(
            rels, license_targets(rels + _elements(graph)), strict=True
        )
    ]


def _elements(graph: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in graph if e.get("type", "").startswith("simplelicensing_")]


def _pt2() -> bytes:
    """A PT2 archive whose own metadata states its licence."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("model/version", "2")
        zf.writestr("model/extra/license", "Apache-2.0")
    return buf.getvalue()


def _model_file(tmp: Path) -> list[dict[str, Any]]:
    model = tmp / "model.pt2"
    model.write_bytes(_pt2())
    graph: list[dict[str, Any]] = json.loads(generate_model_sbom(model))["@graph"]
    return graph


def _project_scan(tmp: Path) -> list[dict[str, Any]]:
    (tmp / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0"\n', encoding="utf-8"
    )
    (tmp / "demo").mkdir()
    (tmp / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (tmp / "demo" / "model.pt2").write_bytes(_pt2())
    graph: list[dict[str, Any]] = json.loads(generate_project_sbom(tmp, offline=True))[
        "@graph"
    ]
    return graph


def _wheel_scan(tmp: Path) -> list[dict[str, Any]]:
    wheel = _make_dummy_wheel(tmp, extra_members={"demo_pkg/model.pt2": _pt2()})
    graph: list[dict[str, Any]] = json.loads(generate_wheel_sbom(wheel, offline=True))[
        "@graph"
    ]
    return graph


@pytest.mark.parametrize("surface", [_model_file, _project_scan, _wheel_scan])
def test_a_model_files_own_licence_is_declared_on_every_surface(
    surface: Any, tmp_path: Path
) -> None:
    graph = surface(tmp_path)
    models = [e["name"] for e in graph if e.get("type") == "ai_AIPackage"]
    assert models
    for name in models:
        assert _relationships(graph, name) == [("hasDeclaredLicense", "Apache-2.0")]


_LICENSE_TEXT = "MIT License\n\nPermission is hereby granted" + "." * 200


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        pytest.param(
            {"CITATION.cff": "cff-version: 1.2.0\nlicense: MIT\n"},
            [("hasDeclaredLicense", "MIT")],
            id="citation-cff",
        ),
        pytest.param(
            {"codemeta.json": '{"license": "MIT"}'},
            [("hasDeclaredLicense", "MIT")],
            id="codemeta",
        ),
        pytest.param(
            {"LICENSE": _LICENSE_TEXT},
            [("hasDeclaredLicense", "MIT")],
            id="license-file-detection",
        ),
        # The manifest states one: it stays declared, detection is concluded.
        pytest.param(
            {"LICENSE": _LICENSE_TEXT, "project": 'license = "Apache-2.0"'},
            [("hasConcludedLicense", "MIT"), ("hasDeclaredLicense", "Apache-2.0")],
            id="manifest-and-file",
        ),
        # Text the manifest states is not replaced by the directory's value.
        pytest.param(
            {
                "CITATION.cff": "cff-version: 1.2.0\nlicense: MIT\n",
                "project": 'license = {text = "Custom terms"}',
            },
            [("hasConcludedLicense", "MIT"), ("hasDeclaredLicense", "Custom terms")],
            id="manifest-text-and-citation",
        ),
        # A classifier is a statement too: the directory is the second opinion.
        pytest.param(
            {
                "LICENSE": _LICENSE_TEXT,
                "project": 'classifiers = ["License :: OSI Approved :: BSD License"]',
            },
            [("hasConcludedLicense", "MIT"), ("hasDeclaredLicense", "BSD License")],
            id="classifier-and-file",
        ),
        pytest.param(
            {"project": 'classifiers = ["License :: OSI Approved :: BSD License"]'},
            [("hasDeclaredLicense", "BSD License")],
            id="classifier-only",
        ),
        # The classifier names the licence the file holds: no conflict.
        pytest.param(
            {
                "LICENSE": _LICENSE_TEXT,
                "project": 'classifiers = ["License :: OSI Approved :: MIT License"]',
            },
            [("hasConcludedLicense", "MIT"), ("hasDeclaredLicense", "MIT License")],
            id="classifier-names-the-file",
        ),
    ],
)
@pytest.mark.parametrize("surface", ["project", "hook"])
def test_an_in_package_source_is_declared_when_the_manifest_states_nothing(
    files: dict[str, str],
    expected: list[tuple[str, str]],
    surface: str,
    tmp_path: Path,
) -> None:
    files = dict(files)
    stated = files.pop("project", "")
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "demo"\nversion = "1.0"\n{stated}\n', encoding="utf-8"
    )
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").write_text("", encoding="utf-8")
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    with patch(
        "pitloom.extract._license.detect_license_from_text",
        autospec=True,
        side_effect=lambda text: "MIT" if text == _LICENSE_TEXT else None,
    ):
        graph = _read(surface, tmp_path)
    assert sorted(_relationships(graph, "demo")) == expected
    conflicts = [e for e in graph if "conflict" in e.get("statement", "")]
    # Two relationships disagree unless one is the other's SPDX List name.
    named = sorted(value for _, value in expected) == ["MIT", "MIT License"]
    assert len(conflicts) == int(len(expected) == 2 and not named)


def _read(surface: str, root: Path) -> list[dict[str, Any]]:
    """The graph the CLI/library (``project``) or the Hatchling hook gives."""
    if surface == "project":
        graph: list[dict[str, Any]] = json.loads(
            generate_project_sbom(root, offline=True)
        )["@graph"]
        return graph
    return project_graph(hook_metadata(root))


def test_a_deployed_packages_own_installed_metadata_is_declared() -> None:
    """``loom env``: the installed copy is the package the SBOM describes."""
    graph = graph_of(deployed({"License": "MIT"}))
    assert _relationships(graph, "x") == [("hasDeclaredLicense", "MIT")]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (None, "hasDeclaredLicense"),  # the model file's own metadata
        # a third-party record, by the rule's own list
        *((f"Source: {s}", "hasConcludedLicense") for s in sorted(THIRD_PARTY_SOURCES)),
    ],
)
def test_a_models_licence_relationship_follows_its_source(
    source: str | None, expected: str
) -> None:
    model = onnx_model("MIT")
    if source is not None:
        model.provenance["license"] = source
    graph = graph_of(build_model(model, CreationMetadata()))
    assert _relationships(graph, "m") == [(expected, "MIT")]
