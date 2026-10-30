# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared ``INFO:``/``WARNING:``/``ERROR:`` log-message formatting.

See also: :mod:`pitloom.__main__` (the ``loom`` CLI entry point),
:mod:`pitloom.plugins.hatch` (the Hatchling build-hook entry point), and
every public generator/enrich function in :mod:`pitloom.assemble` (the
library API) -- all call :func:`configure_logging` so ``log.info(...)``/
``log.warning(...)`` output looks the same regardless of which entry
point invoked Pitloom.
"""

from __future__ import annotations

import io
import logging
import os
import re
import sys
import threading
import traceback
from collections.abc import Mapping
from typing import Any, TextIO, cast

from pitloom.core.untrusted_text import DISPLAY_CONTROLS
from pitloom.core.url_masking import mask_checkout

# Guards the handlers.clear()/addHandler() swap below (see
# configure_logging()'s docstring) and the _WARNED_ONCE read-then-write in
# log_once() -- one lock for all shared mutable state in this module.
_CONFIG_LOCK = threading.Lock()

# The environment variable a bare configure_logging() (debug=None)
# falls back to -- see apply_debug_override()'s docstring for why every
# no-argument call site needs to agree on the same source of truth.
PITLOOM_DEBUG_ENV_VAR = "PITLOOM_DEBUG"

# Truthy values for the PITLOOM_DEBUG opt-in below; anything else
# (including unset) leaves DEBUG suppressed.
_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: The LogRecord (and exception) attribute holding a catalogued message's
#: code (:mod:`pitloom.messages`), printed as a trailing `` [code]``.
CODE_ATTR = "pitloom_code"
#: What a reader takes for a code; one that does not match whole is never
#: printed. :data:`pitloom.messages.CODE_GRAMMAR` is stricter.
CODE_PATTERN = r"[a-z][a-z0-9/-]*"
_CODE_RE = re.compile(CODE_PATTERN)
#: A `` [x]`` ending a text that would read as a code.
CODE_LIKE_END = re.compile(rf" \[({CODE_PATTERN})\]\Z")

#: The ``WARNING:`` for text holding a lone surrogate (U+D800 to U+DFFF),
#: written as text (:func:`~pitloom.core.untrusted_text.escape_lone_surrogates`).
#: Arguments: a prefix (``"FORMAT=<fmt> "`` for a model, else ``""``) and
#: the file, through :func:`loggable`. Logged by :func:`warn_lone_surrogates`.
LONE_SURROGATES_WARNING = "%sFILE=%s: lone surrogates written as \\uXXXX"

#: Keys already surfaced once via :func:`log_once` (and :func:`warn_once`)
#: in this process.
#: Keyed by ``(logger.name, key)`` so two independent call sites can't
#: collide by picking the same short key string.
_WARNED_ONCE: set[tuple[str, str]] = set()


def escape_controls(text: str) -> str:
    """*text* with the temporary checkout of a Git URL masked
    (:func:`~pitloom.core.url_masking.mask_checkout`), each character that is
    not printable, and each code point of
    :data:`~pitloom.core.untrusted_text.DISPLAY_CONTROLS`, written as its ASCII
    escape (``\\n``, ``\\x1b``, ``\\u202e``); anything else, non-ASCII
    letters included, is kept. Unlike :func:`loggable` it never quotes, so a
    message already built stays readable."""
    text = mask_checkout(text)
    if text.isprintable() and DISPLAY_CONTROLS.isdisjoint(text):
        return text
    return "".join(
        ascii(char)[1:-1]
        if not char.isprintable() or char in DISPLAY_CONTROLS
        else char
        for char in text
    )


def _code_suffix(code: object) -> str:
    """`` [code]`` for a *code* :data:`CODE_PATTERN` matches whole, else
    ``""``: a code is printed only as Pitloom's own token."""
    return f" [{code}]" if isinstance(code, str) and _CODE_RE.fullmatch(code) else ""


def _with_code(text: str, code: object) -> str:
    """*text* (escaped already) ending in `` [code]`` when *code* is one
    (:func:`_code_suffix`); else with the ``[`` of a code-like `` [x]`` ending
    written ``\\x5b``, so a line's last `` [code]`` is always Pitloom's, never
    a value it printed (a file named ``m [lfs-pointer]``)."""
    suffix = _code_suffix(code)
    return text + suffix if suffix else CODE_LIKE_END.sub(r" \\x5b\1]", text)


class _OneLineFormatter(logging.Formatter):
    """``LEVEL: message`` with the message escaped by :func:`escape_controls`:
    whatever a call site interpolated, one record is one tagged line on
    stderr, then its :data:`CODE_ATTR` (:func:`_with_code`; none on ``DEBUG``).
    A traceback (``exc_info``) is appended as it is."""

    def formatMessage(self, record: logging.LogRecord) -> str:
        code = (
            getattr(record, CODE_ATTR, None) if record.levelno > logging.DEBUG else None
        )
        record.message = _with_code(escape_controls(record.message), code)
        return super().formatMessage(record)


