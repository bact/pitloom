# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying a catalogued message: as a log record (:func:`emit`) or as an
exception (:class:`CodedValueError`). Either way the catalogue writes the
text from the message's line and the caller's values, and the code travels
with it: on the record and on an exception of any class, as its
:data:`~pitloom.logging_config.CODE_ATTR` attribute (:func:`code_of` reads
it).

See also: :mod:`pitloom.messages` (the catalogue) and
:mod:`pitloom.logging_config` (which prints the code).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping

from pitloom.logging_config import CODE_ATTR, escape_controls, log_once
from pitloom.messages._catalogue import MESSAGES
from pitloom.messages._fields import written
from pitloom.messages._lines import says
from pitloom.messages._types import Line, Message


def emit(
    log: logging.Logger,
    message: Message,
    level: int,
    *,
    line: Line | None = None,
    once: str | None = None,
    extra: Mapping[str, object] | None = None,
    **values: object,
) -> None:
    """Log *message* at *level* on *log*, its code on the record: its line
    at that level that names *values* (*line*, when several do), each value
    written by its field. *once*: through
    :func:`~pitloom.logging_config.log_once` with that key (``DEBUG``, and
    no printed code, after the first time). *extra*: more attributes for
    the record; the code is the message's own, whatever *extra* holds.

    Raises:
        ValueError: No line of *message* at *level* names *values* (or
            *line* is not one), or a value does not have its field's shape.
    """
    shape = message.line_for(logging.getLevelName(level), values, line)
    texts = written(shape.template, values)
    args: tuple[object, ...] = (texts,) if texts else ()
    attrs = {**(extra or {}), CODE_ATTR: message.code}
    if once is None:
        log.log(level, shape.template, *args, extra=attrs)
    else:
        log_once(log, level, once, shape.template, *args, extra=attrs)


def relay_extra(code: object, level: str, text: str) -> dict[str, object] | None:
    """The ``extra`` of a log call that says another record's message again
    at *level* (``"WARNING"``) with new *text* (a prefix added, a path
    replaced): the record's *code* only when *text* is still one of that
    message's lines (a frame before it allowed), else ``None``, so a relayed
    line never carries a code it would not be trusted with."""
    message = MESSAGES.get(code) if isinstance(code, str) else None
    if message is None or not says(message, level, escape_controls(text)):
        return None
    return {CODE_ATTR: message.code}


def code_of(exc: BaseException) -> str | None:
    """*exc*'s ``pitloom_code`` (:data:`~pitloom.logging_config.CODE_ATTR`,
    on the instance or its class) when it is a catalogued code, else
    ``None``. Any exception class can carry one; another attribute, such as
    the ``code`` of an HTTP error, an exit or a remote-source error
    (``git.too-large``), is never read. *exc*'s cause is not consulted: a
    wrapping exception states its own condition."""
    code = getattr(exc, CODE_ATTR, None)
    return code if isinstance(code, str) and code in MESSAGES else None


def code_extra_of(exc: BaseException) -> dict[str, object] | None:
    """The ``extra`` of a log call that reports *exc*: its catalogued code
    (:func:`code_of`), or ``None`` when it has none."""
    code = code_of(exc)
    return None if code is None else {CODE_ATTR: code}


class CodedValueError(ValueError):
    """A :class:`ValueError` that says a catalogued *message*: its text is
    the message's ``ERROR`` line that names *values* (*line*, when several
    do), written by the catalogue, and its ``pitloom_code`` reaches the
    ``ERROR:`` line of every surface that reports it.

    Raises:
        ValueError: (a plain one) No ``ERROR`` line of *message* names
            *values*, or a value does not have its field's shape.
    """

    def __init__(
        self, message: Message, /, *, line: Line | None = None, **values: object
    ) -> None:
        super().__init__(message.line_for("ERROR", values, line).render(values))
        #: The catalogued code (:data:`~pitloom.logging_config.CODE_ATTR`).
        self.pitloom_code: str = message.code

    def __reduce__(
        self,
    ) -> tuple[
        Callable[[type[CodedValueError], str, str], CodedValueError],
        tuple[type[CodedValueError], str, str],
    ]:
        return (_restored, (type(self), str(self), self.pitloom_code))


def _restored(cls: type[CodedValueError], text: str, code: str) -> CodedValueError:
    """A copied or unpickled :class:`CodedValueError`: its text as written
    then, not written again."""
    exc = cls.__new__(cls)
    ValueError.__init__(exc, text)
    exc.pitloom_code = code
    return exc
