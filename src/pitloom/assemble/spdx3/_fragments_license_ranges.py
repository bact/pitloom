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

from pitloom.core.license_individuals import INDIVIDUAL_BY_REFERENCE
from pitloom.export.spdx3_json import Spdx3JsonExporter

LICENSE_RELATIONSHIP_TYPES = (
    spdx3.RelationshipType.hasDeclaredLicense,
    spdx3.RelationshipType.hasConcludedLicense,
)


def find_license_range_violations(
    exporter: Spdx3JsonExporter,
) -> list[tuple[str, str, str, str]]:
    """``(relationship id, end, target id, its type name)`` for each end of a
    licence relationship in *exporter* whose element is of the wrong type:
    *end* is ``from`` or ``to``. An end that resolves to no element is not
    here: the dangling-reference check names it. After a merge every end is
    an id (a named individual is one that no element holds)."""
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
        checked = (
            (end, target, expected, objects.find_by_id(target))
            for end, target, expected in ends
            if isinstance(target, str) and target not in INDIVIDUAL_BY_REFERENCE
        )
        found.extend(
            (str(rel.spdxId), end, str(target), type(element).__name__)
            for end, target, expected, element in checked
            if element is not None and not isinstance(element, expected)
        )
    return found
