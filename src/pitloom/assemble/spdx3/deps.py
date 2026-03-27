# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Dependency package and relationship creation for SPDX 3 SBOM documents."""

from __future__ import annotations

from importlib.metadata import PackageMetadata, PackageNotFoundError
from importlib.metadata import metadata as get_pkg_metadata
from importlib.metadata import version as get_package_version

from spdx_python_model import v3_0_1 as spdx3

from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter

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
    """Return a lowercased-label → URL dict from ``Project-URL`` metadata entries."""
    result: dict[str, str] = {}
    entries = pkg_meta.get_all("Project-URL") or []
    for entry in entries:
        if "," in entry:
            label, url = entry.split(",", 1)
            result[label.strip().lower()] = url.strip()
    return result


def _enrich_from_installed(
    dep_name: str,
    dep_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
) -> None:
    """Populate optional fields on a dependency package from installed metadata.

    Uses ``importlib.metadata`` to read the package's core metadata from the
    build environment and fills in:

    - ``description`` (from ``Summary``)
    - ``software_homePage`` (from ``Home-page`` or a ``Project-URL`` with a
      homepage label)
    - ``software_downloadLocation`` (from ``Download-URL`` or a ``Project-URL``
      with a download label)
    - ``software_packageUrl`` (PyPI PURL constructed from name and version)
    - ``hasDeclaredLicense`` relationship (from ``License-Expression`` or
      ``License`` core metadata field)

    Fields are only set when a non-empty, non-``UNKNOWN`` value is available.
    Does nothing if the package is not found in the build environment.

    Args:
        dep_name: Bare package name (e.g. ``"requests"``).
        dep_package: The ``software_Package`` element to enrich.
        creation_info: Shared ``CreationInfo`` for any new SPDX elements.
        doc_name: Document name (project name) for SPDX ID generation.
        doc_uuid: Document UUID for SPDX ID generation.
        exporter: Receives any new license and relationship elements.
    """
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

    # homePage — core field first, then well-known Project-URL labels
    home_page = pkg_meta["Home-page"] or ""
    if not home_page or home_page == "UNKNOWN":
        for label in _HOMEPAGE_LABELS:
            if label in project_urls:
                home_page = project_urls[label]
                break
    if home_page and home_page != "UNKNOWN":
        dep_package.software_homePage = home_page

    # downloadLocation — core field first, then well-known Project-URL labels
    download_url = pkg_meta["Download-URL"] or ""
    if not download_url or download_url == "UNKNOWN":
        for label in _DOWNLOAD_LABELS:
            if label in project_urls:
                download_url = project_urls[label]
                break
    if download_url and download_url != "UNKNOWN":
        dep_package.software_downloadLocation = download_url

    # packageUrl — PyPI PURL (pkg:pypi/<name>@<version>)
    # The package was resolved from the build environment, so it is pip-installable.
    # Per PURL spec: name lowercased, underscores replaced with hyphens.
    # See ECMA-427 https://tc54.org/purl/
    version = dep_package.software_packageVersion
    if version and version != "unknown":
        purl_name = dep_name.lower().replace("_", "-")
        dep_package.software_packageUrl = f"pkg:pypi/{purl_name}@{version}"

    # hasDeclaredLicense — prefer PEP 639 License-Expression over legacy License
    license_id = pkg_meta["License-Expression"] or pkg_meta["License"] or ""
    if license_id and license_id != "UNKNOWN":
        rel_declared, _ = build_license_elements(
            license_id=license_id,
            package_spdx_id=dep_package.spdxId,
            license_provenance=provenance_source,
            creation_info=creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
        )
        exporter.add_relationship(rel_declared)


