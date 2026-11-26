# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The value of an HTTP header that carries a secret (``X-Api-Key: <key>``)
and of each cookie (``Cookie: sid=<value>``) in a text, as an HTTP client's
debug line or a printed request prints them: masked by
:func:`~pitloom.core.url_masking.masked_given_path`, the header name and the
cookie names kept (``X-Api-Key: ***``, ``Cookie: sid=***; theme=***``).

See also: :mod:`pitloom.core.url_masking._auth_schemes` (the
``Authorization`` header, masked before this pass) and
:mod:`pitloom.core.url_masking._boundary` (where a header name may start).
Standard library only.

The rule:

* **A header name** of :data:`SECRET_HEADERS` (any case), ``Cookie`` or
  ``Set-Cookie``, not glued to a letter, digit, ``_`` or ``-`` before it
  (``My-X-Api-Key`` is no such name) or right after an escape sequence;
  then an optional quote (``"``, ``'``, or ``\\"`` and ``\\\\\\"`` in JSON
  escaped once or twice), ``:`` between spaces, tabs or escaped tabs, and
  an optional quote; or a quote, ``,`` and a quote (a ``(name, value)``
  pair: ``[("X-Api-Key", "<key>")]``). A longer name (``X-Api-Key-Id``) is
  not the header. So a plain header line, a JSON or escaped JSON object, a
  Python ``dict`` repr and a list of pairs are read alike.