def print_traceback() -> None:
    """Print the traceback of the exception being handled to stderr, each
    line indented and escaped by :func:`escape_controls`: a line of an
    exception message that reads ``WARNING: forged`` is not a tagged line."""
    for line in traceback.format_exc().splitlines():
        print(f"  {escape_controls(line)}", file=sys.stderr)


def print_error(message: str, *, code: str | None = None) -> None:
    """Print one ``ERROR: <message>`` line to stderr, the message escaped by
    :func:`escape_controls`: the one way the CLI writes an error, so a newline
    in a path or an exception text cannot start a second, forged line. A
    catalogued *code* follows as `` [code]``; without one, nothing at the end
    reads as a code (:func:`_with_code`)."""
    print(f"ERROR: {_with_code(escape_controls(message), code)}", file=sys.stderr)


def loggable(text: str) -> str:
    """*text* as is when printable, else its ASCII-escaped literal, so
    untrusted text (an archive member name, an exception message quoting
    one) cannot forge a second tagged line, e.g. ``::error::``, on stderr.

    The one escaping every message interpolating such text goes through.
    Text holding a code point of
    :data:`~pitloom.core.untrusted_text.DISPLAY_CONTROLS` is escaped too,
    printable or not (U+034F is a printable combining mark). It does not mask
    the temporary checkout: ``KEY=VALUE`` data on stdout goes through it and
    must stay as it is (messages are masked by :func:`escape_controls`).
    """
    if text.isprintable() and DISPLAY_CONTROLS.isdisjoint(text):
        return text
    return ascii(text)


def warn_lone_surrogates(logger: logging.Logger, where: str, prefix: str = "") -> None:
    """Log :data:`LONE_SURROGATES_WARNING` on *logger*: text read from
    *where* (a file, already through :func:`loggable`) held a lone surrogate,
    now written as text. *prefix* is ``"FORMAT=<fmt> "`` for a model file.
    The one emitter of that wording; each caller says it once per file."""
    logger.warning(LONE_SURROGATES_WARNING, prefix, where)


#: Characters of a value :func:`excerpt` shows.
EXCERPT_CHARS = 120


def excerpt(value: object) -> str:
    """*value* for a warning as one literal, escaped once: on one line, at
    most :data:`EXCERPT_CHARS` characters, ``...`` after it when cut. A
    string is its ``repr`` when printable, else its ASCII-escaped literal
    (:func:`loggable`); any other value is its ``repr``, escaped alike."""
    is_text = isinstance(value, str)
    text = " ".join((value if isinstance(value, str) else repr(value)).split())
    cut = text[:EXCERPT_CHARS]
    escaped = loggable(cut)
    literal = repr(cut) if is_text and escaped == cut else escaped
    return literal + ("..." if len(text) > EXCERPT_CHARS else "")


def _debug_requested(debug: bool | None) -> bool:
    """Resolve the effective debug flag: an explicit ``debug`` argument
    wins; ``None`` falls back to the ``PITLOOM_DEBUG`` environment
    variable, so entry points that don't parse CLI flags themselves
    (the Hatchling hook, every public library-API generator) still get
    the opt-in for free."""
    if debug is not None:
        return debug
    return os.environ.get(PITLOOM_DEBUG_ENV_VAR, "").strip().lower() in _TRUTHY


def debug_enabled() -> bool:
    """Whether ``DEBUG`` diagnostics are on for this process: the
    effective ``PITLOOM_DEBUG``, which the CLI's ``--debug``/``--no-debug``
    set through :func:`apply_debug_override`."""
    return _debug_requested(None)


def apply_debug_override(debug: bool | None) -> None:
    """Set the CLI's explicit ``--debug``/``--no-debug`` choice in the
    ``PITLOOM_DEBUG`` environment variable, so every later bare
    :func:`configure_logging` call (each public generator and the build hook
    makes one) resolves the same level instead of reverting to ``INFO``.

    ``debug=None`` (flag omitted) leaves the variable as found, so an ambient
    ``PITLOOM_DEBUG`` is respected. ``debug=False`` sets it to ``"0"``, not
    unset, so "off by choice" stays distinct from "never configured".

    The change lasts for the rest of the process. A caller running
    :func:`pitloom.__main__.main` or a generator repeatedly in one process
    saves ``os.environ.get(PITLOOM_DEBUG_ENV_VAR)`` before and restores it
    after; ``apply_debug_override(False)`` does not restore it.
    """
    if debug is None:
        return
    os.environ[PITLOOM_DEBUG_ENV_VAR] = "1" if debug else "0"


