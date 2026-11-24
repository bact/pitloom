# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values only the author lines name: a free-text author field (or a
few of them), the key it was read from, and two counts.

An author field is attacker text (a wheel's ``METADATA``, an installed
dependency's record, PyPI's JSON): the ``authors`` writer masks a URL's
credentials, cuts and escapes each field itself
(:func:`~pitloom.logging_config.excerpt`), so no call site can forget to.

See also: :mod:`pitloom.messages._fields` (every field, these included)
and :mod:`pitloom.messages._authors` (the lines).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Final

from pitloom.logging_config import EXCERPT_CHARS, excerpt
from pitloom.messages._field_type import Field
from pitloom.messages._field_writers import plain_text, whole

#: The fields an ``authors`` value shows before ``...``.
SHOWN_FIELDS: Final = 3

#: Every key an author field is named by, as the lines spell them: a core
#: metadata field (or a dependency record's) in upper case, ``-`` as ``_``.
#: A project's own lines name only the first two
#: (:data:`pitloom.extract.authors.AUTHOR_KEYS`); a dependency's may name the
#: ``MAINTAINER`` pair too.
AUTHOR_FIELD_KEYS: Final = ("AUTHOR", "AUTHOR_EMAIL", "MAINTAINER", "MAINTAINER_EMAIL")


def authors_text(value: object) -> str:
    """One author field (a ``str``, or a list or tuple of one) as
    :func:`~pitloom.logging_config.excerpt` shows it: on one line, masked,
    cut to :data:`~pitloom.logging_config.EXCERPT_CHARS` characters, in
    quotes, escaped; several as ``[a, b, c, ...]``, the first
    :data:`SHOWN_FIELDS`, then ``...`` when there are more.

    Raises:
        ValueError: It is none of these, empty, or holds anything but text.
    """
    fields = [value] if isinstance(value, str) else value
    if not isinstance(fields, (list, tuple)) or not fields:
        raise ValueError(f"not author fields: {value!r}")
    texts = [excerpt(plain_text(field)) for field in fields]
    if len(texts) == 1:
        return texts[0]
    shown = texts[:SHOWN_FIELDS] + (["..."] if len(texts) > SHOWN_FIELDS else [])
    return f"[{', '.join(shown)}]"


def author_key_text(value: object) -> str:
    """One of :data:`AUTHOR_FIELD_KEYS`.

    Raises:
        ValueError: It is not.
    """
    if value not in AUTHOR_FIELD_KEYS:
        raise ValueError(f"not an author key: {value!r}")
    return plain_text(value)


def _counted(unit: str, units: str) -> tuple[str, Callable[[object], str]]:
    """The pattern and writer of a count of *unit* (``1 entry``) or
    *units* (``2 entries``): a whole number of at least 1."""

    def write(value: object) -> str:
        number = whole(value)
        if number < 1:
            raise ValueError(f"not a count of {units}: {value!r}")
        return f"{number} {unit if number == 1 else units}"

    pattern = rf"1 {re.escape(unit)}|(?:[2-9]|[1-9][0-9]+) {re.escape(units)}"
    return pattern, write


_ENTRIES_PATTERN, _entries_text = _counted("entry", "entries")
_DEPENDENCIES_PATTERN, _dependencies_text = _counted("dependency", "dependencies")

#: How an author field is shown.
_SHOWN_AUTHORS: Final = (
    f"on one line, a URL's credentials masked, cut to {EXCERPT_CHARS} "
    "characters (`...` after it when cut), in quotes, escaped when it holds "
    "a control character"
)

#: The author lines' fields.
AUTHOR_FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "authors": Field(
            r".+",
            authors_text,
            "<authors>",
            f"a free-text author field as read, {_SHOWN_AUTHORS}; several "
            f"fields as `[a, b, c, ...]`, the first {SHOWN_FIELDS} shown",
            free=True,
        ),
        "author_key": Field(
            "|".join(AUTHOR_FIELD_KEYS),
            author_key_text,
            "<author-key>",
            "the dependency's field the authors were read from: "
            + ", ".join(f"`{key}`" for key in AUTHOR_FIELD_KEYS),
        ),
        "entry_count": Field(
            _ENTRIES_PATTERN,
            _entries_text,
            "<entry-count>",
            "how many entries, `1 entry` or `N entries`",
        ),
        "dependency_count": Field(
            _DEPENDENCIES_PATTERN,
            _dependencies_text,
            "<dependency-count>",
            "how many dependencies, `1 dependency` or `N dependencies`",
        ),
    }
)
