# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every surface turns a licence value into the same element: a
``LicenseExpression`` for a valid SPDX expression, a ``SimpleLicensingText``
for anything else, nothing for an absent value, and for ``NOASSERTION``/
``NONE``/``UNKNOWN`` no element but the ``NoAssertionLicense``/``NoneLicense``
individual; one element per distinct licence, whichever surface or package
asked for it.

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

import pytest

from pitloom.assemble import generate_wheel_sbom
from pitloom.assemble.spdx3.document import build, build_model
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.extract.project.sdist import read_sdist
from tests._license_graph import (
    dependency_graph,
    graph_of,
    hook_metadata,
    license_elements,
    license_targets,
    license_value,
    onnx_model,
    project_graph,
    provenance_fields,
    two_packages,
)

from .conftest import _make_dummy_wheel, _make_sdist

_EXPRESSION = "simplelicensing_LicenseExpression"
_TEXT = "simplelicensing_SimpleLicensingText"
_FULL_TEXT = (
    "Permission is hereby granted, free of charge,\nto any person obtaining a copy."
)

_NOASSERTION = "NOASSERTION"
_NONE = "NONE"

#: raw value -> (expected element: ``(type, value)``; an individual:
#: ``(None, "NOASSERTION"|"NONE")``; ``None`` = nothing), whether a WARNING.
_Expected = tuple[str | None, str] | None
_CASES: list[tuple[str | None, _Expected, bool]] = [
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
    # absent or blank: no claim at all
    (None, None, False),
    ("", None, False),
    ("   ", None, False),
    # a source that says it does not know, or that there is none
    ("UNKNOWN", (None, _NOASSERTION), False),
    ("unknown", (None, _NOASSERTION), False),
    (" UNKNOWN ", (None, _NOASSERTION), False),
    ("NOASSERTION", (None, _NOASSERTION), False),
    ("noassertion", (None, _NOASSERTION), False),
    ("NONE", (None, _NONE), False),
    ("none", (None, _NONE), False),
]


def _project(license_name: str | None) -> ProjectMetadata:
    return ProjectMetadata(name="p", version="1.0", license_name=license_name)


def _deps(license_id: str | None) -> list[dict[str, Any]]:
    """A dependency whose installed metadata declares *license_id*."""
    fields = {} if license_id is None else {"License": license_id}
    return dependency_graph(fields, offline=True)


def _pypi(license_id: str | None) -> list[dict[str, Any]]:
    """A dependency that is not installed, whose PyPI record carries
    *license_id* as ``license_expression``."""
    return dependency_graph(
        None, {} if license_id is None else {"license_expression": license_id}
    )


def _main_package(license_id: str | None) -> list[dict[str, Any]]:
    return project_graph(_project(license_id))


def _wheel(license_id: str | None) -> list[dict[str, Any]]:
    if license_id and "\n" in license_id:
        pytest.skip("a METADATA header is one line")
    with tempfile.TemporaryDirectory() as tmp:
        wheel = _make_dummy_wheel(Path(tmp), license_expression=license_id)
        graph: list[dict[str, Any]] = json.loads(
            generate_wheel_sbom(wheel, offline=True)
        )["@graph"]
    return graph


def _standalone_model(license_id: str | None) -> list[dict[str, Any]]:
    return graph_of(build_model(onnx_model(license_id), CreationMetadata()))


def _project_with_model(license_id: str | None) -> list[dict[str, Any]]:
    doc = DocumentModel(
        project=_project(None),
        creation_metadata=CreationMetadata(),
        ai_models=[onnx_model(license_id)],
    )
    return graph_of(build(doc))


def _file_tag(license_id: str | None) -> list[dict[str, Any]]:
    file = ProjectFile(
        physical_path="pkg/a.py",
        distribution_path="pkg/a.py",
        digest_sha256="a" * 64,
        spdx_license_identifier=license_id,
    )
    return project_graph(ProjectMetadata(name="p", version="1.0", files=[file]))


def _sdist(license_id: str | None) -> list[dict[str, Any]]:
    if license_id and "\n" in license_id:
        pytest.skip("a PKG-INFO header is one line")
    header = "" if license_id is None else f"License-Expression: {license_id}\n"
    pkg_info = f"Metadata-Version: 2.4\nName: demo\nVersion: 1.0.0\n{header}"
    with tempfile.TemporaryDirectory() as tmp:
        sdist = _make_sdist(Path(tmp), members={"PKG-INFO": pkg_info.encode()})
        metadata = read_sdist(sdist, read_config=False).metadata
    return project_graph(metadata)


