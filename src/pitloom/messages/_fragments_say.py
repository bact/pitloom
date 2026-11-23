# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying the SBOM fragment lines: the error a fragment reader raises
(:class:`FragmentReadError`, by the stage that failed) and the line it is
said in (:func:`warn_fragment_unread`), a fragment that is the document
being built (:func:`warn_same_document`), the values of a ``fragment-missing``
error (:func:`missing_files_text`), and one helper per merge line, each
taking the element's spdxId and the values as the merge holds them.

A value of a conflict is a ``str`` (written in quotes) or a
:class:`~pitloom.messages._field_writers.DescribedValue` the caller made
from any other value with its own describer
(:func:`pitloom.export.spdx3_describe.describe_value`): the catalogue
imports nothing of :mod:`pitloom.export`.

See also: :mod:`pitloom.messages._fragments` and
:mod:`pitloom.messages._fragments_merge` (the entries).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final

from pitloom.core.internal_error import InternalError
from pitloom.messages._emit import emit
from pitloom.messages._field_writers import DescribedValue, failure_text, file_text
from pitloom.messages._fragments import (
    FRAGMENT_INVALID,
    FRAGMENT_UNREADABLE,
    FRAGMENT_UNUSABLE,
    NOT_JSON_LINE,
    NOT_SPDX_LINE,
    REFERENCE_LINE,
    REFERENCE_NOT_FOUND,
    REQUIRED_NOT_JSON_LINE,
    REQUIRED_NOT_SPDX_LINE,
    REQUIRED_SAME_DOCUMENT_LINE,
    REQUIRED_UNREADABLE_LINE,
    SAME_DOCUMENT_LINE,
    UNREADABLE_LINE,
)
from pitloom.messages._fragments_merge import (
    ENTRY_CONFLICT_LINE,
    FRAGMENT_CONFLICT,
    FRAGMENT_HASH_CONFLICT,
    FRAGMENT_ID_CONFLICT,
    GENERATED_REPLACED_LINE,
    GENERATED_VALUE_CONFLICT,
    HASH_CONFLICT_LINE,
    ID_OTHER_CONTENT_LINE,
    ID_OTHER_TYPE_LINE,
    MODEL_NAME_REPLACED_LINE,
    NOT_MEASURED_DROPPED_LINE,
    PROPERTY_CONFLICT_LINE,
)
from pitloom.messages._types import Line, Message

#: The stage of a fragment read: the bytes (``read``), their JSON
#: (``json``), or the SPDX 3 document and its RFC 8785 serialisation
#: (``spdx``).
READ_STAGES: Final = ("read", "json", "spdx")

#: Each stage's entry and its (optional, required) lines.
_STAGE_LINES: Final[Mapping[str, tuple[Message, Line, Line]]] = MappingProxyType(
    {
        "read": (FRAGMENT_UNREADABLE, UNREADABLE_LINE, REQUIRED_UNREADABLE_LINE),
        "json": (FRAGMENT_INVALID, NOT_JSON_LINE, REQUIRED_NOT_JSON_LINE),
        "spdx": (FRAGMENT_INVALID, NOT_SPDX_LINE, REQUIRED_NOT_SPDX_LINE),
    }
)

#: The most fragment paths a ``fragment-missing`` line names before ``and
#: N more``.
SHOWN_FILES: Final = 10


class FragmentReadError(Exception):
    """A fragment that could not be read into an object set, at *stage*
    (one of :data:`READ_STAGES`), because of *cause*. Its text is *cause*'s
    as a ``failure`` field writes it (masked, on one line, cut), never the
    raw text: a fragment's keys and values are attacker text.

    Raises:
        pitloom.core.internal_error.InternalError: *stage* is not one of
            :data:`READ_STAGES`.
    """

    def __init__(self, stage: str, cause: BaseException) -> None:
        if stage not in READ_STAGES:
            raise InternalError(f"fragment read stage {stage!r} is not one")
        super().__init__(stage, cause)
        #: Where the read failed.
        self.stage: str = stage
        #: What failed.
        self.cause: BaseException = cause

    def __str__(self) -> str:
        return failure_text(self.cause)


