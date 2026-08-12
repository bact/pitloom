# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Configuration dataclass for per-file SPDX header metadata extraction."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContentTypeOverride:
    """One ``[[tool.pitloom.file-headers.content-type-overrides]]`` entry.

    A project-configured, deterministic ``contentType`` assignment for
    every file whose ``distribution_path`` matches ``pattern`` (a plain
    shell-glob, matched case-sensitively via ``fnmatch.fnmatchcase`` --
    see ``pitloom.extract._file_headers.resolve_content_type_override``).
    A match short-circuits both ``magika`` and the ``mimetypes`` fallback
    for that specific file -- but only when ``detect_content_type`` is
    already on; overrides are a per-file refinement within that gate, not
    a way to bypass it. SPDX role ``sbomAuthorSupplied`` (see
    ``working-docs/implementation/annotation-provenance.md``'s role
    vocabulary): the config author is asserting this value directly, not
    something Pitloom detected.
    """

    pattern: str
    content_type: str


@dataclass(frozen=True)
class FileHeadersConfig:
    """Configuration settings for ``[tool.pitloom.file-headers]``.

    Attributes:
        enabled: Whether to scan each source file's leading comment header
            for SPDX-File* tags (FileCopyrightText, FileContributor,
            FileType) and a per-file SPDX-License-Identifier. On by
            default -- this is pure regex over bytes already read for the
            SHA-256 hash, the same cost class as work Pitloom already does
            unconditionally elsewhere (e.g. LICENSE/CITATION.cff/
            codemeta.json scanning in ``pitloom.extract._license``); the
            "off until proven" precedent ``[tool.pitloom.enrich]`` has
            doesn't apply here, since it was about immature
            external-content parsing, not raw cost.
        detect_content_type: Whether to also detect each file's real IANA
            media type via ``magika``/``mimetypes`` (see
            ``pitloom.extract._file_headers.guess_content_type``). Off by
            default -- unlike ``enabled``, this has a real measured
            per-file cost (``magika`` inference, ~5ms/file), so it keeps
            the same "opt-in, real cost" treatment ``[tool.pitloom.enrich]``
            has. Independent of ``enabled`` -- never used to derive
            ``software_primaryPurpose`` from ``SPDX-FileType``, or vice
            versa; see ``working-docs/design/file-headers.md``.
        content_type_overrides: Glob-pattern -> MIME-type entries that
            pre-empt detection for matching files (see
            :class:`ContentTypeOverride`). Empty by default. Only takes
            effect when ``detect_content_type`` is also on -- a non-match
            still goes through the normal ``magika``/``mimetypes`` path,
            and when ``detect_content_type`` is off, overrides never fire
            either, same as today's behaviour.
    """

    enabled: bool = True
    detect_content_type: bool = False
    content_type_overrides: tuple[ContentTypeOverride, ...] = ()
