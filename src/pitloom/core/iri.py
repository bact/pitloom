# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Turn a human name into an IRI segment for an SPDX 3 identifier.

Every SPDX document namespace and every ``spdxId`` built from a name goes
through :func:`iri_segment`, so a name with a space or ``#`` yields a valid
IRI. The element's ``name`` keeps the original text.

See also: :mod:`pitloom.core.untrusted_text` (the invisible and bidi
controls percent-encoded here).
"""

from __future__ import annotations

import re
import string

from pitloom.core.untrusted_text import DISPLAY_CONTROLS

__all__ = [
    "SPDX_DOCS_BASE",
    "doc_namespace",
    "iri_segment",
    "is_iri_segment",
    "require_namespace_iri",
]

#: Base IRI of every Pitloom-minted SPDX document namespace.
SPDX_DOCS_BASE = "https://spdx.org/spdxdocs/"

# RFC 3987 ipchar in ASCII, minus "%": unreserved, sub-delims, ":" and "@".
# Valid unencoded in both an ipath segment and an ifragment.
_SAFE_ASCII = frozenset(string.ascii_letters + string.digits + "-._~!$&'()*+,;=:@")
# The escape iri_segment() writes.
_SEGMENT_ESCAPE = re.compile(r"%[0-9A-F]{2}")

# RFC 3987 section 4.1 bans the bidi formatting characters (U+200E, U+200F,
# U+202A-U+202E) from an IRI; the isolates, zero-width characters and BOM in
# the shared display-control set are encoded with them.


def _is_ucschar(code_point: int) -> bool:
    """Return whether *code_point* is an RFC 3987 ``ucschar``."""
    if code_point < 0x10000:
        return (
            0xA0 <= code_point <= 0xD7FF
            or 0xF900 <= code_point <= 0xFDCF
            or 0xFDF0 <= code_point <= 0xFFEF
        )
    # Planes 1 to 14, less the last two code points of each plane; plane 14
    # starts at U+E1000 (tags and variation selectors are excluded).
    if code_point > 0xEFFFD or 0xE0000 <= code_point < 0xE1000:
        return False
    return (code_point & 0xFFFF) <= 0xFFFD


def _is_safe(char: str) -> bool:
    if char in _SAFE_ASCII:
        return True
    return char not in DISPLAY_CONTROLS and _is_ucschar(ord(char))


def iri_segment(name: str) -> str:
    """Return *name* as a string valid in an IRI path segment and fragment.

    A character outside RFC 3987 ``ipchar`` -- and ``%`` itself -- becomes
    its UTF-8 bytes, percent-encoded in upper case. Everything else,
    non-ASCII letters included, is kept as is, so a name that is already
    valid comes back unchanged. Always encoding ``%`` makes the mapping
    reversible: two different names never share a segment. Not idempotent:
    pass the raw name, never an already-encoded one.
    """
    return "".join(
        char
        if _is_safe(char)
        else "".join(f"%{byte:02X}" for byte in char.encode("utf-8", "surrogatepass"))
        for char in name
    )


def is_iri_segment(value: str) -> bool:
    """Return whether *value* is a non-empty string :func:`iri_segment` can
    write: characters it keeps, and ``%`` only in an upper-case ``%XX``."""
    return bool(value) and all(
        _is_safe(char) for char in _SEGMENT_ESCAPE.sub("", value)
    )


def doc_namespace(doc_name: str, doc_uuid: str) -> str:
    """Return the SPDX document namespace for (*doc_name*, *doc_uuid*)."""
    return f"{SPDX_DOCS_BASE}{iri_segment(doc_name)}-{doc_uuid}"


_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:(?=.)")
_PERCENT = re.compile(r"%[0-9A-Fa-f]{2}")
# gen-delims a path, query or host may carry, besides the ipchars above.
_EXTRA_ASCII = frozenset("/?[]")


def require_namespace_iri(value: str) -> str:
    """Return *value* when it can be a document namespace, else raise
    ``ValueError``.

    A namespace is an absolute IRI (RFC 3987): a scheme and something after
    it, only characters an IRI allows (a ``%`` followed by two hex digits),
    and no ``#``, because every ``spdxId`` appends its own ``#<fragment>``.
    """
    if not value:
        raise ValueError("namespace is empty")
    if "#" in value:
        raise ValueError(f"namespace {value!r} must not contain '#'")
    if not _SCHEME.match(value):
        raise ValueError(
            f"namespace {value!r} is not an absolute IRI (a scheme is needed, "
            "as in https://example.org/ns)"
        )
    rest = _PERCENT.sub("", value)
    if not all(_is_safe(char) or char in _EXTRA_ASCII for char in rest):
        raise ValueError(f"namespace {value!r} has a character an IRI cannot hold")
    return value
