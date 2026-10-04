# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which licensing profiles a graph needs in ``profileConformance``.

One rule for every SBOM builder and for fragment merge, derived from the
graph rather than from what each builder remembers to append.

See also: :mod:`pitloom.assemble.spdx3.document` (the builders that call it)
and :mod:`pitloom.assemble.spdx3.fragments` (the merge).
"""

from __future__ import annotations

from collections.abc import Iterable

from spdx_python_model.bindings import v3_0_1 as spdx3

#: Relationship types that put a licence on an element.
_LICENSE_RELATIONSHIPS = (
    spdx3.RelationshipType.hasDeclaredLicense,
    spdx3.RelationshipType.hasConcludedLicense,
)

#: ExpandedLicensing named individuals (``NoAssertionLicense``, ...).
_EXPANDED_INDIVIDUALS = frozenset(
    spdx3.expandedlicensing_IndividualLicensingInfo.NAMED_INDIVIDUALS.values()
)

#: Bindings name every class ``<namespace>_<Class>``.
_EXPANDED_PREFIX = "expandedlicensing_"


#: Order of ``profileConformance``; any other profile follows, by IRI.
_PROFILE_ORDER = [
    spdx3.ProfileIdentifierType.core,
    spdx3.ProfileIdentifierType.software,
    spdx3.ProfileIdentifierType.simpleLicensing,
    spdx3.ProfileIdentifierType.expandedLicensing,
    spdx3.ProfileIdentifierType.ai,
    spdx3.ProfileIdentifierType.dataset,
]


def _profile_rank(profile: str) -> tuple[int, str]:
    known = _PROFILE_ORDER.index(profile) if profile in _PROFILE_ORDER else None
    return (len(_PROFILE_ORDER) if known is None else known, profile)


def _endpoint_ids(obj: spdx3.SHACLObject) -> list[str]:
    """Every string endpoint of a ``Relationship``/``Annotation``."""
    if isinstance(obj, spdx3.Relationship):
        return [e for e in [obj.from_, *obj.to] if isinstance(e, str)]
    if isinstance(obj, spdx3.Annotation) and isinstance(obj.subject, str):
        return [obj.subject]
    return []


def licensing_profiles(objects: Iterable[spdx3.SHACLObject]) -> list[str]:
    """The licensing profiles *objects* use, in a fixed order.

    ``simpleLicensing`` for any ``LicenseExpression``/``SimpleLicensingText``
    or any declared/concluded licence relationship, so a licence stated only
    as an individual (``NOASSERTION``) counts; ``expandedLicensing`` for any
    ``expandedlicensing_*`` element or a reference to one of its individuals.
    ``expandedLicensing`` implies ``simpleLicensing``. A graph with no
    licence at all needs neither.
    """
    simple = expanded = False
    for obj in objects:
        if isinstance(
            obj,
            (
                spdx3.simplelicensing_LicenseExpression,
                spdx3.simplelicensing_SimpleLicensingText,
            ),
        ):
            simple = True
        elif isinstance(obj, spdx3.Relationship):
            simple = simple or obj.relationshipType in _LICENSE_RELATIONSHIPS
        if type(obj).__name__.startswith(_EXPANDED_PREFIX) or any(
            e in _EXPANDED_INDIVIDUALS for e in _endpoint_ids(obj)
        ):
            expanded = True
    profiles: list[str] = []
    # ExpandedLicensing classes subclass simplelicensing_AnyLicenseInfo.
    simple = simple or expanded
    if simple:
        profiles.append(spdx3.ProfileIdentifierType.simpleLicensing)
    if expanded:
        profiles.append(spdx3.ProfileIdentifierType.expandedLicensing)
    return profiles


def apply_licensing_profiles(
    spdx_doc: spdx3.SpdxDocument, objects: Iterable[spdx3.SHACLObject]
) -> None:
    """Add to *spdx_doc*'s ``profileConformance`` each licensing profile
    :func:`licensing_profiles` finds in *objects*, then put the whole list in
    one fixed order, so a direct build and a fragment merge of the same
    content agree."""
    conformance = list(spdx_doc.profileConformance or [])
    conformance.extend(p for p in licensing_profiles(objects) if p not in conformance)
    spdx_doc.profileConformance = sorted(conformance, key=_profile_rank)