def _hook(license_id: str | None) -> list[dict[str, Any]]:
    """The Hatchling build hook's reader, *license_id* as ``license.text``."""
    licence = (
        "" if license_id is None else f"license = {{text = {json.dumps(license_id)}}}\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "pyproject.toml").write_text(
            f'[project]\nname = "demo"\nversion = "1.0.0"\n{licence}',
            encoding="utf-8",
        )
        metadata = hook_metadata(root)
    return project_graph(metadata)


_SURFACES: dict[str, Callable[[str | None], list[dict[str, Any]]]] = {
    "dependency-installed": _deps,
    "dependency-pypi": _pypi,
    "main-package": _main_package,
    "hook": _hook,
    "wheel": _wheel,
    "sdist": _sdist,
    "standalone-model": _standalone_model,
    "project-model": _project_with_model,
    "file-tag": _file_tag,
}


#: Relationship a licence stated by each surface gets: the package's own
#: statement (pyproject, wheel METADATA, sdist PKG-INFO, a file's own tag, an
#: AI model's metadata) is *declared*; a dependency's installed metadata and
#: PyPI are third-party records, *concluded* (see ``is_license_concluded``).
_RELATIONSHIP: dict[str, str] = {
    "dependency-installed": "hasConcludedLicense",
    "dependency-pypi": "hasConcludedLicense",
    "main-package": "hasDeclaredLicense",
    "hook": "hasDeclaredLicense",
    "wheel": "hasDeclaredLicense",
    "sdist": "hasDeclaredLicense",
    "standalone-model": "hasDeclaredLicense",
    "project-model": "hasDeclaredLicense",
    "file-tag": "hasDeclaredLicense",
}


def _stated(graph: list[dict[str, Any]]) -> list[tuple[str, str | None]]:
    return [(e["type"], license_value(e)) for e in license_elements(graph)]


