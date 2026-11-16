# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The scanner of :func:`pitloom.core.url_masking.strip_url_secrets` and
:func:`pitloom.core.url_masking.holds_url_credentials`: where the URLs of a
free text are, their user information and their secret parameters.

See also: :mod:`pitloom.core.url_masking` (the public functions),
:mod:`pitloom.core.url_masking._userinfo` (the user information rule) and
:mod:`pitloom.core.url_masking._params` (the secret names). Standard
library only.

A URL starts at ``scheme://`` (the scheme from the first letter of a run of
scheme characters: ``1.https://``; a special scheme, ``http``, ``https``,
``ftp``, ``ws``, ``wss`` or ``file``, also at ``:/``, ``:\\`` and more
separators, as a browser reads ``https:/u:p@h``). With *wide* (the
detector), as the masker reads one: any scheme of two letters or more also
at one ``/`` or ``\\`` or more (:data:`WIDE_URL_START`), with a user
information unless a path separator comes before it.

Two readings (:mod:`pitloom.core.url_masking._userinfo`). In *free text* a
URL's user information is read in free text, and its rest runs to white
space, a quote, a backtick or an angle bracket, without the punctuation
that ends a sentence (``.``, ``,``, ``'``...) or a closing bracket it does
not open (``(see https://h/x)``). When the text *is* one URL (*whole*: a URL
field), each URL in it is read as ``urllib`` reads it: no quote, bracket or
white space ends anything, and nothing is trimmed from its end. A URL inside
another (``?r=https://u:p@h``) is read on its own: the outer one ends where
it starts, unless it is inside a secret value, which runs over it.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from collections import defaultdict, deque
from dataclasses import dataclass, field

from pitloom.core.url_masking._params import (
    PARAM_HEAD,
    WHOLE_PARAM_RE,
    is_secret_name,
    is_secret_param,
    iter_params,
    param_run,
)
from pitloom.core.url_masking._userinfo import (
    has_userinfo,
    is_account_name,
    userinfo_end,
)

#: A run of scheme characters holding a letter, followed by ``://``. A run
#: only starts after a character that is none, and the letter is its first
#: one, so each run is tried once and a search stays linear.
_URL_START = re.compile(
    r"(?<![A-Za-z0-9+.-])(?:(?i:https?|ftp|wss?|file):[/\\]+"
    r"|[0-9+.-]*[A-Za-z][A-Za-z0-9+.-]*://)"
)
#: The same for the detector (*wide*), as the masker reads a URL: any scheme
#: of two letters or more after one or more ``/`` or ``\\`` too
#: (``s3:/u:p@h``, ``ssh:\\\\u:p@h``).
WIDE_URL_START = re.compile(
    r"(?<![A-Za-z0-9+.-])(?:[0-9+.-]*[A-Za-z][A-Za-z0-9+.-]+:[/\\]+"
    r"|[0-9+.-]*[A-Za-z]://[/\\]*)"
)
_LETTER = re.compile(r"[A-Za-z]")
#: Where the rest of a URL in free text ends.
_URL_TAIL = re.compile(r"[\s\"<>`]")
_SLASH = re.compile("/")
_HEAD = re.compile(PARAM_HEAD)
_DELIMITER = re.compile("[&;#]")
#: How many secret parameter values the end of a user information is moved
#: out of at most (each step reads the user information again).
_SECRET_STEPS = 8
#: Where a parameter value ends, in free text and in a URL field.
_VALUE_END = re.compile(r"[&;#\s\"<>`]")
_FIELD_VALUE_END = re.compile(r"[&;#]")
_BRACKET = re.compile(r"[()\[\]{}]")
#: The punctuation that ends a sentence or a quotation after a URL.
_TRAILING = ".,;:!?'"
#: A closing bracket and the one opening it: trailing, it is the URL's only
#: when the URL opens it.
_CLOSERS = {")": "(", "]": "[", "}": "{"}
#: How many characters after a URL are read as punctuation at most.
_TRIM_REACH = 64


@dataclass
class FoundUrl:
    """A URL of a text: its span, its user information and the parameters
    the masker masks."""

    start: int
    end: int
    #: The span of the user information (from after ``://`` to its ``@``).
    userinfo: tuple[int, int] | None = None
    #: Whether that user information is an account name (``git@``).
    account: bool = False
    #: Where the text after a removed user information resumes: after its
    #: ``@``, or after the secret value that ``@`` is in.
    cut: int = 0
    #: Each parameter named like a secret in a message, as (start, value
    #: start, end, removed from an SBOM).
    params: list[tuple[int, int, int, bool]] = field(default_factory=list)


class _Memo:
    """The first match of *pattern* in *text* at or after a position,
    remembered while the asked positions stay before it, so asking in order
    reads each character a bounded number of times."""

    def __init__(self, text: str, pattern: re.Pattern[str]) -> None:
        self.text = text
        self.pattern = pattern
        self._asked = len(text) + 1
        self._found: re.Match[str] | None = None

    def search(self, pos: int) -> re.Match[str] | None:
        found = self._found
        end = len(self.text) if found is None else found.start()
        if not self._asked <= pos <= end:
            found = self._found = self.pattern.search(self.text, pos)
            self._asked = pos
        return found

    def start(self, pos: int) -> int:
        found = self.search(pos)
        return len(self.text) if found is None else found.start()


class _Brackets:
    """Where each bracket of a text is, found on the first question, so the
    brackets of any stretch are counted without reading it."""

    def __init__(self, text: str) -> None:
        self.text = text
        self._at: defaultdict[str, list[int]] | None = None

    def count(self, char: str, start: int, end: int) -> int:
        if self._at is None:
            self._at = defaultdict(list)
            for found in _BRACKET.finditer(self.text):
                self._at[found.group()].append(found.start())
        at = self._at[char]
        return bisect_left(at, end) - bisect_left(at, start)

    def trimmed_end(self, start: int, end: int) -> int:
        """*end* moved back over the punctuation that ends a sentence and
        over each closing bracket the text from *start* does not open, by
        :data:`_TRIM_REACH` characters at most (a text's sentence ends in
        fewer), so asking for many URLs of one stretch stays linear."""
        opened: dict[str, int] = {}
        low = max(start, end - _TRIM_REACH)
        while end > low:
            char = self.text[end - 1]
            if char not in _TRAILING:
                opener = _CLOSERS.get(char)
                if opener is None:
                    break
                if char not in opened:
                    opened[char] = self.count(opener, start, end) - self.count(
                        char, start, end
                    )
                if opened[char] >= 0:
                    break
                opened[char] += 1
            end -= 1
        return end


class _Reader:
    """The URLs of a free text, read in order."""

    def __init__(self, text: str, *, whole: bool, wide: bool) -> None:
        self.text = text
        self.whole = whole
        self.wide = wide
        self.starts = _Memo(text, WIDE_URL_START if wide else _URL_START)
        self._tails = _Memo(text, _URL_TAIL)
        self._slashes = _Memo(text, _SLASH)
        self._brackets = _Brackets(text)
        self._trim: tuple[tuple[int, int], int] = ((-1, -1), -1)
        #: The (host start, end) of the URL read as a field, whose end is
        #: not trimmed.
        self._field: tuple[int, int] | None = None

    def next_url(self, pos: int) -> FoundUrl | None:
        """The first URL at or after *pos*, or ``None``."""
        run = self.starts.search(pos)
        if run is None:
            return None
        letter = _LETTER.search(self.text, run.start(), run.end())
        return self.url(run, run.end() if letter is None else letter.start())

    def url(self, run: re.Match[str], scheme: int) -> FoundUrl:
        """The URL whose scheme starts at *scheme* and whose separator ends
        the *run*."""
        start = run.end()
        found = FoundUrl(scheme, start)
        one = self.whole
        at = None
        colon = self.text.index(":", scheme)
        if not self.wide or has_userinfo(self.text, scheme, colon + 1):
            at = self._userinfo_end(start, self._slashes.start(start))
        host = start
        if at is not None:
            at, host = self._outside_secret_value(start, at, one=one)
        if at is not None:
            found.userinfo = (start, at)
            name = self.text[scheme:colon]
            found.account = is_account_name(name, self.text[start:at])
            found.cut = host = max(host, at + 1)
        rest_end = len(self.text) if one else self._tails.start(host)
        self._field = (host, rest_end) if one else None
        found.end = self._params(found, host, rest_end)
        return found

    def _userinfo_end(self, start: int, end: int) -> int | None:
        """:func:`userinfo_end` of the authority from *start* to *end*, in
        this reader's reading."""
        return userinfo_end(self.text, start, end, free_text=not self.whole)

    def _outside_secret_value(
        self, start: int, at: int, *, one: bool
    ) -> tuple[int, int]:
        """The ``@`` ending the user information from *start* to *at*, and
        where the host starts, read so that the ``@`` is in no secret
        parameter's value (``https://u:#P@h?token=a@b``: ``P@`` ends it).
        When no ``@`` before such a parameter can (``https://u:p?token=x@h``,
        as RFC 3986 reads it), or more than :data:`_SECRET_STEPS` parameters
        would be stepped over, the rest of the value is removed with the user
        information: the host starts after the value."""
        first = at
        for _ in range(_SECRET_STEPS):
            head = self._secret_head(start, at)
            if head is None:
                return at, at + 1
            if self.text.rfind("@", start, head) <= start:
                first = at
                break
            # The part before the head holds an ``@`` and the same first
            # break, so it has a user information; ``or`` keeps *at* if not.
            at = self._userinfo_end(start, head) or at
        value_end = (_FIELD_VALUE_END if one else _VALUE_END).search(
            self.text, first + 1
        )
        return first, len(self.text) if value_end is None else value_end.start()

    def _secret_head(self, start: int, at: int) -> int | None:
        """Where the parameter named like a secret whose value holds the
        ``@`` at *at* starts, if one from *start* does."""
        heads = deque(_HEAD.finditer(self.text, start, at), maxlen=1)
        if not heads or _DELIMITER.search(self.text, heads[0].end(), at):
            return None
        return heads[0].start() if is_secret_name(heads[0].group("name")) else None

    def _trimmed(self, host: int, rest_end: int) -> int:
        """:meth:`_Brackets.trimmed_end` of the rest of a URL, found once
        per URL."""
        if self._field == (host, rest_end):
            return rest_end
        if self._trim[0] != (host, rest_end):
            self._trim = ((host, rest_end), self._brackets.trimmed_end(host, rest_end))
        return self._trim[1]

    def _params(self, found: FoundUrl, host: int, rest_end: int) -> int:
        """Add to *found* each parameter after *host* named like a secret,
        and return where the URL ends: at *rest_end* without the punctuation
        after it (:meth:`_trimmed`: the last URL before *rest_end* only
        asks), or where a URL inside it starts, unless a secret value runs
        over that start."""
        pos = host
        while True:
            bound = self.starts.start(pos)
            final = bound >= rest_end
            if final:
                bound = self._trimmed(host, rest_end)
            rest = None if final else (host, rest_end)
            resume = self._segment(found, (pos, bound), rest)
            if resume is None:
                return bound
            pos = resume

    def _segment(
        self, found: FoundUrl, span: tuple[int, int], rest: tuple[int, int] | None
    ) -> int | None:
        """Add to *found* each parameter in *span* named like a secret; a
        removed one whose value reaches the end of a *span* that a URL
        inside ends runs on over it, to the end of the *rest* (host, end).
        Return where such a value ends, else ``None``."""
        pos, bound = span
        for param in iter_params(WHOLE_PARAM_RE, self.text, pos, bound, weak=False):
            if not is_secret_param(param):
                continue
            removed = is_secret_param(param, weak=False)
            whole = param
            if removed and rest is not None and param.end() == bound:
                end = self._trimmed(*rest)
                run = param_run(WHOLE_PARAM_RE, self.text, param.start(), end)
                whole = run or param
            found.params.append((whole.start(), whole.start(3), whole.end(), removed))
            if whole is not param:
                return whole.end()
        return None


def find_urls(text: str, *, whole: bool, wide: bool = False) -> list[FoundUrl]:
    """Each URL of *text*, in order (the readings: this module's
    docstring); *whole* when *text* is one URL (a URL field). With *wide*
    (the detector), as a masker reads them: a URL of any scheme after one
    ``/`` or ``\\`` too, with a user information unless a path separator
    comes before it (:func:`has_userinfo`)."""
    reader = _Reader(text, whole=whole, wide=wide)
    urls: list[FoundUrl] = []
    while (found := reader.next_url(urls[-1].end if urls else 0)) is not None:
        urls.append(found)
    return urls


class _Plain:
    """The pieces of a URL being rebuilt without its removed parameters: a
    ``?`` or ``#`` that starts a removed one is written only when a
    parameter follows (``?token=T&&a=1`` is ``?a=1``), and the separators
    around a removed parameter are one (``?a=1&token=T&b=2`` is
    ``?a=1&b=2``, ``?a=1&token=T&`` is ``?a=1``)."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.pending = ""
        self.after_removed = False

    def kept(self, text: str) -> None:
        if self.after_removed:
            self.after_removed = False
            text = self._joined(text)
        if self.pending:
            text = text.lstrip("&;")
            if not text:
                return
            if not (self.pending == "?" and text.startswith("#")):
                self.parts.append(self.pending)
            self.pending = ""
        self.parts.append(text)

    def _joined(self, text: str) -> str:
        """*text*, what follows a removed parameter, without the separators
        that would be doubled or dangling: all of them after another
        separator or at the end, else the first one."""
        rest = text.lstrip("&;")
        if rest == text or not rest:
            return rest
        last = self.parts[-1][-1:] if self.parts else ""
        return rest if last in ("", "?", "&", ";", "#") else text[0] + rest

    def removed(self, delimiter: str) -> None:
        self.after_removed = True
        if delimiter in "?#":
            self.pending = "#" if "#" in (self.pending, delimiter) else "?"


def rebuilt(text: str, url: FoundUrl) -> tuple[str, str] | None:
    """The *url* of *text* without what an SBOM may not state, and as a
    message shows it (what is removed masked, what is kept as written), or
    ``None`` when nothing is removed."""
    plain, shown = _Plain(), []
    pos = url.start
    if url.userinfo is not None and not url.account:
        start, at = url.userinfo
        plain.kept(text[pos:start])
        shown.append(text[pos:start] + "***:***@" + "***" * (url.cut > at + 1))
        pos = url.cut
    for start, value, end, removed in url.params:
        if not removed:
            continue
        plain.kept(text[pos:start])
        plain.removed(text[start])
        shown.append(text[pos:value] + "***")
        pos = end
    if pos == url.start:
        return None
    plain.kept(text[pos : url.end])
    shown.append(text[pos : url.end])
    return "".join(plain.parts), "".join(shown)
