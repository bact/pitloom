# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``text-unsafe``: the display text of the elements a model or a loom
dataset brings into the SBOM held invisible or bidi control characters,
written as ``\\uXXXX``.

See also: :mod:`pitloom.messages._text_unsafe_say` (the helper),
:mod:`pitloom.assemble.spdx3._display_text` (the escape),
:mod:`pitloom.assemble.spdx3._ai_package` and
:mod:`pitloom._loom_dataset_meta` (where it is said).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._loom_sdk import LOOM_SDK_PREFIX
from pitloom.messages._types import Line, Message

#: What follows the subject of each line.
_ESCAPED: Final = (
    "invisible or bidi control characters written as \\uXXXX in %(properties)s"
)

#: A model's elements, named by its format and file.
MODEL_TEXT_LINE: Final = Line(
    level="WARNING", template=f"FORMAT=%(format)s FILE=%(file)s: {_ESCAPED}"
)
#: A loom dataset's elements, named by the dataset.
DATASET_TEXT_LINE: Final = Line(
    level="WARNING", template=f"{LOOM_SDK_PREFIX}DATASET=%(dataset)s: {_ESCAPED}"
)

TEXT_UNSAFE: Final = Message(
    code="text-unsafe",
    condition="unsafe",
    lines=(MODEL_TEXT_LINE, DATASET_TEXT_LINE),
    summary="The display text of a model's elements (its package, base "
    "model, datasets and their creators, licence, originators and the "
    "relationships between them) or of a loom dataset's (when it has a "
    "Croissant document or dataset card) held invisible or bidi control "
    "characters (U+202E can make txt.exe read exe.txt), or a control "
    "character. Said once per model or dataset.",
    did="Wrote each such character as \\uXXXX in the properties the line "
    "names (a URL percent-encoded); the spdxId and the artifact-metadata "
    "annotation keep the text as read. The rest of the SBOM is unchanged.",
    effect="weaker",
    actor="user",
    advice="Tell the user which model or dataset and which properties held "
    "such characters: text that reads one way and is stored another is a "
    "spoofing risk. The escape is not reversible on its own (a \\u202e the "
    "file held as text looks the same): they check the model file or the "
    "artifact-metadata annotation. Do not edit the source for them.",
    since="0.25.0",
)

ENTRIES: Final = (TEXT_UNSAFE,)