@pytest.mark.parametrize("surface", list(_SURFACES))
@pytest.mark.parametrize(
    ("raw", "expected", "warns"),
    [pytest.param(*c, id=repr(c[0])[:30]) for c in _CASES],
)
def test_licence_element_by_surface(
    surface: str,
    raw: str | None,
    expected: _Expected,
    warns: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        graph = _SURFACES[surface](raw)
    targets = license_targets(graph)
    if expected is not None:
        assert {
            r["relationshipType"]
            for r in graph
            if r.get("relationshipType")
            in ("hasDeclaredLicense", "hasConcludedLicense")
        } == {_RELATIONSHIP[surface]}
    if expected is None:
        assert not _stated(graph) and not targets
    elif expected[0] is None:
        # An individual: no element, and the relationship points at it.
        assert not _stated(graph)
        assert targets == [expected[1]]
    else:
        assert _stated(graph) == [expected]
        assert targets == [expected[1]]
    # Whatever the surface, NOASSERTION/NONE are never a licence's own value.
    assert not [
        e for e in license_elements(graph) if license_value(e) in {_NOASSERTION, _NONE}
    ]
    # The profile follows (the dependency surfaces build no document).
    documents = [e for e in graph if e["type"] == "SpdxDocument"]
    if documents:
        profiles = documents[0]["profileConformance"]
        assert ("expandedLicensing" in profiles) is bool(
            expected and expected[0] is None
        )
        assert ("simpleLicensing" in profiles) is (expected is not None)
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
    graph = two_packages(["MIT", "mit"], "Source: installed metadata")
    assert [license_value(e) for e in license_elements(graph)] == ["MIT"]
    rels = [e for e in graph if e["type"] == "Relationship"]
    assert len({r["to"][0] for r in rels}) == 1 and len(rels) == 2


@pytest.mark.parametrize(
    ("raw", "kind", "value", "tagged"),
    [
        ("mit", _EXPRESSION, "MIT", True),
        ("MIT", _EXPRESSION, "MIT", False),
        (" MIT ", _EXPRESSION, "MIT", False),
    ],
)
def test_single_candidate_value_is_normalised_and_the_raw_kept(
    raw: str, kind: str, value: str, tagged: bool
) -> None:
    """A changed expression records what it was in the provenance; an
    unchanged one records nothing."""
    graph = _deps(raw)
    (element,) = [e for e in license_elements(graph) if e["type"] == kind]
    assert license_value(element) == value
    statements = " ".join(e["statement"] for e in graph if e["type"] == "Annotation")
    assert ("normalized-from" in statements) is tagged


_DEPRECATED_NOTE = "GPL-2.0 (GPL-2.0-only or GPL-2.0-or-later)"
_MANIFEST = "Source: pyproject.toml | Field: x"


@pytest.mark.parametrize(
    ("values", "provenance", "note", "expected"),
    [
        # D2: the raw value stays in provenance, also from a transparent
        # source (pyproject): on the element made from the raw one ...
        (["mit", "MIT"], _MANIFEST, "normalized-from", ("note", "", "")),
        # ... and on the second source's relationship to a reused element
        (["MIT", "mit"], _MANIFEST, "normalized-from", ("", "", "note")),
        (["GPL-2.0 AND MIT", "gpl-2.0 and mit"], _MANIFEST, _DEPRECATED_NOTE,
         ("note", "", "note")),
        # Only a per-source note goes on the relationship; a non-manifest
        # source's plain provenance is on the element already.
        (["MIT", "MIT"], "Source: installed metadata | Package: d",
         "normalized-from", ("plain", "", "")),
    ],
    ids=["made-from-raw", "reused-raw", "reused-deprecated", "reused-no-note"],
)  # fmt: skip
def test_a_note_is_recorded_per_source(
    values: list[str], provenance: str, note: str, expected: tuple[str, ...]
) -> None:
    """Per subject (the one element, then each relationship): ``note`` when
    a provenance field holds *note*, ``plain`` when fields hold none, ``""``
    when there is no field at all."""
    graph = two_packages(values, provenance)
    (element,) = license_elements(graph)
    rels = [e for e in graph if e["type"] == "Relationship"]
    assert len(rels) == 2
    got = []
    for subject in [element["spdxId"], *(r["spdxId"] for r in rels)]:
        fields = provenance_fields(graph, subject)
        noted = any(note in f for f in fields)
        got.append("note" if noted else "plain" if fields else "")
    assert tuple(got) == expected


@pytest.mark.parametrize(
    ("declared", "concluded", "value"),
    [
        ("GPL-2.0+", "GPL-2.0-or-later", "GPL-2.0-or-later"),
        ("lgpl-2.1+", "LGPL-2.1+", "LGPL-2.1-or-later"),
        ("GPL-2.0 AND MIT", "mit and gpl-2.0", "GPL-2.0 AND MIT"),
        ("Apache-2.0+", "apache-2.0+", "Apache-2.0+"),
        ("Foo ", "Foo", "Foo "),
    ],
)
def test_equivalent_spellings_are_one_element_and_no_conflict(
    declared: str, concluded: str, value: str
) -> None:
    project = ProjectMetadata(
        name="p", version="1.0", license_name=declared, license_concluded=concluded
    )
    graph = project_graph(project)
    assert [license_value(e) for e in license_elements(graph)] == [value]
    assert not [
        e for e in graph if e["type"] == "Annotation" and "candidates" in e["statement"]
    ]


@pytest.mark.parametrize("raw", ["GPL-2.0", "gpl-2.0"])
def test_a_bare_deprecated_id_stays_as_written_with_a_note(raw: str) -> None:
    """``GPL-2.0`` is never mapped to ``-only``/``-or-later``: which was meant
    is unknown, so the id stays and the provenance says so (single source,
    and two sources that disagree only in case)."""
    single = two_packages([raw])
    (element,) = license_elements(single)
    assert license_value(element) == "GPL-2.0"
    assert any(
        _DEPRECATED_NOTE in f for f in provenance_fields(single, element["spdxId"])
    )

    project = ProjectMetadata(
        name="p", version="1.0", license_name=raw, license_concluded="GPL-2.0"
    )
    both = project_graph(project)
    (element,) = license_elements(both)
    assert license_value(element) == "GPL-2.0"
    assert any(
        _DEPRECATED_NOTE in f for f in provenance_fields(both, element["spdxId"])
    )
    assert not [
        e for e in both if e["type"] == "Annotation" and "candidates" in e["statement"]
    ]


@pytest.mark.parametrize("raw", ["GPL-2.0+", "GPL-2.0-only", "MIT", "eCos-2.0"])
def test_no_deprecated_id_note_where_nothing_is_ambiguous(raw: str) -> None:
    graph = two_packages([raw])
    assert license_elements(graph)
    assert not any(
        "deprecated-license-id" in f
        for e in license_elements(graph)
        for f in provenance_fields(graph, e["spdxId"])
    )
