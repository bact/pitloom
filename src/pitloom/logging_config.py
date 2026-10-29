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
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, TextIO, cast
from urllib.parse import unquote

from pitloom.core.untrusted_text import DISPLAY_CONTROLS

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

#: The one ``WARNING:`` for an input over a cap, logged by
#: :func:`warn_over_cap`. Arguments: the key naming the input
#: (:attr:`Cap.subject`), the input (through :func:`loggable`), the cap
#: (:attr:`Cap.reason`), and what was and was not read or done.
OVER_CAP_WARNING = "%s=%s: %s; %s"

# The LogRecord attribute holding (cap, outcome) of an OVER_CAP_WARNING.
_OVER_CAP_ATTR = "pitloom_over_cap"

#: The LogRecord attribute holding a catalogued message's code
#: (:mod:`pitloom.messages`), printed as a trailing `` [code]``; an exception
#: carries its code in an attribute of the same name.
CODE_ATTR = "pitloom_code"
#: What a reader takes for a code (``family`` or ``family/variant``); one
#: that does not match whole is never printed. The catalogue's own grammar is
#: stricter (:data:`pitloom.messages.CODE_GRAMMAR`).
CODE_PATTERN = r"[a-z][a-z0-9/-]*"
_CODE_RE = re.compile(CODE_PATTERN)

#: The ``WARNING:`` for text holding a lone surrogate (U+D800 to U+DFFF),
#: written as text (:func:`~pitloom.core.untrusted_text.escape_lone_surrogates`).
#: Arguments: a prefix (``"FORMAT=<fmt> "`` for a model, else ``""``) and
#: the file, through :func:`loggable`.
LONE_SURROGATES_WARNING = "%sFILE=%s: lone surrogates written as \\uXXXX"

#: Keys already surfaced once via :func:`log_once` (and :func:`warn_once`)
#: in this process.
#: Keyed by ``(logger.name, key)`` so two independent call sites can't
#: collide by picking the same short key string.
_WARNED_ONCE: set[tuple[str, str]] = set()


#: ``://`` and a userinfo (non-empty, up to the last ``@`` before a ``/`` or
#: whitespace: a password holding ``?`` or ``#`` is masked whole).
_URL_USERINFO_RE = re.compile(r"://[^/\s@][^/\s]*@")


#: A URL in a text, to its end at whitespace.
_URL_RE = re.compile(r"://\S+")

#: A query or fragment parameter (name at most 64 characters, so matching is
#: linear), as ``(delimiter, name, value)``.
_PARAM_RE = re.compile(r"([?&;#])([\w.%-]{1,64})=([^&;#\s]*)")

#: Names (lower case) of a parameter that holds a secret, and the endings of
#: such a name (``access_token``, ``db-password``).
_SECRET_NAMES = frozenset(
    {
        "token",
        "key",
        "apikey",
        "secret",
        "password",
        "passwd",
        "pass",
        "pwd",
        "pw",
        "sig",
        "signature",
        "jwt",
        "credential",
        "credentials",
    }
)
_SECRET_ENDINGS = ("_token", "-token", "_secret", "-secret", "_key", "-key") + (
    "_password",
    "-password",
    "_signature",
    "-signature",
)

#: ``://`` and a userinfo of a text that is one URL: up to the last ``@``
#: before the first ``/``, whatever characters (a newline, a space) it holds.
#: ``:/`` and ``:\\`` too, for a URL a path normalisation collapsed.
_WHOLE_URL_USERINFO_RE = re.compile(r":[/\\]{1,2}[^/\\@][^/\\]*@")


def _mask_param(match: re.Match[str]) -> str:
    delimiter, name, value = match.groups()
    plain = unquote(name).lower()
    if plain in _SECRET_NAMES or plain.endswith(_SECRET_ENDINGS):
        value = "***"
    return f"{delimiter}{name}={value}"


def _mask_url_secrets(match: re.Match[str]) -> str:
    return _PARAM_RE.sub(_mask_param, match.group(0))


def sanitize_url_credentials(text: str) -> str:
    """Redact username and password from URLs in *text* (e.g.
    ``https://user:pass@host/`` -> ``https://***:***@host/``), and the value of
    a query parameter named like a secret (``?private_token=***``).

    Used across extractors, build backends, and error loggers to prevent
    sensitive auth tokens from leaking into error messages or SBOM output.
    The userinfo ends at the last ``@`` before the first ``/`` or whitespace,
    so a password holding ``@``, ``?`` or ``#`` is redacted whole. For a text
    that is one URL, use :func:`sanitize_url`.
    """
    return _URL_RE.sub(_mask_url_secrets, _URL_USERINFO_RE.sub("://***:***@", text))


def sanitize_url(url: str) -> str:
    """:func:`sanitize_url_credentials` for a text that is one URL: the
    userinfo is redacted whole even when it holds a newline or a space."""
    return sanitize_url_credentials(_WHOLE_URL_USERINFO_RE.sub("://***:***@", url))