def warn_fragment_unread(
    log: logging.Logger,
    file: str | os.PathLike[str],
    exc: FragmentReadError,
    *,
    required: bool,
) -> None:
    """The one ``WARNING:`` on *log* for the fragment *file* (as configured,
    or a ``loom merge`` directory joined with its name) that *exc* says
    could not be read: ``fragment-unreadable`` for the ``read`` stage,
    ``fragment-invalid`` for ``json`` and ``spdx``; not merged, or,
    *required*, the merge will fail."""
    entry, optional, needed = _STAGE_LINES[exc.stage]
    line = needed if required else optional
    emit(log, entry, logging.WARNING, line=line, file=file, failure=exc.cause)


def warn_same_document(
    log: logging.Logger,
    file: str | os.PathLike[str],
    spdx_id: str,
    *,
    required: bool,
) -> None:
    """The one ``WARNING:`` on *log* for the fragment *file* whose
    ``SpdxDocument`` *spdx_id* is the document being merged into
    (``fragment-unusable``)."""
    line = REQUIRED_SAME_DOCUMENT_LINE if required else SAME_DOCUMENT_LINE
    emit(log, FRAGMENT_UNUSABLE, logging.WARNING, line=line, file=file, spdx_id=spdx_id)


def missing_files_text(files: Sequence[str | os.PathLike[str]]) -> str:
    """*files* (the required fragments not merged, as configured, in
    configuration order) as the ``files`` field of ``fragment-missing``:
    each written as a ``FILE=`` value is (masked, escaped), comma-separated,
    at most :data:`SHOWN_FILES`, then ``and N more``.

    Raises:
        pitloom.core.internal_error.InternalError: *files* is empty.
    """
    if not files:
        raise InternalError("fragment-missing names no fragment")
    shown = ", ".join(file_text(f) for f in files[:SHOWN_FILES])
    more = len(files) - SHOWN_FILES
    return f"{shown} and {more} more" if more > 0 else shown


def warn_reference_not_found(
    log: logging.Logger, *, spdx_id: str, prop: str, reference: str
) -> None:
    """The one ``WARNING:`` on *log* for the element *spdx_id* whose
    property *prop* names *reference*, which the merged document does not
    hold (``reference-not-found``). An empty *reference* (a fragment's
    empty IRI) is shown as ``-``."""
    emit(
        log,
        REFERENCE_NOT_FOUND,
        logging.WARNING,
        line=REFERENCE_LINE,
        spdx_id=spdx_id,
        property=prop,
        reference=reference or "-",
    )


def _value(value: object) -> str:
    """*value*, a value of a conflict, as the caller must pass it.

    Raises:
        pitloom.core.internal_error.InternalError: It is not a ``str`` (a
            :class:`~pitloom.messages._field_writers.DescribedValue` is
            one): an object's own repr can hold a memory address.
    """
    if not isinstance(value, str):
        raise InternalError(
            f"a merged {type(value).__name__} value must be described "
            "(DescribedValue) before it is said"
        )
    return value


# One keyword per field of the line.
# pylint: disable-next=too-many-arguments
def warn_property_conflict(
    log: logging.Logger,
    *,
    spdx_id: str,
    prop: str,
    kept: str | DescribedValue,
    dropped: str | DescribedValue,
    key: str | None = None,
) -> None:
    """The one ``WARNING:`` on *log* for the element *spdx_id*'s property
    *prop* (its Python name, ``from_``, or the document's) holding *kept*,
    which a later source states as *dropped* (``fragment-conflict``); with
    *key*, of that key of a dictionary property."""
    kept_text, dropped_text = _value(kept), _value(dropped)
    if key is None:
        emit(
            log,
            FRAGMENT_CONFLICT,
            logging.WARNING,
            line=PROPERTY_CONFLICT_LINE,
            spdx_id=spdx_id,
            property=prop,
            kept=kept_text,
            dropped=dropped_text,
        )
        return
    emit(
        log,
        FRAGMENT_CONFLICT,
        logging.WARNING,
        line=ENTRY_CONFLICT_LINE,
        spdx_id=spdx_id,
        property=prop,
        entry_key=key,
        kept=kept_text,
        dropped=dropped_text,
    )


