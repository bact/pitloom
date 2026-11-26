# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values the configuration lines name: where a value sits, what it
must be, what was found, where a moved key went, the tables that know a
key, and the unknown keys of the build hook's table.

See also: :mod:`pitloom.messages._fields` (every field, these included),
:mod:`pitloom.messages._config_place` and
:mod:`pitloom.messages._config_found` (the closed tables and writers).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.core.internal_error import InternalError
from pitloom.messages._config_found import FOUND_PATTERN, SHOWN_CHARS, found_text
from pitloom.messages._config_place import (
    DESTINATIONS,
    EXPECTED,
    PLACE_PATTERN,
    TABLE_PATTERN,
    expected_text,
    place_text,
    tables_text,
)
from pitloom.messages._field_type import Field
from pitloom.messages._field_writers import free_text, plain_text


def _one_of(table: tuple[str, ...]) -> str:
    """A pattern matching exactly one entry of *table*."""
    return "|".join(re.escape(entry) for entry in table)


def keys_text(value: object) -> str:
    """A list, tuple, set or frozenset of keys as a file names them, sorted,
    each written as :func:`~pitloom.messages._field_writers.free_text`
    writes it, comma-separated; an empty one writes nothing, which the
    field's shape refuses.

    Raises:
        pitloom.core.internal_error.InternalError: It is none of these (a
            ``str`` included), or holds anything but text.
    """
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise InternalError(f"not a collection: {value!r}")
    return ", ".join(free_text(key) for key in sorted(map(plain_text, value)))


#: The configuration lines' fields.
CONFIG_FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "config_key": Field(
            PLACE_PATTERN,
            place_text,
            "<config-key>",
            "where the value sits: its table as the file spells it "
            "(`[tool.pitloom]`, `[tool:pitloom]` in setup.cfg, "
            "`[[tool.pitloom.creator]]`), then its key, the entry of an array "
            "counted from 0 and the entry's key, each when there is one "
            "(`[tool.pitloom.fragment] files entry 2 role`)",
        ),
        "destination": Field(
            _one_of(DESTINATIONS),
            plain_text,
            "<destination>",
            "where a moved key goes now, as pyproject.toml spells it: "
            + ", ".join(f"`{d}`" for d in DESTINATIONS),
        ),
        "entries": Field(
            r".+",
            keys_text,
            "<entries>",
            "the unknown keys, sorted, comma-separated, each as the file names "
            "it; in quotes, escaped, when it holds a control character",
            free=True,
        ),
        "expected": Field(
            _one_of(tuple(EXPECTED.values())),
            expected_text,
            "<expected>",
            "what the value must be: "
            + "; ".join(f"`{text}`" for text in EXPECTED.values()),
        ),
        "got": Field(
            FOUND_PATTERN,
            found_text,
            "<got>",
            "what was found, by its TOML type (`a string`, `an integer`, `a "
            "float`, `a boolean`, `a date-time`, `a date`, `a time`, `an "
            "array`, `a table`), `nothing` for a missing key, from a library "
            "caller `None` or `a value of type X`; a boolean, a number and a "
            "string are shown after the type (a string in quotes, a URL's "
            f"credentials masked, cut to {SHOWN_CHARS} characters with `...` "
            "after it, escaped), never a table or an array, and never a value "
            "that may be a credential",
        ),
        "tables": Field(
            rf"(?:{TABLE_PATTERN})(?: or (?:{TABLE_PATTERN}))*",
            tables_text,
            "<tables>",
            "the configuration tables that know a key, joined by `or`, as the "
            "file spells them",
        ),
    }
)
