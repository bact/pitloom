# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``card-malformed``: a model or dataset card whose YAML frontmatter does
not parse. A card that has no frontmatter, or one that is valid YAML but no
mapping, is not malformed: it states nothing, quietly.

See also: :mod:`pitloom.enrich.readme` (the one reader of a card) and
:data:`pitloom.messages._field_tables.CARD_KINDS` (the kinds of card).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

#: A card whose frontmatter the YAML parser refused.
CARD_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: %(card)s frontmatter is not valid YAML; %(failure)s",
)

CARD_MALFORMED: Final = Message(
    code="card-malformed",
    condition="malformed",
    lines=(CARD_LINE,),
    summary="The YAML frontmatter at the top of a card (the block between "
    "two --- lines) does not parse: a model card beside a local model, a "
    "dataset's own card, a Hugging Face model's card, or a Hugging Face "
    "dataset card a Hub model lists. "
    "The line gives what the parser reported.",
    did="Used nothing of the frontmatter and went on: a model card beside a "
    "local model sets no license or datasets; a Hugging Face model card "
    "also no tags, base_model, library_name, language, pipeline_tag or "
    "model-index; a dataset card no license, license_name, license_link, "
    "version, tags or pretty_name; a Hugging Face dataset card no license or "
    "keywords (the description is still read from the card's text).",
    effect="thinner",
    actor="user",
    advice="Tell the user which card's frontmatter is not valid YAML and what "
    "the parser reported, as the line says. They fix the card and generate "
    "again; a Hugging Face dataset card only its maintainers can fix. Do not "
    f"edit the card for them; {ASK_FIRST}",
    subject_key="FILE",
    since="0.23.0",
)

ENTRIES: Final = (CARD_MALFORMED,)
