# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Python file the usage scan could not parse, and the model it names:
``usage-unparseable`` and its variant ``usage-unparseable/mention``.

The scan reads the syntax tree of a file that holds a model's file name. A
file that cannot be parsed gives no usage relationship, because the text alone
(a comment, a message, a docstring) does not say a file is used. It is said
once as a ``WARNING:``, and once per model its text names as an ``INFO:``.

See also: :mod:`pitloom.extract.scanner` (where they are said) and
:mod:`pitloom.messages._file_unreadable` (a file that could not be read at
all).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: The end of every advice an agent relays without acting on it.
_ASK: Final = "ask first, and with nobody to ask, report it only."

USAGE_UNPARSEABLE: Final = Message(
    code="usage-unparseable",
    condition="unparseable",
    lines=(
        Line(
            level="WARNING",
            template="FILE=%(file)s: could not parse as Python %(python)s for "
            "usage scanning; %(failure)s",
        ),
    ),
    summary="A Python file that names an AI model file could not be parsed as "
    "Python of the version Pitloom runs on: it has a syntax error, it uses "
    "syntax a newer Python added (the line names this Python's version), it "
    "holds a null byte, or it nests too deeply to read.",
    did="Recorded no usage relationship from it, for any model: the file name "
    "in its text is not a use. The model is listed as before, and the "
    "usage-unparseable/mention line says which model each such file names.",
    effect="thinner",
    actor="user",
    advice="Tell the user which file could not be parsed and why, as the line "
    "says. If the file is valid for a newer Python, they run Pitloom on that "
    "Python; if it is broken, they fix it, or leave it out of the project; "
    "then they generate again. A file that is not meant to be Python (a "
    "template, a Python 2 script) needs nothing. Do not edit the file or "
    f"change the Python for them; {_ASK}",
    subject_key="FILE",
    since="0.22.1",
)

USAGE_UNPARSEABLE_MENTION: Final = Message(
    code="usage-unparseable/mention",
    condition="unparseable",
    lines=(
        Line(
            level="INFO",
            template="FILE=%(file)s MODEL=%(name)s: model file name found; no "
            "usage relationship recorded",
        ),
    ),
    summary="The text of a Python file that could not be parsed names an AI "
    "model file: it may use it, but only a parsed file says how.",
    did="Recorded no relationship between the file and the model. One line "
    "per file and model file name.",
    effect="thinner",
    actor="none",
    advice="Nothing to do on its own: the usage-unparseable warning for the "
    "same file says what stopped the parse.",
    subject_key="FILE",
    since="0.22.1",
)

ENTRIES: Final = (USAGE_UNPARSEABLE, USAGE_UNPARSEABLE_MENTION)
