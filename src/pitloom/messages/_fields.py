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
from pitloom.messages._model_limits import MODEL_LIMIT_REASONS


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


def _limit(value: object) -> str:
    return str(_whole(value))


def _str(value: object) -> str:
    """*value* when it is a ``str``.

    Raises:
        ValueError: It is not.
    """
    if not isinstance(value, str):
        raise ValueError(f"not text: {value!r}")
    return value


def _name(value: object) -> str:
    """A free text value: as it is when printable, else escaped."""
    return loggable(_str(value))


def _formats(value: object) -> str:
    """A list or tuple of format names, comma-separated; an empty one
    writes nothing, which the field's shape refuses.

    Raises:
        ValueError: It is neither (a ``str`` included), or holds anything
            but text.
    """
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"not a list of formats: {value!r}")
    return ", ".join(_str(item) for item in value)


#: A whole number in a bound-check reason (each ``%d`` of the table).
_NUMBER: Final = "(?:0|[1-9][0-9]*)"
#: The bound-check reasons as one pattern, each ``%d`` a whole number.
_REASONS: Final = "|".join(
    _NUMBER.join(re.escape(part) for part in text.split("%d"))
    for text in MODEL_LIMIT_REASONS
)


#: The keys an over-cap line names its input by: a file, a directory, a
#: metadata field (or table), a dataset, a marker or a requirement.
CAP_KEYS: Final = frozenset(
    {"DATASET", "DIR", "FIELD", "FILE", "MARKER", "REQUIREMENT"}
)
#: What a cap counts, singular.
CAP_UNITS: Final = frozenset(
    {
        "byte",
        "character",
        "dataset",
        "digit",
        "element",
        "entry",
        "header",
        "item",
        "label",
        "level",
        "marker",
        "opcode",
        "part",
        "unit",
    }
)
#: One word of a cap's name (``GGUF-header``, ``.npy-header``).
_CAP_WORD: Final = r"[.A-Za-z][-.A-Za-z0-9]*"

#: Every name a template may use.
FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "amount": Field(
            r"1 byte|(?:0|[2-9]|[1-9][0-9]+) bytes|[1-9][0-9]* (?:KiB|MiB|GiB)",
            _str,
            "<amount>",
            "a size in bytes, or in whole KiB, MiB or GiB (`512 MiB`)",
        ),
        "command": Field(
            r"[a-z][a-z-]*",
            _str,
            "<command>",
            "the git command that was stopped or failed (`clone`, `fetch`)",
        ),
        "count": Field(
            r"(?: \((?:[2-9]|[1-9][0-9]+) files\))?",
            _count,
            "<count>",
            "the number of files in brackets, `(N files)`, after a space when "
            "there are two or more; else nothing",
        ),
        "error": Field(
            r".+",
            _name,
            "<error>",
            "what the reader or the file system reported, on one line; in "
            "quotes, escaped, when it holds a control character",
            free=True,
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
        "formats": Field(
            r"[a-z][a-z0-9_]*(?:, [a-z][a-z0-9_]*)*",
            _formats,
            "<formats>",
            "model formats, comma-separated (`gguf, onnx`)",
        ),
        "key": Field(
            "|".join(sorted(CAP_KEYS)),
            _str,
            "<key>",
            "the key naming the input: `FILE`, `DIR`, `FIELD` (a metadata field "
            "or table), `DATASET`, `MARKER` or `REQUIREMENT`",
        ),
        "limit": Field(r"0|[1-9][0-9]*", _limit, "<limit>", "the cap, in its unit"),
        "module": Field(
            r"[a-z][a-z0-9_]*",
            _str,
            "<module>",
            "the Python module Pitloom imports for the step (`h5py`)",
        ),
        "name": Field(
            r".*",
            _name,
            "<name>",
            "the input as Pitloom names it (a path, a field, a dataset, the start "
            "of a requirement); in quotes, escaped, when it holds a control "
            "character",
            free=True,
        ),
        "oid": Field(
            r"[0-9a-f]{64}", str, "<oid>", "the SHA-256 the pointer states, in hex"
        ),
        "outcome": Field(
            r".+",
            _str,
            "<outcome>",
            "what Pitloom kept, and what it did not read or record",
            free=True,
        ),
        "path": Field(
            r"'[^']*'|\"[^\"]*\"|'(?:[^'\\]|\\.)*'",
            _path,
            "'<path>'",
            "a path in quotes",
        ),
        "purpose": Field(
            rf"{_CAP_WORD}(?: {_CAP_WORD}){{0,2}}",
            _str,
            "<cap>",
            "the cap's name; a setting's name when a setting sets it "
            "(`max-model-extract-bytes`)",
        ),
        "reason": Field(
            _REASONS,
            _str,
            "<reason>",
            "what the bound check found: a count the file cannot hold, a "
            "malformed ZIP central directory, or a GGUF version or ZIP archive "
            "it cannot check",
        ),
        "requirement": Field(
            r"pitloom\[[a-z][a-z0-9_-]*\]",
            _str,
            "<requirement>",
            "Pitloom with the extra that installs the library (`pitloom[gguf]`); "
            "`pitloom[ai]` installs every model reader",
        ),
        "size": Field(
            r"1 byte|(?:0|[2-9]|[1-9][0-9]+) bytes",
            _size,
            "<size>",
            "a size in bytes (`1 byte`, `N bytes`)",
        ),
        "unit": Field(
            "|".join(sorted(CAP_UNITS)),
            _str,
            "<unit>",
            "what the cap counts, singular (`byte`, `entry`, `level`)",
        ),
        "value": Field(
            r".*",
            _name,
            "<value>",
            "the value as the file states it (a tensor dimension: its Python "
            "repr, cut to 40 characters); in quotes, escaped, when it holds a "
            "control character",
            free=True,
        ),
    }
)

#: A name in a template.
PLACEHOLDER: Final = re.compile(r"%\(([a-z_]+)\)s")


def template_names(template: str) -> tuple[str, ...]:
    """The names *template* uses, in order.

    A field of a closed shape may stand twice (``header is not
    %(format)s`` after ``FORMAT=%(format)s``), printing the one value both
    times; a free one may not.

    Raises:
        ValueError: A name is not in :data:`FIELDS`, a free one is used
            twice, or a ``%`` is not part of a name.
    """
    names = tuple(PLACEHOLDER.findall(template))
    unknown = sorted(set(names) - set(FIELDS))
    if unknown:
        raise ValueError(f"{template!r}: unknown field {unknown[0]!r}")
    repeated = sorted({n for n in names if FIELDS[n].free and names.count(n) > 1})
    if repeated:
        raise ValueError(f"{template!r}: free field {repeated[0]!r} named twice")
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
        raise ValueError(
            f"{template!r} takes {sorted(set(names))}, not {sorted(values)}"
        )
    texts: dict[str, str] = {}
    for name in dict.fromkeys(names):
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
