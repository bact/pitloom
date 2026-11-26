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


def escaped_literal(text: str) -> str:
    """*text* as is when printable, else its ASCII-escaped literal, so
    untrusted text (an archive member name, an exception message quoting
    one) cannot forge a second tagged line, e.g. ``::error::``, on stderr.

    Text holding a code point of
    :data:`~pitloom.core.untrusted_text.DISPLAY_CONTROLS` is escaped too,
    printable or not (U+034F is a printable combining mark). It masks
    nothing: for ``KEY=VALUE`` data on stdout, which must stay as it is
    (:func:`pitloom.cli.kv_output.kv_line`), and for a writer that has
    masked its text already (:func:`one_line`, :func:`excerpt`); any other
    text goes through :func:`loggable`."""
    if text.isprintable() and DISPLAY_CONTROLS.isdisjoint(text):
        return text
    return ascii(text)


def loggable(text: str) -> str:
    """*text* as is when printable, else masked
    (:func:`~pitloom.log_masking.masked_text`), then its ASCII-escaped
    literal (:func:`escaped_literal`): the one escaping every message
    interpolating untrusted text goes through.

    Masked before it is escaped, so an escape (``\\t``, ``\\u200b``,
    ``\\xe4``) cannot stand inside a credential, or between it and what
    the masker reads before it. A printable text is returned as it is: the
    log sink masks it as it is printed
    (:class:`~pitloom.log_masking.MaskingRecordFactory`)."""
    if text.isprintable() and DISPLAY_CONTROLS.isdisjoint(text):
        return text
    return escaped_literal(masked_text(text))


def collapsed(text: str, steady: Callable[[str], str] | None = None) -> str:
    """*text* on one line, masked: masked
    (:func:`~pitloom.log_masking.masked_text`, which reads a multi-line
    text whole), then every white space run collapsed to one space; with
    *steady*, then put through it (to drop what differs per run) and
    collapsed again; then masked again.

    Two passes, as each step can both split and join a credential. The
    first, before the collapse: a line break or a tab inside a password
    turns into a space, which ends the user information and shows both
    halves (``https://u:pa\\nss@h``). The second, after it: a drop can join
    two harmless pieces into a credential the first never saw
    (``https://u:pw(Request ID: a)@h``), and a collapse moves a header's
    value up beside its name (``Authorization: Bearer\\nabc``). A drop
    that glues a masked token to the word before it (``abc(Request ID:
    a)ghp_...``) leaves it masked, since the first pass masked it.

    Before the first pass, each white space the collapse makes a space but
    the masker reads as the end of a URL in a line (:data:`_URL_ENDING_SPACE`:
    U+00A0, U+3000, ...) is a tab, which the masker reads inside a user
    information as a URL parser deletes it: else the collapse would split a
    password holding one in two shown halves. A text with no credential
    shows the same, as the collapse makes a tab a space too."""
    text = " ".join(masked_text(_URL_ENDING_SPACE.sub("\t", text)).split())
    if steady is not None:
        text = " ".join(steady(text).split())
    return masked_text(text)


#: White space (:meth:`str.isspace`, as :meth:`str.split` reads it) other
#: than a space, a tab and a line break (:meth:`str.splitlines`): the
#: masker reads each as the end of a URL in a line, where the collapse
#: makes it a space.
_URL_ENDING_SPACE = re.compile(r"[^\S \t\n\r\x0b\x0c\x1c-\x1e\x85\u2028\u2029]")


#: Characters of a value :func:`excerpt` shows.
EXCERPT_CHARS = 120


def excerpt(value: object) -> str:
    """*value* for a warning as one literal, escaped once: on one line and
    masked (:func:`collapsed`: masked before and after its white space is
    collapsed), then at most :data:`EXCERPT_CHARS` characters, ``...``
    after it when cut, then escaped. Masked before it is cut, so a cut
    never takes away the end of a URL's user information and shows its
    start, and before it is escaped, so an escape never stands inside a
    credential. A string is its ``repr`` when printable, else its
    ASCII-escaped literal (:func:`escaped_literal`); any other value is its
    ``repr``, escaped alike."""
    is_text = isinstance(value, str)
    raw = value if isinstance(value, str) else repr(value)
    text = collapsed(raw)
    cut = text[:EXCERPT_CHARS]
    escaped = escaped_literal(cut)
    literal = repr(cut) if is_text and escaped == cut else escaped
    return literal + ("..." if len(text) > EXCERPT_CHARS else "")


def one_line(
    value: object,
    limit: int | None = None,
    *,
    ellipsis: bool = False,
    steady: Callable[[str], str] | None = None,
) -> str:
    """*value*'s text on one line and masked (:func:`collapsed`: every white
    space run, newlines included, one space; the credentials in it masked
    before and after the collapse), then escaped
    (:func:`escaped_literal`), so a multi-line exception message
    interpolated into a log message cannot spill untagged continuation
    lines onto stderr, nor forge a tagged one, and a password holding a
    line break is masked whole. An exception with no message yields its
    class name instead of an empty string. With *limit*, the masked text
    is cut to its first *limit* characters, then escaped: a cut never takes
    away the end of a URL's user information and shows its start, nor
    splits an escaped literal and loses its closing quote. With *ellipsis*,
    ``...`` follows a cut. With *steady*, the collapsed text goes through it
    (to drop what differs per run) between the two masker passes, so what
    the cut keeps is the same on every run, a drop cannot join two pieces
    into a credential the second pass does not read, and an exception whose
    whole text it drops yields its class name."""
    text = collapsed(str(value), steady)
    if not text and isinstance(value, BaseException):
        return type(value).__name__
    shown = escaped_literal(text[:limit])
    if ellipsis and limit is not None and len(text) > limit:
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
