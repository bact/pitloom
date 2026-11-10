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
TO_LINE: Final = Line(
    level="WARNING",
    template="RELATIONSHIP=%(name)s: a licence relationship goes to %(target)s, "
    "which is not an AnyLicenseInfo; point it at a LicenseExpression",
)
#: The ``from`` end is no package, file or snippet.
FROM_LINE: Final = Line(
    level="WARNING",
    template="RELATIONSHIP=%(name)s: a licence relationship starts at %(target)s, "
    "which is not a package, file or snippet; start it at one",
)
#: The merge fails.
RANGE_ERROR_LINE: Final = Line(
    level="ERROR",
    template="Fragment merge left a licence relationship of the wrong type; "
    "fix the fragment",
)

LICENSE_RANGE: Final = Message(
    code="license-relationship-invalid",
    condition="invalid",
    lines=(TO_LINE, FROM_LINE, RANGE_ERROR_LINE),
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
    "They fix the fragment (a fragment written by an agent or by hand, or by "
    "an older Pitloom that pointed a relationship at a bare text) and merge "
    "again. Regenerating the base SBOM does not help. Do not rewrite the "
    "fragment for them; ask first, and with nobody to ask, report it only.",
    subject_key="RELATIONSHIP",
    since="0.24.0",
)

ENTRIES: Final = (LICENSE_RANGE,)
