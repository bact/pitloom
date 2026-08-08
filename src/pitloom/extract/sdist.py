# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python source distributions (sdists: .tar.gz, .zip)."""

from __future__ import annotations

import email
import hashlib
import sys
import tarfile
import zipfile
from pathlib import Path

from pitloom.core.project import ProjectFile, ProjectMetadata

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def _parse_pkg_info(metadata_content: str, source_label: str) -> ProjectMetadata:
    """Parse a PKG-INFO file content into ProjectMetadata."""
    msg = email.message_from_string(metadata_content)
    metadata = ProjectMetadata(name=msg.get("Name", "unknown"))

    fields: dict[str, str] = {
        "Version": "version",
        "Summary": "description",
        "Author": "author",
        "Author-email": "author_email",
        "License": "license",
    }
    for header, attr in fields.items():
        value = msg.get(header)
        if value and value != "UNKNOWN":
            setattr(metadata, attr, value)
            metadata.provenance[attr] = source_label

    keywords = msg.get("Keywords")
    if keywords and keywords != "UNKNOWN":
        metadata.keywords = [kw.strip() for kw in keywords.split(",") if kw.strip()]
        metadata.provenance["keywords"] = source_label

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
        metadata.dependencies = list(requires_dist)
        metadata.provenance["dependencies"] = source_label

    return metadata


def _read_tar_sdist(sdist_path: Path) -> tuple[ProjectMetadata, list[ProjectFile]]:
    """Extract metadata and files from a tar-based sdist (.tar.gz, .tgz, etc.)."""
    metadata = ProjectMetadata(name="unknown")
    project_files: list[ProjectFile] = []
    source_label = f"Source: sdist PKG-INFO | File: {sdist_path.name}"

    with tarfile.open(sdist_path, "r:*") as tf:
        pkg_info_content: str | None = None
        pyproject_content: bytes | None = None

        for member in tf.getmembers():
            if not member.isfile():
                continue

            # Read file content for PKG-INFO / pyproject.toml
            basename = Path(member.name).name
            if basename == "PKG-INFO" and pkg_info_content is None:
                extracted = tf.extractfile(member)
                if extracted is not None:
                    pkg_info_content = extracted.read().decode(
                        "utf-8", errors="replace"
                    )
            elif basename == "pyproject.toml" and pyproject_content is None:
                extracted = tf.extractfile(member)
                if extracted is not None:
                    pyproject_content = extracted.read()

            # Hash file content
            extracted_file = tf.extractfile(member)
            hasher = hashlib.sha256()
            if extracted_file is not None:
                while chunk := extracted_file.read(8192):
                    hasher.update(chunk)

            project_files.append(
                ProjectFile(
                    physical_path=member.name,
                    distribution_path=member.name,
                    digest_sha256=hasher.hexdigest(),
                )
            )

        if pkg_info_content is not None:
            metadata = _parse_pkg_info(pkg_info_content, source_label)
        elif pyproject_content is not None:
            # Fallback to parsing pyproject.toml if PKG-INFO is missing
            try:
                data = tomllib.loads(
                    pyproject_content.decode("utf-8", errors="replace")
                )
                proj = data.get("project", {})
                metadata = ProjectMetadata(
                    name=proj.get("name", "unknown"),
                    version=proj.get("version"),
                    description=proj.get("description"),
                    dependencies=proj.get("dependencies", []),
                )
            except Exception:  # pylint: disable=broad-exception-caught
                metadata = ProjectMetadata(name="unknown")

    return metadata, project_files


def _read_zip_sdist(sdist_path: Path) -> tuple[ProjectMetadata, list[ProjectFile]]:
    """Extract metadata and files from a zip-based sdist (.zip)."""
    metadata = ProjectMetadata(name="unknown")
    project_files: list[ProjectFile] = []
    source_label = f"Source: sdist PKG-INFO | File: {sdist_path.name}"

    with zipfile.ZipFile(sdist_path, "r") as zf:
        pkg_info_content: str | None = None
        pyproject_content: bytes | None = None

        for info in zf.infolist():
            if info.is_dir():
                continue

            basename = Path(info.filename).name
            if basename == "PKG-INFO" and pkg_info_content is None:
                pkg_info_content = zf.read(info).decode("utf-8", errors="replace")
            elif basename == "pyproject.toml" and pyproject_content is None:
                pyproject_content = zf.read(info)

            hasher = hashlib.sha256()
            with zf.open(info) as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)

            project_files.append(
                ProjectFile(
                    physical_path=info.filename,
                    distribution_path=info.filename,
                    digest_sha256=hasher.hexdigest(),
                )
            )

        if pkg_info_content is not None:
            metadata = _parse_pkg_info(pkg_info_content, source_label)
        elif pyproject_content is not None:
            try:
                data = tomllib.loads(
                    pyproject_content.decode("utf-8", errors="replace")
                )
                proj = data.get("project", {})
                metadata = ProjectMetadata(
                    name=proj.get("name", "unknown"),
                    version=proj.get("version"),
                    description=proj.get("description"),
                    dependencies=proj.get("dependencies", []),
                )
            except Exception:  # pylint: disable=broad-exception-caught
                metadata = ProjectMetadata(name="unknown")

    return metadata, project_files


def read_sdist(sdist_path: Path | str) -> tuple[ProjectMetadata, list[ProjectFile]]:
    """Extract project metadata and file records from a source distribution archive.

    Args:
        sdist_path: Path to a .tar.gz, .tgz, .tar.bz2, .tar.xz, or .zip sdist file.

    Returns:
        A tuple of (ProjectMetadata, list of ProjectFile).
    """
    path = Path(sdist_path)
    if not path.exists():
        raise FileNotFoundError(f"Source distribution archive not found: {path}")

    filename_lower = path.name.lower()
    if filename_lower.endswith(".zip"):
        return _read_zip_sdist(path)
    return _read_tar_sdist(path)
