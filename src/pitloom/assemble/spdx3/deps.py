# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Dependency package and relationship creation for SPDX 3 SBOM documents."""

from __future__ import annotations

from importlib.metadata import PackageMetadata, PackageNotFoundError
from importlib.metadata import metadata as get_pkg_metadata
from importlib.metadata import version as get_package_version

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import (
    TRANSPARENT_SOURCES,
    ConflictCandidate,
    ProvenanceEncoder,
    build_conflict_annotation,
    emit_provenance,
    parse_provenance_value,
)
from pitloom.core.models import build_pypi_purl, generate_spdx_id
from pitloom.core.project import PhantomDependency
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

# Operators used in PEP 508 dependency specifiers, ordered longest-first to
# avoid splitting on a prefix of a multi-character operator (e.g. "==" before "=").
_VERSION_OPERATORS = ("===", "~=", "!=", "==", ">=", "<=", ">", "<")

# Well-known Project-URL labels that map to homePage / downloadLocation.
# Matched case-insensitively against the label part of "Label, URL" entries.
_HOMEPAGE_LABELS = frozenset(["homepage", "home page", "home"])
_DOWNLOAD_LABELS = frozenset(["download"])


def _parse_dep_name(dep: str) -> str:
    """Return the bare package name from a PEP 508 dependency specifier."""
    for op in _VERSION_OPERATORS:
        if op in dep:
            return dep.split(op)[0].strip()
    return dep.strip()


def _resolve_version(dep_name: str, dep: str) -> tuple[str, str | None]:
    """Return ``(version_string, resolved_from)`` for a dependency.

    Tries to read the installed version via ``importlib.metadata`` first.
    Falls back to extracting the pinned version from an ``==`` constraint,
    or ``"unknown"`` if neither is available.

    Returns:
        A tuple of the version string and an optional provenance note.
        The provenance note is ``None`` when the version comes from the
        declared constraint, as the dep-level comment already records that.
    """
    try:
        return get_package_version(dep_name), (
            "Version resolved: Build-time environment (importlib.metadata)"
        )
    except PackageNotFoundError:
        pass

    if "==" in dep:
        return dep.split("==")[1].strip(), None

    return "unknown", None


