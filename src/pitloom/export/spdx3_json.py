# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 JSON-LD exporter for generating SBOM documents."""

from __future__ import annotations

import io
import json

from spdx_python_model import v3_0_1 as spdx3


class Spdx3JsonExporter:
    """Exports SPDX 3 data structures to JSON-LD format using spdx-python-model."""

    def __init__(self) -> None:
        self.object_set = spdx3.SHACLObjectSet()
        # Maps simplelicensing_licenseText -> spdxId for deduplication.
        self._license_index: dict[str, str] = {}

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

    def find_license(self, license_id: str) -> str | None:
        """Return the spdxId of an existing SimpleLicensingText with the given
        ``simplelicensing_licenseText``, or ``None`` if not yet added.

        Args:
            license_id: The license text value to look up (e.g. ``"Apache-2.0"``).
        """
        return self._license_index.get(license_id)

    def add_license(
        self, simple_licensing_text: spdx3.simplelicensing_SimpleLicensingText
    ) -> None:
        """Add a SimpleLicensingText element to the document.

        Updates the internal license index so subsequent calls to
        :meth:`find_license` with the same ``simplelicensing_licenseText``
        return this element's spdxId.

        Args:
            license_text: The simplelicensing_SimpleLicensingText object
        """
        self.object_set.add(simple_licensing_text)
        license_id: str | None = simple_licensing_text.simplelicensing_licenseText
        if license_id:
            self._license_index[license_id] = simple_licensing_text.spdxId

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

    def to_json(self, pretty: bool = False) -> str:
        """Export to JSON-LD string.

        Args:
            pretty: If True, indent output with 2 spaces for human readability.
                    If False (default), produce compact output with no extra
                    whitespace, suitable for machine consumption and PEP 770
                    wheel embedding.

        Returns:
            str: JSON-LD representation
        """
        out_f = io.BytesIO()
        serializer = spdx3.JSONLDSerializer()
        serializer.write(self.object_set, out_f)
        data = json.loads(out_f.getvalue())
        if pretty:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)

    def to_file(self, file_path: str, pretty: bool = False) -> None:
        """Export to JSON-LD file.

        Args:
            file_path: Path to write the JSON-LD file
            pretty: If True, indent output with 2 spaces for human readability.
                    If False (default), produce compact output.
        """
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.to_json(pretty=pretty))
