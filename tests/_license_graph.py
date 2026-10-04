# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Read licence elements from a serialised SPDX 3 ``@graph``: a
``LicenseExpression`` holds its value in ``simplelicensing_licenseExpression``,
a ``SimpleLicensingText`` in ``simplelicensing_licenseText``."""

from __future__ import annotations

from typing import Any

LICENSE_TYPES = (
    "simplelicensing_LicenseExpression",
    "simplelicensing_SimpleLicensingText",
)


def license_elements(graph: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every licence element of *graph*, either kind."""
    return [e for e in graph if e.get("type") in LICENSE_TYPES]


def license_value(element: dict[str, Any]) -> str | None:
    """The expression or text a licence element holds."""
    return element.get("simplelicensing_licenseExpression") or element.get(
        "simplelicensing_licenseText"
    )


def license_values(graph: list[dict[str, Any]]) -> dict[str, str | None]:
    """``spdxId`` -> value, for every licence element of *graph*."""
    return {e["spdxId"]: license_value(e) for e in license_elements(graph)}
