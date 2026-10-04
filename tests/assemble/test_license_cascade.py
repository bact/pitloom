# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A dependency's licence cascade: installed metadata, then installed
classifiers, then PyPI. ``NOASSERTION`` (``UNKNOWN``) is weak -- a later
source may know better, and the individual is emitted, with the first
stating source's provenance, only if none does. ``NONE`` is a statement and
ends the cascade. Within one PyPI record the placeholder is skipped while
looking for a better value.

See also: :mod:`tests.assemble.test_license_elements_surfaces`.
"""

# pylint: disable=protected-access

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from typing import Any
from unittest.mock import patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import deps, deps_installed, deps_pypi
from pitloom.assemble.spdx3.deps import add_dependencies
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from tests._license_graph import graph_of, license_targets
from tests.assemble.conftest import _FakeMetadata, _make_ci

_MIT_CLASSIFIER = ["License :: OSI Approved :: MIT"]


def _uninstalled(*_args: object) -> None:
    raise PackageNotFoundError


def _dependency(
    installed: dict[str, str] | None,
    *,
    classifiers: list[str] | None = None,
    pypi: dict[str, Any] | None = None,
    offline: bool = False,
) -> tuple[list[dict[str, Any]], list[object]]:
    """One dependency through the whole enrichment; *installed* are its
    installed-metadata fields (``None`` = not installed), *pypi* its PyPI
    ``info``. Returns the graph and the calls made to the PyPI licence
    reader."""
    doc_uuid = compute_doc_uuid("cascade", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    exporter.add_creation_info(ci)
    main = spdx3.software_Package(
        spdxId="https://x/1#Package-1", name="main", creationInfo=ci
    )
    exporter.add_package(main)
    calls: list[object] = []
    real_reader = deps_pypi._extract_pypi_license

    def spy(info: dict[str, Any]) -> str | None:
        calls.append(info)
        return real_reader(info)

    fields = {"Version": "1.0", **(installed or {})}

    def installed_metadata(_name: str) -> _FakeMetadata:
        return _FakeMetadata(fields, classifiers=classifiers)

    with (
        patch.object(deps_installed, "get_package_version", lambda _n: "1.0"),
        patch.object(
            deps_installed,
            "get_pkg_metadata",
            _uninstalled if installed is None else installed_metadata,
        ),
        patch.object(
            deps_pypi,
            "_fetch_pypi_release_info",
            lambda *_a: {"info": pypi} if pypi is not None else None,
        ),
        patch.object(deps, "_extract_pypi_license", spy),
    ):
        add_dependencies(
            ["dep==1.0"],
            "Source: pyproject.toml | Field: project.dependencies",
            require_spdx_id(main),
            ci,
            "cascade",
            doc_uuid,
            exporter,
            offline=offline,
            provenance_config=ProvenanceConfig(detail="full"),
        )
    return graph_of(exporter), calls


def _license_notes(graph: list[dict[str, Any]]) -> str:
    """The provenance comment of every licence relationship and element, as
    one string."""
    return " ".join(
        e.get("comment", "")
        for e in graph
        if e.get("relationshipType") in ("hasDeclaredLicense", "hasConcludedLicense")
        or e["type"].startswith("simplelicensing_")
    )


@pytest.mark.parametrize(
    "pypi",
    [
        {"license_expression": "MIT"},
        {"classifiers": _MIT_CLASSIFIER},
        {"license": "UNKNOWN", "classifiers": _MIT_CLASSIFIER},
    ],
)
def test_installed_unknown_gives_way_to_pypi(pypi: dict[str, Any]) -> None:
    graph, calls = _dependency({"License": "UNKNOWN"}, pypi=pypi)
    assert license_targets(graph) == ["MIT"]
    assert len(calls) == 1


def test_installed_unknown_gives_way_to_an_installed_classifier() -> None:
    graph, calls = _dependency(
        {"License": "UNKNOWN"}, classifiers=_MIT_CLASSIFIER, pypi={}
    )
    assert license_targets(graph) == ["MIT"]
    assert not calls  # the licence was settled locally
    assert "Field: Classifier" in _license_notes(graph)


@pytest.mark.parametrize("pypi", [{}, {"license": "unknown"}, None])
def test_installed_unknown_stays_noassertion_with_its_own_provenance(
    pypi: dict[str, Any] | None,
) -> None:
    """Nothing later knows better (an empty record, another placeholder, or
    no PyPI answer): the individual is emitted, from the installed source."""
    graph, _ = _dependency({"License": "UNKNOWN"}, pypi=pypi)
    assert license_targets(graph) == ["NOASSERTION"]
    notes = _license_notes(graph)
    assert "installed metadata" in notes and "PyPI" not in notes


def test_offline_installed_unknown_is_noassertion() -> None:
    graph, calls = _dependency({"License": "UNKNOWN"}, pypi={}, offline=True)
    assert license_targets(graph) == ["NOASSERTION"]
    assert not calls


def test_pypi_placeholder_is_noassertion_with_pypi_provenance() -> None:
    graph, _ = _dependency(None, pypi={"license_expression": "NOASSERTION"})
    assert license_targets(graph) == ["NOASSERTION"]
    assert "PyPI JSON API" in _license_notes(graph)


def test_installed_none_ends_the_cascade() -> None:
    """``NONE`` is a statement: PyPI is not asked for the licence."""
    graph, calls = _dependency({"License": "NONE"}, pypi={"license_expression": "MIT"})
    assert license_targets(graph) == ["NONE"]
    assert not calls


def test_the_first_placeholder_provides_the_provenance() -> None:
    """Installed says ``unknown``, PyPI ``NOASSERTION``: one individual,
    the installed source's note."""
    graph, _ = _dependency(
        {"License": "unknown"}, pypi={"license_expression": "NOASSERTION"}
    )
    assert license_targets(graph) == ["NOASSERTION"]
    notes = _license_notes(graph)
    assert "installed metadata" in notes and "PyPI" not in notes


