# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.assemble.spdx3.fragments._find_dangling_references`
and :func:`_raise_on_dangling_references` -- the referential-integrity check
that catches a merged element (typically from a fragment) whose ``Relationship``/
``Annotation`` endpoint doesn't resolve to any object actually present in the
merged graph (and isn't a declared external reference either). The prototypical
cause is a fragment built against a base SBOM's old ``doc_uuid`` (see
:func:`pitloom.assemble._model_generator._project_doc_identity`'s docstring)
merged against a regenerated base SBOM whose element ids have since shifted --
a dangling reference always fails the merge (:class:`FragmentMergeError`), it
is never just a warning.

See also: :mod:`tests.core.test_fragments_merge` for the general merge tests.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.fragments import (
    FragmentMergeError,
    _find_dangling_references,
    _raise_on_dangling_references,
)
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

    assert _find_dangling_references(exporter) == []


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

    assert _find_dangling_references(exporter) == []