def build_license_elements(
    license_id: str,
    package_spdx_id: str,
    license_provenance: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
) -> tuple[spdx3.Relationship, spdx3.Relationship]:
    """Get or create a SimpleLicensingText element and build its
    hasDeclaredLicense / hasConcludedLicense relationships for a given package.

    If a ``SimpleLicensingText`` with the same ``simplelicensing_licenseText``
    was already added to *exporter*, it is reused.  Otherwise a new element is
    created and registered.  Either way, two fresh ``Relationship`` elements
    are returned — the caller is responsible for adding them to the exporter.

    Args:
        license_id: SPDX license identifier string (e.g. ``"Apache-2.0"``).
        package_spdx_id: SPDX ID of the package the license applies to
                         (the "from" in each relationship).
        license_provenance: Human-readable provenance note for the comment field
            of a newly created SimpleLicensingText element.
        creation_info: Shared CreationInfo for all new elements.
        doc_name: Document name (project name) used in SPDX ID generation.
        doc_uuid: Document UUID used in SPDX ID generation.
        exporter: Used to look up and register the SimpleLicensingText element.

    Returns:
        A 2-tuple of ``(hasDeclaredLicense Relationship,
        hasConcludedLicense Relationship)``.
    """
    # Reuse an existing SimpleLicensingText if one with the same text exists.
    existing_spdx_id = exporter.find_license(license_id)
    if existing_spdx_id:
        license_spdx_id = existing_spdx_id
    else:
        license_text = spdx3.simplelicensing_SimpleLicensingText(
            spdxId=generate_spdx_id("License", doc_name=doc_name, doc_uuid=doc_uuid),
            creationInfo=creation_info,
        )
        license_text.name = license_id
        license_text.simplelicensing_licenseText = license_id
        license_text.comment = f"Metadata provenance: license: {license_provenance}"
        exporter.add_license(license_text)
        license_spdx_id = license_text.spdxId

    # The license actually found in the Software Artifact.
    rel_has_declared_license = spdx3.Relationship(
        spdxId=generate_spdx_id("Relationship", doc_name=doc_name, doc_uuid=doc_uuid),
        creationInfo=creation_info,
        from_=package_spdx_id,
        relationshipType=spdx3.RelationshipType.hasDeclaredLicense,
        to=[license_spdx_id],
    )

    # The license identified by the SPDX data creator.
    # This can be more complicated.
    # For example, if there are mulitple declared licenses,
    # or if there is no declared licenes but a license
    # can be concluded from other evidence.
    # See https://spdx.github.io/spdx-spec/v3.0/model/Licensing/Licensing/
    # Sort this out in future versions.
    # Eventually we may need to create the relationships separately,
    # as hasDeclaredLicense and hasConcludedLicense can be different and
    # the value of having this helper function will be less clear.
    rel_has_concluded_license = spdx3.Relationship(
        spdxId=generate_spdx_id("Relationship", doc_name=doc_name, doc_uuid=doc_uuid),
        creationInfo=creation_info,
        from_=package_spdx_id,
        relationshipType=spdx3.RelationshipType.hasConcludedLicense,
        to=[license_spdx_id],
    )

    return rel_has_declared_license, rel_has_concluded_license


def add_dependencies(
    dependencies: list[str],
    dep_provenance: str,
    main_package_spdx_id: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
) -> None:
    """Build SPDX ``software_Package`` and ``Relationship`` elements for each
    declared dependency and add them to the exporter.

    For each entry in ``dependencies``:
    - The package name is parsed from the PEP 508 specifier.
    - The installed version is resolved via ``importlib.metadata`` when
      available, providing build-time accuracy beyond the declared constraint.
    - Additional fields (description, homePage, downloadLocation, packageUrl,
      hasDeclaredLicense) are populated from the installed package metadata
      when available.
    - A ``dependsOn`` relationship links the main package to the dependency.
    - Provenance is recorded in the SPDX ``comment`` attribute.

    Args:
        dependencies: List of PEP 508 dependency specifier strings.
        dep_provenance: Provenance string for the dependencies field
            (e.g. ``"Source: pyproject.toml | Field: project.dependencies"``).
        main_package_spdx_id: SPDX ID of the parent package for relationships.
        creation_info: Shared ``CreationInfo`` for all new elements.
        doc_name: Document name (project name) for SPDX ID generation.
        doc_uuid: Document-scoped UUID used in SPDX ID generation.
        exporter: Receives the new package and relationship elements.
    """
    for dep in dependencies:
        dep_name = _parse_dep_name(dep)
        dep_version, version_note = _resolve_version(dep_name, dep)

        provenance_parts = [
            f"dependencies: {dep_provenance}",
            f"Declared constraint: {dep}",
        ]
        if version_note:
            provenance_parts.append(version_note)

        dep_package = spdx3.software_Package(
            spdxId=generate_spdx_id("Package", doc_name=doc_name, doc_uuid=doc_uuid),
            name=dep_name,
            creationInfo=creation_info,
        )
        dep_package.software_packageVersion = dep_version
        dep_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library
        dep_package.comment = "Metadata provenance: " + "; ".join(provenance_parts)

        _enrich_from_installed(
            dep_name, dep_package, creation_info, doc_name, doc_uuid, exporter
        )

        exporter.add_package(dep_package)

        dep_rel = spdx3.Relationship(
            spdxId=generate_spdx_id(
                "Relationship", doc_name=doc_name, doc_uuid=doc_uuid
            ),
            from_=main_package_spdx_id,
            to=[dep_package.spdxId],
            relationshipType=spdx3.RelationshipType.dependsOn,
            creationInfo=creation_info,
        )
        dep_rel.comment = f"Metadata provenance: dependencies: {dep_provenance}"
        exporter.add_relationship(dep_rel)
