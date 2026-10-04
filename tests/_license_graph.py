# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Read licence elements from a serialised SPDX 3 ``@graph``: a
``LicenseExpression`` holds its value in ``simplelicensing_licenseExpression``,
a ``SimpleLicensingText`` in ``simplelicensing_licenseText``."""

from __future__ import annotations

import json
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.deps_license import _apply_license
from pitloom.core.license_individuals import INDIVIDUAL_BY_REFERENCE
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid
from pitloom.export.spdx3_json import Spdx3JsonExporter
from tests.assemble.conftest import _make_ci

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


def two_packages(
    values: list[str], provenance: str = "Source: pyproject.toml | Field: x"
) -> list[dict[str, Any]]:
    """One package per value, each declaring it, sharing one document."""
    doc_uuid = compute_doc_uuid("pkgs", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    exporter.add_creation_info(ci)
    for i, value in enumerate(values):
        package = spdx3.software_Package(
            spdxId=f"https://x/1#Package-{i}", name=f"dep{i}", creationInfo=ci
        )
        exporter.add_package(package)
        _apply_license(value, provenance, package, ci, "pkgs", doc_uuid, exporter)
    return graph_of(exporter)
