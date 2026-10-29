# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values a catalogued line names, ``%(name)s`` in its template: how the
catalogue writes each one, and the shape the written text always has, which
is what a reader trusts a line by.

See also: :mod:`pitloom.messages._types` (the templates) and
:mod:`pitloom.messages._lines` (reading a line back).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from pitloom.core.quote_source import quote_source
from pitloom.logging_config import loggable


@dataclass(frozen=True)
class Field:
    """One value a template names."""

    #: The text the written value always matches (a regular expression).
    pattern: str
    #: Turns the caller's value into the text printed.
    write: Callable[[object], str]
    #: How the reference shows the value in a line.
    shown: str
    #: What the value is, for the reference.
    meaning: str
    #: Whether the value can be any text (a file name), so a template may not
    #: start with it or put it beside another field: it would take in what
    #: lies next to it.
    free: bool = False


def size_text(size: int) -> str:
    """*size* as every message and comment states it: ``1 byte``, ``N bytes``."""
    return f"{size} byte" if size == 1 else f"{size} bytes"


def _path_text(value: object) -> str:
    """*value*, a ``str`` or :class:`os.PathLike` path, as text.

    Raises:
        ValueError: It is neither, or names a path in bytes.
    """
    text = os.fspath(value) if isinstance(value, os.PathLike) else value
    if not isinstance(text, str):
        raise ValueError(f"not a path: {value!r}")
    return text


def _file(value: object) -> str:
    """A ``FILE=`` value: the path as it is when printable, else escaped."""
    return loggable(_path_text(value))


def _path(value: object) -> str:
    """A path in quotes, as every message quotes one."""
    return quote_source(_path_text(value))


def _count(value: object) -> str:
    """`` (N files)`` for two files or more, else nothing."""
    number = _whole(value)
    return f" ({number} files)" if number > 1 else ""


def _size(value: object) -> str:
    return size_text(_whole(value))


def _whole(value: object) -> int:
    """*value* when it is an ``int`` of zero or more (a ``bool`` is not).

    Raises:
        ValueError: It is not.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"not a whole number: {value!r}")
    return value


#: Every name a template may use.
FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "count": Field(
            r"(?: \((?:[2-9]|[1-9][0-9]+) files\))?",
            _count,
            "<count>",
            "the number of files in brackets, `(N files)`, after a space when "
            "there are two or more; else nothing",
        ),
        "file": Field(
            r".+",
            _file,
            "<file>",
            "a path as Pitloom names it; in quotes, escaped, when it holds a "
            "control character",
            free=True,
        ),
        "format": Field(
            r"[a-z][a-z0-9_]*", str, "<format>", "the model format (`gguf`)"
        ),
        "oid": Field(
            r"[0-9a-f]{64}", str, "<oid>", "the SHA-256 the pointer states, in hex"
        ),
        "path": Field(
            r"'[^']*'|\"[^\"]*\"|'(?:[^'\\]|\\.)*'",
            _path,
            "'<path>'",
            "a path in quotes",
        ),
        "size": Field(
            r"1 byte|(?:0|[2-9]|[1-9][0-9]+) bytes",
            _size,
            "<size>",
            "a size the pointer states (`1 byte`, `N bytes`)",
        ),
    }
)

#: A name in a template.
PLACEHOLDER: Final = re.compile(r"%\(([a-z_]+)\)s")


def template_names(template: str) -> tuple[str, ...]:
    """The names *template* uses, in order.

    Raises:
        ValueError: A name is not in :data:`FIELDS`, is used twice, or a
            ``%`` is not part of a name.
    """
    names = tuple(PLACEHOLDER.findall(template))
    unknown = sorted(set(names) - set(FIELDS))
    if unknown:
        raise ValueError(f"{template!r}: unknown field {unknown[0]!r}")
    if len(set(names)) != len(names):
        raise ValueError(f"{template!r}: a field named twice")
    if "%" in PLACEHOLDER.sub("", template):
        raise ValueError(f"{template!r}: a '%' that names no field")
    return names


def template_pattern(template: str) -> str:
    """*template* as a regular expression: its text literal, each name its
    field's :attr:`~Field.pattern`."""
    parts: list[str] = []
    end = 0
    for found in PLACEHOLDER.finditer(template):
        parts.append(re.escape(template[end : found.start()]))
        parts.append(f"(?:{FIELDS[found.group(1)].pattern})")
        end = found.end()
    parts.append(re.escape(template[end:]))
    return "".join(parts)


def written(template: str, values: Mapping[str, object]) -> dict[str, str]:
    """Each value of *values* written by its field, for *template*.

    Raises:
        ValueError: *values* names other fields than *template*, or a
            written value does not have its field's shape.
    """
    names = template_names(template)
    if set(values) != set(names):
        raise ValueError(f"{template!r} takes {sorted(names)}, not {sorted(values)}")
    texts: dict[str, str] = {}
    for name in names:
        text = FIELDS[name].write(values[name])
        if re.fullmatch(FIELDS[name].pattern, text) is None:
            raise ValueError(f"{name}={text!r} is not a {name}")
        texts[name] = text
    return texts


def shown(template: str) -> str:
    """*template* as the reference shows it, each name its field's
    :attr:`~Field.shown` (``<file>``)."""
    return PLACEHOLDER.sub(lambda found: FIELDS[found.group(1)].shown, template)


def render(template: str, values: Mapping[str, object]) -> str:
    """*template* with each name replaced by its value, as written by its
    field (:func:`written`)."""
    texts = written(template, values)
    return PLACEHOLDER.sub(lambda found: texts[found.group(1)], template)
