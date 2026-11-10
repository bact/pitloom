# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``license-relationship-invalid``: a merged ``hasDeclaredLicense`` or
``hasConcludedLicense`` relationship whose ``from`` is no package, file or
snippet, or whose ``to`` is no ``AnyLicenseInfo`` (or subclass), such as a
bare ``SimpleLicensingText``.

See also: :mod:`pitloom.assemble.spdx3._fragments_license_ranges` (the check)
and :func:`pitloom.assemble.spdx3.fragments.merge_fragments` (the merge that
raises).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: The ``to`` end is no licence.
LICENSE_RELATIONSHIP_TO_LINE: Final = Line(
    level="WARNING",
    template="RELATIONSHIP=%(name)s: a licence relationship goes to %(target)s, "
    "which is not an AnyLicenseInfo; point it at a LicenseExpression",
)
#: The ``from`` end is no package, file or snippet.
LICENSE_RELATIONSHIP_FROM_LINE: Final = Line(
    level="WARNING",
    template="RELATIONSHIP=%(name)s: a licence relationship starts at %(target)s, "
    "which is not a package, file or snippet; start it at one",
)
#: The merge fails.
LICENSE_RELATIONSHIP_ERROR_LINE: Final = Line(
    level="ERROR",
    template="Fragment merge left a licence relationship of the wrong type; "
    "fix the fragment",
)

LICENSE_RELATIONSHIP_INVALID: Final = Message(
    code="license-relationship-invalid",
    condition="invalid",
    lines=(
        LICENSE_RELATIONSHIP_TO_LINE,
        LICENSE_RELATIONSHIP_FROM_LINE,
        LICENSE_RELATIONSHIP_ERROR_LINE,
    ),
    summary="After a fragment merge, a hasDeclaredLicense or hasConcludedLicense "
    "relationship has an end of the wrong type: it starts at something that is "
    "no package, file or snippet, or goes to something that is no "
    "AnyLicenseInfo or subclass (a LicenseExpression, an expandedlicensing "
    "licence or a named individual such as NoAssertionLicense). A "
    "SimpleLicensingText is not one: a licence text is reached through a "
    "LicenseExpression of one LicenseRef- that its customIdToUri maps to the "
    "text. One WARNING names each wrong end, then the ERROR ends the run.",
    did="Wrote no SBOM.",
    effect="not-written",
    actor="user",
    advice="Tell the user which relationship and which end the lines name. "
    "Do not rewrite a fragment you did not draft in this session (one by "
    "hand, or from an older Pitloom that pointed a relationship at a bare "
    "text); ask first, and with nobody to ask, report it only. One you "
    "drafted here: fix it (point its to at a LicenseExpression, or its from at "
    "a package, file or snippet) and merge again; regenerating the base SBOM "
    "does not help.",
    subject_key="RELATIONSHIP",
    since="0.24.0",
)

ENTRIES: Final = (LICENSE_RELATIONSHIP_INVALID,)
