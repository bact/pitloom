# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One record a model reader logged, said again by the scanner: the file
named by the model's stable path, not by the name of the file the reader
was handed (a temporary copy, ``0.gguf``, for a model in a wheel), and a
catalogued code kept.

See also: :mod:`pitloom.extract.scanner` (the relay of a read's records)
and :mod:`pitloom.extract._reader_log` (their capture).
"""

from __future__ import annotations

import functools
import logging
import re
from collections.abc import Mapping
from typing import Final

from pitloom.core.internal_error import InternalError
from pitloom.logging_config import CODE_ATTR, KIND_ATTR, escape_controls
from pitloom.messages import FIELDS, relay_extra
from pitloom.messages.datasets import DATASET_METADATA_PREFIX

#: The keys a reader's line names the file it read by, the field whose
#: writer wrote the value, and where in the line the key stands: a model
#: reader's ``FILE=`` at the start or after ``FORMAT=<format>``, and the
#: dataset value checks' ``SOURCE=`` (a GGUF file's dataset keys) after
#: their prefix.
_FILE_KEYS: Final = (
    ("FILE", "file", "(?:FORMAT=[^ ]+ )?"),
    ("SOURCE", "dataset_source", re.escape(DATASET_METADATA_PREFIX)),
)


def named_stably(text: str, read_name: str, stable_path: str) -> str:
    """*text* with the ``FILE=``/``SOURCE=`` value that is *read_name*, the
    name of the file the reader was handed, written as *stable_path*
    instead, by the same field writer. Only a whole value after one of
    those keys where the line's subject stands (:data:`_FILE_KEYS`): a
    model's own metadata quoting the name, even as ``FILE=<name>``, stays."""
    for key, field, before in _FILE_KEYS:
        write = FIELDS[field].write
        given = f"{key}={write(read_name)}"
        pattern = re.compile(rf"\A({before}){re.escape(given)}(?=[:; ]|\Z)")
        # A callable replacement: the stable value's backslashes are text.
        stable = f"{key}={write(stable_path)}"
        text = pattern.sub(functools.partial(_literal, stable), text, count=1)
    return text


def _literal(value: str, match: re.Match[str]) -> str:
    """What comes before the key in *match*, then *value*."""
    return match.group(1) + value


def relay(
    log: logging.Logger, record: logging.LogRecord, text: str, frame: str
) -> None:
    """Say *record* again on *log* as *text*, after *frame* from
    ``WARNING`` up. A record's catalogued code is kept: on the framed text
    when the frame allows the code, else on *text* alone, else, when the
    rewriting of *text* made it no longer one of the message's lines, on
    the record's own text, unframed (it names the file the reader was
    handed; a ``--debug`` line says so). A record below ``INFO`` (no
    catalogued line) or with no code is said as it is, uncoded, its kind
    (:data:`~pitloom.logging_config.KIND_ATTR`, a relay's) kept.

    Raises:
        pitloom.core.internal_error.InternalError: *record* is coded at
            ``INFO`` or above and not even its own text is one of its
            message's lines (a reader's line not written by its message, or
            a code that is not catalogued).
    """
    level, name = record.levelno, record.levelname
    shown = frame + text if level >= logging.WARNING else text
    code = getattr(record, CODE_ATTR, None)
    kind = getattr(record, KIND_ATTR, None)
    extra: Mapping[str, object] | None = (
        {KIND_ATTR: kind} if isinstance(kind, str) else None
    )
    if code is not None and level >= logging.INFO:
        rewritten = tuple(dict.fromkeys((shown, text)))  # the framed text first
        own = escape_controls(record.getMessage())
        said = own
        for said in (*rewritten, own):
            extra = relay_extra(code, name, said)
            if extra is not None:
                break
        if extra is None:
            raise InternalError(f"{code!r}: a reader's {name} record is not its line")
        if said not in rewritten:
            log.debug("%s: a reader's line said as read, its file not renamed", code)
        shown = said
    log.log(level, "%s", shown, extra=extra)
