# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Provenance settings (:class:`ProvenanceConfig`) and the provenance-string
helpers: the parser :func:`parse_provenance_value`, the builders
:func:`provenance_source` and :func:`provenance_segment` with their sanitiser
:func:`sanitize_provenance_text`, and :func:`escape_provenance_comment_part`.

``extract`` and ``assemble`` both write and read provenance strings, so the
helpers sit below both and neither imports the other for them.
"""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass

import rfc8785

from pitloom.core.internal_error import InternalError
from pitloom.core.untrusted_text import escape_display_controls, escape_lone_surrogates

DEFAULT_PROVENANCE_SCHEMA = "pitloom/1"

#: Segment-key normalization for "Key: value | Key: value" strings. The
#: grammar's segment order is Source | Field | Method | Evidence | Reason;
#: ``Evidence`` and ``Reason`` are written only by
#: :func:`pitloom.core.evidence.evidence_segment`. A key not listed passes
#: through lower-cased.
_KEY_MAP = {
    "source": "source",
    "field": "location",
    "method": "method",
    "package": "package",
    "role": "role",
    "evidence": "evidence",
    "reason": "reason",
}

#: Provenance ``Method`` values of a field Pitloom made from a file's own format
#: (the labels of a model, the kind of a model) rather than read from it. A
#: fragment's value for the same property replaces it.
GENERATED_METHODS = frozenset({"generated_from_labels", "derived_from_format"})

#: SPDX property of an ``ai_AIPackage`` -> the provenance fields that write it,
#: as ``pitloom.assemble.spdx3._ai_package`` assigns them. A property is
#: generated when every one of these fields present is.
PROVENANCE_PROPERTY_FIELDS = {
    "description": frozenset({"description"}),
    "ai_domain": frozenset({"domain"}),
    "ai_informationAboutApplication": frozenset({"inputs", "outputs"}),
}

#: Smallest possible non-empty JCS-encoded JSON object (e.g. ``{"a":""}``),
#: computed from the real serializer so it can't silently drift from it.
MIN_SOURCE_METADATA_BYTES = len(rfc8785.dumps({"a": ""}))


def require_max_source_metadata_bytes(
    value: object, label: str = "max_source_metadata_bytes"
) -> int:
    """*value* as an ``int`` when it is ``0`` (no cap) or a budget of at least
    :data:`MIN_SOURCE_METADATA_BYTES`, the smallest annotation that holds any
    metadata. A smaller one is an error, never a silent "unlimited".

    The one validator for every surface that takes the budget: the config
    key, ``--max-source-metadata-bytes``, ``ConfigOverrides`` and the library
    kwargs. *label* names the setting in the error, e.g.
    ``[tool.pitloom.provenance] 'max-source-metadata-bytes'``; ``""`` leaves
    the message to a caller that names the setting itself. Any
    :func:`operator.index`-able integer (a ``numpy.int64``) passes; a ``bool``
    or a ``float`` does not.

    Raises:
        ValueError: *value* is not an integer, is negative, or is below the
            minimum without being ``0``.
    """
    try:
        if isinstance(value, bool):
            raise TypeError
        number = operator.index(value)  # type: ignore[arg-type]
    except TypeError:
        raise ValueError(
            f"{label} must be an integer, got {type(value).__name__}: {value!r}".strip()
        ) from None
    if number != 0 and number < MIN_SOURCE_METADATA_BYTES:
        raise ValueError(
            f"{label} must be 0 (unlimited) or at least "
            f"{MIN_SOURCE_METADATA_BYTES} bytes, got {number}".strip()
        )
    return number


# The characters that structure the provenance comment, each written as
# its \uXXXX escape: ";" ends an entry, a line break starts a new one, and
# ":" (in the field part only) ends the field name.
_COMMENT_SOURCE_ESCAPES = {ord(char): f"\\u{ord(char):04x}" for char in ";\r\n"}
_COMMENT_FIELD_ESCAPES = {
    **_COMMENT_SOURCE_ESCAPES,
    ord(":"): "\\u003a",
}


def escape_provenance_comment_part(text: str, *, field: bool = False) -> str:
    """*text*, one part of a ``"<field>: <source>; ..."`` provenance comment
    entry, with the characters that structure the comment written as
    ``\\uXXXX``, the spelling of the display escape
    (:func:`~pitloom.core.untrusted_text.escape_display_controls`): ``;``,
    CR and LF in either part, and ``:`` too in the *field* part. A field
    or a file name read from a model cannot then forge or split an entry;
    a usual key (``properties.general.name``) is unchanged."""
    return text.translate(_COMMENT_FIELD_ESCAPES if field else _COMMENT_SOURCE_ESCAPES)


#: The keys :func:`provenance_segment` writes a value under, as spelled in
#: the string. ``Source`` is :func:`provenance_source`'s (one per string);
#: ``Evidence`` and ``Reason`` are
#: :func:`pitloom.core.evidence.evidence_segment`'s, a fixed vocabulary.
PROVENANCE_SEGMENT_KEYS: frozenset[str] = frozenset(
    {
        "Deprecated-License-Id",
        "Field",
        "File",
        "Method",
        "Normalized-From",
        "Normalizer",
        "Note",
        "Package",
        "Role",
        "Tool",
    }
)

#: The numbered keys of a licence value's resolution steps
#: (``Resolution-1``, ``Expansion-1``).
_NUMBERED_SEGMENT_KEY = re.compile(r"(?:Resolution|Expansion)-[1-9][0-9]*")


def sanitize_provenance_text(text: str) -> str:
    """*text*, untrusted, made safe to write into a provenance string.

    :func:`parse_provenance_value` splits a provenance string on ``|`` to
    find its ``Source:``/``Field:``/``Method:`` segments, so a ``|`` in a
    file name or a key read from a model would forge a segment (an
    ``Evidence: not_measured`` a merge acts on, a ``Source:`` that drops
    the entry in minimal detail mode). It becomes ``/``: ``a|b`` and
    ``a/b`` then read the same in provenance text, which never serves as
    an identity (registry keys come from
    :func:`pitloom.id_registry.keys.file_lookup_key`).

    The string is shown to a reader (an Annotation ``statement``, the
    element's ``comment``), so each code point of
    :data:`~pitloom.core.untrusted_text.DISPLAY_CONTROLS` is written as
    ``\\uXXXX`` (:func:`~pitloom.core.untrusted_text.escape_display_controls`),
    and each lone surrogate (a non-UTF-8 POSIX file name, ``b"\\xff"`` read
    as ``"\\udcff"``), which no UTF-8 output can hold, too
    (:func:`~pitloom.core.untrusted_text.escape_lone_surrogates`).

    Left as they are: LF, CR and TAB (the comment writer,
    :func:`escape_provenance_comment_part`, escapes ``;``, CR and LF, and
    JSON escapes the Annotation); ``;``, ``,`` and ``:`` (a name with a
    comma reads like a joined source list; only the first ``:`` of a
    segment ends its key). No length cap. Clean text comes back unchanged.
    """
    return escape_display_controls(escape_lone_surrogates(text.replace("|", "/")))


def provenance_source(label: str, *, file: str | None = None) -> str:
    """``"Source: <label>"``, plus ``" | File: <file>"`` when *file* is
    given, both through :func:`sanitize_provenance_text`: the first part of
    a provenance string."""
    source = f"Source: {sanitize_provenance_text(label)}"
    return source if file is None else provenance_segment(source, "File", file)


def provenance_segment(base: str, key: str, value: str) -> str:
    """*base*, a provenance string, with ``" | <key>: <value>"`` appended,
    *value* through :func:`sanitize_provenance_text`; *base* is taken as
    built (by :func:`provenance_source` or this function).

    Raises:
        pitloom.core.internal_error.InternalError: *key* is neither in
            :data:`PROVENANCE_SEGMENT_KEYS` nor a numbered
            ``Resolution-<n>``/``Expansion-<n>`` key (a programming error).
    """
    if key not in PROVENANCE_SEGMENT_KEYS and not _NUMBERED_SEGMENT_KEY.fullmatch(key):
        raise InternalError(f"unknown provenance segment key: {key!r}")
    return f"{base} | {key}: {sanitize_provenance_text(value)}"


def parse_provenance_value(value: str) -> dict[str, str]:
    """Parse ``"Source: X | Field: Y"`` into a structured dict."""
    parsed: dict[str, str] = {}
    notes: list[str] = []
    for raw in value.split("|"):
        segment = raw.strip()
        if not segment:
            continue
        key, sep, val = segment.partition(":")
        if sep:
            norm = _KEY_MAP.get(key.strip().lower(), key.strip().lower())
            parsed[norm] = val.strip()
        else:
            notes.append(segment)
    if notes:
        parsed.setdefault("note", " | ".join(notes))
    return parsed


@dataclass(frozen=True)
class ProvenanceConfig:
    """Configuration settings for SPDX 3 metadata provenance annotations.

    Attributes:
        format: How to record metadata provenance ("annotation", "comment", "both").
        schema: Schema id for provenance Annotations.
        detail: Provenance detail level ("minimal", "full").
        preserve_source_metadata: How to preserve source metadata
            ("auto", "always", "never").
        max_source_metadata_bytes: Byte budget for the serialized
            artifact-metadata Annotation.statement; 0 (default) means
            unlimited, below :data:`MIN_SOURCE_METADATA_BYTES` is an error. See
            :func:`require_max_source_metadata_bytes`.
    """

    format: str = "both"
    schema: str = DEFAULT_PROVENANCE_SCHEMA
    detail: str = "minimal"
    preserve_source_metadata: str = "auto"
    max_source_metadata_bytes: int = 0

    def __post_init__(self) -> None:
        """Reject an invalid budget, however it got here; keep it as a plain int."""
        object.__setattr__(
            self,
            "max_source_metadata_bytes",
            require_max_source_metadata_bytes(self.max_source_metadata_bytes),
        )
