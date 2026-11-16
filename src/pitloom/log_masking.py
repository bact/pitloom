# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Mask the credentials of URLs in ``pitloom`` log records as they are made.

See also: :mod:`pitloom.logging_config` (installs the factory in
:func:`~pitloom.logging_config.configure_logging`),
:mod:`pitloom.core.url_masking` (the masker).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from pitloom.core.url_masking import mask_free_params, masked_given_path

#: The message of a ``pitloom`` record whose text could not be built or
#: masked (a ``msg`` whose ``__str__`` raises): nothing of it is shown.
UNSHOWN_MESSAGE = "(a log message that could not be shown)"
#: The ``exc_text`` of a record whose traceback could not be formatted or
#: masked.
UNSHOWN_TRACEBACK = "(a traceback that could not be shown)"

#: Argument types whose text is the same on every formatting: a record
#: whose arguments are all of exactly these types (no subclass) keeps its
#: ``msg`` template and ``args`` when masking changes nothing.
_STABLE_ARG_TYPES = (str, int, float, bool, type(None))


def masked_text(text: str) -> str:
    """*text* with the credentials of each URL in it masked, as a log line
    masks them (:func:`~pitloom.core.url_masking.masked_given_path`). A text
    with a line break is first masked as one text, not as a line, so a
    password holding a line break is masked whole, not left in pieces.
    Never raises: when the masker fails the text is :data:`UNSHOWN_MESSAGE`,
    never the raw text."""
    try:
        if text.splitlines() != [text]:  # a line break, as splitlines reads one
            text = masked_given_path(text)
        return masked_given_path(text, line=True)
    # pylint: disable-next=broad-exception-caught
    except Exception:  # RecursionError and any other failure of the masker
        return UNSHOWN_MESSAGE


#: The third-party loggers (and their ``.*`` children) whose records are
#: masked too, only where they hold a credential: the HTTP clients Pitloom
#: fetches through, whose ``DEBUG`` lines name a request's target with its
#: query (``"GET /x?token=T HTTP/1.1"``).
THIRD_PARTY_LOGGERS = ("urllib3", "requests")


def _is_under(name: object, roots: tuple[str, ...]) -> bool:
    """Whether the logger *name* is one of *roots* or a child of one."""
    return isinstance(name, str) and any(
        name == root or name.startswith(f"{root}.") for root in roots
    )


def _is_pitloom_record(record: logging.LogRecord) -> bool:
    """Whether *record* was logged on ``pitloom`` or a ``pitloom.*`` logger."""
    return _is_under(record.name, ("pitloom",))


def third_party_text(text: str) -> str:
    """*text*, a line of a :data:`THIRD_PARTY_LOGGERS` record, with its
    credentials masked: each URL's (:func:`masked_text`), and each secret
    parameter's value with or without a URL around it, as an HTTP client
    writes a request's target (``GET /x?token=***``). Never raises."""
    try:
        return masked_text(mask_free_params(text))
    # pylint: disable-next=broad-exception-caught
    except Exception:  # any failure of the masker
        return UNSHOWN_MESSAGE


def mask_third_party_record(record: logging.LogRecord) -> None:
    """Mask the credentials in *record*, a :data:`THIRD_PARTY_LOGGERS`
    record, only where its text holds one: then ``msg`` becomes the masked
    text and ``args`` empty (new objects, the caller's ``args`` untouched);
    else the record is left as it was made, so other handlers see its
    template and arguments. Its traceback and ``stack_info`` are masked as
    a ``pitloom`` record's are. Never raises; a message that cannot be
    formatted is left for the handler to report."""
    try:
        text = record.getMessage()
    # pylint: disable-next=broad-exception-caught
    except Exception:  # the library's own format error
        text = None
    if text is not None:
        masked = third_party_text(text)
        if masked != text:
            record.msg, record.args = masked, ()
    _mask_trace(record)


def _is_exactly(value: object, types: tuple[type, ...]) -> bool:
    """Whether the type of *value* is one of *types*, not a subclass of one,
    which may change how it is formatted (``__str__``, ``__getitem__``)."""
    return type(value) in types


def _keeps_template(record: logging.LogRecord) -> bool:
    """Whether every formatting of *record* gives the same text: a ``str``
    template and a tuple of arguments, or a ``dict`` of ``str`` keys to
    arguments, of :data:`_STABLE_ARG_TYPES`."""
    args = record.args
    if isinstance(args, dict):
        if not _is_exactly(args, (dict,)) or not all(
            _is_exactly(key, (str,)) for key in args
        ):
            return False
        args = tuple(args.values())
    return (
        _is_exactly(record.msg, (str,))
        and isinstance(args, tuple)
        and all(_is_exactly(arg, _STABLE_ARG_TYPES) for arg in args)
    )


