# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generic project metadata representation with provenance tracking."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProjectMetadata:
    """Format-neutral representation of project metadata with provenance tracking.

    This dataclass is the common currency between extractors and generators.
    It carries no knowledge of how the data was obtained; any extractor
    (``pyproject.toml``, ``setup.cfg``, build logs, …) can populate it.

    Provenance is recorded per-field in :attr:`provenance` using the pattern
    ``"Source: <location> | Field: <key>"`` or
    ``"Source: <location> | Method: <method>"``.

    Loom tool settings such as ``fragments`` and ``pretty`` are **not** stored
    here; they live in :class:`~loom.core.config.LoomConfig` which is returned
    alongside this object by
    :func:`~loom.extractors.pyproject.read_pyproject`.
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
