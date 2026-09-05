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
            content/filename (``magika`` or a filename-extension
            fallback), or asserted directly by a
            ``[[tool.pitloom.content-type.override]]`` config match,
            independent of ``file_type`` -- see
            ``pitloom.extract._file_headers.guess_content_type``/
            ``resolve_content_type_override``. ``None`` when
            content-type detection is off or inconclusive.
        content_type_method: ``"magika"``, ``"extension_guess"``, or
            ``"config_override"`` -- which tool (or config match)
            resolved ``content_type``.
        is_license_file: ``True`` when this entry was resolved from
            ``[project.license-files]`` (PEP 639) rather than discovered by
            normal package file selection -- see
            ``pitloom.extract._license.resolve_license_file_entries``. Tells
            the assembler to emit a file-level ``hasDeclaredLicense``
            relationship using the project's declared license, since this
            file carries no ``SPDX-License-Identifier:`` header of its own.
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
    is_license_file: bool = False


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
    extractor (``pyproject.toml``, ``setup.cfg``, build logs, ...) can
    populate it.

    Provenance is recorded per-field in :attr:`provenance` using the pattern
    ``"Source: <location> | Field: <key>"`` or
    ``"Source: <location> | Method: <method>"``.

    Pitloom tool settings such as ``fragments`` and ``pretty`` are **not** stored
    here; they live in :class:`~pitloom.core.config.PitloomConfig` which is returned
    alongside this object by
    :func:`~pitloom.extract._pyproject.read_pyproject`.
    """

    name: str
    version: str | None = None
    description: str | None = None
    readme: str | None = None
    requires_python: str | None = None
    license_name: str | None = None
    license_concluded: str | None = None
    license_files: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    authors: list[dict[str, str]] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    locked_dependencies: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)
    files: list[ProjectFile] = field(default_factory=list)


#: Maps a :class:`ProjectMetadata` field name to the literal provenance key
#: its extractors actually record it under, for the one known case where
#: they differ -- every ``license_name`` producer (``_pyproject.py``,
#: ``_setuptools_py.py``, ``_setuptools_cfg.py``) writes
#: ``provenance["license"]``, never ``provenance["license_name"]``. Consulted
#: by :func:`merge_project_metadata`'s "explicitly declared" check so it
#: looks up the key extractors actually use instead of a field name that's
#: never present in *provenance*.
_PROVENANCE_KEY_ALIASES: dict[str, str] = {"license_name": "license"}


def merge_project_metadata(
    primary: ProjectMetadata, secondary: ProjectMetadata
) -> ProjectMetadata:
    """Merge two :class:`ProjectMetadata` instances, *primary* winning
    field-by-field; *secondary* fills gaps where *primary*'s value is absent.

    Iterates :func:`dataclasses.fields` instead of hand-listing every field,
    so a newly added :class:`ProjectMetadata` field (like ``license_concluded``,
    added for G2) is merged automatically with the same default rule -- no
    call site needs updating when the schema grows. This replaces two
    previously-duplicated, independently-drifting implementations
    (``pyproject.py``'s old ``_merge_with_poetry``, ``setuptools.py``'s old
    ``merge_metadata``) that each hand-listed every field and had to be kept
    in sync by hand; ``license_concluded`` was missing from one of them until
    this fix, precisely because that discipline had already lapsed once.

    Two fields are special-cased rather than "primary when present else
    secondary":

    - ``name`` -- always *primary*'s, even if empty (a project's own name is
      never meaningfully "filled in" from a secondary/fallback source).
    - ``provenance`` -- dict-merged, *primary*'s entries winning on key
      conflict, rather than replaced wholesale.

    Every other field: *primary*'s value when present, else *secondary*'s.
    An empty container (``dependencies``, ``keywords``, ``urls``, etc.)
    with provenance confirming it was explicitly declared in *primary* is
    authoritative and preserved. Default-constructed empty containers (absent
    from *primary*'s provenance) or ``None`` values are treated as absent and
    filled from *secondary*. A non-empty *primary* list replaces *secondary*'s
    wholesale, it is never unioned with it. If a future
    ``locked_dependencies`` source needs union-not-replace semantics (e.g.
    combining two lock-derived dependency sets), that is a deliberate
    deviation from every sibling list field here and belongs in a dedicated
    merge step at the call site, not a silent special case in this
    otherwise-uniform field-by-field loop.

    The "explicitly declared" check looks up *provenance* by the field's own
    name (e.g. ``provenance["keywords"]``) -- except ``license_name``, whose
    extractors have historically recorded its provenance under the literal
    key ``"license"`` (see ``_pyproject.py``/``_setuptools_py.py``/
    ``_setuptools_cfg.py``), not ``"license_name"``; :data:`_PROVENANCE_KEY_ALIASES`
    maps that one known mismatch so the same presence check still finds it.
    """
    merged = dataclasses.replace(primary)
    merged.provenance = {**secondary.provenance, **primary.provenance}
    for f in dataclasses.fields(ProjectMetadata):
        if f.name in ("name", "provenance"):
            continue
        primary_value = getattr(primary, f.name)
        provenance_key = _PROVENANCE_KEY_ALIASES.get(f.name, f.name)
        if primary_value is None or (
            not primary_value and provenance_key not in primary.provenance
        ):
            setattr(merged, f.name, getattr(secondary, f.name))
    return merged
