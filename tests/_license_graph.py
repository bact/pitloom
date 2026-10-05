# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Read licence elements from a serialised SPDX 3 ``@graph``: a
``LicenseExpression`` holds its value in ``simplelicensing_licenseExpression``,
a ``SimpleLicensingText`` in ``simplelicensing_licenseText``. Also the
builders the licence tests share: a dependency through the real enrichment,
the main package, an AI model, ``loom env``, the Hatchling hook's reader and
a fragment merge."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any
from unittest.mock import patch

import hatchling.metadata.core as hatchling_metadata_core
from hatchling.plugin.manager import PluginManager
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import deps_installed, deps_pypi
from pitloom.assemble.spdx3.deps import add_dependencies
from pitloom.assemble.spdx3.deps_license import _apply_license
from pitloom.assemble.spdx3.document import build, build_deployed
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.config import FragmentConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.license_individuals import INDIVIDUAL_BY_REFERENCE
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.extract.project.hatchling import metadata_from_hatchling
from tests.assemble.conftest import _FakeMetadata, _make_ci

LICENSE_TYPES = (
    "simplelicensing_LicenseExpression",
    "simplelicensing_SimpleLicensingText",
)


def license_elements(graph: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every licence element of *graph*, either kind."""
    return [e for e in graph if e.get("type") in LICENSE_TYPES]


def license_value(element: dict[str, Any]) -> str | None:
    """The expression or text a licence element holds."""
    return element.get("simplelicensing_licenseExpression") or element.get(
        "simplelicensing_licenseText"
    )


def license_targets(graph: list[dict[str, Any]]) -> list[str]:
    """What each declared/concluded licence relationship points at, in graph
    order: an element's value, or ``NOASSERTION``/``NONE`` for an individual.
    A target that is neither raises, so a dangling one cannot pass."""
    by_id = {e["spdxId"]: e for e in license_elements(graph)}
    out: list[str] = []
    for rel in graph:
        if rel.get("relationshipType") not in (
            "hasDeclaredLicense",
            "hasConcludedLicense",
        ):
            continue
        for target in rel["to"]:
            if target in INDIVIDUAL_BY_REFERENCE:
                out.append(INDIVIDUAL_BY_REFERENCE[target].spdx_name)
            else:
                out.append(str(license_value(by_id[target])))
    return out


def license_values(graph: list[dict[str, Any]]) -> dict[str, str | None]:
    """``spdxId`` -> value, for every licence element of *graph*."""
    return {e["spdxId"]: license_value(e) for e in license_elements(graph)}


def graph_of(exporter: Spdx3JsonExporter) -> list[dict[str, Any]]:
    """The serialised ``@graph`` of *exporter*."""
    graph: list[dict[str, Any]] = json.loads(exporter.to_json())["@graph"]
    return graph


def provenance_fields(graph: list[dict[str, Any]], subject: str) -> list[str]:
    """The ``license`` provenance string(s) of every Annotation on *subject*."""
    out: list[str] = []
    for e in graph:
        if e["type"] == "Annotation" and e["subject"] == subject:
            fields = json.loads(e["statement"]).get("fields", {})
            if "license" in fields:
                out.append(json.dumps(fields["license"], sort_keys=True))
    return out


def _new_document(
    doc_name: str,
) -> tuple[Spdx3JsonExporter, spdx3.CreationInfo, str]:
    """An empty exporter with its creation info, and the document UUID."""
    doc_uuid = compute_doc_uuid(doc_name, "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    exporter.add_creation_info(ci)
    return exporter, ci, doc_uuid


def two_packages(
    values: list[str], provenance: str = "Source: pyproject.toml | Field: x"
) -> list[dict[str, Any]]:
    """One package per value, each declaring it, sharing one document."""
    exporter, ci, doc_uuid = _new_document("pkgs")
    for i, value in enumerate(values):
        package = spdx3.software_Package(
            spdxId=f"https://x/1#Package-{i}", name=f"dep{i}", creationInfo=ci
        )
        exporter.add_package(package)
        _apply_license(value, provenance, package, ci, "pkgs", doc_uuid, exporter)
    return graph_of(exporter)


def uninstalled(*_args: object) -> None:
    """A distribution that is not installed."""
    raise PackageNotFoundError


def dependency_graph(
    installed: dict[str, str] | None,
    pypi: dict[str, Any] | None = None,
    *,
    classifiers: list[str] | None = None,
    offline: bool = False,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """The graph of one dependency, ``dep==1.0``, through the whole
    enrichment: *installed* are its installed METADATA fields beside
    ``Version: 1.0`` (``None``: not installed), *classifiers* its installed
    ``Classifier`` lines, *pypi* its PyPI ``info`` (``None``: no answer).
    *kwargs* go to ``add_dependencies``."""
    exporter, ci, doc_uuid = _new_document("dependency")
    main = spdx3.software_Package(
        spdxId="https://x/1#Package-1", name="main", creationInfo=ci
    )
    exporter.add_package(main)
    fake = _FakeMetadata(
        {"Version": "1.0", **(installed or {})}, classifiers=classifiers
    )
    with (
        patch.object(
            deps_installed,
            "get_pkg_metadata",
            uninstalled if installed is None else lambda _n: fake,
        ),
        patch.object(
            deps_installed,
            "get_package_version",
            uninstalled if installed is None else lambda _n: "1.0",
        ),
        patch.object(
            deps_pypi,
            "_fetch_pypi_release_info",
            lambda *_a: None if pypi is None else {"info": pypi},
        ),
    ):
        add_dependencies(
            ["dep==1.0"],
            "Source: pyproject.toml | Field: project.dependencies",
            require_spdx_id(main),
            ci,
            "dependency",
            doc_uuid,
            exporter,
            offline=offline,
            **kwargs,
        )
    return graph_of(exporter)


def project_graph(metadata: ProjectMetadata) -> list[dict[str, Any]]:
    """The graph ``build()`` gives for a project with *metadata*."""
    return graph_of(
        build(DocumentModel(project=metadata, creation_metadata=CreationMetadata()))
    )


def onnx_model(license_id: str | None) -> AiModelMetadata:
    """An ONNX model ``m`` whose own metadata states *license_id*."""
    return AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.ONNX),
        name="m",
        license=license_id,
    )


def deployed(fields: dict[str, str] | None) -> Spdx3JsonExporter:
    """``loom env`` with one package ``x`` whose installed metadata has
    *fields* (an empty environment when ``None``); never the real env."""
    doc = DocumentModel(
        project=ProjectMetadata(name="env", version="0.0.0"),
        creation_metadata=CreationMetadata(),
    )
    tree: list[dict[str, Any]] = (
        []
        if fields is None
        else [{"package": {"key": "x", "package_name": "x", "installed_version": "1"}}]
    )
    fake = _FakeMetadata({"Version": "1", **(fields or {})})
    with patch.object(
        deps_installed, "get_pkg_metadata", autospec=True, return_value=fake
    ):
        return build_deployed(doc, tree, offline=True)


def hook_metadata(root: Path) -> ProjectMetadata:
    """What the Hatchling build hook's reader gives for the project at *root*."""
    core = hatchling_metadata_core.ProjectMetadata(str(root), PluginManager())
    return metadata_from_hatchling(core, root)


_FRAGMENT_NS = "https://spdx.org/spdxdocs/frag"


def fragment_graph(
    elements: list[dict[str, Any]], ns: str = _FRAGMENT_NS
) -> dict[str, Any]:
    """A fragment document: its creation info and agent, then *elements*
    (``creationInfo`` filled in)."""
    graph: list[dict[str, Any]] = [
        {
            "type": "CreationInfo",
            "@id": "_:ci",
            "specVersion": "3.0.1",
            "created": "2026-01-01T00:00:00Z",
            "createdBy": [f"{ns}#A"],
        },
        {"type": "SoftwareAgent", "spdxId": f"{ns}#A", "name": "x"},
        *elements,
    ]
    for element in graph[1:]:
        element.setdefault("creationInfo", "_:ci")
    return {
        "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
        "@graph": graph,
    }


def licensed_package(
    name: str, target: str, ns: str = _FRAGMENT_NS
) -> list[dict[str, Any]]:
    """Package *name* of a fragment declaring licence *target*."""
    return [
        {"type": "software_Package", "spdxId": f"{ns}#{name}", "name": name},
        {
            "type": "Relationship",
            "spdxId": f"{ns}#R-{name}",
            "from": f"{ns}#{name}",
            "to": [target],
            "relationshipType": "hasDeclaredLicense",
        },
    ]


def license_node(spdx_id: str, kind: str, value: str) -> dict[str, Any]:
    """A serialised licence element: *kind* ``expression`` or ``text``."""
    if kind == "expression":
        return {
            "type": "simplelicensing_LicenseExpression",
            "spdxId": spdx_id,
            "simplelicensing_licenseExpression": value,
        }
    return {
        "type": "simplelicensing_SimpleLicensingText",
        "spdxId": spdx_id,
        "simplelicensing_licenseText": value,
    }


def write_fragment(path: Path, document: dict[str, Any]) -> Path:
    """Write *document* to *path*, making its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def merged_fragment(tmp_path: Path, target: str | None) -> Spdx3JsonExporter:
    """A licence-free base document merged with a fragment whose package has
    a ``hasDeclaredLicense`` relationship to *target* (none when ``None``)."""
    elements = (
        [{"type": "software_Package", "spdxId": f"{_FRAGMENT_NS}#P", "name": "p"}]
        if target is None
        else licensed_package("P", target)
    )
    write_fragment(tmp_path / "f.spdx3.json", fragment_graph(elements))
    ci = spdx3.CreationInfo(
        _id="_:ci",
        specVersion="3.0.1",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        createdBy=["https://spdx.org/agent1"],
    )
    exporter = Spdx3JsonExporter()
    exporter.add_document(
        spdx3.SpdxDocument(
            spdxId="https://spdx.org/spdxdocs/main", name="m", creationInfo=ci
        )
    )
    merge_fragments(tmp_path, [FragmentConfig(path="f.spdx3.json")], exporter)
    return exporter
