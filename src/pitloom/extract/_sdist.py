# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata from an sdist archive
(``PKG-INFO``, falling back to ``pyproject.toml``)."""

from __future__ import annotations

import email
import hashlib
import logging
import tarfile
import zipfile
from pathlib import Path
from typing import Any

from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.extract._toml_io import tomllib
from pitloom.logging_config import field_loss_suffix

log = logging.getLogger(__name__)


def _parse_pkg_info(pkg_info_text: str, source_label: str) -> ProjectMetadata:
    """Parse Metadata-Version 2.x PKG-INFO content into ProjectMetadata."""
    msg = email.message_from_string(pkg_info_text)
    name = msg.get("Name", "unknown")
    version = msg.get("Version")
    summary = msg.get("Summary")
    license_name = msg.get("License")
    requires_python = msg.get("Requires-Python")

    metadata = ProjectMetadata(
        name=name,
        version=version,
        description=summary,
        license_name=license_name,
        requires_python=requires_python,
    )
    metadata.provenance["name"] = source_label
    if version:
        metadata.provenance["version"] = source_label
    if summary:
        metadata.provenance["description"] = source_label
    if license_name:
        metadata.provenance["license"] = source_label
    if requires_python:
        metadata.provenance["requires_python"] = source_label

    project_urls = msg.get_all("Project-URL") or []
    if project_urls:
        urls: dict[str, str] = {}
        for entry in project_urls:
            if "," in entry:
                label, url = entry.split(",", 1)
                urls[label.strip()] = url.strip()
        if urls:
            metadata.urls = urls
            metadata.provenance["urls"] = source_label

    author = msg.get("Author")
    if author and author != "UNKNOWN":
        metadata.authors = [{"name": author}]
        metadata.provenance["authors"] = source_label

    requires_dist = msg.get_all("Requires-Dist") or []
    if requires_dist:
        metadata.dependencies = [r.strip() for r in requires_dist]
        metadata.provenance["dependencies"] = source_label

    return metadata


def _parse_pyproject_bytes(pyproject_content: bytes) -> ProjectMetadata:
    """Parse fallback ProjectMetadata from pyproject.toml bytes."""
    try:
        data = tomllib.loads(pyproject_content.decode("utf-8", errors="replace"))
        proj = data.get("project", {})
        return ProjectMetadata(
            name=proj.get("name", "unknown"),
            version=proj.get("version"),
            description=proj.get("description"),
            dependencies=proj.get("dependencies", []),
        )
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        msg = (
            "Failed to parse pyproject.toml from sdist member: %s"
            + field_loss_suffix(
                "skipped", "name", "version", "description", "dependencies"
            )
        )
        log.warning(msg, exc)
        return ProjectMetadata(name="unknown")


def _read_tar_member_bytes(
    extracted: Any, is_special: bool
) -> tuple[bytes | None, str]:
    """Read tar member content and compute SHA-256 digest."""
    hasher = hashlib.sha256()
    with extracted:
        if is_special:
            content = extracted.read()
            hasher.update(content)
            return content, hasher.hexdigest()
        while chunk := extracted.read(8192):
            hasher.update(chunk)
    return None, hasher.hexdigest()


# pylint: disable-next=too-many-locals
def _read_tar_sdist(sdist_path: Path) -> tuple[ProjectMetadata, list[ProjectFile]]:
    """Extract metadata and files from a tar-based sdist (.tar.gz, .tgz)."""
    project_files: list[ProjectFile] = []
    pkg_info_content: str | None = None
    pyproject_content: bytes | None = None
    source_label = f"Source: sdist PKG-INFO | File: {sdist_path.name}"

    with tarfile.open(sdist_path, "r:*") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue

            extracted = tf.extractfile(member)
            if extracted is None:
                continue

            parts = Path(member.name).parts
            basename = Path(member.name).name
            is_pkg_info = (
                basename == "PKG-INFO" and pkg_info_content is None and len(parts) == 2
            )
            is_pyproject = (
                basename == "pyproject.toml"
                and pyproject_content is None
                and len(parts) == 2
            )

            content, digest = _read_tar_member_bytes(
                extracted, is_pkg_info or is_pyproject
            )
            if is_pkg_info and content is not None:
                pkg_info_content = content.decode("utf-8", errors="replace")
            elif is_pyproject and content is not None:
                pyproject_content = content

            project_files.append(
                ProjectFile(
                    physical_path=member.name,
                    distribution_path=member.name,
                    digest_sha256=digest,
                )
            )

        if pkg_info_content is not None:
            metadata = _parse_pkg_info(pkg_info_content, source_label)
        elif pyproject_content is not None:
            metadata = _parse_pyproject_bytes(pyproject_content)
        else:
            metadata = ProjectMetadata(name="unknown")

    return metadata, project_files


# pylint: disable-next=too-many-locals
def _read_zip_sdist(sdist_path: Path) -> tuple[ProjectMetadata, list[ProjectFile]]:
    """Extract metadata and files from a zip-based sdist (.zip)."""
    metadata = ProjectMetadata(name="unknown")
    project_files: list[ProjectFile] = []
    source_label = f"Source: sdist PKG-INFO | File: {sdist_path.name}"
    pkg_info_content: str | None = None
    pyproject_content: bytes | None = None

    with zipfile.ZipFile(sdist_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue

            parts = Path(info.filename).parts
            basename = Path(info.filename).name

            is_pkg_info = (
                basename == "PKG-INFO" and pkg_info_content is None and len(parts) == 2
            )
            is_pyproject = (
                basename == "pyproject.toml"
                and pyproject_content is None
                and len(parts) == 2
            )

            hasher = hashlib.sha256()
            with zf.open(info) as f:
                if is_pkg_info or is_pyproject:
                    content = f.read()
                    hasher.update(content)
                    if is_pkg_info:
                        pkg_info_content = content.decode("utf-8", errors="replace")
                    else:
                        pyproject_content = content
                else:
                    while chunk := f.read(8192):
                        hasher.update(chunk)

            digest = hasher.hexdigest()
            project_files.append(
                ProjectFile(
                    physical_path=info.filename,
                    distribution_path=info.filename,
                    digest_sha256=digest,
                )
            )

        if pkg_info_content is not None:
            metadata = _parse_pkg_info(pkg_info_content, source_label)
        elif pyproject_content is not None:
            metadata = _parse_pyproject_bytes(pyproject_content)
        else:
            metadata = ProjectMetadata(name="unknown")

    return metadata, project_files


def read_sdist(sdist_path: Path) -> tuple[ProjectMetadata, list[ProjectFile]]:
    """Read metadata and files from an sdist archive (.tar.gz, .tgz, .zip).

    Args:
        sdist_path: Path to the sdist archive.

    Returns:
        Tuple of (ProjectMetadata, list of ProjectFile).
    """
    if not sdist_path.exists():
        raise FileNotFoundError(f"Sdist archive not found: {sdist_path}")

    filename_lower = sdist_path.name.lower()
    if filename_lower.endswith(".zip"):
        return _read_zip_sdist(sdist_path)
    return _read_tar_sdist(sdist_path)
