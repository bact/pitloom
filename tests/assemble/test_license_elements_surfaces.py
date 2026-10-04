# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every surface turns a licence value into the same element: a
``LicenseExpression`` for a valid SPDX expression, a ``SimpleLicensingText``
for anything else, nothing for an absent value; one element per distinct
licence, whichever surface or package asked for it.

See also: :mod:`tests.extract.test_license_classify` for the classifier and
:mod:`pitloom.assemble.spdx3._license_elements` for the one builder.
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import generate_wheel_sbom
from pitloom.assemble.spdx3 import deps_installed
from pitloom.assemble.spdx3.deps import add_dependencies
from pitloom.assemble.spdx3.deps_license import _apply_license
from pitloom.assemble.spdx3.document import build, build_model
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from tests._license_graph import license_elements, license_value

from .conftest import _FakeMetadata, _make_ci, _make_dummy_wheel

_EXPRESSION = "simplelicensing_LicenseExpression"
_TEXT = "simplelicensing_SimpleLicensingText"
_FULL_TEXT = (
    "Permission is hereby granted, free of charge,\nto any person obtaining a copy."
)

#: raw value -> (element type, element value); ``None`` = no element.
_CASES: list[tuple[str | None, tuple[str, str] | None, bool]] = [
    ("MIT", (_EXPRESSION, "MIT"), False),
    ("mit and apache-2.0", (_EXPRESSION, "Apache-2.0 AND MIT"), False),
    (
        "GPL-2.0-only WITH Classpath-exception-2.0",
        (_EXPRESSION, "GPL-2.0-only WITH Classpath-exception-2.0"),
        False,
    ),
    ("LicenseRef-x", (_EXPRESSION, "LicenseRef-x"), False),
    (_FULL_TEXT, (_TEXT, _FULL_TEXT), False),
    ("MIT OR", (_TEXT, "MIT OR"), True),
    (None, None, False),
    ("", None, False),
    ("UNKNOWN", None, False),
    ("unknown", None, False),
    (" UNKNOWN ", None, False),
    ("   ", None, False),
]


def _graph(exporter: Spdx3JsonExporter) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(exporter.to_json())["@graph"]
    return graph


def _project(license_name: str | None) -> ProjectMetadata:
    return ProjectMetadata(name="p", version="1.0", license_name=license_name)


def _model(license_id: str | None) -> AiModelMetadata:
    return AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.ONNX),
        name="m",
        license=license_id,
    )


def _deps(license_id: str | None) -> list[dict[str, Any]]:
    """A dependency whose installed metadata declares *license_id*, through
    the whole enrichment (so the NOASSERTION fallback applies)."""
    fields = {"Version": "1.0"}
    if license_id is not None:
        fields["License"] = license_id
    doc_uuid = compute_doc_uuid("surfaces", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    exporter.add_creation_info(ci)
    main = spdx3.software_Package(
        spdxId="https://x/1#Package-1", name="main", creationInfo=ci
    )
    exporter.add_package(main)
    with (
        patch.object(
            deps_installed, "get_pkg_metadata", lambda _n: _FakeMetadata(fields)
        ),
        patch.object(deps_installed, "get_package_version", lambda _n: "1.0"),
    ):
        add_dependencies(
            ["dep==1.0"],
            "Source: pyproject.toml | Field: project.dependencies",
            require_spdx_id(main),
            ci,
            "surfaces",
            doc_uuid,
            exporter,
            offline=True,
        )
    return _graph(exporter)


def _main_package(license_id: str | None) -> list[dict[str, Any]]:
    doc = DocumentModel(
        project=_project(license_id), creation_metadata=CreationMetadata()
    )
    return _graph(build(doc))


def _wheel(license_id: str | None) -> list[dict[str, Any]]:
    if license_id and "\n" in license_id:
        pytest.skip("a METADATA header is one line")
    return _wheel_graph(license_id)


def _wheel_graph(license_id: str | None) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory() as tmp:
        wheel = _make_dummy_wheel(Path(tmp), license_expression=license_id)
        graph: list[dict[str, Any]] = json.loads(
            generate_wheel_sbom(wheel, offline=True)
        )["@graph"]
    return graph


def _standalone_model(license_id: str | None) -> list[dict[str, Any]]:
    return _graph(build_model(_model(license_id), CreationMetadata()))


def _project_with_model(license_id: str | None) -> list[dict[str, Any]]:
    doc = DocumentModel(
        project=_project(None),
        creation_metadata=CreationMetadata(),
        ai_models=[_model(license_id)],
    )
    return _graph(build(doc))


def _file_tag(license_id: str | None) -> list[dict[str, Any]]:
    file = ProjectFile(
        physical_path="pkg/a.py",
        distribution_path="pkg/a.py",
        digest_sha256="a" * 64,
        spdx_license_identifier=license_id,
    )
    project = ProjectMetadata(name="p", version="1.0", files=[file])
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())
    return _graph(build(doc))


