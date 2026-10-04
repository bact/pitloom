# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The SPDX 3 named licence individuals Pitloom emits, in one table.

``NOASSERTION`` and ``NONE`` are not licence elements: a relationship points
at the ``NoAssertionLicense``/``NoneLicense`` individual. Every place that
needs one of its spellings (IRI, compact JSON-LD name, SPDX licence name)
reads it here, so none keeps a copy.
"""

from __future__ import annotations

from typing import NamedTuple

from spdx_python_model.bindings import v3_0_1 as spdx3

__all__ = [
    "INDIVIDUAL_BY_COMPACT_NAME",
    "INDIVIDUAL_BY_KIND",
    "INDIVIDUAL_BY_REFERENCE",
    "LicenseIndividual",
]

_NAMED = spdx3.expandedlicensing_IndividualLicensingInfo.NAMED_INDIVIDUALS


class LicenseIndividual(NamedTuple):
    """One named licence individual."""

    #: Its full IRI, which is what a relationship's ``to`` holds in memory.
    iri: str
    #: Its name in serialised JSON-LD.
    compact_name: str
    #: The SPDX licence name it stands for.
    spdx_name: str


_NO_ASSERTION = LicenseIndividual(
    _NAMED["NoAssertionLicense"], "expandedlicensing_NoAssertionLicense", "NOASSERTION"
)
_NONE = LicenseIndividual(
    _NAMED["NoneLicense"], "expandedlicensing_NoneLicense", "NONE"
)

#: ``classify_license`` kind -> individual.
INDIVIDUAL_BY_KIND: dict[str, LicenseIndividual] = {
    "noassertion": _NO_ASSERTION,
    "none": _NONE,
}

#: Serialised ``to`` value (compact name) -> individual.
INDIVIDUAL_BY_COMPACT_NAME: dict[str, LicenseIndividual] = {
    i.compact_name: i for i in INDIVIDUAL_BY_KIND.values()
}

#: Either spelling of a reference (compact name or full IRI) -> individual,
#: for a reader of a document it did not write.
INDIVIDUAL_BY_REFERENCE: dict[str, LicenseIndividual] = {
    **INDIVIDUAL_BY_COMPACT_NAME,
    **{i.iri: i for i in INDIVIDUAL_BY_KIND.values()},
}