#: The name prefix of the temporary directory a Git URL is checked out in.
CHECKOUT_DIR_PREFIX = "pitloom-git-"
#: What a message shows for that directory, so two runs read the same.
CHECKOUT_PLACEHOLDER = "<checkout>"
#: ``tempfile.mkdtemp`` appends eight characters of ``[a-z0-9_]``: a directory
#: of another name (a worktree called ``pitloom-git-fix``) is not the checkout.
_CHECKOUT_DIR = re.compile(
    re.escape(CHECKOUT_DIR_PREFIX) + r"[a-z0-9_]{8}(?![a-z0-9_])"
)
#: A word of a message: a run without a space, quote, bracket, backtick, ``=``,
#: ``,`` or ``;`` (where a path ends in a message that quotes, brackets or
#: follows ``KEY=``).
_WORD = re.compile(r"[^\s'\"`()\[\]<>=,;]+")
#: ``user@host:path``, the scp-style address of a repository.
_SCP_ADDRESS = re.compile(r"[\w.+-]+@[\w.-]+:")


def _mask_word(found: re.Match[str]) -> str:
    word = found.group(0)
    if (
        CHECKOUT_DIR_PREFIX not in word
        or "://" in word
        or _SCP_ADDRESS.match(word) is not None
    ):
        return word
    last = deque(_CHECKOUT_DIR.finditer(word), maxlen=1)
    return CHECKOUT_PLACEHOLDER + word[last[0].end() :] if last else word


def mask_checkout(text: str) -> str:
    """*text* with the temporary checkout of a Git URL written as
    ``<checkout>``: each word that is a path holding the directory
    (``pitloom-git-`` and its eight random characters) becomes ``<checkout>``
    and what follows the directory, so a path below it keeps its tail
    (``<checkout>/setup.cfg``). A word that is an address (``https://host/o/
    pitloom-git-abcdefgh``, ``git@host:o/pitloom-git-abcdefgh``) is kept. One
    pass over the words; text without the prefix is returned as it is."""
    if CHECKOUT_DIR_PREFIX not in text:
        return text
    return _WORD.sub(_mask_word, text)


def escape_controls(text: str) -> str:
    """*text* with the temporary checkout of a Git URL masked
    (:func:`mask_checkout`), each character that is not printable, and each
    code point of :data:`~pitloom.core.untrusted_text.DISPLAY_CONTROLS`,
    written as its ASCII escape (``\\n``, ``\\x1b``, ``\\u202e``); anything
    else, non-ASCII letters included, is kept. Unlike :func:`loggable` it never
    quotes, so a message already built stays readable."""
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


class _OneLineFormatter(logging.Formatter):
    """``LEVEL: message`` with the message escaped by :func:`escape_controls`:
    whatever a call site interpolated, one record is one tagged line on
    stderr; a record's :data:`CODE_ATTR` follows it (``DEBUG`` lines carry
    none). A traceback (``exc_info``) is appended as it is."""

    def formatMessage(self, record: logging.LogRecord) -> str:
        code = (
            getattr(record, CODE_ATTR, None) if record.levelno > logging.DEBUG else None
        )
        record.message = escape_controls(record.message) + _code_suffix(code)
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
    catalogued *code* follows as `` [code]``."""
    print(f"ERROR: {escape_controls(message)}{_code_suffix(code)}", file=sys.stderr)


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


@dataclass(frozen=True)
class Cap:
    """A limit Pitloom puts on an input, as :func:`warn_over_cap` names it:
    ``<subject>=<where>: larger than the <limit>-<unit> <purpose> cap``."""

    #: The most the input may hold, in *unit*.
    limit: int
    #: What *limit* counts, singular (``"byte"``, ``"entry"``).
    unit: str
    #: What the cap is for (``"license-detection"``).
    purpose: str
    #: The key naming the input, ``"FILE"`` or ``"FIELD"``, after the keys
    #: of :meth:`after` (``"FORMAT=gguf FILE"``).
    subject: str = "FILE"

    @property
    def reason(self) -> str:
        """What an input over this cap is, the same in a ``WARNING:`` and
        in an error's text."""
        return f"larger than the {self.limit}-{self.unit} {self.purpose} cap"

    def after(self, keys: str) -> Cap:
        """This cap, its input named after *keys* (``"FORMAT=gguf"``,
        trusted text): the keys a subsystem puts first."""
        return replace(self, subject=f"{keys} {self.subject}")


def warn_over_cap(
    log: logging.Logger,
    cap: Cap,
    where: str,
    outcome: str = "skipped",
    *,
    once: bool = False,
    key: str | None = None,
) -> None:
    """The one ``WARNING:`` for an input over *cap*: *where* names the
    input (escaped through :func:`loggable`), *outcome* what was read and
    what was not. *once*: through :func:`warn_once`, once per cap and
    input in this process, the input known by *key* (default *where*)
    when two spellings name one input. The record carries *cap* and
    *outcome* for :func:`over_cap_of`."""
    args = (cap.subject, loggable(where), cap.reason, outcome)
    extra = {_OVER_CAP_ATTR: (cap, outcome)}
    if once:
        seen = f"over-cap:{cap.purpose}:{where if key is None else key}"
        warn_once(log, seen, OVER_CAP_WARNING, *args, extra=extra)
    else:
        log.warning(OVER_CAP_WARNING, *args, extra=extra)


def over_cap_of(record: logging.LogRecord) -> tuple[Cap, str] | None:
    """The cap and outcome of a record :func:`warn_over_cap` logged, so a
    caller relaying it can name the input in its own words; else ``None``."""
    found: tuple[Cap, str] | None = getattr(record, _OVER_CAP_ATTR, None)
    return found


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
