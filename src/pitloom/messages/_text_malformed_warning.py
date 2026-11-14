# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one ``WARNING:`` for text holding lone surrogates
(:func:`warn_lone_surrogates`), and the lines for a name the ID registry
cannot hold (:func:`registry_name_error`, :func:`warn_registry_name_skipped`,
:func:`warn_registry_file_name`).

See also: :mod:`pitloom.messages._text_malformed` (the entry).
"""

from __future__ import annotations

import logging
import os

from pitloom.messages._emit import CodedValueError, emit
from pitloom.messages._text_malformed import (
    FILE_LINE,
    MODEL_LINE,
    REGISTRY_FILE_NAME_LINE,
    REGISTRY_NAME_LINE,
    REGISTRY_NAME_SKIPPED_LINE,
    TEXT_MALFORMED,
    TEXT_MALFORMED_REGISTRY,
)


def warn_lone_surrogates(
    log: logging.Logger,
    *,
    file: str | os.PathLike[str],
    model_format: str | None = None,
) -> None:
    """The one ``WARNING:`` on *log* that text read from *file* (as the
    line names it, raw: the line escapes it) held lone surrogates, now
    written as text, ``[text-malformed]``; *model_format* names the format
    of a model file first. Each caller says it once per file."""
    if model_format is None:
        emit(log, TEXT_MALFORMED, logging.WARNING, line=FILE_LINE, file=file)
    else:
        emit(
            log,
            TEXT_MALFORMED,
            logging.WARNING,
            line=MODEL_LINE,
            file=file,
            format=model_format,
        )


def registry_name_error(part: str, text: str) -> CodedValueError:
    """The error to raise for *text*, the *part* (one of
    :data:`~pitloom.messages._field_tables.REGISTRY_PARTS`) of an element the
    ID registry is asked to hold, which holds lone surrogates its UTF-8 file
    cannot hold, ``text-malformed/registry``; the line shows it escaped."""
    return CodedValueError(
        TEXT_MALFORMED_REGISTRY,
        line=REGISTRY_NAME_LINE,
        registry_part=part,
        value=text,
    )


def warn_registry_name_skipped(
    log: logging.Logger, part: str, text: str, *, once: str | None = None
) -> None:
    """The one ``WARNING:`` on *log* for an SBOM element the ID registry
    leaves out, as :func:`registry_name_error` words its *part* and *text*.
    *once*: said once per key and process (a repeat is ``DEBUG``)."""
    emit(
        log,
        TEXT_MALFORMED_REGISTRY,
        logging.WARNING,
        line=REGISTRY_NAME_SKIPPED_LINE,
        once=once,
        registry_part=part,
        value=text,
    )


def warn_registry_file_name(
    log: logging.Logger, *, file: str | os.PathLike[str]
) -> None:
    """The one ``WARNING:`` on *log* for a file ``loom id generate`` leaves
    out of the index because the ID registry cannot hold its name (*file*,
    as the line names it, raw: the line escapes it)."""
    emit(
        log,
        TEXT_MALFORMED_REGISTRY,
        logging.WARNING,
        line=REGISTRY_FILE_NAME_LINE,
        file=file,
    )
