# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``_find_dangling_references``
(:mod:`pitloom.assemble.spdx3._fragments_refs`) and
``_raise_on_dangling_references`` (:mod:`pitloom.assemble.spdx3.fragments`) --
the referential-integrity check
that catches a merged element (typically from a fragment) whose ``Relationship``/
``Annotation`` endpoint doesn't resolve to any object actually present in the
merged graph (and isn't a declared external reference either). The prototypical
cause is a fragment built against a base SBOM's old ``doc_uuid`` (see
:func:`pitloom.assemble._model_generator._doc_identity_of`'s docstring)
merged against a regenerated base SBOM whose element ids have since shifted --
a dangling reference always fails the merge (:class:`FragmentMergeError`), it
is never just a warning.

See also: :mod:`tests.core.test_fragments_merge` for the general merge tests.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._fragments_refs import NAMED_INDIVIDUAL_IDS
from pitloom.assemble.spdx3.fragments import (
    FragmentMergeError,
    _find_dangling_references,
    _raise_on_dangling_references,
    merge_fragments,
)
from pitloom.core.config import FragmentConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter


def _creation_info() -> spdx3.CreationInfo:
    return spdx3.CreationInfo(
        specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )


def test_find_dangling_references_relationship_to_missing_target() -> None:
    """A Relationship's ``to`` pointing at an id with no matching object
    in the graph is reported."""
    ci = _creation_info()
    pkg = spdx3.software_Package(
        spdxId="https://spdx.org/spdxdocs/x-1#Package-1", name="pkg", creationInfo=ci
    )
    rel = spdx3.Relationship(
        spdxId="https://spdx.org/spdxdocs/x-1#Relationship-1",
        from_="https://spdx.org/spdxdocs/x-1#Package-1",
        to=["https://spdx.org/spdxdocs/x-0#Package-1"],  # stale doc_uuid ("x-0")
        relationshipType=spdx3.RelationshipType.dependsOn,
        creationInfo=ci,
    )
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(ci)
    exporter.add_package(pkg)
    exporter.add_relationship(rel)

    dangling = _find_dangling_references(exporter)

    assert dangling == [
        (
            "https://spdx.org/spdxdocs/x-1#Relationship-1",
            "to",
            "https://spdx.org/spdxdocs/x-0#Package-1",
        )
    ]


def test_find_dangling_references_relationship_from_missing_source() -> None:
    """A Relationship's ``from`` pointing at a missing id is also
    reported, independently of ``to``."""
    ci = _creation_info()
    pkg = spdx3.software_Package(
        spdxId="https://spdx.org/spdxdocs/x-1#Package-1", name="pkg", creationInfo=ci
    )
    rel = spdx3.Relationship(
        spdxId="https://spdx.org/spdxdocs/x-1#Relationship-1",
        from_="https://spdx.org/spdxdocs/x-0#Package-1",  # stale doc_uuid ("x-0")
        to=["https://spdx.org/spdxdocs/x-1#Package-1"],
        relationshipType=spdx3.RelationshipType.dependsOn,
        creationInfo=ci,
    )
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(ci)
    exporter.add_package(pkg)
    exporter.add_relationship(rel)

    dangling = _find_dangling_references(exporter)

    assert dangling == [
        (
            "https://spdx.org/spdxdocs/x-1#Relationship-1",
            "from",
            "https://spdx.org/spdxdocs/x-0#Package-1",
        )
    ]


def test_find_dangling_references_annotation_missing_subject() -> None:
    """An Annotation's ``subject`` pointing at a missing id is reported."""
    ci = _creation_info()
    ann = spdx3.Annotation(
        spdxId="https://spdx.org/spdxdocs/x-1#Annotation-1",
        subject="https://spdx.org/spdxdocs/x-0#Package-1",
        annotationType=spdx3.AnnotationType.other,
        statement="stale",
        creationInfo=ci,
    )
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(ci)
    exporter.add_annotation(ann)

    dangling = _find_dangling_references(exporter)

    assert dangling == [
        (
            "https://spdx.org/spdxdocs/x-1#Annotation-1",
            "subject",
            "https://spdx.org/spdxdocs/x-0#Package-1",
        )
    ]


def test_find_dangling_references_all_resolved_is_empty() -> None:
    """No false positives: every endpoint resolving to a real object in
    the graph reports nothing."""
    ci = _creation_info()
    pkg1 = spdx3.software_Package(
        spdxId="https://spdx.org/spdxdocs/x-1#Package-1", name="a", creationInfo=ci
    )
    pkg2 = spdx3.software_Package(
        spdxId="https://spdx.org/spdxdocs/x-1#Package-2", name="b", creationInfo=ci
    )
    rel = spdx3.Relationship(
        spdxId="https://spdx.org/spdxdocs/x-1#Relationship-1",
        from_="https://spdx.org/spdxdocs/x-1#Package-1",
        to=["https://spdx.org/spdxdocs/x-1#Package-2"],
        relationshipType=spdx3.RelationshipType.dependsOn,
        creationInfo=ci,
    )
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(ci)
    exporter.add_package(pkg1)
    exporter.add_package(pkg2)
    exporter.add_relationship(rel)

    result = _find_dangling_references(exporter)
    assert isinstance(result, list)
    assert not result


def test_raise_on_dangling_references_logs_and_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """End-to-end: each dangling reference gets its own ``WARNING:``
    (naming both the referencing element and the missing target, so a
    stale-fragment merge is diagnosable, not a silent no-op), and the
    merge must still fail -- a dangling reference is never just a
    warning."""
    ci = _creation_info()
    pkg = spdx3.software_Package(
        spdxId="https://spdx.org/spdxdocs/x-1#Package-1", name="pkg", creationInfo=ci
    )
    rel = spdx3.Relationship(
        spdxId="https://spdx.org/spdxdocs/x-1#Relationship-1",
        from_="https://spdx.org/spdxdocs/x-1#Package-1",
        to=["https://spdx.org/spdxdocs/x-0#Package-1"],
        relationshipType=spdx3.RelationshipType.dependsOn,
        creationInfo=ci,
    )
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(ci)
    exporter.add_package(pkg)
    exporter.add_relationship(rel)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(FragmentMergeError, match="1 dangling reference"):
            _raise_on_dangling_references(exporter)

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "https://spdx.org/spdxdocs/x-1#Relationship-1" in message
    assert "https://spdx.org/spdxdocs/x-0#Package-1" in message


def test_find_dangling_references_excludes_declared_external_imports() -> None:
    """A Relationship endpoint matching a declared ``ExternalMap`` in the
    main document's ``import_`` is a legitimate external reference, not a
    dangling one -- must not be reported."""
    ci = _creation_info()
    main_doc = spdx3.SpdxDocument(
        spdxId="https://spdx.org/spdxdocs/x-1",
        creationInfo=ci,
        import_=[
            spdx3.ExternalMap(
                externalSpdxId="https://spdx.org/spdxdocs/other-doc#Package-9",
                locationHint="other-fragment.spdx3.json",
            )
        ],
    )
    pkg = spdx3.software_Package(
        spdxId="https://spdx.org/spdxdocs/x-1#Package-1", name="pkg", creationInfo=ci
    )
    rel = spdx3.Relationship(
        spdxId="https://spdx.org/spdxdocs/x-1#Relationship-1",
        from_="https://spdx.org/spdxdocs/x-1#Package-1",
        to=["https://spdx.org/spdxdocs/other-doc#Package-9"],
        relationshipType=spdx3.RelationshipType.dependsOn,
        creationInfo=ci,
    )
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(ci)
    exporter.add_document(main_doc)
    exporter.add_package(pkg)
    exporter.add_relationship(rel)

    result = _find_dangling_references(exporter)
    assert isinstance(result, list)
    assert not result


_TERMS = "https://spdx.org/rdf/3.0.1/terms"
#: Named individuals of SPDX 3 ``Element`` classes (compact JSON name, IRI).
_INDIVIDUALS = [
    ("NoAssertionElement", f"{_TERMS}/Core/NoAssertionElement"),
    ("NoneElement", f"{_TERMS}/Core/NoneElement"),
    ("SpdxOrganization", f"{_TERMS}/Core/SpdxOrganization"),
    (
        "expandedlicensing_NoAssertionLicense",
        f"{_TERMS}/ExpandedLicensing/NoAssertionLicense",
    ),
    (
        "expandedlicensing_NoneLicense",
        f"{_TERMS}/ExpandedLicensing/NoneLicense",
    ),
]
#: Look-alikes that are not element individuals: still dangling.
_NOT_INDIVIDUALS = [
    f"{_TERMS}/Core/NoSuchIndividual",
    f"{_TERMS}/Core/HashAlgorithm/sha256",
    "NoAssertionElement",
]


def _one_package_exporter(
    *, from_: str | None = None, to: str | None = None
) -> Spdx3JsonExporter:
    """An exporter whose only relationship has the given endpoints (the
    package's id where one is ``None``)."""
    ci = _creation_info()
    pkg_id = "https://spdx.org/spdxdocs/x-1#Package-1"
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(ci)
    exporter.add_package(
        spdx3.software_Package(spdxId=pkg_id, name="pkg", creationInfo=ci)
    )
    exporter.add_relationship(
        spdx3.Relationship(
            spdxId="https://spdx.org/spdxdocs/x-1#Relationship-1",
            from_=from_ or pkg_id,
            to=[to or pkg_id],
            relationshipType=spdx3.RelationshipType.hasDeclaredLicense,
            creationInfo=ci,
        )
    )
    return exporter


def test_named_individual_ids_are_read_from_the_bindings() -> None:
    """Every element individual is covered, and no enumeration value."""
    assert {iri for _, iri in _INDIVIDUALS} == NAMED_INDIVIDUAL_IDS
    assert spdx3.HashAlgorithm.sha256 not in NAMED_INDIVIDUAL_IDS


@pytest.mark.parametrize("iri", [iri for _, iri in _INDIVIDUALS])
def test_named_individual_relationship_source_is_not_dangling(iri: str) -> None:
    """The ``to`` end is covered by the merge test below."""
    assert not _find_dangling_references(_one_package_exporter(from_=iri))


def test_named_individual_annotation_subject_is_not_dangling() -> None:
    ci = _creation_info()
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(ci)
    exporter.add_annotation(
        spdx3.Annotation(
            spdxId="https://spdx.org/spdxdocs/x-1#Annotation-1",
            subject=spdx3.IndividualElement.NoneElement,
            annotationType=spdx3.AnnotationType.other,
            statement="s",
            creationInfo=ci,
        )
    )
    assert not _find_dangling_references(exporter)


@pytest.mark.parametrize("target", _NOT_INDIVIDUALS)
def test_non_individual_lookalike_is_still_dangling(target: str) -> None:
    dangling = _find_dangling_references(_one_package_exporter(to=target))
    assert [d[2] for d in dangling] == [target]


def _fragment(namespace: str, target: str) -> dict[str, object]:
    return {
        "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
        "@graph": [
            {
                "type": "CreationInfo",
                "@id": "_:creationinfo0",
                "specVersion": "3.0.1",
                "created": "2026-01-01T00:00:00Z",
                "createdBy": [f"{namespace}#Agent-1"],
            },
            {
                "type": "SoftwareAgent",
                "spdxId": f"{namespace}#Agent-1",
                "creationInfo": "_:creationinfo0",
                "name": "Pitloom",
            },
            {
                "type": "software_Package",
                "spdxId": f"{namespace}#Package-1",
                "creationInfo": "_:creationinfo0",
                "name": "pkg",
            },
            {
                "type": "Relationship",
                "spdxId": f"{namespace}#Relationship-1",
                "creationInfo": "_:creationinfo0",
                "from": f"{namespace}#Package-1",
                "to": [target],
                "relationshipType": "hasDeclaredLicense",
            },
        ],
    }


def _merge_fragment_into_base(tmp_path: Path, target: str) -> Spdx3JsonExporter:
    (tmp_path / "frag.spdx3.json").write_text(
        json.dumps(_fragment("https://spdx.org/spdxdocs/individual-frag", target))
    )
    ci = spdx3.CreationInfo(
        _id="_:ci",
        specVersion="3.0.1",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        createdBy=["https://spdx.org/agent1"],
    )
    exporter = Spdx3JsonExporter()
    exporter.add_document(
        spdx3.SpdxDocument(
            spdxId="https://spdx.org/spdxdocs/main-doc", name="main", creationInfo=ci
        )
    )
    merge_fragments(tmp_path, [FragmentConfig(path="frag.spdx3.json")], exporter)
    return exporter


@pytest.mark.parametrize("form", ["compact", "iri"])
@pytest.mark.parametrize(("compact", "iri"), _INDIVIDUALS)
def test_merging_a_fragment_that_references_an_individual_succeeds(
    tmp_path: Path, form: str, compact: str, iri: str
) -> None:
    """Both JSON spellings of an individual merge, and the relationship to
    it is kept (not dropped, which would pass vacuously)."""
    exporter = _merge_fragment_into_base(
        tmp_path, compact if form == "compact" else iri
    )
    ends = [
        t
        for o in exporter.object_set.objects
        if isinstance(o, spdx3.Relationship)
        for t in o.to
    ]
    assert ends == [iri]


def test_merging_a_fragment_with_a_truly_dangling_target_still_raises(
    tmp_path: Path,
) -> None:
    with pytest.raises(FragmentMergeError, match="dangling reference"):
        _merge_fragment_into_base(tmp_path, f"{_TERMS}/Core/NoSuchIndividual")
