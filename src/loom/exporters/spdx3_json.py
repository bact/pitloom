# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3.0 JSON-LD exporter for generating SBOM documents."""

from __future__ import annotations

import io

from spdx_python_model import v3_0_1 as spdx3


class Spdx3JsonExporter:
    """Exports SPDX 3.0 data structures to JSON-LD format using spdx-python-model."""

    def __init__(self) -> None:
        self.object_set = spdx3.SHACLObjectSet()

    def add_creation_info(self, creation_info: spdx3.CreationInfo) -> None:
        """Add creation info to the document.

        Args:
            creation_info: The CreationInfo object
        """
        self.object_set.add(creation_info)

    def add_person(self, person: spdx3.Person) -> None:
        """Add a person to the document.

        Args:
            person: The Person object
        """
        self.object_set.add(person)

    def add_package(self, package: spdx3.software_Package) -> None:
        """Add a software package to the document.

        Args:
            package: The software_Package object
        """
        self.object_set.add(package)

    def add_relationship(self, relationship: spdx3.Relationship) -> None:
        """Add a relationship to the document.

        Args:
            relationship: The Relationship object
        """
        self.object_set.add(relationship)

    def add_sbom(self, sbom: spdx3.software_Sbom) -> None:
        """Add an SBOM to the document.

        Args:
            sbom: The software_Sbom object
        """
        self.object_set.add(sbom)

    def add_document(self, document: spdx3.SpdxDocument) -> None:
        """Add an SPDX document to the graph.

        Args:
            document: The SpdxDocument object
        """
        self.object_set.add(document)

    def to_json(self) -> str:
        """Export to JSON-LD string.

        Returns:
            str: JSON-LD representation
        """
        out_f = io.BytesIO()
        serializer = spdx3.JSONLDSerializer()
        serializer.write(self.object_set, out_f)
        return out_f.getvalue().decode("utf-8")

    def to_file(self, file_path: str) -> None:
        """Export to JSON-LD file.

        Args:
            file_path: Path to write the JSON-LD file
        """
        with open(file_path, "wb") as f:
            serializer = spdx3.JSONLDSerializer()
            serializer.write(self.object_set, f)
