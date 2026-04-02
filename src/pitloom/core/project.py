# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generic project metadata representation with provenance tracking."""

from __future__ import annotations

from dataclasses import dataclass, field

@dataclass
class ProjectFile:
    """A file included in the project distribution.
    
    Attributes:
        physical_path: Absolute or relative path to the physical file on disk.
        distribution_path: Canonical path of the file inside the wheel/package.
        digest_sha256: Hex-encoded SHA-256 digest of the file contents.
    """

    physical_path: str
    distribution_path: str
    digest_sha256: str


@dataclass
class ProjectMetadata:
    """Format-neutral representation of project metadata with provenance tracking.

    This dataclass is the common currency between the extract and assemble
    layers.  It carries no knowledge of how the data was obtained; any
    extractor (``pyproject.toml``, ``setup.cfg``, build logs, …) can
    populate it.

    Provenance is recorded per-field in :attr:`provenance` using the pattern
    ``"Source: <location> | Field: <key>"`` or
    ``"Source: <location> | Method: <method>"``.

    Pitloom tool settings such as ``fragments`` and ``pretty`` are **not** stored
    here; they live in :class:`~pitloom.core.config.PitloomConfig` which is returned
    alongside this object by
    :func:`~pitloom.extract.pyproject.read_pyproject`.
    """

    name: str
    version: str | None = None
    description: str | None = None
    readme: str | None = None
    requires_python: str | None = None
    license_name: str | None = None
    keywords: list[str] = field(default_factory=list)
    authors: list[dict[str, str]] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)
    files: list[ProjectFile] = field(default_factory=list)
