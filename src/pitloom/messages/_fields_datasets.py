# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values only the dataset and loom run lines name: a dataset by the
name it was declared or read under, the source and field of a dataset value,
and the type of a value that is not text.

A dataset name or source may come from a card, a Croissant document or a
Hub id: the writers mask a URL's credentials, cut and escape it themselves
(:func:`~pitloom.messages._field_writers.quoted_name_text`).

See also: :mod:`pitloom.messages._fields` (every field, these included)
and :mod:`pitloom.messages._loom_sdk` (the lines).
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.core.internal_error import InternalError
from pitloom.messages._field_tables import VALUE_TYPES
from pitloom.messages._field_type import QUOTED, Field
from pitloom.messages._field_writers import (
    NAME_CHARACTERS,
    NAME_CUT_MARK,
    plain_text,
    quoted_name_text,
)

#: How a dataset name given as text is shown.
_SHOWN_TEXT: Final = (
    f"in quotes, a URL's credentials masked, cut to {NAME_CHARACTERS} "
    f"characters with `{NAME_CUT_MARK}` before the closing quote, escaped when "
    "it holds a control character"
)
#: How a dataset name is shown.
_SHOWN_NAME: Final = f"{_SHOWN_TEXT}; `None` for a dataset declared without a name"


def _dataset_name_text(value: object) -> str:
    """A dataset name in quotes (:func:`quoted_name_text`), or ``None``
    for a dataset declared without a name, as Python shows it.

    Raises:
        pitloom.core.internal_error.InternalError: *value* is neither text nor
            ``None``.
    """
    return "None" if value is None else quoted_name_text(value)


#: The type of a dataset value, as a line names it: each type a JSON or
#: YAML reader gives (:data:`~pitloom.messages._field_tables.VALUE_TYPES`,
#: and YAML's ``!!binary`` and ``!!set``), a tuple a library caller may
#: pass; any other is ``object``, so naming a value never raises.
DATASET_VALUE_TYPES: Final[Mapping[type, str]] = MappingProxyType(
    {
        bool: "bool",
        bytes: "bytes",
        datetime.date: "date",
        datetime.datetime: "datetime",
        dict: "dict",
        float: "float",
        int: "int",
        list: "list",
        type(None): "NoneType",
        set: "set",
        str: "str",
        datetime.time: "time",
        tuple: "tuple",
    }
)
#: What a value of a type not in :data:`DATASET_VALUE_TYPES` is named.
OTHER_TYPE: Final = "object"
_TYPE_NAMES: Final = tuple(
    sorted({*VALUE_TYPES, *DATASET_VALUE_TYPES.values(), OTHER_TYPE})
)


def dataset_value_type_text(value: object) -> str:
    """The name of *value*'s type (:data:`DATASET_VALUE_TYPES`, exactly that
    type, not a subclass), else :data:`OTHER_TYPE`; never raises."""
    return DATASET_VALUE_TYPES.get(type(value), OTHER_TYPE)


#: A dataset field as a line names it: a source's key (``license``,
#: ``rai:dataBiases``, a GGUF ``general.dataset.0.repo_url``, a field
#: of :class:`~pitloom.core.dataset_metadata.DatasetMetadata`), `` name``
#: after it for the name of a node (``creator name``).
DATASET_FIELD: Final = r"[A-Za-z_@][A-Za-z0-9_.:@-]*(?: name)?"


def dataset_field_text(value: object) -> str:
    """A dataset field (:data:`DATASET_FIELD`), as given.

    Raises:
        pitloom.core.internal_error.InternalError: It is not text of that shape.
    """
    text = plain_text(value)
    if re.fullmatch(DATASET_FIELD, text) is None:
        raise InternalError(f"not a dataset field: {text!r}")
    return text


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
            QUOTED,
            quoted_name_text,
            "'<dataset-input>'",
            f"a name given in add_output_dataset's input_datasets, {_SHOWN_TEXT}",
        ),
        "dataset_spelling": Field(
            QUOTED,
            quoted_name_text,
            "'<dataset-spelling>'",
            "another spelling of the dataset's name read as the same dataset "
            "(a Hub id in other case or spacing), in quotes, a URL's "
            f"credentials masked, cut to {NAME_CHARACTERS} characters",
        ),
        "dataset_source": Field(
            QUOTED,
            quoted_name_text,
            "'<dataset-source>'",
            "where a dataset value was read, in quotes: a card or Croissant file "
            "as named (`'corpus/README.md'`), a GGUF file as its model's "
            "`FILE=` names it (`'demo/m.gguf'`, its path in a wheel or "
            "project), `'Hugging Face model card'`, or the dataset's name for "
            "a value a library caller "
            f"set; a URL's credentials masked, cut to {NAME_CHARACTERS} "
            f"characters (then `{NAME_CUT_MARK}`)",
        ),
        "dataset_field": Field(
            DATASET_FIELD,
            dataset_field_text,
            "<dataset-field>",
            "the dataset field as its source names it (`license`, `version`, "
            "`general.dataset.0.repo_url`, `rai:dataBiases`, `creator name`), "
            "or a dataset metadata field (`byte_size`, `download_url`)",
        ),
        "model": Field(
            QUOTED,
            quoted_name_text,
            "'<model>'",
            "a model by the name it is shown under: one with no file (a "
            "Hugging Face model, a library caller's model), or the file name "
            f"a Python file mentions, {_SHOWN_TEXT}",
        ),
        "dataset_value_type": Field(
            "|".join(re.escape(name) for name in _TYPE_NAMES),
            dataset_value_type_text,
            "<dataset-value-type>",
            "the type of the value that is not text, as Python names it: "
            + ", ".join(f"`{name}`" for name in _TYPE_NAMES),
        ),
    }
)
