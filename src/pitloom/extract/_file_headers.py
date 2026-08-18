# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Per-file SPDX header tag parsing and content-type detection.

Two independent, pure functions, no filesystem I/O of their own -- callers
supply already-read bytes:

- :func:`parse_file_header` reads a file's leading comment block for
  ``SPDX-FileCopyrightText``/``SPDX-FileContributor``/``SPDX-FileType``/
  ``SPDX-License-Identifier`` tags
  (https://spdx.github.io/spdx-spec/v2.3.1-dev/file-tags/), falling back
  to a bare ``Copyright (c) ...`` line when no SPDX tag is present.
  Deterministic, first-party (reads the project's own files) --
  distinct from :func:`guess_content_type`, which is Pitloom's own
  detection applied to bytes/filename, not a claim the file itself makes.
- :func:`guess_content_type` detects a real IANA media type via ``magika``
  (optional dependency, ``pitloom[content-type]``) when installed, falling
  back to a stdlib ``mimetypes`` filename-extension guess. Independent of
  ``SPDX-FileType`` -- never used to derive ``software_primaryPurpose``
  (see ``working-docs/design/file-headers.md`` for why the two are kept
  apart).
- :func:`resolve_content_type_override` matches a file's distribution
  path against a project-configured
  ``[[tool.pitloom.content-type.override]]`` table, pre-empting
  :func:`guess_content_type` for a match -- a deterministic,
  ``sbomAuthorSupplied`` alternative to detection for files the project
  author already knows the content type of.
- :func:`require_magika_available` raises when ``magika`` isn't
  installed -- called once, up front, when
  ``[tool.pitloom.content-type] method = "magika"`` is explicitly
  configured, so a misconfigured project fails immediately rather than
  after silently degrading every file's ``contentType``.
"""

from __future__ import annotations

import fnmatch
import logging
import mimetypes
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from pitloom.core.content_type_config import ContentTypeOverride

log = logging.getLogger(__name__)

#: Bound the header scan to the leading region of a file, whichever limit
#: is hit first -- bounds cost regardless of file size.
_HEADER_SCAN_MAX_BYTES = 4096
_HEADER_SCAN_MAX_LINES = 30

# Strips common comment-syntax markers from a line without any per-language
# awareness: "#"/shebang "#!", "//", "/*"/"/**", a lone "*" (Java-doc
# continuation lines), "<!--". Matched at the start of the (already
# whitespace-trimmed) line.
_COMMENT_PREFIX_RE = re.compile(r"^\s*(?:#!|#|//|/\*+|\*/?|<!--)\s*")
# Strips a trailing block-comment/HTML-comment closer, when present.
_COMMENT_SUFFIX_RE = re.compile(r"\s*(?:\*/|-->)\s*$")

# SPDX tags are case-sensitive per spec; matched against the exact
# canonical casing only.
_SPDX_COPYRIGHT_TAG_RE = re.compile(r"^SPDX-FileCopyrightText:\s*(.+?)\s*$")
_SPDX_CONTRIBUTOR_TAG_RE = re.compile(r"^SPDX-FileContributor:\s*(.+?)\s*$")
_SPDX_FILETYPE_TAG_RE = re.compile(r"^SPDX-FileType:\s*(.+?)\s*$")
_SPDX_LICENSE_TAG_RE = re.compile(r"^SPDX-License-Identifier:\s*(.+?)\s*$")

# Fallback for files that predate SPDX tagging. Own copy, not imported from
# assemble/spdx3/deps.py's _COPYRIGHT_LINE_RE -- that one scans a different
# corpus (a dependency's installed License-File, first 500 chars) for a
# different purpose; extract/ shouldn't import from assemble/.
_BARE_COPYRIGHT_RE = re.compile(r"^Copyright\s+(?:\(c\)|©)?\s*\S.*$", re.IGNORECASE)

# magika labels that mean "no real determination", worth falling back to
# mimetypes rather than trusting -- an empty file's "inode/x-empty" and a
# low-confidence "application/octet-stream" are both technically an
# answer, but not a useful content type for an SBOM.
_MAGIKA_INCONCLUSIVE_LABELS = frozenset({"unknown", "empty"})


@dataclass(frozen=True)
class FileHeaderMetadata:
    """Facts read from a single file's own leading comment header.

    Every field is the file's own stated claim (SPDX role ``declared``) --
    nothing here is inferred or detected. ``file_type`` is the raw
    ``SPDX-FileType:`` tag value, untranslated; mapping it to SPDX 3's
    ``SoftwarePurpose`` vocabulary is an assembly-layer concern, not
    this module's -- this stays a pure text-header parser with no SPDX3
    model knowledge.
    """

    copyright_text: str | None = None
    #: ``"spdx_tag"`` or ``"bare_copyright_line"`` -- which source
    #: produced ``copyright_text``, so callers can pick the right
    #: provenance ``Field:`` string.
    copyright_source: str | None = None
    file_contributors: list[str] = field(default_factory=list)
    file_type: str | None = None
    spdx_license_identifier: str | None = None


@dataclass
class _HeaderBuilder:
    copyright_text: str | None = None
    copyright_source: str | None = None
    file_contributors: list[str] = field(default_factory=list)
    file_type: str | None = None
    spdx_license_identifier: str | None = None

    def build(self) -> FileHeaderMetadata | None:
        if (
            self.copyright_text is None
            and not self.file_contributors
            and self.file_type is None
            and self.spdx_license_identifier is None
        ):
            return None
        return FileHeaderMetadata(
            copyright_text=self.copyright_text,
            copyright_source=self.copyright_source,
            file_contributors=list(self.file_contributors),
            file_type=self.file_type,
            spdx_license_identifier=self.spdx_license_identifier,
        )


def _strip_comment_markers(line: str) -> str:
    """Strip leading/trailing comment-syntax markers, return the remainder."""
    stripped = _COMMENT_PREFIX_RE.sub("", line)
    stripped = _COMMENT_SUFFIX_RE.sub("", stripped)
    return stripped.strip()


def _find_bare_copyright(lines: list[str]) -> str | None:
    """Find a fallback bare copyright line in comment-stripped lines."""
    for raw_line in lines:
        stripped = _strip_comment_markers(raw_line)
        if stripped and _BARE_COPYRIGHT_RE.match(stripped):
            return stripped
    return None


def _parse_header_line(
    stripped: str,
    meta: _HeaderBuilder,
) -> None:
    """Parse a single comment-stripped line into _HeaderBuilder."""
    if meta.copyright_text is None:
        match = _SPDX_COPYRIGHT_TAG_RE.match(stripped)
        if match:
            meta.copyright_text = match.group(1)
            meta.copyright_source = "spdx_tag"
            return

    if meta.file_type is None:
        match = _SPDX_FILETYPE_TAG_RE.match(stripped)
        if match:
            meta.file_type = match.group(1)
            return

    if meta.spdx_license_identifier is None:
        match = _SPDX_LICENSE_TAG_RE.match(stripped)
        if match:
            meta.spdx_license_identifier = match.group(1)
            return

    match = _SPDX_CONTRIBUTOR_TAG_RE.match(stripped)
    if match:
        meta.file_contributors.append(match.group(1))


def parse_file_header(data: bytes) -> FileHeaderMetadata | None:
    """Parse SPDX-File* tags (and a bare copyright fallback) from *data*."""
    head = data[:_HEADER_SCAN_MAX_BYTES]
    if b"\x00" in head:
        return None
    text = head.decode("utf-8", errors="ignore")

    non_blank_lines = [raw_line for raw_line in text.splitlines() if raw_line.strip()]
    lines = non_blank_lines[:_HEADER_SCAN_MAX_LINES]

    meta = _HeaderBuilder()
    for raw_line in lines:
        stripped = _strip_comment_markers(raw_line)
        if stripped:
            _parse_header_line(stripped, meta)

    if meta.copyright_text is None:
        bare = _find_bare_copyright(lines)
        if bare is not None:
            meta.copyright_text = bare
            meta.copyright_source = "bare_copyright_line"

    return meta.build()


@lru_cache(maxsize=1)
def _get_magika() -> Any:
    """Build (and cache) a single ``Magika`` instance for process lifetime.

    ``Magika()`` loads an ONNX inference session -- expensive enough that
    re-creating it per file (once per call to :func:`guess_content_type`)
    would multiply the ~5ms/file cost this feature is gated on. Returns
    ``None`` when ``magika`` isn't installed, cached the same way so the
    failed import isn't retried on every call either.
    """
    try:
        # pylint: disable=import-outside-toplevel
        from magika import Magika
    except ImportError:
        return None
    return Magika()


def require_magika_available() -> None:
    """Raise ``RuntimeError`` when ``magika`` isn't importable.

    Called once, up front (not per file), when
    ``[tool.pitloom.content-type] method = "magika"`` is explicitly
    configured -- the config author demanded ``magika`` specifically, so
    silently degrading every file's ``contentType`` to the extension
    guess (as ``"auto"`` would) would hide that the SBOM's content types
    are lower-quality than requested.
    """
    if _get_magika() is None:
        raise RuntimeError(
            "content-type-method 'magika' requires the magika package "
            "(pip install pitloom[content-type])"
        )


def guess_content_type(
    data: bytes, filename: str, method: str = "auto"
) -> tuple[str | None, str | None]:
    """Detect a real IANA media type for *data*, independent of any tag.

    *method* is ``"auto"`` (default), ``"magika"``, or ``"extension"``.
    Unless *method* is ``"extension"``, tries ``magika`` (byte-content-based
    ML detection) first, falling back to a stdlib ``mimetypes``
    filename-extension guess when ``magika`` isn't installed or its
    result is inconclusive -- ``"auto"`` and ``"magika"`` behave
    identically here; the difference between them is enforced by
    :func:`require_magika_available`, called separately, once, before
    any file is scanned. ``"extension"`` skips ``magika`` entirely.
    Returns ``(mime_type, method)`` where ``method`` is ``"magika"`` or
    ``"extension_guess"``, or ``(None, None)`` when neither resolves.
    This is Pitloom's own determination (SPDX role ``detected``) --
    never derived from, or used to derive,
    ``SPDX-FileType``/``software_primaryPurpose``.
    """
    if method != "extension":
        magika_instance = _get_magika()
        if magika_instance is not None:
            try:
                result = magika_instance.identify_bytes(data)
                label: str = result.output.label
                magika_mime_type: str = result.output.mime_type
                if magika_mime_type and label not in _MAGIKA_INCONCLUSIVE_LABELS:
                    return magika_mime_type, "magika"
            # pylint: disable=broad-exception-caught
            except Exception as exc:
                log.debug(
                    "magika content-type detection failed for %s: %s", filename, exc
                )

    guessed_mime_type, _encoding = mimetypes.guess_type(filename)
    if guessed_mime_type:
        return guessed_mime_type, "extension_guess"
    return None, None


def resolve_content_type_override(
    distribution_path: str, overrides: tuple[ContentTypeOverride, ...]
) -> ContentTypeOverride | None:
    """Return the first *overrides* entry whose ``pattern`` matches
    *distribution_path*, or ``None`` when none do.

    Patterns are plain shell-glob syntax matched via
    :func:`fnmatch.fnmatchcase` -- always case-sensitive, unlike plain
    :func:`fnmatch.fnmatch` (which case-normalizes via
    ``os.path.normcase``, a no-op on POSIX but lowercasing on Windows) --
    so the same pattern behaves identically on every platform regardless
    of the host filesystem's own case-sensitivity. Matched against
    *distribution_path*, the file's full POSIX-style canonical in-package
    path (the same string that becomes the ``software_File``'s own
    ``name`` in the generated SBOM). ``*`` matches any characters,
    including ``/`` -- so ``vendor/*`` matches everything under
    ``vendor/``, not just its direct children; there is no
    ``.gitignore``-style negation or directory-boundary distinction.
    First match wins, in configuration order.
    """
    for override in overrides:
        if fnmatch.fnmatchcase(distribution_path, override.pattern):
            return override
    return None