def _parse_project_urls(pkg_meta: PackageMetadata) -> dict[str, str]:
    """Return a lowercased-label -> URL dict from ``Project-URL`` metadata entries."""
    result: dict[str, str] = {}
    entries = pkg_meta.get_all("Project-URL") or []
    for entry in entries:
        if "," in entry:
            label, url = entry.split(",", 1)
            result[label.strip().lower()] = url.strip()
    return result


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _enrich_from_installed(
    dep_name: str,
    dep_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> None:
    """Populate optional fields on a dependency package from installed metadata."""
    try:
        pkg_meta: PackageMetadata = get_pkg_metadata(dep_name)
    except PackageNotFoundError:
        return

    project_urls = _parse_project_urls(pkg_meta)
    provenance_source = f"Source: installed metadata | Package: {dep_name}"

    # description
    summary = pkg_meta["Summary"] or ""
    if summary and summary != "UNKNOWN":
        dep_package.description = summary

    # homePage -- core field first, then well-known Project-URL labels
    home_page = pkg_meta["Home-page"] or ""
    if not home_page or home_page == "UNKNOWN":
        for label in _HOMEPAGE_LABELS:
            if label in project_urls:
                home_page = project_urls[label]
                break
    if home_page and home_page != "UNKNOWN":
        dep_package.software_homePage = home_page

    # downloadLocation -- core field first, then well-known Project-URL labels
    download_url = pkg_meta["Download-URL"] or ""
    if not download_url or download_url == "UNKNOWN":
        for label in _DOWNLOAD_LABELS:
            if label in project_urls:
                download_url = project_urls[label]
                break
    if download_url and download_url != "UNKNOWN":
        dep_package.software_downloadLocation = download_url

    # packageUrl -- PyPI PURL (pkg:pypi/<name>@<version>)
    version = dep_package.software_packageVersion
    if version and version != "unknown":
        dep_package.software_packageUrl = build_pypi_purl(dep_name, version)

    # hasDeclaredLicense -- prefer PEP 639 License-Expression over legacy License
    license_id = pkg_meta["License-Expression"] or pkg_meta["License"] or ""
    if license_id and license_id != "UNKNOWN":
        rel_declared, _ = build_license_elements(
            license_id=license_id,
            package_spdx_id=require_spdx_id(dep_package),
            license_provenance=provenance_source,
            creation_info=creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )
        if rel_declared:
            exporter.add_relationship(rel_declared)


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
    return spdx3.Relationship(
        spdxId=generate_spdx_id("Relationship", doc_name=doc_name, doc_uuid=doc_uuid),
        creationInfo=creation_info,
        from_=package_spdx_id,
        relationshipType=relationship_type,
        to=[license_spdx_id],
    )


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

    declared_spdx_id = _get_or_create_license_element(
        license_id,
        license_provenance,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    concluded_spdx_id = _get_or_create_license_element(
        concluded_license_id,
        concluded_license_provenance or license_provenance,
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

    if license_id.strip() != concluded_license_id.strip():
        candidates: list[ConflictCandidate] = [
            {
                "value": license_id,
                "role": "declared",
                "source": license_provenance,
                "ref": declared_spdx_id,
            },
            {
                "value": concluded_license_id,
                "role": "detected",
                "source": concluded_license_provenance or license_provenance,
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
def add_dependencies(
    dependencies: list[str],
    dep_provenance: str,
    main_package_spdx_id: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> None:
    """Build SPDX ``software_Package`` and ``Relationship`` elements for each
    declared dependency."""
    for dep in dependencies:
        dep_name = _parse_dep_name(dep)
        dep_version, version_note = _resolve_version(dep_name, dep)

        dep_provenance_fields: dict[str, str] = {
            "dependencies": dep_provenance,
            "declared_constraint": dep,
        }
        if version_note:
            dep_provenance_fields["version"] = version_note

        dep_package = spdx3.software_Package(
            spdxId=generate_spdx_id("Package", doc_name=doc_name, doc_uuid=doc_uuid),
            name=dep_name,
            creationInfo=creation_info,
        )
        dep_package.software_packageVersion = dep_version
        dep_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library

        _enrich_from_installed(
            dep_name,
            dep_package,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )

        exporter.add_package(dep_package)
        emit_provenance(
            subject=dep_package,
            provenance=dep_provenance_fields,
            creation_info=creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )

        dep_rel = spdx3.Relationship(
            spdxId=generate_spdx_id(
                "Relationship", doc_name=doc_name, doc_uuid=doc_uuid
            ),
            from_=main_package_spdx_id,
            to=[require_spdx_id(dep_package)],
            relationshipType=spdx3.RelationshipType.dependsOn,
            creationInfo=creation_info,
        )
        exporter.add_relationship(dep_rel)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def add_phantom_dependencies(
    phantom_deps: list[PhantomDependency],
    main_package_spdx_id: str,
    file_spdx_ids: dict[str, str],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> None:
    """Build SPDX elements for bundled phantom binary dependencies."""
    for dep in phantom_deps:
        dep_package = spdx3.software_Package(
            spdxId=generate_spdx_id("Package", doc_name=doc_name, doc_uuid=doc_uuid),
            name=dep.name,
            creationInfo=creation_info,
        )
        if dep.version:
            dep_package.software_packageVersion = dep.version
        else:
            dep_package.software_packageVersion = "unknown"

        dep_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library

        exporter.add_package(dep_package)
        emit_provenance(
            subject=dep_package,
            provenance={
                "package": "Phantom dependency bundled in distribution artifact"
            },
            creation_info=creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )

        # The main package depends on this phantom package.
        dep_rel = spdx3.Relationship(
            spdxId=generate_spdx_id(
                "Relationship", doc_name=doc_name, doc_uuid=doc_uuid
            ),
            from_=main_package_spdx_id,
            to=[require_spdx_id(dep_package)],
            relationshipType=spdx3.RelationshipType.dependsOn,
            creationInfo=creation_info,
        )
        exporter.add_relationship(dep_rel)

        # Link the phantom package to the physical file if it was registered
        file_spdx_id = file_spdx_ids.get(dep.file_path)
        if file_spdx_id:
            file_rel = spdx3.Relationship(
                spdxId=generate_spdx_id(
                    "Relationship", doc_name=doc_name, doc_uuid=doc_uuid
                ),
                from_=require_spdx_id(dep_package),
                to=[file_spdx_id],
                relationshipType=spdx3.RelationshipType.contains,
                creationInfo=creation_info,
            )
            exporter.add_relationship(file_rel)
