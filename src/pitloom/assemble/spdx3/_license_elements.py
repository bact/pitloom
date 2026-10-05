# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one place a licence value becomes a licence element: a
``LicenseExpression`` for a valid SPDX expression, a ``SimpleLicensingText``
for anything else, and for ``NOASSERTION``/``NONE`` no element at all: the
``NoAssertionLicense``/``NoneLicense`` named individuals (see
:func:`pitloom.extract._license.classify_license`).

Every surface reaches it through :mod:`pitloom.assemble.spdx3.deps_license`:
dependencies, the main package, a wheel's ``License-Expression``, AI models
and per-file ``SPDX-License-Identifier`` tags.

See also: :mod:`pitloom.assemble.spdx3.deps_license` (relationships).
"""

from __future__ import annotations

from typing import NamedTuple

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import ProvenanceEncoder, emit_provenance
from pitloom.core.license_individuals import INDIVIDUAL_BY_KIND
from pitloom.core.models import generate_spdx_id
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.extract._license import (
    classify_license,
    tag_deprecated_license_ids,
    tag_license_normalization,
)
from pitloom.extract.license_refs import classifier_terms


def _without_blank_ends(text: str) -> str:
    """*text* without its blank ends, serialisation not content:
    leading blank lines, spaces and tabs (a Core Metadata header loses them)
    and the final line breaks (a file or a TOML string ends in them). String
    methods, not a regular expression: an alternation anchored at the end
    is quadratic on a long run of line breaks inside the text."""
    return text.lstrip(" \t\r\n").rstrip("\r\n")


#: Longest ``name`` kept as is; longer is cut to fit with ``...``.
_MAX_NAME_LENGTH = 60


class LicenseElement(NamedTuple):
    """The element a licence value resolved to."""

    #: The element's id; for a named individual, its IRI (no element exists).
    spdx_id: str
    #: What the element holds: the canonical expression, the text, or
    #: ``NOASSERTION``/``NONE`` for an individual.
    value: str
    #: The source provenance, noting a normalisation when one changed *value*.
    provenance: str
    #: Whether this call made the element (else an earlier one did).
    created: bool
    #: Whether *provenance* carries a note of its own (a normalisation, a
    #: deprecated id): it is per source, so a reused element needs it again.
    noted: bool

    @property
    def is_noassertion(self) -> bool:
        """Whether this is the ``NoAssertionLicense`` individual: "the source
        does not know", which never conflicts with a real licence."""
        return self.spdx_id == INDIVIDUAL_BY_KIND["noassertion"].iri


def license_key(
    element: (
        spdx3.simplelicensing_LicenseExpression
        | spdx3.simplelicensing_SimpleLicensingText
    ),
) -> tuple[str, str]:
    """The ``(kind, value)`` a build indexes *element* under (see
    :meth:`~pitloom.export.spdx3_json.Spdx3JsonExporter.find_license`), for
    an element a build did not make: an expression in its canonical form
    (``mit`` -> ``MIT``; a classifier ``AND`` and one that is not an
    expression as written, stripped), a text stripped. A fragment merge
    unifies licences by it."""
    if isinstance(element, spdx3.simplelicensing_SimpleLicensingText):
        return "text", (element.simplelicensing_licenseText or "").strip()
    value = (element.simplelicensing_licenseExpression or "").strip()
    if classifier_terms(value):
        return "expression", value
    classified = classify_license(value, warn=False)
    if classified is not None and classified.kind == "expression":
        return "expression", classified.value
    return "expression", value


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
    verbatim: str | None = None,
    custom_ids: list[tuple[str, str]] | None = None,
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
        element.simplelicensing_customIdToUri = [
            spdx3.DictionaryEntry(key=ref, value=iri) for ref, iri in custom_ids or []
        ]
    else:
        element = spdx3.simplelicensing_SimpleLicensingText(
            spdxId=spdx_id, creationInfo=creation_info
        )
        element.simplelicensing_licenseText = value if verbatim is None else verbatim
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


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _classifier_and(
    expression: str,
    terms: list[tuple[str, str]],
    provenance: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    provenance_config: ProvenanceConfig | None,
    encoder: ProvenanceEncoder | None,
) -> LicenseElement:
    """The ``AND`` of several ``License ::`` classifiers: one
    ``LicenseExpression`` whose ``customIdToUri`` maps each
    ``LicenseRef-pitloom-classifier-`` term to the text element of its
    licence name (shared with any other use of that text)."""
    custom_ids = [
        (
            ref,
            _get_or_create(
                "text",
                name,
                provenance,
                False,
                creation_info,
                doc_name,
                doc_uuid,
                exporter,
                provenance_config,
                encoder,
            ).spdx_id,
        )
        for ref, name in terms
    ]
    return _get_or_create(
        "expression",
        expression,
        provenance,
        False,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config,
        encoder,
        custom_ids=custom_ids,
    )


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
    apart). Leading blank space and the final line breaks are dropped
    first, here only, so every surface records one text (a file or a TOML
    string keeps them, a wheel's ``METADATA`` drops them); the rest is kept
    as written. The dedup key is that text stripped (the classifier's
    value), so ``"Foo "`` and ``"Foo"``, differing only in trailing spaces,
    share the first-seen element. ``None`` when *license_id* states no
    licence (blank).
    ``NOASSERTION``, ``NONE`` and ``UNKNOWN`` give the named individual, never
    an element; the relationship then carries the source's provenance.
    """
    license_id = _without_blank_ends(license_id)
    terms = classifier_terms(license_id.strip())
    if terms:
        return _classifier_and(
            license_id.strip(),
            terms,
            license_provenance,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            provenance_config,
            encoder,
        )
    classified = classify_license(license_id)
    if classified is None:
        return None
    provenance = license_provenance
    if classified.kind in INDIVIDUAL_BY_KIND:
        provenance = tag_license_normalization(
            provenance, license_id, classified.value, normalizer=False
        )
        return LicenseElement(
            INDIVIDUAL_BY_KIND[classified.kind].iri,
            classified.value,
            provenance,
            False,
            True,
        )
    if classified.kind == "expression":
        provenance = tag_deprecated_license_ids(
            tag_license_normalization(license_provenance, license_id, classified.value),
            classified.value,
        )
        kind, value = "expression", classified.value
    else:
        kind, value = "text", classified.value
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
        verbatim=classified.raw if kind == "text" else None,
    )
