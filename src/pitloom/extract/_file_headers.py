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
  back to stdlib ``mimetypes``. Independent of ``SPDX-FileType`` -- never
  used to derive ``software_primaryPurpose`` (see
  ``working-docs/design/file-headers.md`` for why the two are kept apart).
"""

from __future__ import annotations

import logging
import mimetypes
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

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


def _strip_comment_markers(line: str) -> str:
    """Strip leading/trailing comment-syntax markers, return the remainder."""
    stripped = _COMMENT_PREFIX_RE.sub("", line)
    stripped = _COMMENT_SUFFIX_RE.sub("", stripped)
    return stripped.strip()


def parse_file_header(data: bytes) -> FileHeaderMetadata | None:
    """Parse SPDX-File* tags (and a bare copyright fallback) from *data*.

    Scans only the leading ``_HEADER_SCAN_MAX_BYTES``/``_HEADER_SCAN_MAX_LINES``
    of *data* (whichever limit is hit first). Binary content (detected via
    a null byte in the scanned region) is silently skipped, returning
    ``None`` -- never raises on non-text input. Returns ``None`` when
    nothing at all was found, so a header-less file (the common case)
    doesn't produce an all-empty result.
    """
    head = data[:_HEADER_SCAN_MAX_BYTES]
    if b"\x00" in head:
        return None
    text = head.decode("utf-8", errors="ignore")

    non_blank_lines = [raw_line for raw_line in text.splitlines() if raw_line.strip()]
    lines = non_blank_lines[:_HEADER_SCAN_MAX_LINES]

    copyright_text: str | None = None
    copyright_source: str | None = None
    file_contributors: list[str] = []
    file_type: str | None = None
    spdx_license_identifier: str | None = None

    for raw_line in lines:
        stripped = _strip_comment_markers(raw_line)
        if not stripped:
            continue

        if copyright_text is None:
            match = _SPDX_COPYRIGHT_TAG_RE.match(stripped)
            if match:
                copyright_text = match.group(1)
                copyright_source = "spdx_tag"
                continue

        if file_type is None:
            match = _SPDX_FILETYPE_TAG_RE.match(stripped)
            if match:
                file_type = match.group(1)
                continue

        if spdx_license_identifier is None:
            match = _SPDX_LICENSE_TAG_RE.match(stripped)
            if match:
                spdx_license_identifier = match.group(1)
                continue

        match = _SPDX_CONTRIBUTOR_TAG_RE.match(stripped)
        if match:
            file_contributors.append(match.group(1))

    if copyright_text is None:
        for raw_line in lines:
            stripped = _strip_comment_markers(raw_line)
            if stripped and _BARE_COPYRIGHT_RE.match(stripped):
                copyright_text = stripped
                copyright_source = "bare_copyright_line"
                break

    if (
        copyright_text is None
        and not file_contributors
        and file_type is None
        and spdx_license_identifier is None
    ):
        return None

    return FileHeaderMetadata(
        copyright_text=copyright_text,
        copyright_source=copyright_source,
        file_contributors=file_contributors,
        file_type=file_type,
        spdx_license_identifier=spdx_license_identifier,
    )


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
        from magika import Magika  # pylint: disable=import-outside-toplevel
    except ImportError:
        return None
    return Magika()


def guess_content_type(data: bytes, filename: str) -> tuple[str | None, str | None]:
    """Detect a real IANA media type for *data*, independent of any tag.

    Tries ``magika`` (byte-content-based ML detection) first, falling back
    to stdlib ``mimetypes`` (filename-extension-based) when ``magika``
    isn't installed or its result is inconclusive. Returns
    ``(mime_type, method)`` where ``method`` is ``"magika"`` or
    ``"mimetype_extension_guess"``, or ``(None, None)`` when neither
    resolves. This is Pitloom's own determination (SPDX role
    ``detected``) -- never derived from, or used to derive,
    ``SPDX-FileType``/``software_primaryPurpose``.
    """
    magika_instance = _get_magika()
    if magika_instance is not None:
        try:
            result = magika_instance.identify_bytes(data)
            label: str = result.output.label
            magika_mime_type: str = result.output.mime_type
            if magika_mime_type and label not in _MAGIKA_INCONCLUSIVE_LABELS:
                return magika_mime_type, "magika"
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.debug("magika content-type detection failed for %s: %s", filename, exc)

    guessed_mime_type, _encoding = mimetypes.guess_type(filename)
    if guessed_mime_type:
        return guessed_mime_type, "mimetype_extension_guess"
    return None, None
