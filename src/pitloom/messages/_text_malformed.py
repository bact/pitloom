# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``text-malformed``: text Pitloom read holds lone surrogates, which no
UTF-8 output can hold.

See also: :mod:`pitloom.messages._text_malformed_warning` (the one helper
every site says it through) and
:func:`pitloom.core.untrusted_text.escape_lone_surrogates` (how each is
written).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: What every line says was done.
_WRITTEN: Final = "lone surrogates written as \\uXXXX"

#: Text read from a file, or an SBOM element named by its name.
FILE_LINE: Final = Line(level="WARNING", template=f"FILE=%(file)s: {_WRITTEN}")
#: Text read from a model file, its format named first.
MODEL_LINE: Final = Line(
    level="WARNING", template=f"FORMAT=%(format)s FILE=%(file)s: {_WRITTEN}"
)

TEXT_MALFORMED: Final = Message(
    code="text-malformed",
    condition="malformed",
    lines=(FILE_LINE, MODEL_LINE),
    summary="Text Pitloom read holds lone surrogates (U+D800 to U+DFFF), which "
    "UTF-8 cannot hold: a JSON or YAML \\ud800 escape in a file (a model's "
    "metadata, a model or dataset card, a Croissant document, an SBOM "
    "fragment), or a file name that is not UTF-8. For the SBOM itself, the "
    "line names the first element holding one, by its name.",
    did="Wrote each lone surrogate as the six characters \\udXXX, in the SBOM "
    "and in its provenance, and went on; said once per file (once per SBOM "
    "for element names).",
    effect="weaker",
    actor="user",
    advice="Tell the user which file (or element) holds lone surrogates, as "
    "the line says, and that the SBOM shows each as \\udXXX, not as the "
    "character the source meant. If the exact text matters, they correct the "
    "source (a proper escape, a UTF-8 file name) and generate again. Do not "
    "rename or edit files for them; ask first, and with nobody to ask, report "
    "it only.",
    subject_key="FILE",
    since="0.23.0",
)

ENTRIES: Final = (TEXT_MALFORMED,)
