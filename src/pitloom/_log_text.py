# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Untrusted text written into a log message: escaped, masked, on one line.

See also: :mod:`pitloom.logging_config`, which re-exports every name here
(callers import them from there), and :mod:`pitloom.log_masking` (the
masker these writers call).
"""

from __future__ import annotations

import http.client
import re
from collections.abc import Callable

from pitloom.core.untrusted_text import DISPLAY_CONTROLS
from pitloom.log_masking import masked_text


def loggable(text: str) -> str:
    """*text* as is when printable, else its ASCII-escaped literal, so
    untrusted text (an archive member name, an exception message quoting
    one) cannot forge a second tagged line, e.g. ``::error::``, on stderr.

    The one escaping every message interpolating such text goes through.
    Text holding a code point of
    :data:`~pitloom.core.untrusted_text.DISPLAY_CONTROLS` is escaped too,
    printable or not (U+034F is a printable combining mark). It masks
    nothing, neither the temporary checkout nor a credential: ``KEY=VALUE``
    data on stdout goes through it and must stay as it is
    (:func:`pitloom.cli.kv_output.kv_line` masks only a URL's credentials;
    messages are masked by :func:`escape_controls`).
    """
    if text.isprintable() and DISPLAY_CONTROLS.isdisjoint(text):
        return text
    return ascii(text)


#: Characters of a value :func:`excerpt` shows.
EXCERPT_CHARS = 120


def excerpt(value: object) -> str:
    """*value* for a warning as one literal, escaped once: the credentials
    of a URL in it masked (:func:`~pitloom.log_masking.masked_text`), then
    on one line, then at most :data:`EXCERPT_CHARS` characters, ``...``
    after it when cut. Masked before its white space is collapsed, so a
    password holding a line break or a tab is masked whole, and before it
    is cut, so a cut never takes away the end of a URL's user information
    and shows its start. A string is its ``repr`` when
    printable, else its ASCII-escaped literal (:func:`loggable`); any other
    value is its ``repr``, escaped alike."""
    is_text = isinstance(value, str)
    raw = value if isinstance(value, str) else repr(value)
    # Masked again once collapsed: a scheme word and its credential split by
    # a line break read as one run only after it.
    text = masked_text(" ".join(masked_text(raw).split()))
    cut = text[:EXCERPT_CHARS]
    escaped = loggable(cut)
    literal = repr(cut) if is_text and escaped == cut else escaped
    return literal + ("..." if len(text) > EXCERPT_CHARS else "")


def one_line(
    value: object,
    limit: int | None = None,
    *,
    ellipsis: bool = False,
    steady: Callable[[str], str] | None = None,
) -> str:
    """*value*'s text with every whitespace run, newlines included,
    collapsed to one space, then escaped as :func:`loggable` does, so a
    multi-line exception message interpolated into a log message cannot
    spill untagged continuation lines onto stderr, nor forge a tagged one.
    The credentials of a URL in it are masked
    (:func:`~pitloom.log_masking.masked_text`). An
    exception with no message yields its class name instead of an empty
    string. With *limit*, the collapsed text is masked, then cut to its
    first *limit* characters, then escaped: a cut never takes away the end
    of a URL's user information and shows its start, nor splits an escaped
    literal and loses its closing quote. With *ellipsis*, ``...`` follows a
    cut. With *steady*, the collapsed text goes through it first (to drop
    what differs per run) and is collapsed again, so what the cut keeps is
    the same on every run, and an exception whose whole text it drops
    yields its class name. *steady* runs before the masker, so the masker
    reads the text as shown: a drop cannot join two harmless pieces into
    a credential it never saw (``https://u:pw(Request ID: a)@h``). One
    masker pass on the steadied text, not one before and one after, keeps
    the cost of a long text at one pass."""
    text = " ".join(str(value).split())
    if steady is not None:
        text = " ".join(steady(text).split())
    if not text and isinstance(value, BaseException):
        return type(value).__name__
    masked = masked_text(text)
    shown = loggable(masked[:limit])
    if ellipsis and limit is not None and len(masked) > limit:
        return f"{shown}..."
    return shown


def failure_reason(
    failure: BaseException,
    limit: int | None = None,
    *,
    ellipsis: bool = False,
    steady: Callable[[str], str] | None = None,
) -> str:
    """The text of *failure* for a message, as :func:`one_line` writes it
    (*limit*, *ellipsis* and *steady* as there).

    An :class:`http.client.InvalidURL` quotes the path of the URL it
    refused, without its scheme (``'/x?token=...'``), where no URL masking
    finds a secret parameter: only its text before the first quoted value
    is written (``URL can't contain control characters.``), its class name
    when that is empty or *steady* drops all of it. The message naming the
    failure names the URL itself, masked."""
    if isinstance(failure, http.client.InvalidURL):
        head = _QUOTED_VALUE.split(str(failure), maxsplit=1)[0].rstrip(" :")
        shown = one_line(head, limit, ellipsis=ellipsis, steady=steady)
        return shown or type(failure).__name__
    return one_line(failure, limit, ellipsis=ellipsis, steady=steady)


#: Where a quoted value (a ``repr``) starts in an exception's text: a quote
#: at the start or after white space, not an apostrophe (``can't``).
_QUOTED_VALUE = re.compile(r"(?:^|\s)['\"]")