* **A secret header's value** is the run after it up to white space, a
  quote, a backslash, ``,`` or ``;``; a placeholder starting ``<``, ``$``,
  ``{`` or ``*`` (``<your key>``, ``${API_KEY}``, ``$GITLAB_TOKEN``, a
  value masked already) is kept. A scheme word first (``Bearer``, ``Basic``,
  ``token``) is kept and the run after it masked, as after
  ``Authorization:``. Prose after a header name is masked as after
  ``Authorization:`` (``the X-Api-Key: header must be set`` prints
  ``X-Api-Key: *** must be set``).
* **A cookie header's value**: the value of each ``name=value`` pair, up to
  ``;``, white space, a quote or a backslash (a quoted value from inside its
  quote to its closing quote, a space in it too: ``sid="a b"``), with the
  same placeholders kept; in ``Set-Cookie`` the attributes
  (``Path``, ``Domain``, ``Expires``, ``Max-Age``, ``SameSite``,
  ``Priority``, any case) keep their values. A cookie header's pairs end at
  the quote closing the one after its ``:``, if any.

Each header's value is read only up to the next header name of this pass
or the end of the line, so a line of many headers is read once.

Missed: a value on the line after its header name (a line break never joins
them here), a second word of a value (``X-Api-Key: abc def`` prints
``X-Api-Key: *** def``), and a header name that the ``Authorization`` pass
masked as its credential (``Authorization: Bearer X-Api-Key: v``). The
order is kept so: run first, this pass would end a value at a terminal
sequence's ``;`` and hide a scheme word from the ``Authorization`` pass
(``X-Api-Key: Bearer\x1b[0;1m<key>``). Prose
quoting a header name before another quoted word loses that word, read as a
pair (``the "X-Api-Key", "Accept" headers`` prints ``"X-Api-Key", "***"``).
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterator

from pitloom.core.url_masking._boundary import word_start

__all__ = ["SECRET_HEADERS", "mask_secret_headers"]

#: The header names whose value is a secret, matched in any case: a closed
#: list, so a name merely holding ``key`` or ``token`` (``Cache-Key``,
#: ``Public-Key``, ``Session-Id``) is kept. Sorted; one name per line.
SECRET_HEADERS = (
    "Access-Token",
    "Api-Key",
    "Job-Token",
    "Ocp-Apim-Subscription-Key",
    "Private-Token",
    "X-Access-Token",
    "X-Amz-Security-Token",
    "X-Api-Key",
    "X-Auth-Token",
    "X-Goog-Api-Key",
    "X-JFrog-Art-Api",
    "X-Registry-Auth",
    "X-Vault-Token",
)
#: The headers whose every ``name=value`` value is masked, in lower case.
_COOKIE_HEADERS = ("cookie", "set-cookie")
#: The ``Set-Cookie`` attributes (RFC 6265 and its successors), whose values
#: are kept.
_COOKIE_ATTRIBUTES = frozenset(
    {
        "domain",
        "expires",
        "httponly",
        "max-age",
        "partitioned",
        "path",
        "priority",
        "samesite",
        "secure",
    }
)
#: The scheme words a secret header's value may start with, kept.
_SCHEME_WORDS = frozenset({"basic", "bearer", "token"})
#: Spaces, tabs and escaped tabs around a header's ``:``: no line break.
_GAP = r"(?:[ \t]|\\{1,2}t)*"
#: A quote, also escaped once or twice (``\\"``, ``\\\\\\"``).
_QUOTED = r"\\{0,3}[\"']"
#: What stands between a header name and its value: an optional quote and
#: ``:``, or a quote and ``,`` before a quote (a ``(name, value)`` pair:
#: ``("X-Api-Key", "v")``); spaces, tabs or escaped tabs around either.
_COLON = f"(?:(?:{_QUOTED})?{_GAP}:|{_QUOTED}{_GAP},(?={_GAP}{_QUOTED}))"
#: An optional quote after a header's ``:`` (group ``open``).
_OPEN = f"(?P<open>{_QUOTED})?"
#: A header name of this pass, its ``:`` and what is around it.
_HEADER_RE = re.compile(
    "(?=[AaCcJjOoPpSsXx])"
    + word_start("A-Za-z0-9_-")
    + "(?P<name>(?i:"
    + "|".join(re.escape(name) for name in (*SECRET_HEADERS, *_COOKIE_HEADERS))
    + "))"
    + _COLON
    + _GAP
    + _OPEN
)
#: The first characters of a placeholder (``<your key>``, ``${API_KEY}``,
#: ``$TOKEN``, a value masked already), kept as a header's or a cookie's
#: value.
_PLACEHOLDER_STARTS = "<${*"
#: A secret header's value, or the run after its scheme word.
_VALUE = re.compile(rf"[^\s\"'\\,;{re.escape(_PLACEHOLDER_STARTS)}][^\s\"'\\,;]*")
#: The separators after a scheme word.
_SEPARATORS = re.compile(r"(?:[ \t]|\\{1,2}t)+")
#: A raw or escaped line break: where a header's value ends at the latest.
_LINE_END = re.compile(r"[\r\n]|\\{1,2}[rn]")
#: A cookie's ``name=value`` (group ``value``, a quoted one from inside its
#: quote). The name starts after a character no name holds, so each run of
#: name characters is tried once.
_PAIR = re.compile(
    r"(?<![^\s=;,\"'\\:])(?P<name>[^\s=;,\"'\\:]+)="
    r"(?:\\{0,3}\"(?P<quoted>[^\"\\\r\n]*)(?=\\{0,3}\")"
    r"|(?:\\{0,3}\")?(?P<value>[^\s;\"\\]*))"
)
#: The quote closing a cookie header's value, by the quote that opened it:
#: one no backslash escapes, or after an escaped quote, the next quote.
_CLOSE = {
    '"': re.compile(r'(?<!\\)"'),
    "'": re.compile(r"(?<!\\)'"),
    '\\"': re.compile('"'),
    "\\'": re.compile("'"),
}


def _value_spans(text: str, start: int, stop: int) -> Iterator[tuple[int, int]]:
    """The secret value of a header whose value starts at *start*, read up
    to *stop*: a scheme word is kept and the run after it masked."""
    found = _VALUE.match(text, start, stop)
    if found is None:
        return
    if found.group().lower() not in _SCHEME_WORDS:
        yield found.span()
        return
    gap = _SEPARATORS.match(text, found.end(), stop)
    run = None if gap is None else _VALUE.match(text, gap.end(), stop)
    if run is not None:
        yield run.span()


def _cookie_spans(
    text: str, header: re.Match[str], stop: int
) -> Iterator[tuple[int, int]]:
    """The cookie values of a ``Cookie`` or ``Set-Cookie`` *header*, read up
    to *stop* or the quote closing its value."""
    start = header.end()
    opened = header.group("open")
    if opened is not None:
        closing = _CLOSE[opened if len(opened) == 1 else "\\" + opened[-1]]
        close = closing.search(text, start, stop)
        stop = stop if close is None else close.start()
    attributes = header.group("name").lower() == "set-cookie"
    for pair in _PAIR.finditer(text, start, stop):
        group = "value" if pair.group("quoted") is None else "quoted"
        value = pair.group(group)
        if not value or value[0] in _PLACEHOLDER_STARTS:
            continue
        if attributes and pair.group("name").lower() in _COOKIE_ATTRIBUTES:
            continue
        yield pair.span(group)


def _spans_of_header(
    text: str, header: re.Match[str], following: re.Match[str] | None
) -> Iterator[tuple[int, int]]:
    """The secret of one *header* of *text*, in order, read up to the
    *following* header name or the line end."""
    start = header.end()
    stop = len(text) if following is None else following.start()
    line_end = _LINE_END.search(text, start, stop)
    if line_end is not None:
        stop = line_end.start()
    if header.group("name").lower() in _COOKIE_HEADERS:
        yield from _cookie_spans(text, header, stop)
    else:
        yield from _value_spans(text, start, stop)


def _spans(text: str) -> Iterator[tuple[int, int]]:
    """The secret after each header name in *text*, in order."""
    headers = _HEADER_RE.finditer(text)
    header = next(headers, None)
    while header is not None:
        following = next(headers, None)
        yield from _spans_of_header(text, header, following)
        header = following


def mask_secret_headers(text: str) -> str:
    """*text* with the value of each secret header and each cookie written
    as ``***``, the header and cookie names kept (see the module's rule)."""
    if ":" not in text and "," not in text:
        return text
    out = io.StringIO()
    done = 0
    for start, end in _spans(text):
        out.write(text[done:start])
        out.write("***")
        done = end
    if not out.tell():
        return text
    out.write(text[done:])
    return out.getvalue()
