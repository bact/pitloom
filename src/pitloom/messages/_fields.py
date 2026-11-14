# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values a catalogued line names, ``%(name)s`` in its template: how the
catalogue writes each one, and the shape the written text always has, which
is what a reader trusts a line by.

See also: :mod:`pitloom.messages._field_tables` (the closed tables),
:mod:`pitloom.messages._types` (the templates),
:mod:`pitloom.messages._lines` (reading a line back), and
:mod:`pitloom.messages._templates` (rendering a template from its fields).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from pitloom.messages._field_tables import (
    CAP_KEYS,
    CAP_UNITS,
    CAP_WORD,
    CARD_KINDS,
    CONFIG_TABLES,
    ELEMENT,
    INPUT_KINDS,
    KEY_STEP,
    LOOM_COMMANDS,
    MODEL_FIELD,
    READ_USES,
    REASONS,
    REGISTRY_PARTS,
    SETTING,
)
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


#: A path in quotes, as :func:`~pitloom.messages._field_writers.path_text`
#: writes it.
QUOTED_PATH: Final = r"'[^']*'|\"[^\"]*\"|'(?:[^'\\]|\\.)*'"

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
        "arity": Field(
            r"(?:one|at most one|at least one|[1-9][0-9]*) arguments?",
            plain_text,
            "<arity>",
            "how many values argparse expected after the option (`one "
            "argument`, `2 arguments`, `at least one argument`)",
        ),
        "card": Field(
            "|".join(re.escape(kind) for kind in CARD_KINDS),
            plain_text,
            "<card>",
            "the kind of card: " + ", ".join(f"`{kind}`" for kind in CARD_KINDS),
        ),
        "subcommand": Field(
            "(?:" + "|".join(re.escape(c) for c in LOOM_COMMANDS) + ")",
            plain_text,
            "<subcommand>",
            "the `loom` command that failed (`generate`, `fragment validate`)",
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
        "element_type": Field(
            r".+",
            free_text,
            "<type>",
            "an element type as the ID registry file names it (`software_File`), "
            "or its Python repr when it is not a type name the file can hold; "
            "in quotes, escaped, when it holds a control character",
            free=True,
        ),
        "elements": Field(
            rf"{ELEMENT}(?:, {ELEMENT})*",
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
            rf"{MODEL_FIELD}(?:, {MODEL_FIELD})*",
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
        "input": Field(
            "|".join(re.escape(kind) for kind in INPUT_KINDS),
            plain_text,
            "<input>",
            "what the path was named as: "
            + ", ".join(f"`{kind}`" for kind in INPUT_KINDS),
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
        "namespace": Field(
            r".+",
            free_text,
            "<namespace>",
            "a document namespace IRI, as an ID registry file states it; in "
            "quotes, escaped, when it holds a control character",
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
        "option": Field(
            r"\S+",
            plain_text,
            "<option>",
            "a command-line option as the command names it (`--allow-build`, "
            "`-o/--output`, `--pretty/--no-pretty`), a positional argument as "
            "argparse names it (`command`), or a library parameter "
            "(`project_metadata`)",
        ),
        "other": Field(
            r"\S+",
            plain_text,
            "<other>",
            "the option given before, which the one named first cannot be "
            "given with, as argparse names it (`--pretty`)",
        ),
        "outcome": Field(
            r".+",
            plain_text,
            "<outcome>",
            "what Pitloom kept, and what it did not read or record",
            free=True,
        ),
        "part": Field(
            rf"{KEY_STEP}(?:\.{KEY_STEP})*",
            plain_text,
            "<part>",
            "the part of a Keras or HDF5 model that was not read: a root "
            "attribute (`model_config`) or a key path in a config "
            "(`training_config.optimizer`, `layers[0].config`)",
        ),
        "path": Field(
            QUOTED_PATH,
            path_text,
            "'<path>'",
            "a path in quotes",
        ),
        "purpose": Field(
            rf"{CAP_WORD}(?: {CAP_WORD}){{0,2}}",
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
            REASONS,
            plain_text,
            "<reason>",
            "what the bound check found: a count the file cannot hold, a "
            "malformed ZIP central directory, or a GGUF version or ZIP archive "
            "it cannot check",
        ),
        "refusal": Field(
            r"(?!expected |not allowed with ).+",
            free_text,
            "<refusal>",
            "argparse's reason for refusing the value, on one line (`invalid "
            "choice: ...`); never a missing value (`expected ...`) or a "
            "conflict (`not allowed with ...`); in quotes, escaped, when it "
            "holds a control character",
            free=True,
        ),
        "registry_part": Field(
            "|".join(re.escape(part) for part in REGISTRY_PARTS),
            plain_text,
            "<what>",
            "what of an element the ID registry cannot hold: "
            + ", ".join(f"`{part}`" for part in REGISTRY_PARTS),
        ),
        "requirement": Field(
            r"pitloom\[[a-z][a-z0-9_-]*\]",
            plain_text,
            "<requirement>",
            "Pitloom with the extra that installs the library (`pitloom[gguf]`); "
            "`pitloom[ai]` installs every model reader",
        ),
        "root": Field(
            QUOTED_PATH,
            path_text,
            "'<root>'",
            "the directory a path is checked against (--project-dir, a "
            "project root), in quotes like the path beside it",
        ),
        "seconds": Field(
            r"0|[1-9][0-9]*",
            number_text,
            "<seconds>",
            "the time allowed, in whole seconds",
        ),
        "settings": Field(
            rf"{SETTING}(?:, {SETTING})*",
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
        "table": Field(
            "|".join(re.escape(table) for table in CONFIG_TABLES),
            plain_text,
            "<table>",
            "the configuration table: "
            + " or ".join(f"`{table}`" for table in CONFIG_TABLES),
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
        "when": Field(
            r"(?:for|in|when|with|without) .+",
            free_text,
            "<when>",
            "the case the option has no effect in, or cannot be used in "
            "(`without --allow-build`, `for a remote repository (...)`, `when "
            "embedding multiple wheels`)",
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
