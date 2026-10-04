# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""License element and relationship construction for dependency enrichment.

See also: :mod:`pitloom.assemble.spdx3.deps`, which calls into this module
to build declared/concluded license relationships for a dependency package.
"""

from __future__ import annotations

from dataclasses import dataclass

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._license_elements import (
    LicenseElement,
    get_or_create_license_element,
)
from pitloom.assemble.spdx3.provenance import (
    ConflictCandidate,
    ProvenanceEncoder,
    build_conflict_annotation,
    emit_provenance,
    is_license_concluded,
    parse_provenance_value,
)
from pitloom.core.models import build_relationship, generate_spdx_id
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.extract._license import classify_license, is_listed_name


# Shared document context plus the element; see build_license_elements.
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _build_license_relationship(
    package_spdx_id: str,
    element: LicenseElement,
    relationship_type: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
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

    When *element* was made for an earlier source and this source's value
    was normalised (or has a deprecated id), that note is recorded on the
    relationship (it is per source; the shared element keeps only the first
    source's).
    """
    rel = build_relationship(
        from_id=package_spdx_id,
        to_ids=[element.spdx_id],
        rel_type=relationship_type,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        creation_info=creation_info,
    )
    if not rel:
        raise ValueError("Failed to build relationship")
    if element.noted and not element.created:
        emit_provenance(
            subject=rel,
            provenance={"license": element.provenance},
            creation_info=creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )
    return rel


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
def _same_licence(first: str, second: str) -> bool:
    """Whether two recorded licence values name one licence: equal, or one
    is the SPDX List name of the other's id (``MIT License`` and ``MIT``)."""
    return (
        first == second
        or is_listed_name(first, second)
        or is_listed_name(second, first)
    )


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
    """Get or create licence element(s) and build declared/concluded
    license relationships.

    Single-candidate mode (*concluded_license_id* falsy, the default):
    one element, declared XOR concluded by its source
    (:func:`~pitloom.assemble.spdx3.provenance.is_license_concluded` on
    *license_provenance*): the package's own statement is declared, a
    third-party record concluded.

    Two-candidate mode (G2, *concluded_license_id* given -- currently only the
    main project package path supplies this, since it's the only one with a
    local directory to independently detect a second opinion from): *license_id*
    is always the declared value, *concluded_license_id* the independently
    detected one. Both relationships are built unconditionally, whether or not
    the two agree -- when they *do* agree, both point at the same deduped
    license element. When they disagree, an additional G2 conflict Annotation
    is emitted on *package_spdx_id* recording both candidates; see
    :func:`~pitloom.assemble.spdx3.provenance.build_conflict_annotation`.
    ``NOASSERTION`` (also ``UNKNOWN``) only says "not known", so it never
    conflicts: against a real licence both relationships stay, the real
    licence being the only one with content; ``NONE`` is a statement and
    conflicts with a real licence. A licence's SPDX List name against its id
    (``MIT License`` and ``MIT``) is the same licence, not a conflict.

    Dispatches on truthiness, not just ``is None`` -- unlike ``requires_python``,
    a license id is never meaningfully ``""``, so that must not route into
    two-candidate mode with a spurious empty second candidate.
    """
    declared = get_or_create_license_element(
        license_id,
        license_provenance,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    if not concluded_license_id:
        if declared is None:
            return None, None
        if is_license_concluded(parse_provenance_value(license_provenance)):
            return None, _build_license_relationship(
                package_spdx_id,
                declared,
                spdx3.RelationshipType.hasConcludedLicense,
                creation_info,
                doc_name,
                doc_uuid,
                exporter,
                provenance_config=provenance_config,
                encoder=encoder,
            )
        return (
            _build_license_relationship(
                package_spdx_id,
                declared,
                spdx3.RelationshipType.hasDeclaredLicense,
                creation_info,
                doc_name,
                doc_uuid,
                exporter,
                provenance_config=provenance_config,
                encoder=encoder,
            ),
            None,
        )

    # Each candidate goes through the same classification, so a casing or
    # spelling difference ("mit" vs "MIT", "MIT AND MIT" vs "MIT") is one
    # licence element and no conflict; the element's provenance records a
    # normalisation (see get_or_create_license_element).
    concluded = get_or_create_license_element(
        concluded_license_id,
        concluded_license_provenance or license_provenance,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    rel_declared = rel_concluded = None
    if declared is not None:
        rel_declared = _build_license_relationship(
            package_spdx_id,
            declared,
            spdx3.RelationshipType.hasDeclaredLicense,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )
    if concluded is not None:
        rel_concluded = _build_license_relationship(
            package_spdx_id,
            concluded,
            spdx3.RelationshipType.hasConcludedLicense,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )
    if (
        declared is not None
        and concluded is not None
        and not (declared.is_noassertion or concluded.is_noassertion)
        and not _same_licence(declared.value, concluded.value)
    ):
        candidates: list[ConflictCandidate] = [
            {
                "value": declared.value,
                "role": "declared",
                "source": declared.provenance,
                "ref": declared.spdx_id,
            },
            {
                "value": concluded.value,
                "role": "detected",
                "source": concluded.provenance,
                "ref": concluded.spdx_id,
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

    return rel_declared, rel_concluded


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
) -> spdx3.Relationship | None:
    """Get-or-create the licence element for *license_id* and return a
    ``hasDeclaredLicense`` Relationship from *file_spdx_id* to it (``None``
    when *license_id* states no licence).

    A file's own ``SPDX-License-Identifier`` tag is always its own
    ``declared`` claim by construction -- there is exactly one candidate at
    file granularity, nothing to disambiguate against -- so this does not
    consult the source at all.

    Dedup is by ``(kind, value)`` via :func:`get_or_create_license_element`
    -- a file whose license matches the project's or another file's reuses
    the same element.
    """
    element = get_or_create_license_element(
        license_id,
        license_provenance,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    if element is None:
        return None
    return _build_license_relationship(
        file_spdx_id,
        element,
        spdx3.RelationshipType.hasDeclaredLicense,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )


@dataclass
class WeakLicense:
    """The first ``UNKNOWN``/``NOASSERTION`` a dependency's sources stated.

    ``NOASSERTION`` is weak in a cascade: a later source may know better, so
    :func:`_apply_license` holds it here instead of emitting it, and the
    caller emits it (:func:`emit_weak_license`) only when no source gave a
    licence.
    ``NONE`` is a statement and is never held.
    """

    raw: str | None = None
    provenance: str = ""

    def hold(self, raw: str, provenance: str) -> None:
        """Keep the first one stated; a later one adds nothing."""
        if self.raw is None:
            self.raw, self.provenance = raw, provenance


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
    weak: WeakLicense | None = None,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> bool:
    """Build and add whichever declared/concluded license relationship(s)
    *license_id* resolves to (see :func:`build_license_elements`). Returns
    whether a relationship was added: ``False`` for a value that states no
    licence, so the caller falls back to the next source or leaves the
    package without one.

    With *weak* given, an ``UNKNOWN``/``NOASSERTION`` is held there, not
    emitted, and ``False`` is returned: a later source may still state a
    licence (see :class:`WeakLicense`).
    """
    classified = classify_license(license_id)
    if classified is None:
        return False
    if weak is not None and classified.kind == "noassertion":
        weak.hold(str(license_id), license_provenance)
        return False
    rel_declared, rel_concluded = build_license_elements(
        license_id=str(license_id),
        package_spdx_id=require_spdx_id(dep_package),
        license_provenance=license_provenance,
        creation_info=creation_info,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        exporter=exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    added = False
    for rel in (rel_declared, rel_concluded):
        if rel:
            exporter.add_relationship(rel)
            added = True
    return added


# pylint: disable=too-many-arguments,too-many-positional-arguments
def emit_weak_license(
    weak: WeakLicense,
    dep_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> None:
    """Emit the held ``NOASSERTION``, with the first stating source's
    provenance; nothing when no source stated one."""
    if weak.raw is not None:
        _apply_license(
            weak.raw,
            weak.provenance,
            dep_package,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )


# pylint: disable=too-many-arguments,too-many-positional-arguments
def attach_main_package_license(
    metadata: ProjectMetadata,
    main_package: spdx3.software_Package,
    spdx_ci: spdx3.CreationInfo,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> None:
    """Attach declared and/or concluded license elements and relationships for
    the main Python project package.

    ``metadata.license_name`` truthy does not guarantee two-candidate mode:
    when ``metadata.license_concluded`` is falsy, :func:`build_license_elements`
    still runs single-candidate on ``license_name``'s own provenance (an
    in-package source, so declared, when the manifest states nothing). A
    ``license_concluded`` with no ``license_name`` is always concluded. No
    licence at all (absent or blank) adds no relationship: Pitloom asserts
    nothing.
    """
    # A blank value states no licence: it is absent.
    license_name = (
        metadata.license_name if classify_license(metadata.license_name) else None
    )
    license_concluded = (
        metadata.license_concluded
        if classify_license(metadata.license_concluded)
        else None
    )
    if license_name:
        relationships = build_license_elements(
            license_id=license_name,
            package_spdx_id=require_spdx_id(main_package),
            license_provenance=metadata.provenance.get(
                "license", "Source: pyproject.toml | Field: project.license"
            ),
            creation_info=spdx_ci,
            doc_name=metadata.name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            concluded_license_id=license_concluded,
            concluded_license_provenance=metadata.provenance.get("license_concluded"),
            provenance_config=provenance_config,
            encoder=encoder,
        )
    elif license_concluded:
        # The concluded slot is honoured as such, whatever its source.
        element = get_or_create_license_element(
            license_concluded,
            metadata.provenance.get(
                "license_concluded", "Source: LICENSE | Method: licenseid_detection"
            ),
            spdx_ci,
            metadata.name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )
        relationships = (
            None,
            _build_license_relationship(
                require_spdx_id(main_package),
                element,
                spdx3.RelationshipType.hasConcludedLicense,
                spdx_ci,
                metadata.name,
                doc_uuid,
                exporter,
                provenance_config=provenance_config,
                encoder=encoder,
            )
            if element
            else None,
        )
    else:
        return
    for rel in relationships:
        if rel:
            exporter.add_relationship(rel)
