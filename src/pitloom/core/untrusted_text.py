# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Untrusted text shown to a reader, with its invisible controls visible.

Text read from a model file or a Hugging Face card (a name, a label, a
hyperparameter key, a dataset id) can hold a bidi control that reorders
what a reader sees (U+202E turns ``txt.exe`` into ``exe.txt`` on screen),
an invisible character that hides a difference between two names, or a
control a terminal acts on once the SBOM is decoded (ESC).
:data:`DISPLAY_CONTROLS` is the one set of such code points; each helper
below writes them in the spelling its context needs:

- :func:`escape_display_controls`: display text, as the literal six
  characters ``\\uXXXX`` (four lowercase hex digits; a code point above
  U+FFFF as its UTF-16 surrogate pair, two such escapes, as JSON spells it);
- :func:`escape_display_controls_in_json`: the same, inside JSON text;
- :func:`escape_display_controls_in_iri`: an IRI or URL, percent-encoded
  (lossless: the IRI still names the same resource).

The same set is used by :func:`pitloom.core.iri.iri_segment` (percent-encoded
in a minted ``spdxId``) and by
:func:`pitloom.extract._extract_utils.sanitize_provenance_text` (a file or
key name in a provenance string). :func:`pitloom.logging_config.loggable`
and :func:`pitloom.core.file_names.escape_file_name_part` cover it too.

A lone surrogate (U+D800 to U+DFFF, which ``json.loads`` accepts from
``"\\ud800"``) is not a display control: no UTF-8 text can hold it, so it
is written as text where model metadata is read
(:func:`escape_lone_surrogates`), in the same spelling.

Layering with RFC 8785 (JCS, :mod:`pitloom.core.canonical_json`): JCS is a
lossless serialisation. Its string rule (section 3.2.2.2) writes ``\\b``,
``\\t``, ``\\n``, ``\\f``, ``\\r``, ``\\"`` and ``\\\\`` with their short
escapes, every other C0 control (U+0000 to U+001F) as ``\\u00xx`` in lowercase
hex, and everything else as it is, as UTF-8: U+007F, the bidi controls and
code points above U+FFFF included (no surrogate pairs). Pitloom's escape is
a display-safety content transform applied to the text *before*
serialisation, so the two compose and intentionally do not align: JCS then
writes the escape's backslash as ``\\\\``, and a reader decoding the JSON
gets the six characters ``\\u202e``, never U+202E. The spelling matches the
one JCS uses for its own ``\\u00xx`` escapes, four lowercase hex digits.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pitloom.core.canonical_json import canonical_json

__all__ = [
    "DISPLAY_CONTROLS",
    "escape_display_controls",
    "escape_display_controls_in_iri",
    "escape_display_controls_in_json",
    "escape_lone_surrogates",
    "escape_lone_surrogates_in",
]

#: The code points every display-safety helper neutralises, one rule: a
#: code point a reader cannot see, or that changes how the text around it
#: is shown. The C0 controls but TAB, LF and CR, DEL and the C1 controls
#: (U+0000-U+0008, U+000B, U+000C, U+000E-U+001F, U+007F-U+009F); U+00AD
#: SOFT HYPHEN; U+034F COMBINING GRAPHEME JOINER; U+061C ARABIC LETTER MARK;
#: U+180E MONGOLIAN VOWEL SEPARATOR; the zero-width characters and the
#: LEFT-TO-RIGHT and RIGHT-TO-LEFT MARK (U+200B-U+200F); U+2028 LINE and
#: U+2029 PARAGRAPH SEPARATOR; the bidi embeddings and overrides
#: (U+202A-U+202E); U+2060 WORD JOINER and the invisible operators
#: (U+2061-U+2064); the bidi isolates and the deprecated format characters
#: (U+2066-U+206F); U+FEFF (byte order mark); the interlinear annotation
#: characters (U+FFF9-U+FFFB); and the tag characters (U+E0000-U+E007F).
DISPLAY_CONTROLS: frozenset[str] = frozenset(
    chr(code_point)
    for code_point in (
        *range(0x00, 0x09),
        0x0B,
        0x0C,
        *range(0x0E, 0x20),
        *range(0x7F, 0xA0),
        0xAD,
        0x034F,
        0x061C,
        0x180E,
        *range(0x200B, 0x2010),
        0x2028,
        0x2029,
        *range(0x202A, 0x202F),
        *range(0x2060, 0x2065),
        *range(0x2066, 0x2070),
        0xFEFF,
        *range(0xFFF9, 0xFFFC),
        *range(0xE0000, 0xE0080),
    )
)


def _escape(code_point: int) -> str:
    """*code_point* as ``\\uXXXX``; above U+FFFF, its UTF-16 surrogate pair."""
    if code_point <= 0xFFFF:
        return f"\\u{code_point:04x}"
    offset = code_point - 0x10000
    return _escape(0xD800 + (offset >> 10)) + _escape(0xDC00 + (offset & 0x3FF))


