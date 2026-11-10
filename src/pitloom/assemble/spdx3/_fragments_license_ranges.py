# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ends of a merged ``hasDeclaredLicense``/``hasConcludedLicense``
relationship: ``from`` a ``software_SoftwareArtifact`` (a package, file or
snippet), ``to`` a ``simplelicensing_AnyLicenseInfo`` or one of its
subclasses (a ``LicenseExpression``, an ``expandedlicensing_*`` licence, or
a named individual such as ``NoAssertionLicense``). A ``SimpleLicensingText``
is not one: a text is reached through a ``LicenseExpression`` whose
``customIdToUri`` maps a ``LicenseRef-`` to it.

Pitloom's own builders keep to this; a fragment (written by hand, by an
agent, or by an older Pitloom) may not, and no other step would say so.

See also: :mod:`pitloom.assemble.spdx3.fragments` (the merge that calls
:func:`find_license_range_violations`).
"""

from __future__ import annotations

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._fragments_refs import NAMED_INDIVIDUAL_IDS
from pitloom.core.license_individuals import INDIVIDUAL_BY_REFERENCE
from pitloom.export.spdx3_json import Spdx3JsonExporter

LICENSE_RELATIONSHIP_TYPES = (
    spdx3.RelationshipType.hasDeclaredLicense,
    spdx3.RelationshipType.hasConcludedLicense,
)


def _wrong_type(
    objects: spdx3.SHACLObjectSet, end: str, target_id: str, expected: type
) -> str | None:
    """The type name of the element *target_id* names when it is not an
    *expected*; ``None`` when it is, or when it resolves to nothing (the
    dangling-reference check names that). A named individual is a licence
    one only at a ``to`` end and then only ``NoAssertionLicense`` and
    ``NoneLicense``; any other is no licence, and none is an artifact."""
    if end == "to" and target_id in INDIVIDUAL_BY_REFERENCE:
        return None
    if target_id in NAMED_INDIVIDUAL_IDS:
        return "named individual"
    element = objects.find_by_id(target_id)
    if element is None or isinstance(element, expected):
        return None
    return type(element).__name__


def find_license_range_violations(
    exporter: Spdx3JsonExporter,
) -> list[tuple[str, str, str, str]]:
    """``(relationship id, end, target id, its type name)`` for each end of a
    licence relationship in *exporter* whose element is of the wrong type,
    sorted: *end* is ``from`` or ``to``. After a merge every end is an id."""
    objects = exporter.object_set
    found: list[tuple[str, str, str, str]] = []
    for rel in objects.objects:
        if (
            not isinstance(rel, spdx3.Relationship)
            or rel.relationshipType not in LICENSE_RELATIONSHIP_TYPES
        ):
            continue
        ends: list[tuple[str, object, type]] = [
            ("from", rel.from_, spdx3.software_SoftwareArtifact),
            *(("to", t, spdx3.simplelicensing_AnyLicenseInfo) for t in rel.to),
        ]
        typed = (
            (end, str(target), _wrong_type(objects, end, str(target), expected))
            for end, target, expected in ends
            if isinstance(target, str)
        )
        found.extend(
            (str(rel.spdxId), end, target, wrong)
            for end, target, wrong in typed
            if wrong is not None
        )
    return sorted(found)
