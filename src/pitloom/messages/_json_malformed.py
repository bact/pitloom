# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``json-malformed``: a JSON document Pitloom was given to read does not
parse, or its top level is no object. ``ERROR`` only: the read raises.

See also: :func:`pitloom.extract._extract_utils.fetch_json` (the reader).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: A document the JSON parser refused.
NOT_JSON_LINE: Final = Line(
    level="ERROR", template="FILE=%(file)s: not valid JSON %(use)s; %(failure)s"
)
#: A document whose top level is an array, a string, a number or a literal.
NOT_OBJECT_LINE: Final = Line(
    level="ERROR", template="FILE=%(file)s: not a JSON object %(use)s"
)

JSON_MALFORMED: Final = Message(
    code="json-malformed",
    condition="malformed",
    lines=(NOT_JSON_LINE, NOT_OBJECT_LINE),
    summary="A JSON document Pitloom was given to read (a Croissant file) "
    "does not parse, or its top level is not an object.",
    did="Read nothing of it: the call raises ValueError carrying the code, "
    "and the dataset declaration (loom.add_dataset with croissant=, or "
    "read_croissant) fails.",
    effect="not-written",
    actor="user",
    advice="Tell the user which document is not valid JSON, or not a JSON "
    "object, and what the parser reported, as the line says. They fix or "
    "replace it and run again. Do not edit or replace the document for them; "
    "ask first, and with nobody to ask, report it only.",
    subject_key="FILE",
    since="0.23.0",
)

ENTRIES: Final = (JSON_MALFORMED,)
