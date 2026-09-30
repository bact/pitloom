# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Turn a human name into an IRI segment for an SPDX 3 identifier.

Every SPDX document namespace and every ``spdxId`` built from a name goes
through :func:`iri_segment`, so a name with a space, ``#`` or ``/`` yields a
valid IRI. The element's ``name`` keeps the original text.
"""

from __future__ import annotations

import string

__all__ = ["SPDX_DOCS_BASE", "doc_namespace", "iri_segment"]

#: Base IRI of every Pitloom-minted SPDX document namespace.
SPDX_DOCS_BASE = "https://spdx.org/spdxdocs/"

# RFC 3987 ipchar in ASCII, minus "%": unreserved, sub-delims, ":" and "@".
# Valid unencoded in both an ipath segment and an ifragment.
_SAFE_ASCII = frozenset(string.ascii_letters + string.digits + "-._~!$&'()*+,;=:@")

# RFC 3987 section 4.1: an IRI must not contain bidi formatting characters.
_BIDI_FORMATTING = frozenset(
    chr(code_point) for code_point in (0x200E, 0x200F, *range(0x202A, 0x202F))
)


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
    return char not in _BIDI_FORMATTING and _is_ucschar(ord(char))


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


def doc_namespace(doc_name: str, doc_uuid: str) -> str:
    """Return the SPDX document namespace for (*doc_name*, *doc_uuid*)."""
    return f"{SPDX_DOCS_BASE}{iri_segment(doc_name)}-{doc_uuid}"
