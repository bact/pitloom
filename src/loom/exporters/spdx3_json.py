# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3.0 JSON-LD exporter for generating SBOM documents."""

from __future__ import annotations

import json
from typing import Any

from loom.core.models import (
    CreationInfo,
    Person,
    Relationship,
    Sbom,
    SoftwarePackage,
    SpdxDocument,
)


class Spdx3JsonExporter:
    """Exports SPDX 3.0 data structures to JSON-LD format."""

    CONTEXT_URL = "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"

    def __init__(self) -> None:
        self.elements: list[Any] = []
        self.creation_info: CreationInfo | None = None

    def add_creation_info(self, creation_info: CreationInfo) -> None:
        """Add creation info to the document.

        Args:
            creation_info: The CreationInfo object
        """
        self.creation_info = creation_info
        self.elements.append(creation_info.to_dict())

    def add_person(self, person: Person) -> None:
        """Add a person to the document.

        Args:
            person: The Person object
        """
        self.elements.append(person.to_dict())

    def add_package(self, package: SoftwarePackage) -> None:
        """Add a software package to the document.

        Args:
            package: The SoftwarePackage object
        """
        self.elements.append(package.to_dict())

    def add_relationship(self, relationship: Relationship) -> None:
        """Add a relationship to the document.

        Args:
            relationship: The Relationship object
        """
        self.elements.append(relationship.to_dict())

    def add_sbom(self, sbom: Sbom) -> None:
        """Add an SBOM to the document.

        Args:
            sbom: The Sbom object
        """
        self.elements.append(sbom.to_dict())

    def add_document(self, document: SpdxDocument) -> None:
        """Add an SPDX document to the graph.

        Args:
            document: The SpdxDocument object
        """
        self.elements.append(document.to_dict())

    def to_json(self, indent: int | None = 4) -> str:
        """Export to JSON-LD string.

        Args:
            indent: Number of spaces for indentation (None for compact)

        Returns:
            str: JSON-LD representation
        """
        output: dict[str, Any] = {
            "@context": self.CONTEXT_URL,
            "@graph": self.elements,
        }
        return json.dumps(output, indent=indent, ensure_ascii=False)

    def to_file(self, file_path: str, indent: int | None = 4) -> None:
        """Export to JSON-LD file.

        Args:
            file_path: Path to write the JSON-LD file
            indent: Number of spaces for indentation (None for compact)
        """
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.to_json(indent=indent))
