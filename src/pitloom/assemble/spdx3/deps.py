# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Dependency package and relationship creation for SPDX 3 SBOM documents."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as get_package_version

from spdx_python_model import v3_0_1 as spdx3

from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter

# Operators used in PEP 508 dependency specifiers, ordered longest-first to
# avoid splitting on a prefix of a multi-character operator (e.g. "==" before "=").
_VERSION_OPERATORS = ("===", "~=", "!=", "==", ">=", "<=", ">", "<")


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


def add_dependencies(
    dependencies: list[str],
    dep_provenance: str,
    main_package_spdx_id: str,
    creation_info: spdx3.CreationInfo,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
) -> None:
    """Build SPDX ``software_Package`` and ``Relationship`` elements for each
    declared dependency and add them to the exporter.

    For each entry in ``dependencies``:
    - The package name is parsed from the PEP 508 specifier.
    - The installed version is resolved via ``importlib.metadata`` when
      available, providing build-time accuracy beyond the declared constraint.
    - A ``dependsOn`` relationship links the main package to the dependency.
    - Provenance is recorded in the SPDX ``comment`` attribute.

    Args:
        dependencies: List of PEP 508 dependency specifier strings.
        dep_provenance: Provenance string for the dependencies field
            (e.g. ``"Source: pyproject.toml | Field: project.dependencies"``).
        main_package_spdx_id: SPDX ID of the parent package for relationships.
        creation_info: Shared ``CreationInfo`` for all new elements.
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
            spdxId=generate_spdx_id("Package", doc_name=dep_name, doc_uuid=doc_uuid),
            name=dep_name,
            creationInfo=creation_info,
        )
        dep_package.software_packageVersion = dep_version
        dep_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library
        dep_package.comment = "Metadata provenance: " + "; ".join(provenance_parts)
        exporter.add_package(dep_package)

        dep_rel = spdx3.Relationship(
            spdxId=generate_spdx_id(
                "Relationship",
                doc_name=f"{dep_name}-dep",
                doc_uuid=doc_uuid,
            ),
            from_=main_package_spdx_id,
            to=[dep_package.spdxId],
            relationshipType=spdx3.RelationshipType.dependsOn,
            creationInfo=creation_info,
        )
        dep_rel.comment = f"Metadata provenance: dependencies: {dep_provenance}"
        exporter.add_relationship(dep_rel)
