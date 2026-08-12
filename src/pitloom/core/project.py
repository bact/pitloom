# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generic project metadata representation with provenance tracking."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


@dataclass
class ProjectFile:
    """A file included in the project distribution.

    Attributes:
        physical_path: Absolute or relative path to the physical file on disk.
        distribution_path: Canonical path of the file inside the wheel/package.
        digest_sha256: Hex-encoded SHA-256 digest of the file contents.
        copyright_text: The file's own declared copyright text, from an
            ``SPDX-FileCopyrightText:`` tag or a bare ``Copyright (c) ...``
            fallback line in its header. ``None`` when neither is present
            or file-header scanning is off (see
            ``pitloom.extract._file_headers.parse_file_header``).
        copyright_source: ``"spdx_tag"`` or ``"bare_copyright_line"`` --
            which form produced ``copyright_text``.
        file_contributors: Every ``SPDX-FileContributor:`` value from the
            file's header, in order. Empty when none are present.
        file_type: The raw ``SPDX-FileType:`` tag value, untranslated.
        spdx_license_identifier: The file's own ``SPDX-License-Identifier:``
            expression, independent of the project's overall license.
        content_type: A real IANA media type detected from the file's
            content/filename (``magika`` or a ``mimetypes`` fallback),
            independent of ``file_type`` -- see
            ``pitloom.extract._file_headers.guess_content_type``. ``None``
            when content-type detection is off or inconclusive.
        content_type_method: ``"magika"`` or ``"mimetype_extension_guess"``
            -- which tool resolved ``content_type``.
    """

    physical_path: str
    distribution_path: str
    digest_sha256: str
    copyright_text: str | None = None
    copyright_source: str | None = None
    file_contributors: list[str] = field(default_factory=list)
    file_type: str | None = None
    spdx_license_identifier: str | None = None
    content_type: str | None = None
    content_type_method: str | None = None


@dataclass
class PhantomDependency:
    """A bundled binary dependency not tracked by normal package metadata.

    Examples include bundled shared libraries (.so, .dll, .dylib) inside wheels
    and pre-compiled extension modules (.pyd) that link to external C/C++ libraries.

    Attributes:
        name: Name of the binary dependency (e.g., 'libz', 'openssl').
        file_path: Canonical path to the binary inside the distribution/wheel.
        digest_sha256: Hex-encoded SHA-256 digest of the binary file contents.
        version: Inferred version of the binary, if any.
    """

    name: str
    file_path: str
    digest_sha256: str | None = None
    version: str | None = None


@dataclass
# pylint: disable-next=too-many-instance-attributes
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
    license_concluded: str | None = None
    keywords: list[str] = field(default_factory=list)
    authors: list[dict[str, str]] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)
    files: list[ProjectFile] = field(default_factory=list)


def merge_project_metadata(
    primary: ProjectMetadata, secondary: ProjectMetadata
) -> ProjectMetadata:
    """Merge two :class:`ProjectMetadata` instances, *primary* winning
    field-by-field; *secondary* fills gaps where *primary*'s value is falsy.

    Iterates :func:`dataclasses.fields` instead of hand-listing every field,
    so a newly added :class:`ProjectMetadata` field (like ``license_concluded``,
    added for G2) is merged automatically with the same default rule -- no
    call site needs updating when the schema grows. This replaces two
    previously-duplicated, independently-drifting implementations
    (``pyproject.py``'s old ``_merge_with_poetry``, ``setuptools.py``'s old
    ``merge_metadata``) that each hand-listed every field and had to be kept
    in sync by hand; ``license_concluded`` was missing from one of them until
    this fix, precisely because that discipline had already lapsed once.

    Two fields are special-cased rather than "primary if truthy else
    secondary":

    - ``name`` -- always *primary*'s, even if empty (a project's own name is
      never meaningfully "filled in" from a secondary/fallback source).
    - ``provenance`` -- dict-merged, *primary*'s entries winning on key
      conflict, rather than replaced wholesale.

    Every other field: *primary*'s value when truthy, else *secondary*'s.
    """
    merged = dataclasses.replace(primary)
    merged.provenance = {**secondary.provenance, **primary.provenance}
    for f in dataclasses.fields(ProjectMetadata):
        if f.name in ("name", "provenance"):
            continue
        primary_value = getattr(primary, f.name)
        if not primary_value:
            setattr(merged, f.name, getattr(secondary, f.name))
    return merged
