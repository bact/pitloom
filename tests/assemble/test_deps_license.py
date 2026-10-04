# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ``pitloom.assemble.spdx3.deps_license`` -- license-element
creation/truncation, declared-vs-concluded classification, the two-candidate
conflict rules (``NOASSERTION`` never conflicts, ``NONE`` does against a real
licence), and the defensive relationship-build raise. Split out of
test_deps_enrichment_pypi_fallback.py to keep that file under this repo's
file-size soft limit.

See also: test_deps_enrichment_originator_license.py for the
higher-level, pipeline-integration license tests.
"""

# pylint: disable=protected-access
# pylint: disable=missing-function-docstring

from __future__ import annotations

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._license_elements import (
    LicenseElement,
    get_or_create_license_element,
)
from pitloom.assemble.spdx3.deps_license import (
    _build_license_relationship,
    build_license_elements,
)
from pitloom.assemble.spdx3.provenance import (
    is_license_concluded,
    parse_provenance_value,
)
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid
from pitloom.export.spdx3_json import Spdx3JsonExporter

from .conftest import _make_ci


@pytest.mark.parametrize(
    ("length", "name"), [(60, "X" * 60), (61, "X" * 57 + "..."), (80, "X" * 57 + "...")]
)
def test_get_or_create_license_element_truncates_long_name(
    length: int, name: str
) -> None:
    doc_uuid = compute_doc_uuid("longlicense", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()

    element = get_or_create_license_element(
        "X" * length, "Source: test", ci, "longlicense", doc_uuid, exporter
    )

    assert element is not None
    license_text = exporter.object_set.obj_by_id[element.spdx_id]
    assert isinstance(license_text, spdx3.simplelicensing_SimpleLicensingText)
    assert license_text.name == name


def test_get_or_create_license_element_truncates_at_first_newline() -> None:
    """A multi-line license_id (e.g. full custom license text used as its
    own LicenseRef identifier) must use only its first line as the
    element's display name."""
    doc_uuid = compute_doc_uuid("multilinelicense", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    multiline_id = "Custom License\nAll rights reserved.\nSee LICENSE for details."

    element = get_or_create_license_element(
        multiline_id, "Source: test", ci, "multilinelicense", doc_uuid, exporter
    )

    assert element is not None
    license_text = exporter.object_set.obj_by_id[element.spdx_id]
    assert isinstance(license_text, spdx3.simplelicensing_SimpleLicensingText)
    assert license_text.name == "Custom License"
    assert license_text.simplelicensing_licenseText == multiline_id


@pytest.mark.parametrize(
    ("provenance", "concluded"),
    [
        ("Source: pyproject.toml | Field: project.license", False),
        # How a value was read does not change whose statement it is.
        ("Source: pyproject.toml | Field: x | Method: licenseid_detection", False),
        ("Source: LICENSE | Method: licenseid_detection | Tool: licenseid==1", False),
        ("Source: CITATION.cff | Field: license", False),
        ("Source: codemeta.json | Field: license", False),
        ("Source: README.md | Method: yaml_frontmatter", False),
        ("Source: model.pt2 | Field: extra/license", False),
        (
            "Source: Hugging Face Hub | File: LICENSE | Method: licenseid_detection",
            False,
        ),
        ("Source: demo-1.0.dist-info | File: METADATA", False),
        ("Source: deployed package metadata | Package: dep", False),
        ("Source: installed metadata | Package: dep", True),
        ("Source: installed metadata | Package: dep | Field: Classifier", True),
        ("Source: PyPI JSON API | Package: dep", True),
        ("Source: PyPI JSON API (cached) | Package: dep", True),
        ("Field: license", True),  # no source: nobody's statement
    ],
)
def test_is_license_concluded_only_for_a_third_party_record(
    provenance: str, concluded: bool
) -> None:
    assert is_license_concluded(parse_provenance_value(provenance)) is concluded


def test_build_license_elements_single_candidate_transparent_source_is_declared() -> (
    None
):
    """build_license_elements() in single-candidate mode, given a
    transparent/method-less provenance, must return (rel_declared,
    None) -- not silently return None for both halves, which would leave
    the caller with no relationship to add at all for a value it does
    have."""
    doc_uuid = compute_doc_uuid("single-candidate", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()

    rel_declared, rel_concluded = build_license_elements(
        license_id="MIT",
        package_spdx_id="https://example.com/Package-1",
        license_provenance="Source: pyproject.toml | Field: project.license_concluded",
        creation_info=ci,
        doc_name="single-candidate",
        doc_uuid=doc_uuid,
        exporter=exporter,
    )

    assert rel_concluded is None
    assert rel_declared is not None
    assert rel_declared.relationshipType == spdx3.RelationshipType.hasDeclaredLicense


def test_build_license_elements_empty_string_concluded_id_is_single_candidate() -> None:
    """An empty-string concluded_license_id (never a meaningful license id,
    unlike a field like requires_python where "" can mean "explicitly no
    constraint") must dispatch to single-candidate mode exactly like None
    -- not silently enter two-candidate mode with a spurious empty second
    candidate."""
    doc_uuid = compute_doc_uuid("empty-concluded", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()

    rel_declared, rel_concluded = build_license_elements(
        license_id="MIT",
        package_spdx_id="https://example.com/Package-1",
        license_provenance="Source: pyproject.toml | Field: project.license",
        creation_info=ci,
        doc_name="empty-concluded",
        doc_uuid=doc_uuid,
        exporter=exporter,
        concluded_license_id="",
    )

    assert rel_concluded is None
    assert rel_declared is not None
    assert rel_declared.relationshipType == spdx3.RelationshipType.hasDeclaredLicense


def test_build_license_relationship_raises_when_relationship_build_fails() -> None:
    """``build_relationship`` returns ``None`` when ``from_id`` is ``None``;
    ``_build_license_relationship`` must fail loudly rather than silently
    swallow it."""
    ci = _make_ci()
    with pytest.raises(ValueError, match="Failed to build relationship"):
        _build_license_relationship(
            None,  # type: ignore[arg-type]
            LicenseElement(
                "http://spdx.org/spdxdocs/license-1", "MIT", "", True, False
            ),
            spdx3.RelationshipType.hasDeclaredLicense,
            ci,
            "doc",
            "uuid",
            Spdx3JsonExporter(),
        )


@pytest.mark.parametrize(
    ("declared", "concluded", "expected"),
    [
        ("  ", "MIT", (False, True)),
        ("MIT", "  ", (True, False)),
        ("  ", "  ", (False, False)),
    ],
)
def test_build_license_elements_two_candidates_one_states_no_licence(
    declared: str, concluded: str, expected: tuple[bool, bool]
) -> None:
    """A candidate that states no licence yields no relationship and no
    conflict annotation; the other one is unaffected."""
    doc_uuid = compute_doc_uuid("one-unknown", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()

    rels = build_license_elements(
        license_id=declared,
        package_spdx_id="https://example.com/Package-1",
        license_provenance="Source: pyproject.toml | Field: project.license",
        creation_info=_make_ci(),
        doc_name="one-unknown",
        doc_uuid=doc_uuid,
        exporter=exporter,
        concluded_license_id=concluded,
    )

    assert tuple(r is not None for r in rels) == expected
    assert not [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Annotation)
    ]


@pytest.mark.parametrize(
    ("declared", "concluded", "same_target", "conflicts"),
    [
        ("UNKNOWN", "noassertion", True, 0),
        ("NONE", "none", True, 0),
        ("NOASSERTION", "MIT", False, 0),
        ("unknown", "MIT", False, 0),
        ("MIT", "UNKNOWN", False, 0),
        ("NONE", "MIT", False, 1),
        ("MIT", "none", False, 1),
        ("NOASSERTION", "NONE", False, 0),
        # a licence's SPDX List name and its id are one licence, either way
        ("MIT License", "MIT", False, 0),
        ("MIT", "mit license", False, 0),
        ("Apache Software License", "Apache-2.0", False, 1),  # not the List name
    ],
)
def test_build_license_elements_two_candidates_with_individuals(
    declared: str, concluded: str, same_target: bool, conflicts: int
) -> None:
    """Two candidates that are the same individual (``UNKNOWN`` is
    ``NOASSERTION``) are no conflict. ``NOASSERTION`` against a real licence
    is none either, nor against ``NONE`` (it only says "unknown"; both
    relationships stay, each for its own role); ``NONE`` against a real
    licence is one."""
    doc_uuid = compute_doc_uuid("individuals", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()

    rel_declared, rel_concluded = build_license_elements(
        license_id=declared,
        package_spdx_id="https://example.com/Package-1",
        license_provenance="Source: pyproject.toml | Field: project.license",
        creation_info=_make_ci(),
        doc_name="individuals",
        doc_uuid=doc_uuid,
        exporter=exporter,
        concluded_license_id=concluded,
    )

    assert rel_declared is not None and rel_concluded is not None
    assert (rel_declared.to == rel_concluded.to) is same_target
    objects = exporter.object_set.objects
    found = [
        o
        for o in objects
        if isinstance(o, spdx3.Annotation) and "candidates" in (o.statement or "")
    ]
    assert len(found) == conflicts
    # An individual never becomes an element.
    held = {
        getattr(o, "simplelicensing_licenseExpression", None)
        or getattr(o, "simplelicensing_licenseText", None)
        for o in objects
        if isinstance(o, spdx3.simplelicensing_AnyLicenseInfo)
    }
    assert not {"NOASSERTION", "NONE"} & {h for h in held if h}
