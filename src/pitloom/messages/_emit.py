# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""How a catalogued message carries its code: on a log record
(:func:`emit`, :func:`code_extra`) and on an exception of any class, as its
:data:`~pitloom.logging_config.CODE_ATTR` attribute (:class:`CodedValueError`
sets it; :func:`code_of` reads it).

See also: :mod:`pitloom.messages` (the catalogue) and
:mod:`pitloom.logging_config` (which prints the code).
"""

from __future__ import annotations

import logging

from pitloom.logging_config import CODE_ATTR, log_once
from pitloom.messages._catalogue import MESSAGES
from pitloom.messages._types import Message


def code_extra(message: Message) -> dict[str, object]:
    """The ``extra`` of a log call that says *message*: its code on the
    record (:data:`~pitloom.logging_config.CODE_ATTR`)."""
    return {CODE_ATTR: message.code}


def emit(
    log: logging.Logger,
    message: Message,
    level: int,
    fmt: str,
    *args: object,
    once: str | None = None,
) -> None:
    """Log *fmt* % *args* at *level* on *log* as *message*, its code on the
    record. *once*: through :func:`~pitloom.logging_config.log_once` with
    that key (``DEBUG``, and no printed code, after the first time).

    Raises:
        ValueError: *level* is not one of *message*'s levels.
    """
    if logging.getLevelName(level) not in message.levels:
        raise ValueError(f"{message.code} is not said at level {level}")
    if once is None:
        log.log(level, fmt, *args, extra=code_extra(message))
    else:
        log_once(log, level, once, fmt, *args, extra=code_extra(message))


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
    """A :class:`ValueError` that says a catalogued *message*: its
    ``pitloom_code`` reaches the ``ERROR:`` line of every surface that
    reports it."""

    def __init__(self, message: Message, text: str) -> None:
        super().__init__(text)
        #: The catalogued code (:data:`~pitloom.logging_config.CODE_ATTR`).
        self.pitloom_code: str = message.code
        self._message = message

    def __reduce__(self) -> tuple[type[CodedValueError], tuple[Message, str]]:
        return (type(self), (self._message, str(self)))
