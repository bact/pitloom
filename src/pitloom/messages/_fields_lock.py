# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values the lines of a lock file, a lock entry and a declared
requirement name: a package, a dependency as declared, an extra, a value
read from a lock, what a conflict kept and dropped, a line number, a lock
key, a source kind, a value's type and where a dependency is declared.

A value read from a file (a 50 MB lock can hold a 10 MB version) is
written by :func:`~pitloom.logging_config.excerpt`: on one line, a URL's
credentials masked, cut to
:data:`~pitloom.logging_config.EXCERPT_CHARS` characters, escaped.

See also: :mod:`pitloom.messages._fields` (every field, these included),
:mod:`pitloom.messages._field_tables` (the closed tables).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.logging_config import EXCERPT_CHARS, excerpt, one_line
from pitloom.messages._field_tables import LOCK_KEYS, SOURCE_KINDS, VALUE_TYPES
from pitloom.messages._field_type import Field
from pitloom.messages._field_writers import (
    NAME_CHARACTERS,
    DescribedValue,
    free_name_text,
    free_text,
    plain_text,
    whole,
)

#: How a value read from a file is written, for the reference.
EXCERPT_MEANING: Final = (
    "on one line, a URL's credentials masked, cut to 120 characters "
    "(`...` after it when cut), in quotes, escaped when it holds a control "
    "character"
)
#: How a value merged from SBOM fragments that is not a text is written.
_DESCRIBED_MEANING: Final = (
    "a value merged from SBOM fragments that is not a text: an element "
    "(`ai_AIPackage <spdx-id> 'name'`), a structure (`Hash(algorithm=..., "
    "hashValue='...')`) or a number, not in quotes"
)


def excerpt_text(value: object) -> str:
    """A value read from a file or a declaration, as
    :func:`~pitloom.logging_config.excerpt` writes it: a string in quotes,
    any other value (a Poetry table, a missing name's ``None``) its repr; a
    :class:`~pitloom.messages._field_writers.DescribedValue` as it is, not
    in quotes, on one line, masked and cut alike."""
    if isinstance(value, DescribedValue):
        return one_line(str(value), EXCERPT_CHARS, ellipsis=True)
    return excerpt(value)


def excerpts_text(value: object) -> str:
    """A text, or a list, tuple, set or frozenset of texts, sorted, each as
    :func:`excerpt_text` writes it, comma-separated; an empty one writes
    nothing, which the field's shape refuses.

    Raises:
        ValueError: It is none of these, or holds anything but text.
    """
    if isinstance(value, str):
        return excerpt_text(value)
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError(f"not a text or a collection: {value!r}")
    texts = [plain_text(item) for item in value]
    return ", ".join(excerpt_text(text) for text in sorted(texts))


def line_number_text(value: object) -> str:
    """A line number: a whole number of 1 or more, in digits.

    Raises:
        ValueError: It is not.
    """
    number = whole(value)
    if number < 1:
        raise ValueError(f"not a line number: {value!r}")
    return str(number)


def value_type_text(value: object) -> str:
    """The type of *value*, a value a lock file holds, as Python names it
    (``list``): one of :data:`~pitloom.messages._field_tables.VALUE_TYPES`.
    The caller passes the value, never its type's name.

    Raises:
        ValueError: Its type is not in the table (no TOML or JSON reader
            loads it).
    """
    name = type(value).__name__
    if name not in VALUE_TYPES:
        raise ValueError(f"not a type a lock file holds: {name!r}")
    return name


def _one_of(table: tuple[str, ...]) -> str:
    """A pattern matching exactly one entry of *table*."""
    return "|".join(re.escape(entry) for entry in table)


def _listed(table: tuple[str, ...]) -> str:
    """*table* for a meaning, each entry in backticks."""
    return ", ".join(f"`{entry}`" for entry in table)


#: The lock files' and requirements' fields.
LOCK_FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "declared_in": Field(
            r".+",
            free_text,
            "<declared-in>",
            "where the dependency is declared: `Poetry`, "
            "`optional-dependencies`, `extras_require`, or the setting that "
            "lists a requirements file; escaped when it holds a control "
            "character",
            free=True,
        ),
        "dependency": Field(
            r".+",
            excerpt_text,
            "<dependency>",
            f"a dependency as declared (a requirement, a Poetry table), "
            f"{EXCERPT_MEANING}",
            free=True,
        ),
        "dropped": Field(
            r".+",
            excerpts_text,
            "<dropped>",
            "what a conflict left out (versions, a lock file, a value), sorted, "
            f"comma-separated, each {EXCERPT_MEANING}; {_DESCRIBED_MEANING}",
            free=True,
        ),
        "extra_name": Field(
            r".+",
            excerpts_text,
            "<extra>",
            f"an extra, or several sorted and comma-separated, each {EXCERPT_MEANING}",
            free=True,
        ),
        "kept": Field(
            r".+",
            excerpt_text,
            "<kept>",
            "what a conflict kept (a lock file, a version, a value), "
            f"{EXCERPT_MEANING}; {_DESCRIBED_MEANING}",
            free=True,
        ),
        "line_number": Field(
            r"[1-9][0-9]*",
            line_number_text,
            "<line>",
            "the line of a requirements file, counted from 1 as pip counts "
            "it (str.splitlines(); a continued line by its first)",
        ),
        "lock_key": Field(
            _one_of(LOCK_KEYS),
            plain_text,
            "<lock-key>",
            "the lock-file key the line is about: " + _listed(LOCK_KEYS),
        ),
        "lock_value": Field(
            r".+",
            excerpt_text,
            "<lock-value>",
            f"a value as the lock file or the line states it, {EXCERPT_MEANING}",
            free=True,
        ),
        "package": Field(
            r".+",
            free_name_text,
            "<package>",
            "a package as the lock file or the declaration names it (a valid "
            "distribution name), a URL's credentials masked, cut to "
            f"{NAME_CHARACTERS} characters (`...` after it when cut); escaped "
            "when it holds a control character",
            free=True,
        ),
        "source_kind": Field(
            _one_of(SOURCE_KINDS),
            plain_text,
            "<source-kind>",
            "the kind of source that gives no registry version: "
            + _listed(SOURCE_KINDS),
        ),
        "value_type": Field(
            _one_of(VALUE_TYPES),
            value_type_text,
            "<type>",
            "the type of the value the file holds, as Python names it: "
            + _listed(VALUE_TYPES),
        ),
    }
)
