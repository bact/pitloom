# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The closed value tables and sub-patterns the catalogue's fields are built
from: the command paths a frame names, the kinds of input and card, what a
file is read for, the cap keys and units, and the pattern pieces a field
shares.

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
    "project directory",
    "project path",
    "pyproject.toml",
    "SBOM file",
    "sdist archive",
    "setup.cfg",
    "setup.py",
    "wheel file",
)

#: The configuration tables a line names (``set id-registry in <table>``).
CONFIG_TABLES: Final = ("[tool.pitloom]", "[tool:pitloom]")
