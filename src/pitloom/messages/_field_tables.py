# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The closed value tables and sub-patterns the catalogue's fields are built
from: the command paths a frame names, the kinds of input and card, what a
file is read for, the cap keys and units, the lock keys, source kinds and
value types, and the pattern pieces a field shares.

See also: :mod:`pitloom.messages._fields` (the fields built from them).
"""

from __future__ import annotations

import re
from typing import Final

from pitloom.messages._model_limits import MODEL_LIMIT_REASONS

#: The command paths a CLI line's frame names (``loom <path>: ``): every
#: subcommand and nested subcommand of the parser. A drift test holds the
#: tuple and the parser's ``prog`` values together
#: (``tests/messages/test_frames.py``).
LOOM_COMMANDS: Final[tuple[str, ...]] = (
    "embed-wheel",
    "enrich",
    "env",
    "fragment",
    "fragment list",
    "fragment validate",
    "generate",
    "id",
    "id generate",
    "id import",
    "merge",
    "model",
    "project",
    "validate-wheel",
    "verify-wheel",
    "wheel",
)

#: A whole number in a bound-check reason (each ``%d`` of the table).
NUMBER: Final = "(?:0|[1-9][0-9]*)"
#: The bound-check reasons as one pattern, each ``%d`` a whole number.
REASONS: Final = "|".join(
    NUMBER.join(re.escape(part) for part in text.split("%d"))
    for text in MODEL_LIMIT_REASONS
)


#: A G7 element as a ``field-not-recordable`` line names it.
ELEMENT: Final = r"[a-z][a-z0-9-]* \((?:not recorded|written in [A-Za-z_]+)\)"
#: A model field as a ``model-field-unreadable`` line names it: a dotted
#: name, a note in brackets after it when it has one.
MODEL_FIELD: Final = r"[a-z_][A-Za-z0-9_.]*(?: \([^()]+\))?"
#: A build setting, as its file names it (``tool.pdm.build.custom-hook``).
SETTING: Final = r"[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)*"
#: One step of a Keras config key path (``layers[0]``).
KEY_STEP: Final = r"[a-z_]+(?:\[(?:0|[1-9][0-9]*)\])?"

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
CAP_WORD: Final = r"[.A-Za-z][-.A-Za-z0-9]*"

#: What an SBOM given to read (to embed, to import into an ID registry) is
#: read for, as its lines say it: one of :data:`READ_USES`.
SBOM_USE: Final = "for the SBOM"
#: What an ID registry file is read for, as its ``file-unreadable`` and
#: ``json-malformed`` lines say it: one of :data:`READ_USES`.
REGISTRY_USE: Final = "for the ID registry"
#: The use of a path named for Pitloom to read that the system will not let
#: it look at (:func:`~pitloom.messages.targets.input_exists`): one of
#: :data:`READ_USES`.
INPUT_USE: Final = "for the input check"

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
    INPUT_USE,
    "for license files",
    "for the Croissant document",
    "for the dataset card",
    "for the Hugging Face dataset card",
    REGISTRY_USE,
    "for the model card",
    "for the model hash",
    "for the PyPI release metadata",
    SBOM_USE,
    "for the script hash",
    "for usage scanning",
)

#: The kinds of card whose YAML frontmatter Pitloom reads, as a
#: ``card-malformed`` line names one: a closed table.
CARD_KINDS: Final = ("model card", "dataset card", "Hugging Face dataset card")

#: What an ``input-not-found`` line names the missing path as: a closed table.
INPUT_KINDS: Final = (
    "config file",
    "fragments directory",
    "ID registry file",
    "PATH",
    "project directory",
    "project path",
    "pyproject.toml",
    "SBOM file",
    "sdist archive",
    "setup.cfg",
    "setup.py",
    "wheel file",
)

#: The type of a value a lock file holds, as a lock line names it
#: (``type(value).__name__``): every type ``tomllib`` and ``json`` load.
VALUE_TYPES: Final = (
    "bool",
    "date",
    "datetime",
    "dict",
    "float",
    "int",
    "list",
    "NoneType",
    "str",
    "time",
)

#: The lock-file keys a lock line names: the keys the readers of
#: :mod:`pitloom.extract.lock` check, a format marker inside a table dotted
#: (``metadata.lock-version``). A drift test holds each in the readers.
LOCK_KEYS: Final = (
    "_meta.pipfile-spec",
    "category",
    "created-by",
    "default",
    "default-groups",
    "dependencies",
    "extra",
    "extras",
    "groups",
    "lock-version",
    "marker",
    "metadata.lock-version",
    "metadata.lock_version",
    "name",
    "optional-dependencies",
    "package",
    "packages",
    "version",
)

#: The kinds of source that give no registry version to pin, as a lock or
#: Poetry line names one: the union of the readers' non-registry source keys
#: and Poetry's local sources. A drift test holds it equal to them.
SOURCE_KINDS: Final = (
    "archive",
    "bzr",
    "directory",
    "editable",
    "file",
    "git",
    "hg",
    "path",
    "svn",
    "url",
    "vcs",
    "virtual",
)

#: The configuration tables a line names (``set id-registry in <table>``).
CONFIG_TABLES: Final = ("[tool.pitloom]", "[tool:pitloom]")

#: What a line about a name the ID registry cannot hold names it as: a closed
#: table (an element's key, its name, its type name, or its ``spdxId``).
REGISTRY_PARTS: Final = (
    "key",
    "name",
    "project_root",
    "sha256",
    "spdxId",
    "type name",
)

#: What an element is, as a line about its ID registry lookup names it
#: (``model 'm'``): a closed table.
ELEMENT_KINDS: Final = ("dataset", "dataset package", "entity", "file", "model")

#: Why an element is keyed by its name, not by its path (or files by their
#: path as read), as a line about its ID registry key says it: a closed
#: table. These texts are the reasons' one source; the code that decides
#: imports them.
KEY_NOT_FOUND: Final = "not found"
KEY_OUTSIDE_ROOT: Final = "outside the project root"
KEY_NOT_A_FILE: Final = "not a regular file"
KEY_MODEL_PIN: Final = "used only by a model with no file"
#: ``id import``: a dataset name found neither below the root nor from the
#: current directory (a loom script declared it relative to its own one).
KEY_IMPORT_NOT_FOUND: Final = (
    "not found: declare paths relative to the registry root "
    "(id import --project-dir) or run id import from the directory the "
    "script ran in"
)
KEY_PROJECT_OUTSIDE: Final = "the project is outside the registry's root"
KEY_PATH_OUTSIDE: Final = "their path is outside the registry's root"
KEY_PATH_OUTSIDE_ARCHIVE: Final = "their path leads outside the archive's project"
KEY_REASONS: Final = (
    KEY_NOT_FOUND,
    KEY_OUTSIDE_ROOT,
    KEY_NOT_A_FILE,
    KEY_MODEL_PIN,
    KEY_IMPORT_NOT_FOUND,
    KEY_PROJECT_OUTSIDE,
    KEY_PATH_OUTSIDE,
    KEY_PATH_OUTSIDE_ARCHIVE,
)
