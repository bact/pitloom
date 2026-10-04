# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one place a licence value becomes a licence element: a
``LicenseExpression`` for a valid SPDX expression, a ``SimpleLicensingText``
for anything else (see :func:`pitloom.extract._license.classify_license`).

Every surface reaches it through :mod:`pitloom.assemble.spdx3.deps_license`:
dependencies, the main package, a wheel's ``License-Expression``, AI models
and per-file ``SPDX-License-Identifier`` tags.

See also: :mod:`pitloom.assemble.spdx3.deps_license` (relationships).
"""

from __future__ import annotations

from typing import NamedTuple

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import ProvenanceEncoder, emit_provenance
from pitloom.core.models import generate_spdx_id
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.extract._license import (
    classify_license,
    tag_deprecated_license_ids,
    tag_license_normalization,
)

#: Longest ``name`` kept as is; longer is cut to fit with ``...``.
_MAX_NAME_LENGTH = 60


class LicenseElement(NamedTuple):
    """The element a licence value resolved to."""

    spdx_id: str
    #: What the element holds: the canonical expression, or the text.
    value: str
    #: The source provenance, noting a normalisation when one changed *value*.
    provenance: str
    #: Whether this call made the element (else an earlier one did).
    created: bool
    #: Whether *provenance* carries a note of its own (a normalisation, a
    #: deprecated id): it is per source, so a reused element needs it again.
    noted: bool


def _element_name(value: str) -> str:
    name = value.strip()
    if "\n" in name:
        name = name.split("\n")[0]
    if len(name) > _MAX_NAME_LENGTH:
        name = name[: _MAX_NAME_LENGTH - 3] + "..."
    return name


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _get_or_create(
    kind: str,
    value: str,
    provenance: str,
    noted: bool,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    provenance_config: ProvenanceConfig | None,
    encoder: ProvenanceEncoder | None,
) -> LicenseElement:
    existing = exporter.find_license(kind, value)
    if existing:
        return LicenseElement(existing, value, provenance, False, noted)

    spdx_id = generate_spdx_id("License", doc_name=doc_name, doc_uuid=doc_uuid)
    element: (
        spdx3.simplelicensing_LicenseExpression
        | spdx3.simplelicensing_SimpleLicensingText
    )
    if kind == "expression":
        element = spdx3.simplelicensing_LicenseExpression(
            spdxId=spdx_id, creationInfo=creation_info
        )
        element.simplelicensing_licenseExpression = value
    else:
        element = spdx3.simplelicensing_SimpleLicensingText(
            spdxId=spdx_id, creationInfo=creation_info
        )
        element.simplelicensing_licenseText = value
    element.name = _element_name(value)
    exporter.add_license(element)
    emit_provenance(
        subject=element,
        provenance={"license": provenance},
        creation_info=creation_info,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        exporter=exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    return LicenseElement(require_spdx_id(element), value, provenance, True, noted)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def get_or_create_license_element(
    license_id: str,
    license_provenance: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> LicenseElement | None:
    """Get or create the licence element for *license_id*, deduped by
    ``(kind, value)`` (an expression and a text of the same string stay
    apart). ``None`` when *license_id* states no licence (blank,
    ``UNKNOWN``). ``NOASSERTION``/``NONE`` are recorded as text as written.
    """
    classified = classify_license(license_id)
    if classified is None:
        return None
    provenance = license_provenance
    if classified.kind == "expression":
        provenance = tag_deprecated_license_ids(
            tag_license_normalization(license_provenance, license_id, classified.value),
            classified.value,
        )
        kind, value = "expression", classified.value
    else:
        # Text is deduped stripped; NOASSERTION/NONE are text as written.
        kind = "text"
        value = classified.value if classified.kind == "text" else license_id.strip()
    return _get_or_create(
        kind,
        value,
        provenance,
        provenance != license_provenance,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config,
        encoder,
    )


# pylint: disable=too-many-arguments,too-many-positional-arguments
def get_or_create_noassertion_element(
    license_provenance: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> LicenseElement:
    """Get or create the ``NOASSERTION`` licence element (text, as today)."""
    return _get_or_create(
        "text",
        "NOASSERTION",
        license_provenance,
        False,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config,
        encoder,
    )
