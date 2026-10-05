# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Licence unification for a fragment merge: a fragment's licence element
equal to one already in the document, or to an earlier one in the same
fragment, is dropped and its references point at the kept one.

Equal means the same :func:`~pitloom.assemble.spdx3._license_elements.license_key`,
the ``(kind, value)`` a build dedupes by, so an expression and a text of the
same string stay apart. The dropped element's ``name`` and ``comment`` are
not folded into the kept one: a licence element is shared by everything that
uses it, and a unification Annotation records the drop.

See also: :mod:`pitloom.assemble.spdx3._fragments_unify` (the merge that
calls this).
"""

from __future__ import annotations

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._license_elements import license_key
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

#: A licence element of the simpleLicensing profile.
LicenseObject = (
    spdx3.simplelicensing_LicenseExpression | spdx3.simplelicensing_SimpleLicensingText
)

LICENSE_TYPES = (
    spdx3.simplelicensing_LicenseExpression,
    spdx3.simplelicensing_SimpleLicensingText,
)


def find_license_survivor(
    obj: LicenseObject,
    exporter: Spdx3JsonExporter,
    pending: dict[tuple[str, str], str],
) -> str | None:
    """The id of the licence *obj* unifies with: one already in *exporter*,
    else an earlier one of the same fragment (*pending*). ``None`` keeps
    *obj*, recorded in *pending* for the rest of its fragment. A blank
    licence never unifies."""
    key = license_key(obj)
    if not key[1]:
        return None
    found = exporter.find_license(*key) or pending.get(key)
    if found is None:
        pending[key] = require_spdx_id(obj)
    return found


def register_license(obj: LicenseObject, exporter: Spdx3JsonExporter) -> None:
    """Add a kept fragment licence to *exporter*, indexed by its canonical
    key so a later fragment unifies with it."""
    key = license_key(obj)
    exporter.add_license(obj, key=key if key[1] else None)