_ESCAPES = {ord(char): _escape(ord(char)) for char in DISPLAY_CONTROLS}

# Each code point as its UTF-8 bytes, percent-encoded in upper case (RFC 3986).
_IRI_ESCAPES = {
    ord(char): "".join(f"%{byte:02X}" for byte in char.encode("utf-8"))
    for char in DISPLAY_CONTROLS
}

_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def escape_display_controls(text: str) -> str:
    """*text* with each code point of :data:`DISPLAY_CONTROLS` written as
    the six characters ``\\u`` and its four lowercase hex digits (a tag
    character as its surrogate pair, twelve characters); *text* itself when
    it holds none.

    Not reversible: a ``\\u202e`` already in *text* as six characters stays
    as it is, so the result alone cannot tell it from an escaped control.
    Where the original matters, keep it elsewhere (the artifact-metadata
    annotation keeps a model's metadata as read).
    """
    return text.translate(_ESCAPES)


def _escape_strings(value: Any) -> Any:
    """*value*, decoded JSON, with every string, key or value, escaped."""
    if isinstance(value, str):
        return escape_display_controls(value)
    if isinstance(value, list):
        return [_escape_strings(item) for item in value]
    if isinstance(value, dict):
        return {
            escape_display_controls(key): _escape_strings(item)
            for key, item in value.items()
        }
    return value


def escape_display_controls_in_json(text: str) -> str:
    """JSON *text* whose strings, keys and values, are each
    :func:`escape_display_controls`'d: decoding the result gives the
    escaped strings. The text is decoded first, since JCS writes a C0
    control as an escape (``\\u001b``), and written back with RFC 8785 only
    when a string changed; *text* itself otherwise. Text that is not JSON
    is escaped as display text."""
    try:
        data = json.loads(text)
    except ValueError:
        return escape_display_controls(text)
    shown = _escape_strings(data)
    return text if shown == data else canonical_json(shown)


def escape_display_controls_in_iri(text: str) -> str:
    """IRI or URL *text* with each code point of :data:`DISPLAY_CONTROLS`
    percent-encoded as its UTF-8 bytes (``%E2%80%AE`` for U+202E), as RFC
    3987 section 4.1 asks for bidi controls; *text* itself when it holds
    none. Lossless, unlike :func:`escape_display_controls`: a ``\\`` is not
    valid in a URL."""
    return text.translate(_IRI_ESCAPES)


def escape_lone_surrogates(text: str) -> str:
    """*text* with each lone surrogate (U+D800 to U+DFFF) written as the six
    characters ``\\udXXX``, in lowercase hex; *text* itself without one. A
    string holding one cannot be encoded as UTF-8: not in an SBOM, a hash
    seed or a file."""
    return _LONE_SURROGATE.sub(lambda match: _escape(ord(match.group())), text)


def escape_lone_surrogates_in(value: Any) -> tuple[Any, bool]:
    """*value* with :func:`escape_lone_surrogates` applied to every string
    it holds: inside a list, a tuple, a dict (keys too) or a dataclass,
    whose fields are set in place. Returns the value, the same object when
    nothing changed, and whether anything did."""
    if isinstance(value, str):
        shown = escape_lone_surrogates(value)
        return shown, shown != value
    if isinstance(value, (list, tuple)):
        return _escape_lone_surrogates_in_sequence(value)
    if isinstance(value, dict):
        return _escape_lone_surrogates_in_dict(value)
    changed_any = False
    for name in getattr(value, "__dataclass_fields__", ()):
        shown, changed = escape_lone_surrogates_in(getattr(value, name))
        if changed:
            object.__setattr__(value, name, shown)
            changed_any = True
    return value, changed_any


def _escape_lone_surrogates_in_sequence(
    value: list[Any] | tuple[Any, ...],
) -> tuple[Any, bool]:
    """:func:`escape_lone_surrogates_in` for a list or a (named) tuple: a
    new one of the same type when an item changed."""
    pairs = [escape_lone_surrogates_in(item) for item in value]
    if not any(changed for _, changed in pairs):
        return value, False
    items = [item for item, _ in pairs]
    if hasattr(value, "_fields"):  # a named tuple
        return type(value)(*items), True
    return type(value)(items), True


def _escape_lone_surrogates_in_dict(value: dict[Any, Any]) -> tuple[Any, bool]:
    """:func:`escape_lone_surrogates_in` for a dict, in place, its order
    kept; of two keys that escape to the same text, the later one stays."""
    items = [
        (escape_lone_surrogates_in(key), escape_lone_surrogates_in(item))
        for key, item in value.items()
    ]
    if not any(k_changed or v_changed for (_, k_changed), (_, v_changed) in items):
        return value, False
    rebuilt = {key: item for (key, _), (item, _) in items}
    value.clear()
    value.update(rebuilt)
    return value, True
