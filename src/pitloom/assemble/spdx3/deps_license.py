# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""License element and relationship construction for dependency enrichment.

See also: :mod:`pitloom.assemble.spdx3.deps`, which calls into this module
to build declared/concluded license relationships for a dependency package.
"""

from __future__ import annotations

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import (
    TRANSPARENT_SOURCES,
    ConflictCandidate,
    ProvenanceEncoder,
    build_conflict_annotation,
    emit_provenance,
    parse_provenance_value,
)
from pitloom.core.models import build_relationship, generate_spdx_id
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.extract._license import (
    normalize_license_expression,
    tag_license_normalization,
)


def _is_license_concluded(parsed_prov: dict[str, str]) -> bool:
    """Determine if a license is concluded rather than declared.

    A license is concluded if we used a heuristic/detection method,
    or if the source is not a transparent manifest (e.g. it was extracted
    from a LICENSE file directly).
    """
    if parsed_prov.get("method"):
        return True
    source = parsed_prov.get("source", "").strip().lower()
    if " (" in source:
        source = source.split(" (", 1)[0].strip()
    return not source or source not in TRANSPARENT_SOURCES


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _get_or_create_license_element(
    license_id: str,
    license_provenance: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> str:
    """Get or create a ``SimpleLicensingText`` element for *license_id*, deduped
    by license-id string, and return its spdxId."""
    existing_spdx_id = exporter.find_license(license_id)
    if existing_spdx_id:
        return existing_spdx_id

    name_str = license_id.strip()
    if "\n" in name_str:
        name_str = name_str.split("\n")[0]
    if len(name_str) > 60:
        name_str = name_str[:57] + "..."

    license_text = spdx3.simplelicensing_SimpleLicensingText(
        spdxId=generate_spdx_id("License", doc_name=doc_name, doc_uuid=doc_uuid),
        creationInfo=creation_info,
    )
    license_text.name = name_str
    license_text.simplelicensing_licenseText = license_id
    exporter.add_license(license_text)
    emit_provenance(
        subject=license_text,
        provenance={"license": license_provenance},
        creation_info=creation_info,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        exporter=exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    return require_spdx_id(license_text)


def _build_license_relationship(
    package_spdx_id: str,
    license_spdx_id: str,
    relationship_type: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
) -> spdx3.Relationship:
    """Build a declared/concluded license ``dependsOn``-family relationship.

    Unlike every other :func:`build_relationship` call site in this
    codebase (``ai.py``, ``_document_files.py``, ``deps.py``, ...), which
    treat a ``None`` result as expected -- their ``from_id`` often comes
    from a raw, genuinely-``Optional`` ``.spdxId`` field access -- and
    skip adding that relationship, this one raises. *package_spdx_id* is
    typed ``str`` (not ``Optional``) and every caller sources it from
    :func:`~pitloom.export.spdx3_json.require_spdx_id`, which itself
    raises immediately if the element has no ``spdxId``. So a ``None``
    here would mean that guarantee was silently violated somewhere else
    -- a real internal bug, not an expected missing-data case -- and
    fails fast instead of masking it as a silently-dropped license edge.
    """
    rel = build_relationship(
        from_id=package_spdx_id,
        to_ids=[license_spdx_id],
        rel_type=relationship_type,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        creation_info=creation_info,
    )
    if not rel:
        raise ValueError("Failed to build relationship")
    return rel


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
def build_license_elements(
    license_id: str,
    package_spdx_id: str,
    license_provenance: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    concluded_license_id: str | None = None,
    concluded_license_provenance: str | None = None,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> tuple[spdx3.Relationship | None, spdx3.Relationship | None]:
    """Get or create SimpleLicensingText element(s) and build declared/concluded
    license relationships.

    Single-candidate mode (*concluded_license_id* omitted, the default):
    unchanged behavior -- one element, classified as declared XOR concluded
    via :func:`_is_license_concluded` on *license_provenance*.

    Two-candidate mode (G2, *concluded_license_id* given -- currently only the
    main project package path supplies this, since it's the only one with a
    local directory to independently detect a second opinion from): *license_id*
    is always the declared value, *concluded_license_id* the independently
    detected one. Both relationships are built unconditionally, whether or not
    the two agree -- when they *do* agree, both point at the same deduped
    license element. When they disagree, an additional G2 conflict Annotation
    is emitted on *package_spdx_id* recording both candidates; see
    :func:`~pitloom.assemble.spdx3.provenance.build_conflict_annotation`.
    """
    if concluded_license_id is None:
        license_spdx_id = _get_or_create_license_element(
            license_id,
            license_provenance,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )
        parsed_prov = parse_provenance_value(license_provenance)
        if _is_license_concluded(parsed_prov):
            return None, _build_license_relationship(
                package_spdx_id,
                license_spdx_id,
                spdx3.RelationshipType.hasConcludedLicense,
                creation_info,
                doc_name,
                doc_uuid,
            )
        return (
            _build_license_relationship(
                package_spdx_id,
                license_spdx_id,
                spdx3.RelationshipType.hasDeclaredLicense,
                creation_info,
                doc_name,
                doc_uuid,
            ),
            None,
        )

    # Normalize both candidates to a canonical SPDX license expression before
    # comparing or creating elements -- otherwise a mere casing difference
    # (declared "mit", detected "MIT") or an equivalent-but-differently-
    # spelled compound expression ("MIT AND MIT" vs "MIT") would be
    # misreported as a genuine conflict and create two separate license
    # elements for one license. Unrecognized values pass through unchanged
    # (see normalize_license_expression).
    canonical_declared_id = normalize_license_expression(license_id.strip())
    canonical_concluded_id = normalize_license_expression(concluded_license_id.strip())

    # Flag when normalization actually rewrote a candidate's value (e.g. a
    # casing fix or a dedup/reorder of a compound expression), and record
    # the py-spdx-license version that did it -- so a G2 candidate's
    # evidence stays auditable even when its stored value differs from what
    # the source literally said. No-op when normalization was a pass-through.
    declared_provenance = tag_license_normalization(
        license_provenance, license_id, canonical_declared_id
    )
    concluded_provenance = tag_license_normalization(
        concluded_license_provenance or license_provenance,
        concluded_license_id,
        canonical_concluded_id,
    )

    declared_spdx_id = _get_or_create_license_element(
        canonical_declared_id,
        declared_provenance,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    concluded_spdx_id = _get_or_create_license_element(
        canonical_concluded_id,
        concluded_provenance,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )

    rel_has_declared_license = _build_license_relationship(
        package_spdx_id,
        declared_spdx_id,
        spdx3.RelationshipType.hasDeclaredLicense,
        creation_info,
        doc_name,
        doc_uuid,
    )
    rel_has_concluded_license = _build_license_relationship(
        package_spdx_id,
        concluded_spdx_id,
        spdx3.RelationshipType.hasConcludedLicense,
        creation_info,
        doc_name,
        doc_uuid,
    )

    if canonical_declared_id != canonical_concluded_id:
        candidates: list[ConflictCandidate] = [
            {
                "value": canonical_declared_id,
                "role": "declared",
                "source": declared_provenance,
                "ref": declared_spdx_id,
            },
            {
                "value": canonical_concluded_id,
                "role": "detected",
                "source": concluded_provenance,
                "ref": concluded_spdx_id,
            },
        ]
        exporter.add_annotation(
            build_conflict_annotation(
                subject_spdx_id=package_spdx_id,
                field="license",
                candidates=candidates,
                creation_info=creation_info,
                annotation_spdx_id=generate_spdx_id(
                    "Annotation", doc_name=doc_name, doc_uuid=doc_uuid
                ),
            )
        )

    return rel_has_declared_license, rel_has_concluded_license


# pylint: disable=too-many-arguments,too-many-positional-arguments
def build_file_declared_license(
    license_id: str,
    file_spdx_id: str,
    license_provenance: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> spdx3.Relationship:
    """Get-or-create a ``SimpleLicensingText`` element for *license_id* and
    return a ``hasDeclaredLicense`` Relationship from *file_spdx_id* to it.

    Unlike :func:`build_license_elements`, this never applies the
    declared/concluded classification heuristic
    (:func:`_is_license_concluded`): a file's own ``SPDX-License-Identifier``
    tag is always its own ``declared`` claim by construction -- there is
    exactly one candidate at file granularity, nothing to disambiguate
    against. Calling :func:`build_license_elements` here would silently
    misclassify it as ``hasConcludedLicense`` instead, since a file's own
    path is never in :data:`~pitloom.assemble.spdx3.provenance.TRANSPARENT_SOURCES`.

    Dedup is by license-id string via :func:`_get_or_create_license_element`
    -- a file whose license matches the project's or another file's reuses
    the same element.
    """
    license_spdx_id = _get_or_create_license_element(
        license_id,
        license_provenance,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    return _build_license_relationship(
        file_spdx_id,
        license_spdx_id,
        spdx3.RelationshipType.hasDeclaredLicense,
        creation_info,
        doc_name,
        doc_uuid,
    )


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _apply_license(
    license_id: str | None,
    license_provenance: str,
    dep_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> bool:
    """Build and add whichever declared/concluded license relationship(s)
    *license_id* resolves to (see :func:`build_license_elements`). Returns
    whether anything was added."""
    if not license_id or license_id == "UNKNOWN":
        return False
    rel_declared, rel_concluded = build_license_elements(
        license_id=license_id,
        package_spdx_id=require_spdx_id(dep_package),
        license_provenance=license_provenance,
        creation_info=creation_info,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        exporter=exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    for rel in (rel_declared, rel_concluded):
        if rel:
            exporter.add_relationship(rel)
    return True


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _add_license_noassertion(
    dep_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> None:
    """Assert ``hasDeclaredLicense: NOASSERTION`` for a package whose license
    couldn't be determined locally or via PyPI -- an explicit "we checked
    and don't know" is more useful to a consumer than a silently absent
    field, and is the standard SPDX placeholder for exactly this case.
    Deduped like any other license value, so every such package shares one
    NOASSERTION element.
    """
    license_spdx_id = _get_or_create_license_element(
        "NOASSERTION",
        "Source: NOASSERTION (no license information found locally or via PyPI)",
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    exporter.add_relationship(
        _build_license_relationship(
            require_spdx_id(dep_package),
            license_spdx_id,
            spdx3.RelationshipType.hasDeclaredLicense,
            creation_info,
            doc_name,
            doc_uuid,
        )
    )