# One keyword per field of the line.
# pylint: disable-next=too-many-arguments
def warn_id_conflict(
    log: logging.Logger,
    *,
    spdx_id: str,
    element_type: str,
    holder_type: str,
    new_id: str,
    hash_algorithm: str | None,
) -> None:
    """The one ``WARNING:`` on *log* for an element of *element_type* that
    wants the id *spdx_id*, held by an element of *holder_type*, and is
    given *new_id* (``fragment-id-conflict``): another type, or, with
    *hash_algorithm*, the same type with digests of that algorithm that
    share no value."""
    if hash_algorithm is None:
        emit(
            log,
            FRAGMENT_ID_CONFLICT,
            logging.WARNING,
            line=ID_OTHER_TYPE_LINE,
            spdx_id=spdx_id,
            element_type=element_type,
            holder_type=holder_type,
            new_id=new_id,
        )
        return
    emit(
        log,
        FRAGMENT_ID_CONFLICT,
        logging.WARNING,
        line=ID_OTHER_CONTENT_LINE,
        spdx_id=spdx_id,
        element_type=element_type,
        hash_algorithm=hash_algorithm,
        new_id=new_id,
    )


# One keyword per field of the line.
# pylint: disable-next=too-many-arguments
def warn_hash_conflict(
    log: logging.Logger,
    *,
    spdx_id: str,
    element_type: str,
    name: str,
    digest: str,
    other_digest: str,
) -> None:
    """The one ``WARNING:`` on *log* for the element *spdx_id* of
    *element_type* named *name* with SHA-256 *digest*, where another of
    that type and name states *other_digest* (``fragment-hash-conflict``)."""
    emit(
        log,
        FRAGMENT_HASH_CONFLICT,
        logging.WARNING,
        line=HASH_CONFLICT_LINE,
        spdx_id=spdx_id,
        element_type=element_type,
        name=name,
        digest=digest,
        other_digest=other_digest,
    )


def say_generated_value_replaced(
    log: logging.Logger,
    *,
    spdx_id: str,
    prop: str,
    kept: str | DescribedValue,
    dropped: str | DescribedValue,
) -> None:
    """The one ``INFO:`` on *log* for the base model *spdx_id*'s property
    *prop*, generated from the model file as *dropped*, which a fragment
    replaces with *kept* (``generated-value-conflict``)."""
    emit(
        log,
        GENERATED_VALUE_CONFLICT,
        logging.INFO,
        line=GENERATED_REPLACED_LINE,
        spdx_id=spdx_id,
        property=prop,
        kept=_value(kept),
        dropped=_value(dropped),
    )


def say_model_name_replaced(
    log: logging.Logger,
    *,
    spdx_id: str,
    kept: str | DescribedValue,
    dropped: str | DescribedValue,
) -> None:
    """The one ``INFO:`` on *log* for the base model *spdx_id* whose name
    *dropped* is replaced by *kept*, the one the fragments agree on
    (``generated-value-conflict``)."""
    emit(
        log,
        GENERATED_VALUE_CONFLICT,
        logging.INFO,
        line=MODEL_NAME_REPLACED_LINE,
        spdx_id=spdx_id,
        kept=_value(kept),
        dropped=_value(dropped),
    )


def say_not_measured_dropped(
    log: logging.Logger, *, spdx_id: str, prop: str, provenance_field: str
) -> None:
    """The one ``INFO:`` on *log* for the element *spdx_id* whose property
    *prop* now holds a value, so the ``not_measured`` provenance entry of
    *provenance_field* is dropped (``generated-value-conflict``)."""
    emit(
        log,
        GENERATED_VALUE_CONFLICT,
        logging.INFO,
        line=NOT_MEASURED_DROPPED_LINE,
        spdx_id=spdx_id,
        property=prop,
        provenance_field=provenance_field,
    )
