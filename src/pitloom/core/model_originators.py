# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model's originators (SPDX ``originatedBy``): the names a source states.

Only structured fields are read; whether a name is a person or an
organisation is not decided here. The functions are pure.

See also: :mod:`pitloom.core.model_parameters` (the sibling for the count).
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from pitloom.core.ai_metadata import MAX_MODEL_ENTRIES
from pitloom.messages import Cap

#: The provenance key of the originators: the
#: :class:`~pitloom.core.ai_metadata.AiModelMetadata` field name.
ORIGINATORS_PROVENANCE_KEY = "originators"

#: The provenance key of the supplier (SPDX ``suppliedBy``): the
#: :class:`~pitloom.core.ai_metadata.AiModelMetadata` field name.
SUPPLIER_PROVENANCE_KEY = "supplier"

#: The provenance suffix of names split on commas.
COMMA_LIST_METHOD = " | Method: comma_list"

#: The provenance suffix of a name that is a hub repository's owner.
REPOSITORY_OWNER_METHOD = " | Method: repository_owner"


#: Most non-empty parts (comma-separated pieces; a whitespace-only one counts)
#: one call examines, so a value of millions of commas or of one repeated
#: name stays cheap; 16 x (:data:`MAX_MODEL_ENTRIES` + 1). Empty pieces
#: between commas are not counted. Parts past the bound are not read.
MAX_ORIGINATOR_PARTS = 16 * (MAX_MODEL_ENTRIES + 1)

#: :data:`MAX_ORIGINATOR_PARTS` as a model warning says it.
ORIGINATOR_PARTS_CAP = Cap(MAX_ORIGINATOR_PARTS, "part", "model-author")

#: What a part-bound cut leaves out, as a model warning says it.
ORIGINATOR_PARTS_SKIPPED = "rest of model_author not read"

_NON_EMPTY_PART = re.compile(r"[^,]+")


def _comma_parts(text: str) -> Iterator[str]:
    """The non-empty parts of *text* between commas, found one at a time so a
    string of millions of commas never builds a list."""
    for match in _NON_EMPTY_PART.finditer(text):
        yield match.group()


def originator_names_cut(
    *values: object, comma_list: bool = False
) -> tuple[list[str], bool]:
    """The originator names in *values*, in source order, first of repeats,
    and whether the parts bound cut the read.

    A ``str`` value is one name, or with *comma_list* a comma-separated list
    of names (so ``"Doe, Jane"`` is two). Names are stripped; blank names
    and values that are not ``str`` are skipped. Collecting stops once
    ``MAX_MODEL_ENTRIES + 1`` names are held, so the cut that follows
    (:func:`~pitloom.extract.ai_model.limits.cap_entries`) warns, or once
    :data:`MAX_ORIGINATOR_PARTS` parts have been examined. The flag is true
    only when a further part was left unread: a bound reached exactly at
    the end of the input is no cut.
    """
    names: dict[str, None] = {}
    limit = MAX_MODEL_ENTRIES + 1
    examined = 0
    for value in values:
        if not isinstance(value, str):
            continue
        for part in _comma_parts(value) if comma_list else (value,):
            examined += 1
            if examined > MAX_ORIGINATOR_PARTS:
                return list(names), True
            name = part.strip()
            if name:
                names.setdefault(name)
                if len(names) >= limit:
                    return list(names), False
    return list(names), False


def originator_names(*values: object, comma_list: bool = False) -> list[str]:
    """The names of :func:`originator_names_cut`, without its flag."""
    return originator_names_cut(*values, comma_list=comma_list)[0]