@pytest.mark.parametrize(
    ("info", "expected"),
    [
        ({"license_expression": "NOASSERTION", "classifiers": _MIT_CLASSIFIER}, "MIT"),
        ({"license_expression": "unknown", "license": "MIT"}, "MIT"),
        ({"license": "Unknown", "classifiers": _MIT_CLASSIFIER}, "MIT"),
        ({"license_expression": "UNKNOWN"}, "UNKNOWN"),
        ({"license_expression": "noassertion", "license": "unknown"}, "noassertion"),
        ({"license": "unknown"}, "unknown"),
        ({"license_expression": "NONE", "classifiers": _MIT_CLASSIFIER}, "NONE"),
        ({"license_expression": "MIT", "license": "UNKNOWN"}, "MIT"),
        ({"classifiers": ["Programming Language :: Python"]}, None),
        ({}, None),
    ],
)
def test_pypi_record_skips_a_placeholder_for_something_better(
    info: dict[str, Any], expected: str | None
) -> None:
    assert deps_pypi._extract_pypi_license(info) == expected


def test_a_held_noassertion_belongs_to_one_dependency() -> None:
    """Two dependencies in one call, offline: A says UNKNOWN, B says
    nothing. Only A gets the individual; the held state is not shared."""
    doc_uuid = compute_doc_uuid("two-deps", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    exporter.add_creation_info(ci)
    main = spdx3.software_Package(
        spdxId="https://x/1#Package-1", name="main", creationInfo=ci
    )
    exporter.add_package(main)

    def metadata(name: str) -> _FakeMetadata:
        fields = {"Version": "1.0"}
        if name == "a":
            fields["License"] = "UNKNOWN"
        return _FakeMetadata(fields)

    with (
        patch.object(deps_installed, "get_package_version", lambda _n: "1.0"),
        patch.object(deps_installed, "get_pkg_metadata", metadata),
    ):
        add_dependencies(
            ["a==1.0", "b==1.0"],
            "Source: pyproject.toml | Field: project.dependencies",
            require_spdx_id(main),
            ci,
            "two-deps",
            doc_uuid,
            exporter,
            offline=True,
        )
    graph = graph_of(exporter)
    ids = {e["name"]: e["spdxId"] for e in graph if e["type"] == "software_Package"}
    by_package = {
        name: [
            r["to"][0]
            for r in graph
            if r.get("relationshipType")
            in ("hasDeclaredLicense", "hasConcludedLicense")
            and r["from"] == ids[name]
        ]
        for name in ("a", "b")
    }
    assert by_package["a"] == ["expandedlicensing_NoAssertionLicense"]
    assert by_package["b"] == []
