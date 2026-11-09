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

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from pitloom.messages._field_writers import (
    bytes_text,
    count_text,
    failure_text,
    file_text,
    free_text,
    joined,
    number_text,
    path_text,
    plain_text,
)
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


#: A whole number in a bound-check reason (each ``%d`` of the table).
_NUMBER: Final = "(?:0|[1-9][0-9]*)"
#: The bound-check reasons as one pattern, each ``%d`` a whole number.
_REASONS: Final = "|".join(
    _NUMBER.join(re.escape(part) for part in text.split("%d"))
    for text in MODEL_LIMIT_REASONS
)


#: A G7 element as a ``field-not-recordable`` line names it.
_ELEMENT: Final = r"[a-z][a-z0-9-]* \((?:not recorded|written in [A-Za-z_]+)\)"
#: A model field as a ``model-field-unreadable`` line names it: a dotted
#: name, a note in brackets after it when it has one.
_MODEL_FIELD: Final = r"[a-z_][A-Za-z0-9_.]*(?: \([^()]+\))?"
#: One step of a Keras config key path (``layers[0]``).
_KEY_STEP: Final = r"[a-z_]+(?:\[(?:0|[1-9][0-9]*)\])?"

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

#: What a file was read for, or a directory listed for, as a
#: ``file-unreadable`` or ``dir-unlistable`` line says it after ``could not
#: read`` or ``could not list`` (and a ``json-malformed`` or JSON ``over-cap``
#: line after its condition): a closed table. A project setting that lists
#: the file is named by the ``field`` value instead.
READ_USES: Final = (
    "for dataset hashing",
    "for dependency pins",
    "for file discovery",
    "for file scanning",
    "for ID registry indexing",
    "for license files",
    "for the Croissant document",
    "for the dataset card",
    "for the Hugging Face dataset card",
    "for the model card",
    "for the model hash",
    "for the PyPI release metadata",
    "for the script hash",
    "for usage scanning",
)

#: The kinds of card whose YAML frontmatter Pitloom reads, as a
#: ``card-malformed`` line names one: a closed table.
CARD_KINDS: Final = ("model card", "dataset card", "Hugging Face dataset card")

