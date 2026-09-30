# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python wheels (Analyzed SBOM)."""

from __future__ import annotations

import email
import email.message
import hashlib
import logging
import zipfile
from pathlib import Path

from pitloom._wheel_sbom_location import name_version_from_email_message
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.core.wheel_member_names import wheel_file_members
from pitloom.extract._core_metadata import parse_project_urls

log = logging.getLogger(__name__)


def _hash_wheel_entry(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, name: str
) -> ProjectFile:
    """Compute SHA-256 hash for a wheel entry in streaming chunks.

    *name* is the entry's install-location name (see
    :func:`pitloom.core.wheel_member_names.wheel_file_members`).
    """
    hasher = hashlib.sha256()
    with zf.open(info) as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return ProjectFile(
        physical_path=name,
        distribution_path=name,
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
    return parse_project_urls(msg, include_download=True)


def _populate_metadata_from_email(
    metadata: ProjectMetadata,
    provenance: dict[str, str],
    msg: email.message.Message,
    source: str,
) -> None:
    """Populate ProjectMetadata and provenance from parsed METADATA msg."""
    name, version = name_version_from_email_message(msg)
    if name:
        metadata.name = name
        provenance["name"] = source
    if version:
        metadata.version = version
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

        for member in wheel_file_members(zf, wheel_path_obj.name, log):
            if member.name.endswith(".dist-info/METADATA"):
                metadata_content = zf.read(member.info).decode(
                    "utf-8", errors="replace"
                )
            project_files.append(_hash_wheel_entry(zf, member.info, member.name))

        if metadata_content:
            msg = email.message_from_string(metadata_content)
            _populate_metadata_from_email(metadata, provenance, msg, source)

    metadata.provenance = provenance
    metadata.files = project_files
    return metadata, project_files
