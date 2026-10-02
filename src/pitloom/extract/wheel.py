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
from pitloom.core.archive_member_names import zip_file_members
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.core.wheel_dist_info import (
    MAX_METADATA_BYTES,
    read_member_bounded,
    refuse_unreadable,
    resolve_own_dist_info,
)
from pitloom.extract._core_metadata import parse_project_urls

log = logging.getLogger(__name__)


def _hash_wheel_entry(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, name: str, archive: str
) -> ProjectFile:
    """Compute SHA-256 hash for a wheel entry in streaming chunks.

    *name* is the entry's install-location name (see
    :func:`pitloom.core.archive_member_names.zip_file_members`), the
    ``distribution_path``. ``physical_path`` is the raw archive name, so a
    registry keyed by it before names were normalised still hits.

    Raises:
        ValueError: The member cannot be read (damaged, encrypted,
            unsupported, badly named): the wheel is refused as a whole.
    """
    hasher = hashlib.sha256()
    with refuse_unreadable(archive, info.orig_filename), zf.open(info) as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return ProjectFile(
        physical_path=info.orig_filename,
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
        The ProjectMetadata contains core fields extracted from the
        ``METADATA`` of the wheel's own top-level ``.dist-info`` (see
        :func:`pitloom.core.wheel_dist_info.resolve_own_dist_info`); any
        other ``*.dist-info`` directory is an ordinary file.
    """
    wheel_path_obj = Path(wheel_path)
    metadata = ProjectMetadata(name="unknown")
    project_files: list[ProjectFile] = []
    provenance: dict[str, str] = {}
    archive = wheel_path_obj.name
    source = f"Source: wheel METADATA | File: {archive}"

    with zipfile.ZipFile(wheel_path_obj, "r") as zf:
        members = zip_file_members(zf, archive, log)
        choice = resolve_own_dist_info(archive, [name for name, _ in members])
        if choice.problem:
            log.warning("ARCHIVE=%r: %s", archive, choice.problem)
        own_metadata = f"{choice.prefix}METADATA" if choice.prefix else None
        metadata_content: bytes | None = None

        for name, info in members:
            record = _hash_wheel_entry(zf, info, name, archive)
            project_files.append(record)
            if name == own_metadata:
                metadata_content = read_member_bounded(zf, info, MAX_METADATA_BYTES)
                if metadata_content is None:
                    log.warning(
                        "ARCHIVE=%r ENTRY=%r: larger than %d bytes -- not read",
                        archive,
                        info.orig_filename,
                        MAX_METADATA_BYTES,
                    )

        if metadata_content:
            msg = email.message_from_string(
                metadata_content.decode("utf-8", errors="replace")
            )
            _populate_metadata_from_email(metadata, provenance, msg, source)

    # Archive order is the writer's; SPDX ids are minted in file order.
    project_files.sort(key=lambda f: f.distribution_path)
    metadata.provenance = provenance
    metadata.files = project_files
    return metadata, project_files