#: Every name a template may use.
FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "amount": Field(
            r"1 byte|(?:0|[2-9]|[1-9][0-9]+) bytes|[1-9][0-9]* (?:KiB|MiB|GiB)",
            plain_text,
            "<amount>",
            "a size in bytes, or in whole KiB, MiB or GiB (`512 MiB`)",
        ),
        "card": Field(
            "|".join(re.escape(kind) for kind in CARD_KINDS),
            plain_text,
            "<card>",
            "the kind of card: " + ", ".join(f"`{kind}`" for kind in CARD_KINDS),
        ),
        "command": Field(
            r"[a-z][a-z-]*",
            plain_text,
            "<command>",
            "the git command that was stopped or failed (`clone`, `fetch`)",
        ),
        "count": Field(
            r"(?: \((?:[2-9]|[1-9][0-9]+) files\))?",
            count_text,
            "<count>",
            "the number of files in brackets, `(N files)`, after a space when "
            "there are two or more; else nothing",
        ),
        "dir": Field(
            r".+",
            file_text,
            "<dir>",
            "a directory as Pitloom names it; in quotes, escaped, when it holds "
            "a control character",
            free=True,
        ),
        "elements": Field(
            rf"{_ELEMENT}(?:, {_ELEMENT})*",
            joined,
            "<elements>",
            "G7 elements, comma-separated, each with where its value is written "
            "(`model-architecture (written in ai_typeOfModel)`) or `(not recorded)`",
        ),
        "entry": Field(
            r".+",
            free_text,
            "<entry>",
            "an archive member or a metadata key, as the file names it; in "
            "quotes, escaped, when it holds a control character",
            free=True,
        ),
        "error": Field(
            r".+",
            free_text,
            "<error>",
            "what the reader or the file system reported, on one line; in "
            "quotes, escaped, when it holds a control character",
            free=True,
        ),
        "failure": Field(
            r".+",
            failure_text,
            "<failure>",
            "what the operating system reported (`Permission denied`), never "
            "the path it names, or what the decoder or reader reported; on one "
            "line, in quotes, escaped, when it holds a control character",
            free=True,
        ),
        "field": Field(
            r".+",
            free_text,
            "<field>",
            "the project setting that lists the file (`project.readme`, "
            "`tool.setuptools.dynamic.dependencies`, `setup.cfg "
            "metadata.long_description`); in quotes, escaped, when it holds a "
            "control character",
            free=True,
        ),
        "fields": Field(
            rf"{_MODEL_FIELD}(?:, {_MODEL_FIELD})*",
            joined,
            "<fields>",
            "the model fields not recorded, or recorded weaker, comma-separated, "
            "each with a note in brackets when it has one (`type_of_model`, "
            "`properties.tags (kept as raw string)`)",
        ),
        "file": Field(
            r".+",
            file_text,
            "<file>",
            "a file as Pitloom names it (its path, or a remote document's URL "
            "or Hub dataset id); in quotes, escaped, when it holds a control "
            "character",
            free=True,
        ),
        "files": Field(
            r".+",
            free_text,
            "<files>",
            "file names, comma-separated, `and N more` after the last one "
            "shown; a name in quotes, escaped, when it holds a control character",
            free=True,
        ),
        "format": Field(
            r"[a-z][a-z0-9_]*", str, "<format>", "the model format (`gguf`)"
        ),
        "formats": Field(
            r"[a-z][a-z0-9_]*(?:, [a-z][a-z0-9_]*)*",
            joined,
            "<formats>",
            "model formats, comma-separated (`gguf, onnx`)",
        ),
        "key": Field(
            "|".join(sorted(CAP_KEYS)),
            plain_text,
            "<key>",
            "the key naming the input: `FILE`, `DIR`, `FIELD` (a metadata field "
            "or table), `DATASET`, `MARKER` or `REQUIREMENT`",
        ),
        "limit": Field(
            r"0|[1-9][0-9]*", number_text, "<limit>", "the cap, in its unit"
        ),
        "module": Field(
            r"[a-z][a-z0-9_]*",
            plain_text,
            "<module>",
            "the Python module Pitloom imports for the step (`h5py`)",
        ),
        "name": Field(
            r".*",
            free_text,
            "<name>",
            "the input as Pitloom names it (a path, a field, a dataset, the start "
            "of a requirement); in quotes, escaped, when it holds a control "
            "character",
            free=True,
        ),
        "number": Field(
            r"0|[1-9][0-9]*",
            number_text,
            "<number>",
            "a whole number: a count, or a length in characters",
        ),
        "oid": Field(
            r"[0-9a-f]{64}", str, "<oid>", "the SHA-256 the pointer states, in hex"
        ),
        "outcome": Field(
            r".+",
            plain_text,
            "<outcome>",
            "what Pitloom kept, and what it did not read or record",
            free=True,
        ),
        "part": Field(
            rf"{_KEY_STEP}(?:\.{_KEY_STEP})*",
            plain_text,
            "<part>",
            "the part of a Keras or HDF5 model that was not read: a root "
            "attribute (`model_config`) or a key path in a config "
            "(`training_config.optimizer`, `layers[0].config`)",
        ),
        "path": Field(
            r"'[^']*'|\"[^\"]*\"|'(?:[^'\\]|\\.)*'",
            path_text,
            "'<path>'",
            "a path in quotes",
        ),
        "purpose": Field(
            rf"{_CAP_WORD}(?: {_CAP_WORD}){{0,2}}",
            plain_text,
            "<cap>",
            "the cap's name; a setting's name when a setting sets it "
            "(`max-model-extract-bytes`)",
        ),
        "python": Field(
            r"[0-9]+\.[0-9]+",
            plain_text,
            "<x.y>",
            "the Python version Pitloom runs on, as `3.10`: the grammar a file "
            "was read as",
        ),
        "reason": Field(
            _REASONS,
            plain_text,
            "<reason>",
            "what the bound check found: a count the file cannot hold, a "
            "malformed ZIP central directory, or a GGUF version or ZIP archive "
            "it cannot check",
        ),
        "requirement": Field(
            r"pitloom\[[a-z][a-z0-9_-]*\]",
            plain_text,
            "<requirement>",
            "Pitloom with the extra that installs the library (`pitloom[gguf]`); "
            "`pitloom[ai]` installs every model reader",
        ),
        "size": Field(
            r"1 byte|(?:0|[2-9]|[1-9][0-9]+) bytes",
            bytes_text,
            "<size>",
            "a size in bytes (`1 byte`, `N bytes`)",
        ),
        "unit": Field(
            "|".join(sorted(CAP_UNITS)),
            plain_text,
            "<unit>",
            "what the cap counts, singular (`byte`, `entry`, `level`)",
        ),
        "use": Field(
            "|".join(re.escape(use) for use in READ_USES),
            plain_text,
            "<use>",
            "what the file was read for, or the directory listed for: "
            + ", ".join(f"`{use}`" for use in READ_USES),
        ),
        "value": Field(
            r".*",
            free_text,
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
