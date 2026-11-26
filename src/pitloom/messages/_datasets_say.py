# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The helpers that say the shared dataset lines: a dataset value its field
cannot hold (:func:`warn_dataset_field`), two references to one dataset
that differ (:func:`warn_dataset_conflict`, naming the model by
:class:`DatasetModel`) or spell it two ways
(:func:`say_one_dataset`). Each takes the values as read; the fields mask,
cut and escape them.

See also: :mod:`pitloom.messages._datasets` (the entries).
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from pitloom.core.internal_error import InternalError
from pitloom.messages._datasets import (
    CONFLICT_LINE,
    DATASET_CONFLICT,
    DATASET_CONFLICT_SPELLING,
    DATASET_FIELD_INVALID,
    MODEL_CONFLICT_LINE,
    NOT_A_COUNT_LINE,
    NOT_A_URL_LINE,
    NOT_TEXT_LINE,
    UNQUOTED_VERSION_LINE,
)
from pitloom.messages._emit import emit
from pitloom.messages._types import Line

#: A value of a type that holds no text.
NOT_TEXT: Final = "not-text"
#: A card ``version`` YAML did not read as text.
UNQUOTED_VERSION: Final = "unquoted-version"
#: Text in a URL field that is not a URL.
NOT_A_URL: Final = "not-a-url"
#: A size or count that is not a whole number of zero or more.
NOT_A_COUNT: Final = "not-a-count"

#: Each kind's line.
_FIELD_LINES: Final[Mapping[str, Line]] = MappingProxyType(
    {
        NOT_TEXT: NOT_TEXT_LINE,
        UNQUOTED_VERSION: UNQUOTED_VERSION_LINE,
        NOT_A_URL: NOT_A_URL_LINE,
        NOT_A_COUNT: NOT_A_COUNT_LINE,
    }
)
#: The kinds whose line names the value's type.
_TYPED: Final = frozenset({NOT_TEXT, UNQUOTED_VERSION})

#: The types YAML gives an unquoted scalar it does not read as text
#: (``1.10``, ``yes``, ``2024-01-01``): only these are kept as written by
#: quoting. A ``!!binary`` or ``!!set`` value is not.
_UNQUOTED_SCALARS: Final = frozenset(
    {bool, int, float, datetime.date, datetime.datetime}
)


def _field_line(kind: str, value: object) -> Line:
    """The line of *kind* for *value*: the quoting advice only for a scalar
    YAML read from unquoted text.

    Raises:
        pitloom.core.internal_error.InternalError: *kind* is not a kind.
    """
    line = _FIELD_LINES.get(kind)
    if line is None:
        raise InternalError(f"dataset field kind {kind!r} is not a kind")
    if kind == UNQUOTED_VERSION and type(value) not in _UNQUOTED_SCALARS:
        return NOT_TEXT_LINE
    return line


# One value per part of the line.
# pylint: disable-next=too-many-arguments
def warn_dataset_field(
    log: logging.Logger,
    kind: str,
    source: str,
    field: str,
    value: object = None,
) -> None:
    """The one ``WARNING:`` (``dataset-field-invalid``) that *field* of
    *source* holds *value*, of the *kind* its field cannot hold
    (:data:`NOT_TEXT`, :data:`UNQUOTED_VERSION`, :data:`NOT_A_URL`,
    :data:`NOT_A_COUNT`); a typed kind names *value*'s type, never the
    value.

    Raises:
        pitloom.core.internal_error.InternalError: *kind* is not a kind.
    """
    line = _field_line(kind, value)
    # Each value is a field's, written by it: emit takes them as keywords.
    typed: dict[str, Any] = {"dataset_value_type": value} if kind in _TYPED else {}
    emit(
        log,
        DATASET_FIELD_INVALID,
        logging.WARNING,
        line=line,
        dataset_source=source,
        dataset_field=field,
        **typed,
    )


@dataclass(frozen=True)
class DatasetModel:
    """The model a dataset conflict is said of: by its *file* when it has
    one (``FILE=``), else by its *name* (``MODEL=``).

    Raises:
        pitloom.core.internal_error.InternalError: Neither is given, or one
            is empty.
    """

    #: The model's file, as its other lines name it; ``None`` with none.
    file: str | None = None
    #: The model's name, for a model with no file.
    name: str | None = None

    def __post_init__(self) -> None:
        """Check that the model is named."""
        if self.file is None and self.name is None:
            raise InternalError("a dataset's model needs a file or a name")
        if self.file == "" or self.name == "":
            raise InternalError("a dataset's model is named by empty text")


def warn_dataset_conflict(
    log: logging.Logger, model: DatasetModel, dataset: str, field: str
) -> None:
    """The ``WARNING:`` (``dataset-conflict``) that two references of
    *model* to the dataset *dataset* state different values of *field*;
    the first is kept. The caller says it once per model, dataset and
    field."""
    # Each value is a field's, written by it: emit takes them as keywords.
    values: dict[str, Any] = {"dataset": dataset, "dataset_field": field}
    if model.file is not None:
        line = CONFLICT_LINE
        values["file"] = model.file
    else:
        line = MODEL_CONFLICT_LINE
        values["model"] = model.name
    emit(log, DATASET_CONFLICT, logging.WARNING, line=line, **values)


def say_one_dataset(log: logging.Logger, kept: str, spelling: str) -> None:
    """The ``INFO:`` (``dataset-conflict/spelling``) that *spelling* was
    read as the dataset *kept*, which names it (the first spelling wins)."""
    emit(
        log,
        DATASET_CONFLICT_SPELLING,
        logging.INFO,
        dataset=kept,
        dataset_spelling=spelling,
    )
