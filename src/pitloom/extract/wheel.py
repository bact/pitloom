# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python wheels (Analyzed SBOM)."""

from __future__ import annotations

import email
import email.message
import hashlib
import zipfile
from pathlib import Path

from pitloom.core.project import ProjectFile, ProjectMetadata


def _hash_wheel_entry(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> ProjectFile:
    """Compute SHA-256 hash for a wheel entry in streaming chunks."""
    hasher = hashlib.sha256()
    with zf.open(info) as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return ProjectFile(
        physical_path=info.filename,
        distribution_path=info.filename,
        digest_sha256=hasher.hexdigest(),
    )


def _parse_metadata_authors(msg: email.message.Message) -> list[dict[str, str]]:
    """Extract authors from email METADATA message."""
    authors: list[dict[str, str]] = []
    author_name = msg.get("Author")
    author_email = msg.get("Author-email")
    if author_name or author_email:
        author_dict: dict[str, str] = {}
        if author_name:
            author_dict["name"] = author_name
        if author_email:
            author_dict["email"] = author_email
        authors.append(author_dict)
    return authors


def _parse_metadata_urls(msg: email.message.Message) -> dict[str, str]:
    """Extract URLs from email METADATA message."""
    urls: dict[str, str] = {}
    if msg.get("Home-page"):
        urls["Homepage"] = msg["Home-page"]
    if msg.get("Download-URL"):
        urls["Download"] = msg["Download-URL"]
    project_url_entries = msg.get_all("Project-URL") or []
    for entry in project_url_entries:
        if "," in entry:
            label, url = entry.split(",", 1)
            urls[label.strip()] = url.strip()
    return urls


def _populate_metadata_from_email(
    metadata: ProjectMetadata,
    provenance: dict[str, str],
    msg: email.message.Message,
    source: str,
) -> None:
    """Populate ProjectMetadata and provenance from parsed METADATA msg."""
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

    license_expr = msg.get("License-Expression")
    if license_expr:
        metadata.license_name = license_expr
        provenance["license"] = source
    elif msg.get("License"):
        metadata.license_name = msg["License"]
        provenance["license"] = source

    reqs = msg.get_all("Requires-Dist")
    if reqs:
        metadata.dependencies = reqs
        provenance["dependencies"] = source

    metadata.authors = _parse_metadata_authors(msg)
    metadata.urls = _parse_metadata_urls(msg)


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

        for info in zf.infolist():
            if info.is_dir():
                continue
            if info.filename.endswith(".dist-info/METADATA"):
                metadata_content = zf.read(info).decode("utf-8", errors="replace")

            project_files.append(_hash_wheel_entry(zf, info))

        if metadata_content:
            msg = email.message_from_string(metadata_content)
            _populate_metadata_from_email(metadata, provenance, msg, source)

    metadata.provenance = provenance
    metadata.files = project_files
    return metadata, project_files
