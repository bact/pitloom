# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""AI model order through ``generate_project_sbom``.

Only the scanner's input order is varied. Enrichment results and registry
claims are matched to models by position, so an order that depends on the
input would attach them to the wrong model.

See also: :mod:`tests.extract.test_scanner` for the sort itself and
:mod:`tests.extract.test_scanner_project` for the project producer.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.project import ProjectFile
from pitloom.enrich.base import EnrichedField, EnrichmentResult
from pitloom.extract.scanner_project import scan_project_for_ai_models
from pitloom.id_registry import EntityEntry, IdRegistry

_NUMPY = Path(__file__).parent.parent / "fixtures" / "aimodels" / "numpy"
_NAMESPACE = "https://example.org/doc"
_MODELS = ["twomodels/a/w.npy", "twomodels/b/w.npy", "twomodels/z_model.npy"]
_Sbom = tuple[str, list[str]]


def _project(root: Path) -> Path:
    pkg = root / "src" / "twomodels"
    for rel, fixture in [
        ("a/w.npy", "v1"),
        ("b/w.npy", "v2"),
        ("z_model.npy", "v1"),
    ]:
        (pkg / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(_NUMPY / f"example-model-{fixture}.npy", pkg / rel)
    (pkg / "__init__.py").write_text('X = ["w.npy", "z_model.npy"]\n')
    (pkg / "load.py").write_text('open("z_model.npy")\n')
    (root / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
        '[project]\nname = "twomodels"\nversion = "0.1.0"\n'
    )
    return root


def _generate(
    proj: Path, monkeypatch: pytest.MonkeyPatch, *, reverse: bool, **kwargs: Any
) -> _Sbom:
    """The SBOM, and the file order the scanner was given."""
    seen: list[str] = []

    def _scan(project_dir: Path, files: list[ProjectFile]) -> list[AiModelMetadata]:
        files = files[::-1] if reverse else files
        seen[:] = [f.distribution_path for f in files]
        return scan_project_for_ai_models(project_dir, files)

    monkeypatch.setattr(
        "pitloom.assemble._generators.scan_project_for_ai_models", _scan
    )
    sbom = generate_project_sbom(
        proj,
        creation_metadata=CreationMetadata(creation_datetime="2026-01-01T00:00:00Z"),
        update_id_registry=False,
        offline=True,
        **kwargs,
    )
    return sbom, seen


def _graph(sbom: str) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    return graph


def _rels(graph: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [
        e
        for e in graph
        if e["type"].endswith("Relationship") and e["relationshipType"] == kind
    ]


def _names(graph: list[dict[str, Any]]) -> dict[str, str]:
    return {e["spdxId"]: e["name"] for e in graph if e["type"] == "software_File"}


def _package_files(graph: list[dict[str, Any]]) -> dict[str, str]:
    """AIPackage spdxId -> the name of the file it ``contains``."""
    names = _names(graph)
    packages = {e["spdxId"] for e in graph if e["type"] == "ai_AIPackage"}
    return {
        r["from"]: names[r["to"][0]]
        for r in _rels(graph, "contains")
        if r["from"] in packages
    }


def test_scanner_input_order_does_not_change_sbom_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _project(tmp_path)
    (fwd, order_fwd), (rev, order_rev) = (
        _generate(proj, monkeypatch, reverse=r) for r in (False, True)
    )
    assert order_fwd != order_rev  # not vacuous
    assert sorted(_package_files(_graph(fwd)).values()) == _MODELS
    assert fwd == rev

    names = _names(_graph(rev))
    uses = sorted(
        (names[r["from"]], names[t])
        for r in _rels(_graph(rev), "hasDataFile")
        for t in r["to"]
    )
    assert uses == [
        ("twomodels/__init__.py", "twomodels/a/w.npy"),
        ("twomodels/__init__.py", "twomodels/b/w.npy"),
        ("twomodels/__init__.py", "twomodels/z_model.npy"),
        ("twomodels/load.py", "twomodels/z_model.npy"),
    ]


def test_enrichment_results_stay_with_their_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake(model: AiModelMetadata, *_: Any) -> list[EnrichmentResult]:
        tag = f"tag::{model.format_info.file_path_relative}"
        return [
            EnrichmentResult(
                "fake", [EnrichedField("license", None, tag, "detected", "Source: x")]
            )
        ]

    monkeypatch.setattr("pitloom.enrich.run_enrichers", _fake)
    graph = _graph(_generate(_project(tmp_path), monkeypatch, reverse=True)[0])
    package_file = _package_files(graph)
    tagged = [
        a
        for a in graph
        if a["type"] == "Annotation" and "tag::" in a.get("statement", "")
    ]
    assert len(tagged) == 3
    for annotation in tagged:
        assert f"tag::{package_file[annotation['subject']]}" in annotation["statement"]


@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reversed"])
def test_registry_pin_goes_to_first_model_in_sorted_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    reverse: bool,
) -> None:
    pin = f"{_NAMESPACE}#AIPackage-pinned-1"
    registry = IdRegistry(
        namespace=_NAMESPACE,
        entities={("ai_AIPackage", "w"): EntityEntry(spdx_id=pin)},
    )
    with caplog.at_level(logging.WARNING, logger="pitloom.id_registry"):
        sbom, _ = _generate(
            _project(tmp_path), monkeypatch, reverse=reverse, id_registry=registry
        )
    assert _package_files(_graph(sbom))[pin] == "twomodels/a/w.npy"
    assert any(
        "twomodels/b/w.npy gets a new id" in r.getMessage() for r in caplog.records
    )
