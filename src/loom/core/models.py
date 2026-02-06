# SPDX-FileCopyrightText: 2024-present Loom Contributors
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3.0 data models for representing software bill of materials."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def generate_spdx_id(prefix: str) -> str:
    """Generate a unique SPDX ID with UUID.

    Args:
        prefix: The prefix for the SPDX ID (e.g., 'Person', 'Package', 'File')

    Returns:
        str: A unique SPDX ID in the format:
            https://spdx.org/spdxdocs/{prefix}/{prefix_abbrev}-{uuid}
    """
    prefix_abbrev = "".join([c for c in prefix if c.isupper()]) or prefix[:2].upper()
    unique_id = str(uuid4())
    return f"https://spdx.org/spdxdocs/{prefix}/{prefix_abbrev}-{unique_id}"


class CreationInfo:
    """SPDX 3.0 CreationInfo - metadata about the creation of an SPDX element."""

    def __init__(
        self,
        created: datetime | None = None,
        created_by: list[str] | None = None,
        spec_version: str = "3.0.1",
    ) -> None:
        self.created = created or datetime.now(timezone.utc)
        self.created_by = created_by or []
        self.spec_version = spec_version

    def to_dict(self) -> dict[str, Any]:
        """Convert CreationInfo to dictionary for JSON-LD serialization."""
        return {
            "@id": "_:creationinfo",
            "type": "CreationInfo",
            "specVersion": self.spec_version,
            "created": self.created.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "createdBy": self.created_by,
        }


class Person:
    """SPDX 3.0 Person - an individual person."""

    def __init__(
        self,
        name: str,
        spdx_id: str | None = None,
        email: str | None = None,
        creation_info: CreationInfo | None = None,
    ) -> None:
        self.name = name
        self.spdx_id = spdx_id or generate_spdx_id("Person")
        self.email = email
        self.creation_info = creation_info

    def to_dict(self) -> dict[str, Any]:
        """Convert Person to dictionary for JSON-LD serialization."""
        result: dict[str, Any] = {
            "spdxId": self.spdx_id,
            "type": "Person",
            "name": self.name,
            "creationInfo": "_:creationinfo",
        }

        if self.email:
            result["externalIdentifier"] = [
                {
                    "type": "ExternalIdentifier",
                    "externalIdentifierType": "email",
                    "identifier": self.email,
                }
            ]

        return result


class SoftwarePackage:
    """SPDX 3.0 Software Package - represents a unit of software."""

    def __init__(
        self,
        name: str,
        spdx_id: str | None = None,
        version: str | None = None,
        download_location: str | None = None,
        homepage: str | None = None,
        description: str | None = None,
        summary: str | None = None,
        copyright_text: str | None = None,
        package_url: str | None = None,
        primary_purpose: str | None = None,
        creation_info: CreationInfo | None = None,
    ) -> None:
        self.name = name
        self.spdx_id = spdx_id or generate_spdx_id("Package")
        self.version = version
        self.download_location = download_location
        self.homepage = homepage
        self.description = description
        self.summary = summary
        self.copyright_text = copyright_text
        self.package_url = package_url
        self.primary_purpose = primary_purpose
        self.creation_info = creation_info

    def to_dict(self) -> dict[str, Any]:
        """Convert SoftwarePackage to dictionary for JSON-LD serialization."""
        result: dict[str, Any] = {
            "spdxId": self.spdx_id,
            "type": "software_Package",
            "name": self.name,
            "creationInfo": "_:creationinfo",
        }

        if self.version:
            result["software_packageVersion"] = self.version
        if self.download_location:
            result["software_downloadLocation"] = self.download_location
        if self.homepage:
            result["software_homePage"] = self.homepage
        if self.description:
            result["description"] = self.description
        if self.summary:
            result["summary"] = self.summary
        if self.copyright_text:
            result["software_copyrightText"] = self.copyright_text
        if self.package_url:
            result["externalIdentifier"] = [
                {
                    "type": "ExternalIdentifier",
                    "externalIdentifierType": "purl",
                    "identifier": self.package_url,
                }
            ]
        if self.primary_purpose:
            result["software_primaryPurpose"] = self.primary_purpose

        return result


class Relationship:
    """SPDX 3.0 Relationship - defines a relationship between SPDX elements."""

    def __init__(
        self,
        from_element: str,
        to_elements: list[str],
        relationship_type: str,
        spdx_id: str | None = None,
        description: str | None = None,
        creation_info: CreationInfo | None = None,
    ) -> None:
        self.from_element = from_element
        self.to_elements = to_elements
        self.relationship_type = relationship_type
        self.spdx_id = spdx_id or generate_spdx_id("Relationship")
        self.description = description
        self.creation_info = creation_info

    def to_dict(self) -> dict[str, Any]:
        """Convert Relationship to dictionary for JSON-LD serialization."""
        result: dict[str, Any] = {
            "spdxId": self.spdx_id,
            "type": "Relationship",
            "from": self.from_element,
            "relationshipType": self.relationship_type,
            "to": self.to_elements,
            "creationInfo": "_:creationinfo",
        }

        if self.description:
            result["description"] = self.description

        return result


class Sbom:
    """SPDX 3.0 Software SBOM - a software bill of materials."""

    def __init__(
        self,
        spdx_id: str | None = None,
        root_elements: list[str] | None = None,
        sbom_types: list[str] | None = None,
        creation_info: CreationInfo | None = None,
    ) -> None:
        self.spdx_id = spdx_id or generate_spdx_id("Sbom")
        self.root_elements = root_elements or []
        self.sbom_types = sbom_types or ["build"]
        self.creation_info = creation_info

    def to_dict(self) -> dict[str, Any]:
        """Convert Sbom to dictionary for JSON-LD serialization."""
        return {
            "spdxId": self.spdx_id,
            "type": "software_Sbom",
            "rootElement": self.root_elements,
            "software_sbomType": self.sbom_types,
            "creationInfo": "_:creationinfo",
        }


class SpdxDocument:
    """SPDX 3.0 Document - the top-level container for SPDX elements."""

    def __init__(
        self,
        spdx_id: str | None = None,
        root_elements: list[str] | None = None,
        profile_conformance: list[str] | None = None,
        creation_info: CreationInfo | None = None,
    ) -> None:
        self.spdx_id = spdx_id or generate_spdx_id("SpdxDocument")
        self.root_elements = root_elements or []
        self.profile_conformance = profile_conformance or ["core", "software"]
        self.creation_info = creation_info

    def to_dict(self) -> dict[str, Any]:
        """Convert SpdxDocument to dictionary for JSON-LD serialization."""
        return {
            "spdxId": self.spdx_id,
            "type": "SpdxDocument",
            "rootElement": self.root_elements,
            "profileConformance": self.profile_conformance,
            "creationInfo": "_:creationinfo",
        }
