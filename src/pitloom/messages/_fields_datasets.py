# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values only the dataset and loom run lines name: a dataset by the
name it was declared or read under.

A dataset name may come from a card, a Croissant document or a Hub id:
the writer masks a URL's credentials, cuts and escapes it itself
(:func:`~pitloom.messages._field_writers.quoted_name_text`).

See also: :mod:`pitloom.messages._fields` (every field, these included)
and :mod:`pitloom.messages._loom_sdk` (the lines).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.messages._field_type import QUOTED, Field
from pitloom.messages._field_writers import (
    NAME_CHARACTERS,
    NAME_CUT_MARK,
    quoted_name_text,
)

#: How a dataset name is shown.
_SHOWN_NAME: Final = (
    f"in quotes, a URL's credentials masked, cut to {NAME_CHARACTERS} "
    f"characters with `{NAME_CUT_MARK}` before the closing quote, escaped when "
    "it holds a control character; `None` for a dataset declared without "
    "a name"
)


def _dataset_name_text(value: object) -> str:
    """A dataset name in quotes (:func:`quoted_name_text`), or ``None``
    for a dataset declared without a name, as Python shows it.

    Raises:
        ValueError: *value* is neither text nor ``None``.
    """
    return "None" if value is None else quoted_name_text(value)


#: A quoted name, or ``None``.
_NAME_OR_NONE: Final = f"{QUOTED}|None"

#: The dataset lines' fields.
DATASET_FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "dataset": Field(
            _NAME_OR_NONE,
            _dataset_name_text,
            "'<dataset>'",
            f"a dataset by the name it was declared under, {_SHOWN_NAME}",
        ),
        "dataset_input": Field(
            _NAME_OR_NONE,
            _dataset_name_text,
            "'<dataset-input>'",
            f"a name given in add_output_dataset's input_datasets, {_SHOWN_NAME}",
        ),
    }
)