def configure_logging(*, debug: bool | None = None) -> None:
    """Prefix ``pitloom`` log records with their level, on stderr.

    ``log.info(...)`` and ``log.warning(...)`` records become ``INFO: ...``
    and ``WARNING: ...``, the grep-able ``LEVEL: <description>`` convention of
    CLAUDE.md's "CLI output" section (without a handler, ``INFO`` is dropped
    and ``WARNING`` has no prefix). ``DEBUG`` is suppressed unless *debug* is
    ``True``, or *debug* is ``None`` and ``PITLOOM_DEBUG`` is one of
    ``1``/``true``/``yes``/``on`` (case-insensitive); the CLI passes no
    argument and sets ``PITLOOM_DEBUG`` through :func:`apply_debug_override`.
    Enabled ``DEBUG`` records are prefixed ``DEBUG: ``.

    Each call replaces the logger's handlers with a new list, so repeated
    calls do not stack handlers and a concurrent log call sees a complete
    list; a lock serialises the reconfiguration. Propagation to the root
    logger stays on (``caplog`` captures the records), so a host that
    configures root logging itself may see each line twice.
    """
    level = logging.DEBUG if _debug_requested(debug) else logging.INFO
    logger = logging.getLogger("pitloom")
    handler = logging.StreamHandler(_uncaptured_stderr())
    handler.setLevel(level)
    handler.setFormatter(_OneLineFormatter("%(levelname)s: %(message)s"))
    with _CONFIG_LOCK:
        logger.setLevel(level)
        logger.handlers = [handler]


def _uncaptured_stderr() -> TextIO:
    """``sys.stderr``, or the stream behind it while a thread captures it
    (:func:`pitloom.extract.stderr_capture.capture_stderr` swaps in a proxy
    that sends each capturing thread's writes to that thread's sink). A handler
    bound to the proxy would hand a Pitloom record logged in a capturing
    thread to the sink, to be logged again as the captured tool's own text.
    Read by attribute name, not by import: ``pitloom.extract`` imports this
    module."""
    stream: Any = sys.stderr
    while hasattr(type(stream), "uncaptured_stderr"):  # a proxy, maybe of a proxy
        stream = stream.uncaptured_stderr
        if stream is None:  # there is no stderr to write to
            return io.StringIO()
    return cast(TextIO, stream)


def warn_once(
    log: logging.Logger,
    key: str,
    msg: str,
    *args: object,
    extra: Mapping[str, object] | None = None,
) -> None:
    """Log *msg* at WARNING the first time *key* fires on *log* in this
    process, at DEBUG on every later occurrence.

    For a check run in a loop (e.g. once per :mod:`pitloom.loom` call) whose
    failure persists: the first occurrence is reported, the rest are visible
    with ``--debug`` only.

    *key* is scoped by ``log.name``, so call sites on different loggers may
    reuse a key. *extra* is set on the record, as :meth:`logging.Logger.log`
    sets it.
    """
    log_once(log, logging.WARNING, key, msg, *args, extra=extra)


def log_once(
    log: logging.Logger,
    level: int,
    key: str,
    msg: str,
    *args: object,
    extra: Mapping[str, object] | None = None,
) -> None:
    """Log *msg* at *level* the first time *key* fires on *log* in this
    process, at DEBUG on every later occurrence (see :func:`warn_once`, which
    shares the keys: a value said once at one level is not said at another)."""
    dedup_key = (log.name, key)
    with _CONFIG_LOCK:
        first_occurrence = dedup_key not in _WARNED_ONCE
        _WARNED_ONCE.add(dedup_key)
    log.log(level if first_occurrence else logging.DEBUG, msg, *args, extra=extra)


def field_loss_suffix(status: str, *fields: str) -> str:
    """Build the `` | Field(s) affected (<status>): <fields>`` suffix for
    a WARNING logged when a failure drops or degrades SBOM/AIBOM data.

    *status* is ``"skipped"`` (field ends up unset) or ``"degraded"`` (a
    lower-quality value is still used). Each of *fields* is one field
    name, joined with ``", "`` -- a field may carry its own parenthetical
    note (e.g. ``"license (file-based detection)"``) when specific to it.
    """
    return f" | Field(s) affected ({status}): {', '.join(fields)}"


def one_line(value: object, limit: int | None = None) -> str:
    """*value*'s text with every whitespace run, newlines included,
    collapsed to one space, then escaped as :func:`loggable` does, so a
    multi-line exception message interpolated into a log message cannot
    spill untagged continuation lines onto stderr, nor forge a tagged one.
    An exception with no message yields its class name instead of an empty
    string. With *limit*, the collapsed text is cut to its first *limit*
    characters before it is escaped, so the cut never splits an escaped
    literal and loses its closing quote."""
    text = " ".join(str(value).split())[:limit]
    if not text and isinstance(value, BaseException):
        return type(value).__name__
    return loggable(text)
