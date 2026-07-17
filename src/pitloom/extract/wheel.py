# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python wheels (Analyzed SBOM)."""

from __future__ import annotations

import email
import hashlib
import zipfile
from pathlib import Path

from pitloom.core.project import ProjectFile, ProjectMetadata


# pylint: disable=too-many-locals
def read_wheel(wheel_path: Path | str) -> tuple[ProjectMetadata, list[ProjectFile]]:
    """Extract project metadata and file records from a built wheel.

    Args:
        wheel_path: Path to the .whl file.

    Returns:
        A tuple of (ProjectMetadata, list of ProjectFile).
        The ProjectMetadata contains core fields extracted from METADATA.
    """
    wheel_path_obj = Path(wheel_path)
    metadata = ProjectMetadata(name="unknown")
    project_files: list[ProjectFile] = []
    provenance: dict[str, str] = {}
    source = f"Source: wheel METADATA | File: {wheel_path_obj.name}"

    with zipfile.ZipFile(wheel_path_obj, "r") as zf:
        metadata_content = None

        # 1. Collect files and calculate hashes
        for info in zf.infolist():
            if info.is_dir():
                continue

            # Identify the METADATA file among the wheel's contents.
            if info.filename.endswith(".dist-info/METADATA"):
                metadata_content = zf.read(info).decode("utf-8", errors="replace")

            hasher = hashlib.sha256()
            with zf.open(info) as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)

            project_files.append(
                ProjectFile(
                    # No filesystem path outside the archive; use the
                    # archive-relative path for both fields.
                    physical_path=info.filename,
                    distribution_path=info.filename,
                    digest_sha256=hasher.hexdigest(),
                )
            )

        # 2. Parse the METADATA file if found
        if metadata_content:
            msg = email.message_from_string(metadata_content)

            if msg.get("Name"):
                metadata.name = msg["Name"]
                provenance["name"] = source
            if msg.get("Version"):
                metadata.version = msg["Version"]
                provenance["version"] = source
            if msg.get("Summary"):
                metadata.description = msg["Summary"]
            if msg.get("Requires-Python"):
                metadata.requires_python = msg["Requires-Python"]

            # License-Expression or License
            license_expr = msg.get("License-Expression")
            if license_expr:
                metadata.license_name = license_expr
                provenance["license"] = source
            elif msg.get("License"):
                metadata.license_name = msg["License"]
                provenance["license"] = source

            # Dependencies
            reqs = msg.get_all("Requires-Dist")
            if reqs:
                # Kept as raw PEP 508 strings, unparsed.
                metadata.dependencies = reqs
                provenance["dependencies"] = source

            # Authors/Emails
            authors = []
            author_name = msg.get("Author")
            author_email = msg.get("Author-email")
            if author_name or author_email:
                author_dict = {}
                if author_name:
                    author_dict["name"] = author_name
                if author_email:
                    author_dict["email"] = author_email
                authors.append(author_dict)
            metadata.authors = authors

            # URLs
            urls = {}
            if msg.get("Home-page"):
                urls["Homepage"] = msg["Home-page"]
            if msg.get("Download-URL"):
                urls["Download"] = msg["Download-URL"]
            project_url_entries = msg.get_all("Project-URL") or []
            for entry in project_url_entries:
                if "," in entry:
                    label, url = entry.split(",", 1)
                    urls[label.strip()] = url.strip()
            metadata.urls = urls

    metadata.provenance = provenance
    metadata.files = project_files
    return metadata, project_files
