# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Configuration dataclasses for per-file content-type detection."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContentTypeOverride:
    """One ``[[tool.pitloom.content-type.override]]`` entry.

    A project-configured, deterministic ``contentType`` assignment for
    every file whose ``distribution_path`` matches ``pattern`` (a plain
    shell-glob, matched case-sensitively via ``fnmatch.fnmatchcase`` --
    see ``pitloom.extract._file_headers.resolve_content_type_override``).
    A match short-circuits detection entirely for that specific file --
    but only when ``[tool.pitloom.content-type] enabled`` is already on;
    overrides are a per-file refinement within that gate, not a way to
    bypass it. SPDX role ``sbomAuthorSupplied`` (see
    ``working-docs/implementation/annotation-provenance.md``'s role
    vocabulary): the config author is asserting this value directly, not
    something Pitloom detected.
    """

    pattern: str
    content_type: str


@dataclass(frozen=True)
class ContentTypeConfig:
    """Configuration settings for ``[tool.pitloom.content-type]``.

    Independent of ``[tool.pitloom] extract-file-header`` -- a file gets
    a detected/overridden ``contentType`` regardless of whether it has a
    text header at all (e.g. an AI model binary), and regardless of
    whether SPDX-File* header scanning is enabled.

    Attributes:
        enabled: Whether to detect each file's real IANA media type via
            ``magika``/``mimetypes`` (see
            ``pitloom.extract._file_headers.guess_content_type``). Off by
            default -- this has a real measured per-file cost (``magika``
            inference, ~5ms/file), so it's opt-in rather than on by
            default.
        method: Which detector resolves ``contentType`` when ``enabled``
            is on: ``"auto"`` (default -- try ``magika``, fall back to a
            filename-extension guess via stdlib ``mimetypes`` when
            ``magika`` isn't installed or its result is inconclusive),
            ``"magika"`` (same per-file behavior as ``"auto"``, but
            raises a clear error up front if the ``magika`` package
            isn't installed at all, rather than silently degrading),
            or ``"extension"`` (skip ``magika`` entirely, resolve purely
            from the filename's extension -- cheaper, deterministic, no
            ML dependency needed).
        overrides: Glob-pattern -> MIME-type entries that pre-empt
            detection for matching files (see :class:`ContentTypeOverride`).
            Empty by default. Only takes effect when ``enabled`` is also
            on -- a non-match still goes through the normal detection
            path, and when ``enabled`` is off, overrides never fire
            either.
    """

    enabled: bool = False
    method: str = "auto"
    overrides: tuple[ContentTypeOverride, ...] = ()
