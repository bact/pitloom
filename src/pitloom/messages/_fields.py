# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values a catalogued line names, ``%(name)s`` in its template: how the
catalogue writes each one, and the shape the written text always has, which
is what a reader trusts a line by.

See also: :mod:`pitloom.messages._types` (the templates),
:mod:`pitloom.messages._lines` (reading a line back), and
:mod:`pitloom.messages._templates` (rendering a template from its fields).
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
#: A build setting, as its file names it (``tool.pdm.build.custom-hook``).
_SETTING: Final = r"[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)*"
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
        "second",
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
        "answered": Field(
            r".+",
            free_text,
            "<answered>",
            "the project name PyPI answered for, as its answer gives it; in quotes, "
            "escaped, when it holds a control character",
            free=True,
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
        "declared": Field(
            r"[0-9a-f]{64}", str, "<declared>", "the SHA-256 a source declares, in hex"
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
        "hosts": Field(
            r".+",
            free_text,
            "<hosts>",
            "the hosts Pitloom fetches PyPI files from, comma-separated "
            "(`files.pythonhosted.org`)",
            free=True,
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
        "measured": Field(
            r"[0-9a-f]{64}", str, "<sha256>", "the SHA-256 of the bytes read, in hex"
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
        "seconds": Field(
            r"0|[1-9][0-9]*",
            number_text,
            "<seconds>",
            "the time allowed, in whole seconds",
        ),
        "settings": Field(
            rf"{_SETTING}(?:, {_SETTING})*",
            joined,
            "<settings>",
            "the build settings left out, comma-separated, as the file names "
            "them (`tool.hatch.metadata.hooks`, `tool.setuptools.cmdclass`, "
            "`metadata.version`)",
        ),
        "size": Field(
            r"1 byte|(?:0|[2-9]|[1-9][0-9]+) bytes",
            bytes_text,
            "<size>",
            "a size in bytes (`1 byte`, `N bytes`)",
        ),
        "source": Field(
            r".+",
            free_text,
            "<source>",
            "what declared a digest (`the PyPI JSON API`)",
            free=True,
        ),
        "target": Field(
            r".+",
            free_text,
            "<target>",
            "a URL a redirect or a file points to, as given; in quotes, escaped, when "
            "it holds a control character",
            free=True,
        ),
        "unit": Field(
            "|".join(sorted(CAP_UNITS)),
            plain_text,
            "<unit>",
            "what the cap counts, singular (`byte`, `entry`, `level`)",
        ),
        "url": Field(
            r".+",
            free_text,
            "<url>",
            "a URL as given (a PyPI page URL, a request URL, or huggingface_hub's "
            "HF_ENDPOINT); in quotes, escaped, when it holds a control character",
            free=True,
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
        "version": Field(
            r".+",
            free_text,
            "<version>",
            "a release version as the URL or PyPI gives it; in quotes, escaped, when "
            "it holds a control character",
            free=True,
        ),
        "why": Field(
            r".+",
            free_text,
            "<why>",
            "why a redirect or an HF_ENDPOINT was refused, a file skipped, or a "
            "release yanked (`no reason given` when PyPI gives none); on one line, "
            "in quotes, escaped, when it holds a control character",
            free=True,
        ),
    }
)