def _mask_message(record: logging.LogRecord) -> None:
    """Mask the message of *record*; ``msg`` becomes the final text and
    ``args`` empty unless :func:`_keeps_template` and nothing was masked.
    A message that cannot be formatted is its ``msg`` and the class of the
    failure."""
    args = record.args
    # A copy: the caller may change its dict.
    if isinstance(args, dict) and _is_exactly(args, (dict,)):
        record.args = dict(args)
    try:
        text = record.getMessage()
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:  # a call site's format error
        text = f"{record.msg} (arguments not formatted: {type(exc).__name__})"
        record.msg, record.args = masked_text(text), ()
        return
    masked = masked_text(text)
    if masked != text or not _keeps_template(record):
        record.msg, record.args = masked, ()


def _mask_trace(record: logging.LogRecord) -> None:
    """Set ``exc_text`` to the masked traceback of ``exc_info`` (formatted
    afresh, whatever ``exc_text`` held), else mask the ``exc_text`` given;
    mask ``stack_info``."""
    try:
        if record.exc_info:
            trace = logging.Formatter().formatException(record.exc_info)
            record.exc_text = masked_text(trace)
        elif record.exc_text:
            record.exc_text = masked_text(record.exc_text)
    # pylint: disable-next=broad-exception-caught
    except Exception:  # an exception whose text cannot be built
        record.exc_text = UNSHOWN_TRACEBACK
    if record.stack_info:
        try:
            record.stack_info = masked_text(record.stack_info)
        # pylint: disable-next=broad-exception-caught
        except Exception:
            record.stack_info = None


def mask_record(record: logging.LogRecord) -> None:
    """Mask the credentials in *record* in place; never raises.

    The message (:func:`_mask_message`), the traceback and ``stack_info``
    (:func:`_mask_trace`). When anything else fails (the masker itself),
    the message is :data:`UNSHOWN_MESSAGE`. ``exc_info`` is kept, so a
    handler that formats the exception object itself, not ``exc_text``,
    sees it raw. Masking a masked record changes nothing."""
    try:
        _mask_message(record)
    # pylint: disable-next=broad-exception-caught
    except Exception:
        record.msg, record.args = UNSHOWN_MESSAGE, ()
    _mask_trace(record)


# pylint: disable-next=too-few-public-methods
class MaskingRecordFactory:
    """A :func:`logging.setLogRecordFactory` factory that masks
    (:func:`mask_record`) every record logged on ``pitloom`` or a
    ``pitloom.*`` logger, at any level, as the record is made: before any
    filter or handler sees it, so every handler gets it masked, whatever
    its level and wherever it is attached (a ``pitloom.*`` child logger,
    ``pitloom``, the root, ``caplog``).

    A record of a :data:`THIRD_PARTY_LOGGERS` logger (``urllib3``,
    ``requests``) is masked only where it holds a credential
    (:func:`mask_third_party_record`).

    Not covered: a record of any other logger (another third-party
    library's), passed on as made; a record not made through the
    factory (:func:`logging.makeLogRecord`), which only the handler of
    :func:`~pitloom.logging_config.configure_logging` masks, for itself and
    the handlers after it; an attribute set after the record is made (an
    ``extra`` key); the exception object in ``exc_info``; and anything
    logged before
    :func:`~pitloom.logging_config.configure_logging` installs the factory.

    It wraps the factory installed before it and calls it to make the
    record."""

    def __init__(self, previous: Callable[..., logging.LogRecord]) -> None:
        self.previous = previous

    def __call__(self, *args: Any, **kwargs: Any) -> logging.LogRecord:
        record = self.previous(*args, **kwargs)
        if _is_pitloom_record(record):
            mask_record(record)
        elif _is_under(record.name, THIRD_PARTY_LOGGERS):
            mask_third_party_record(record)
        return record


def install_record_factory() -> None:
    """Install :class:`MaskingRecordFactory` over the current factory,
    unless it is the current one already: calling it again adds no layer."""
    current = logging.getLogRecordFactory()
    if not isinstance(current, MaskingRecordFactory):
        logging.setLogRecordFactory(MaskingRecordFactory(current))