#: surface -> (builder, whether a package without a licence gets NOASSERTION).
_SURFACES: dict[str, tuple[Callable[[str | None], list[dict[str, Any]]], bool]] = {
    "dependency": (_deps, True),
    "main-package": (_main_package, True),
    "wheel": (_wheel, True),
    "standalone-model": (_standalone_model, False),
    "project-model": (_project_with_model, True),
    "file-tag": (_file_tag, True),
}


def _stated(graph: list[dict[str, Any]]) -> list[tuple[str, str | None]]:
    """The licence elements a surface was asked for, not the NOASSERTION a
    package without one gets."""
    return [
        (e["type"], license_value(e))
        for e in license_elements(graph)
        if license_value(e) != "NOASSERTION"
    ]


@pytest.mark.parametrize("surface", list(_SURFACES))
@pytest.mark.parametrize(
    ("raw", "expected", "warns"),
    [pytest.param(*c, id=repr(c[0])[:30]) for c in _CASES],
)
def test_licence_element_by_surface(
    surface: str,
    raw: str | None,
    expected: tuple[str, str] | None,
    warns: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    build_surface, falls_back = _SURFACES[surface]
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        graph = build_surface(raw)
    assert _stated(graph) == ([expected] if expected else [])
    if expected is None:
        # A value that states no licence is as good as none: NOASSERTION.
        assert any(
            license_value(e) == "NOASSERTION" for e in license_elements(graph)
        ) is (falls_back)
    if warns:
        assert (
            sum(
                "not a valid SPDX license expression" in r.message
                for r in caplog.records
            )
            == 1
        )
    else:
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_same_licence_from_two_dependencies_is_one_element() -> None:
    doc_uuid = compute_doc_uuid("twodeps", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    exporter.add_creation_info(ci)
    for i, spelling in enumerate(["MIT", "mit"]):
        package = spdx3.software_Package(
            spdxId=f"https://x/1#Package-{i}", name=f"dep{i}", creationInfo=ci
        )
        exporter.add_package(package)
        _apply_license(
            spelling,
            "Source: installed metadata",
            package,
            ci,
            "twodeps",
            doc_uuid,
            exporter,
        )
    graph = _graph(exporter)
    assert [license_value(e) for e in license_elements(graph)] == ["MIT"]
    rels = [e for e in graph if e["type"] == "Relationship"]
    assert len({r["to"][0] for r in rels}) == 1 and len(rels) == 2


@pytest.mark.parametrize(
    ("raw", "kind", "value", "tagged"),
    [
        ("mit", _EXPRESSION, "MIT", True),
        ("MIT", _EXPRESSION, "MIT", False),
        (" MIT ", _EXPRESSION, "MIT", False),
        ("none", _TEXT, "none", False),
        ("NOASSERTION", _TEXT, "NOASSERTION", False),
    ],
)
def test_single_candidate_value_is_normalised_and_the_raw_kept(
    raw: str, kind: str, value: str, tagged: bool
) -> None:
    """A changed expression records what it was in the provenance; an
    unchanged one, and NOASSERTION/NONE as written, record nothing."""
    graph = _deps(raw)
    (element,) = [e for e in license_elements(graph) if e["type"] == kind]
    assert license_value(element) == value
    statements = " ".join(e["statement"] for e in graph if e["type"] == "Annotation")
    assert ("normalized-from" in statements) is tagged


def _provenance_fields(graph: list[dict[str, Any]], subject: str) -> list[str]:
    """The ``license`` provenance string(s) of every Annotation on *subject*."""
    out: list[str] = []
    for e in graph:
        if e["type"] == "Annotation" and e["subject"] == subject:
            fields = json.loads(e["statement"]).get("fields", {})
            if "license" in fields:
                out.append(json.dumps(fields["license"], sort_keys=True))
    return out


def _two_packages(
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
    return _graph(exporter)


@pytest.mark.parametrize(
    ("first", "second", "note_on"),
    [
        ("mit", "MIT", "element"),  # the element is made from the raw one
        ("MIT", "mit", "relationship"),  # a reused element: the second source's
    ],
)
def test_the_raw_value_is_recorded_per_source(
    first: str, second: str, note_on: str
) -> None:
    """D2: the raw value stays in provenance, also from a transparent source
    (pyproject) and also when the element already exists."""
    graph = _two_packages([first, second])
    (element,) = license_elements(graph)
    rels = [e for e in graph if e["type"] == "Relationship"]
    noted = [
        subject
        for subject in [element["spdxId"], *(r["spdxId"] for r in rels)]
        if any("normalized-from" in f for f in _provenance_fields(graph, subject))
    ]
    expected = element["spdxId"] if note_on == "element" else rels[1]["spdxId"]
    assert noted == [expected]


@pytest.mark.parametrize(
    ("declared", "concluded", "value"),
    [
        ("GPL-2.0+", "GPL-2.0-or-later", "GPL-2.0-or-later"),
        ("lgpl-2.1+", "LGPL-2.1+", "LGPL-2.1-or-later"),
        ("GPL-2.0 AND MIT", "mit and gpl-2.0", "GPL-2.0 AND MIT"),
        ("Apache-2.0+", "apache-2.0+", "Apache-2.0+"),
        ("Foo ", "Foo", "Foo"),
    ],
)
def test_equivalent_spellings_are_one_element_and_no_conflict(
    declared: str, concluded: str, value: str
) -> None:
    project = ProjectMetadata(
        name="p", version="1.0", license_name=declared, license_concluded=concluded
    )
    graph = _graph(
        build(DocumentModel(project=project, creation_metadata=CreationMetadata()))
    )
    assert [license_value(e) for e in license_elements(graph)] == [value]
    assert not [
        e for e in graph if e["type"] == "Annotation" and "candidates" in e["statement"]
    ]


_DEPRECATED_NOTE = "GPL-2.0 (GPL-2.0-only or GPL-2.0-or-later)"


@pytest.mark.parametrize("raw", ["GPL-2.0", "gpl-2.0"])
def test_a_bare_deprecated_id_stays_as_written_with_a_note(raw: str) -> None:
    """``GPL-2.0`` is never mapped to ``-only``/``-or-later``: which was meant
    is unknown, so the id stays and the provenance says so (single source,
    and two sources that disagree only in case)."""
    single = _two_packages([raw])
    (element,) = license_elements(single)
    assert license_value(element) == "GPL-2.0"
    assert any(
        _DEPRECATED_NOTE in f for f in _provenance_fields(single, element["spdxId"])
    )

    project = ProjectMetadata(
        name="p", version="1.0", license_name=raw, license_concluded="GPL-2.0"
    )
    both = _graph(
        build(DocumentModel(project=project, creation_metadata=CreationMetadata()))
    )
    (element,) = license_elements(both)
    assert license_value(element) == "GPL-2.0"
    assert any(
        _DEPRECATED_NOTE in f for f in _provenance_fields(both, element["spdxId"])
    )
    assert not [
        e for e in both if e["type"] == "Annotation" and "candidates" in e["statement"]
    ]


def test_the_deprecated_id_note_is_per_source_on_a_reused_element() -> None:
    graph = _two_packages(["GPL-2.0 AND MIT", "gpl-2.0 and mit"])
    (element,) = license_elements(graph)
    rels = [e for e in graph if e["type"] == "Relationship"]
    assert any(
        _DEPRECATED_NOTE in f for f in _provenance_fields(graph, element["spdxId"])
    )
    assert any(
        _DEPRECATED_NOTE in f for f in _provenance_fields(graph, rels[1]["spdxId"])
    )
    assert not _provenance_fields(graph, rels[0]["spdxId"])


@pytest.mark.parametrize("raw", ["GPL-2.0+", "GPL-2.0-only", "MIT", "eCos-2.0"])
def test_no_deprecated_id_note_where_nothing_is_ambiguous(raw: str) -> None:
    graph = _two_packages([raw])
    assert not any(
        "deprecated-license-id" in f
        for e in license_elements(graph)
        for f in _provenance_fields(graph, e["spdxId"])
    )
