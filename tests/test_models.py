# SPDX-FileCopyrightText: 2024-present Loom Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for SPDX 3.0 core models."""

from datetime import datetime, timezone

from loom.core.models import (
    CreationInfo,
    Person,
    Relationship,
    Sbom,
    SoftwarePackage,
    SpdxDocument,
    generate_spdx_id,
)


def test_generate_spdx_id():
    """Test SPDX ID generation."""
    person_id = generate_spdx_id("Person")
    assert person_id.startswith("https://spdx.org/spdxdocs/Person/")
    assert "Person/P-" in person_id or "Person/PE-" in person_id

    package_id = generate_spdx_id("Package")
    assert package_id.startswith("https://spdx.org/spdxdocs/Package/")


def test_creation_info():
    """Test CreationInfo model."""
    created = datetime(2024, 6, 24, 5, 30, 0, tzinfo=timezone.utc)
    creator_id = "https://spdx.org/spdxdocs/Person/P-test-123"

    ci = CreationInfo(
        created=created,
        created_by=[creator_id],
        spec_version="3.0.1",
    )

    data = ci.to_dict()
    assert data["@id"] == "_:creationinfo"
    assert data["type"] == "CreationInfo"
    assert data["specVersion"] == "3.0.1"
    assert data["created"] == "2024-06-24T05:30:00Z"
    assert data["createdBy"] == [creator_id]


def test_person():
    """Test Person model."""
    person = Person(
        name="Test User",
        email="test@example.com",
    )

    data = person.to_dict()
    assert data["type"] == "Person"
    assert data["name"] == "Test User"
    assert data["creationInfo"] == "_:creationinfo"
    assert "spdxId" in data
    assert "externalIdentifier" in data
    assert data["externalIdentifier"][0]["externalIdentifierType"] == "email"
    assert data["externalIdentifier"][0]["identifier"] == "test@example.com"


def test_software_package():
    """Test SoftwarePackage model."""
    package = SoftwarePackage(
        name="test-package",
        version="1.0.0",
        download_location="https://github.com/test/test-package",
        description="A test package",
        primary_purpose="library",
    )

    data = package.to_dict()
    assert data["type"] == "software_Package"
    assert data["name"] == "test-package"
    assert data["software_packageVersion"] == "1.0.0"
    assert data["software_downloadLocation"] == "https://github.com/test/test-package"
    assert data["description"] == "A test package"
    assert data["software_primaryPurpose"] == "library"


def test_relationship():
    """Test Relationship model."""
    from_id = "https://spdx.org/spdxdocs/Package/PKG-123"
    to_id = "https://spdx.org/spdxdocs/Package/PKG-456"

    rel = Relationship(
        from_element=from_id,
        to_elements=[to_id],
        relationship_type="dependsOn",
        description="Package depends on another package",
    )

    data = rel.to_dict()
    assert data["type"] == "Relationship"
    assert data["from"] == from_id
    assert data["to"] == [to_id]
    assert data["relationshipType"] == "dependsOn"
    assert data["description"] == "Package depends on another package"


def test_sbom():
    """Test Sbom model."""
    package_id = "https://spdx.org/spdxdocs/Package/PKG-123"

    sbom = Sbom(
        root_elements=[package_id],
        sbom_types=["build", "runtime"],
    )

    data = sbom.to_dict()
    assert data["type"] == "software_Sbom"
    assert data["rootElement"] == [package_id]
    assert data["software_sbomType"] == ["build", "runtime"]


def test_spdx_document():
    """Test SpdxDocument model."""
    sbom_id = "https://spdx.org/spdxdocs/Sbom/SBOM-123"

    doc = SpdxDocument(
        root_elements=[sbom_id],
        profile_conformance=["core", "software", "ai"],
    )

    data = doc.to_dict()
    assert data["type"] == "SpdxDocument"
    assert data["rootElement"] == [sbom_id]
    assert data["profileConformance"] == ["core", "software", "ai"]
