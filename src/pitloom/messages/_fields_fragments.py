# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values only the SBOM fragment lines name: a property of an SPDX 3
element as the JSON-LD document names it, the element a reference names,
the new id an element is given, the type of the element holding an id,
a dictionary entry's key, a digest algorithm and two SHA-256 values, and a
provenance field.

A value read from a fragment is untrusted: each writer masks a URL's
credentials and escapes a control character; a value of any length
(a key, a digest) is cut to
:data:`~pitloom.logging_config.EXCERPT_CHARS` characters.

See also: :mod:`pitloom.messages._fields` (every field, these included),
:mod:`pitloom.messages._fragments` and
:mod:`pitloom.messages._fragments_merge` (the lines).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Final

from pitloom.core.internal_error import InternalError
from pitloom.messages._field_type import QUOTED, Field
from pitloom.messages._field_writers import (
    entity_text,
    free_text,
    plain_text,
    quoted_text,
)
from pitloom.messages._fields_lock import EXCERPT_MEANING, excerpt_text

#: What a property name always is, as the JSON-LD document writes it.
PROPERTY_PATTERN: Final = r"[A-Za-z][A-Za-z0-9_]*"

_MASKED: Final = (
    "a URL's credentials masked; in quotes, escaped, when it holds a control character"
)


def property_text(value: object) -> str:
    """A property of an SPDX 3 element as the JSON-LD document names it
    (``from``), from its name in the SPDX 3 Python bindings (``from_``,
    whose one trailing ``_`` stands for a Python keyword) or in the
    document.

    Raises:
        pitloom.core.internal_error.InternalError: It is not a ``str``.
    """
    name = plain_text(value)
    return name[:-1] if name.endswith("_") else name


def datetime_text(value: object) -> str:
    """An aware :class:`~datetime.datetime` in UTC, to the second, as an
    SBOM states ``created`` (``1970-01-01T00:00:00Z``).

    Raises:
        pitloom.core.internal_error.InternalError: It is not an aware
            ``datetime``.
    """
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InternalError(f"not an aware datetime: {value!r}")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


#: The SBOM fragment lines' fields.
FRAGMENT_FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "datetime": Field(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
            datetime_text,
            "<datetime>",
            "a date and time in UTC as an SBOM states created (`1970-01-01T00:00:00Z`)",
        ),
        "entry_key": Field(
            r".+",
            excerpt_text,
            "<entry-key>",
            f"the key of a dictionary entry (`DictionaryEntry`), {EXCERPT_MEANING}",
            free=True,
        ),
        "hash_algorithm": Field(
            r".+",
            free_text,
            "<algorithm>",
            "a digest algorithm as the SPDX 3 vocabulary names it (`sha256`); "
            "escaped when it holds a control character",
            free=True,
        ),
        "holder_type": Field(
            QUOTED,
            quoted_text,
            "'<holder-type>'",
            "the SPDX 3 type of the element that already holds the id, in "
            "quotes (`'software_Package'`), escaped when it holds a control "
            "character",
        ),
        "new_id": Field(
            r".+",
            entity_text,
            "<new-id>",
            f"the spdxId the element is given instead, {_MASKED}",
            free=True,
        ),
        "other_digest": Field(
            r".+",
            excerpt_text,
            "<other-digest>",
            "the SHA-256 the other element of that name states, in hex, "
            f"{EXCERPT_MEANING}",
            free=True,
        ),
        "property": Field(
            PROPERTY_PATTERN,
            property_text,
            "<property>",
            "a property of an SPDX 3 element as the JSON-LD document names it "
            "(`description`, `software_downloadLocation`, `from`)",
        ),
        "provenance_field": Field(
            r"[a-z][a-z0-9_]*",
            plain_text,
            "<provenance-field>",
            "the field a provenance entry is about, as Pitloom's provenance "
            "names it (`byte_size`, `verified_using`)",
        ),
        "reference": Field(
            r".+",
            entity_text,
            "<reference>",
            f"the spdxId a property names (`-` for an empty one), {_MASKED}",
            free=True,
        ),
        "digest": Field(
            r".+",
            excerpt_text,
            "<digest>",
            f"the SHA-256 an element states, in hex, {EXCERPT_MEANING}",
            free=True,
        ),
    }
)
