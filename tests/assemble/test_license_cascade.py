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

from typing import Any
from unittest.mock import patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import deps, deps_installed, deps_pypi
from pitloom.assemble.spdx3.deps import add_dependencies
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from tests._license_graph import dependency_graph, graph_of, license_targets
from tests.assemble.conftest import _FakeMetadata, _make_ci

_MIT_CLASSIFIER = ["License :: OSI Approved :: MIT"]


def _dependency(
    installed: dict[str, str] | None = None, **kwargs: Any
) -> tuple[list[dict[str, Any]], list[object]]:
    """One dependency through the whole enrichment (*installed* and *kwargs*
    as :func:`tests._license_graph.dependency_graph` takes them). Returns
    the graph and the calls made to the PyPI licence reader."""
    calls: list[object] = []
    real_reader = deps_pypi._extract_pypi_license

    def spy(info: dict[str, Any], source: str) -> tuple[str | None, str]:
        calls.append(info)
        return real_reader(info, source)

    with patch.object(deps, "_extract_pypi_license", spy):
        graph = dependency_graph(
            installed, provenance_config=ProvenanceConfig(detail="full"), **kwargs
        )
    return graph, calls


def _license_notes(graph: list[dict[str, Any]]) -> str:
    """The provenance comment of every licence relationship and element, as
    one string."""
    return " ".join(
        e.get("comment", "")
        for e in graph
        if e.get("relationshipType") in ("hasDeclaredLicense", "hasConcludedLicense")
        or e["type"].startswith("simplelicensing_")
    )


_UNKNOWN = {"installed": {"License": "UNKNOWN"}}
_FROM_INSTALLED = ("installed metadata", "PyPI")  # this note, never that


@pytest.mark.parametrize(
    ("given", "target", "asked", "notes"),
    [
        pytest.param(
            {**_UNKNOWN, "pypi": {"license_expression": "MIT"}}, "MIT", 1, None,
            id="pypi-expression",
        ),
        pytest.param(
            {**_UNKNOWN, "pypi": {"classifiers": _MIT_CLASSIFIER}}, "MIT", 1, None,
            id="pypi-classifier",
        ),
        pytest.param(
            {
                **_UNKNOWN,
                "pypi": {"license": "UNKNOWN", "classifiers": _MIT_CLASSIFIER},
            },
            "MIT", 1, None,
            id="pypi-placeholder-then-classifier",
        ),
        # settled locally: PyPI is not asked
        pytest.param(
            {**_UNKNOWN, "classifiers": _MIT_CLASSIFIER, "pypi": {}}, "MIT", 0,
            ("Field: Classifier", None),
            id="installed-classifier",
        ),
        # nothing later knows better (an empty record, another placeholder,
        # no PyPI answer): the individual, from the installed source
        pytest.param(
            {**_UNKNOWN, "pypi": {}}, "NOASSERTION", None, _FROM_INSTALLED,
            id="pypi-empty",
        ),
        pytest.param(
            {**_UNKNOWN, "pypi": {"license": "unknown"}}, "NOASSERTION", None,
            _FROM_INSTALLED,
            id="pypi-placeholder",
        ),
        pytest.param(
            _UNKNOWN, "NOASSERTION", None, _FROM_INSTALLED, id="pypi-no-answer"
        ),
        pytest.param(
            {**_UNKNOWN, "pypi": {}, "offline": True}, "NOASSERTION", 0, None,
            id="offline",
        ),
        pytest.param(
            {"pypi": {"license_expression": "NOASSERTION"}}, "NOASSERTION", None,
            ("PyPI JSON API", None),
            id="pypi-only-placeholder",
        ),
        # NONE is a statement: PyPI is not asked for the licence
        pytest.param(
            {"installed": {"License": "NONE"}, "pypi": {"license_expression": "MIT"}},
            "NONE", 0, None,
            id="installed-none-ends",
        ),
        # two placeholders: one individual, the first source's note
        pytest.param(
            {
                "installed": {"License": "unknown"},
                "pypi": {"license_expression": "NOASSERTION"},
            },
            "NOASSERTION", None, _FROM_INSTALLED,
            id="first-placeholder-provenance",
        ),
    ],
)  # fmt: skip
def test_licence_cascade(
    given: dict[str, Any],
    target: str,
    asked: int | None,
    notes: tuple[str, str | None] | None,
) -> None:
    """*given*: the dependency's sources; *asked*: calls to the PyPI licence
    reader (``None``: not checked); *notes*: a provenance note that must be
    there, and one that must not."""
    graph, calls = _dependency(**given)
    assert license_targets(graph) == [target]
    if asked is not None:
        assert len(calls) == asked
    if notes is not None:
        present, absent = notes
        recorded = _license_notes(graph)
        assert present in recorded
        assert absent is None or absent not in recorded


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
        # a malformed record: a non-string classifier, a non-list value
        ({"classifiers": [None, 3, *_MIT_CLASSIFIER]}, "MIT"),
        ({"classifiers": 3}, None),
        ({}, None),
    ],
)
def test_pypi_record_skips_a_placeholder_for_something_better(
    info: dict[str, Any], expected: str | None
) -> None:
    assert deps_pypi._extract_pypi_license(info, "Source: x")[0] == expected


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
