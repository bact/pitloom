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
    _is_license_concluded,
    build_license_elements,
)
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid
from pitloom.export.spdx3_json import Spdx3JsonExporter

from .conftest import _make_ci


def test_get_or_create_license_element_truncates_long_name() -> None:
    doc_uuid = compute_doc_uuid("longlicense", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    long_id = "X" * 80

    element = get_or_create_license_element(
        long_id, "Source: test", ci, "longlicense", doc_uuid, exporter
    )

    assert element is not None
    license_text = exporter.object_set.obj_by_id[element.spdx_id]
    assert isinstance(license_text, spdx3.simplelicensing_SimpleLicensingText)
    assert license_text.name == "X" * 57 + "..."
    assert len(license_text.name) == 60


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


def test_is_license_concluded_transparent_no_method_classified_as_declared() -> None:
    """A transparent, method-less source (e.g. read straight out of
    pyproject.toml, not detected/inferred) is classified as declared, not
    concluded -- every shipped extractor's real license_concluded
    provenance is non-transparent (a LICENSE/CITATION.cff/codemeta.json
    scan), so this only fires for a value a future/library-API caller
    supplies directly, but build_license_elements()'s single-candidate
    mode must still classify it correctly rather than assuming "concluded"
    just because the caller happened to populate license_concluded."""
    assert (
        _is_license_concluded({"source": "pyproject.toml", "field": "license"}) is False
    )


def test_is_license_concluded_non_transparent_source_classified_as_concluded() -> None:
    """A non-transparent source (e.g. an independent LICENSE-file scan) is
    classified as concluded even with no explicit Method: tag."""
    assert _is_license_concluded({"source": "LICENSE"}) is True


def test_is_license_concluded_method_tag_always_wins() -> None:
    """An explicit Method: tag (a detection heuristic ran) always means
    concluded, regardless of source transparency."""
    assert (
        _is_license_concluded(
            {"source": "pyproject.toml", "method": "licenseid_detection"}
        )
        is True
    )


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
