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

import logging
import os
import sys
import threading
from collections.abc import Mapping
from dataclasses import dataclass, replace

from pitloom.core.untrusted_text import DISPLAY_CONTROLS

# Guards the handlers.clear()/addHandler() swap below (see
# configure_logging()'s docstring) and the _WARNED_ONCE read-then-write in
# warn_once() -- one lock for all shared mutable state in this module.
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

#: The ``WARNING:`` for text holding a lone surrogate (U+D800 to U+DFFF),
#: written as text (:func:`~pitloom.core.untrusted_text.escape_lone_surrogates`).
#: Arguments: a prefix (``"FORMAT=<fmt> "`` for a model, else ``""``) and
#: the file, through :func:`loggable`.
LONE_SURROGATES_WARNING = "%sFILE=%s: lone surrogates written as \\uXXXX"

#: Keys already surfaced once via :func:`warn_once` in this process.
#: Keyed by ``(logger.name, key)`` so two independent call sites can't
#: collide by picking the same short key string.
_WARNED_ONCE: set[tuple[str, str]] = set()


def loggable(text: str) -> str:
    """*text* as is when printable, else its ASCII-escaped literal, so
    untrusted text (an archive member name, an exception message quoting
    one) cannot forge a second tagged line, e.g. ``::error::``, on stderr.

    The one escaping every message interpolating such text goes through.
    Text holding a code point of
    :data:`~pitloom.core.untrusted_text.DISPLAY_CONTROLS` is escaped too,
    printable or not (U+034F is a printable combining mark).
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
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    with _CONFIG_LOCK:
        logger.setLevel(level)
        logger.handlers = [handler]


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
    dedup_key = (log.name, key)
    with _CONFIG_LOCK:
        first_occurrence = dedup_key not in _WARNED_ONCE
        _WARNED_ONCE.add(dedup_key)
    level = logging.WARNING if first_occurrence else logging.DEBUG
    log.log(level, msg, *args, extra=extra)


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
