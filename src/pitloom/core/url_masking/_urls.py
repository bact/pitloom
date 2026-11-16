# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The URL scanner of the detector
(:func:`pitloom.core.url_masking.find_url_credentials`): where the URLs of
a URL-typed value are, their user information and their secret parameters.

See also: :mod:`pitloom.core.url_masking._hits` (what the detector reads
with it), :mod:`pitloom.core.url_masking._userinfo` (the user information
rule) and :mod:`pitloom.core.url_masking._params` (the secret names).
Standard library only.

A URL starts at a scheme of two letters or more followed by one ``/`` or
``\\`` or more, or at a one-letter scheme followed by ``://``
(:data:`WIDE_URL_START`; the scheme from the first letter of a run of scheme
characters: ``1.https://``), as the masker reads one: ``s3:/u:p@h`` and
``ssh:\\\\u:p@h`` too. It has a user information unless a path separator
comes before a scheme a URL does not use (:func:`has_userinfo`: ``/x/T10:/a@b``
is a path).

Each URL is read as ``urllib`` reads a URL field: no quote, bracket or white
space ends anything, and it runs to the end of the value. A URL inside
another (``?r=https://u:p@h``) is read on its own: the outer one ends where
it starts, unless it is inside a secret value, which runs over it.
"""

from __future__ import annotations

import re
from collections import deque
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

#: Where a URL starts, as the masker reads one: a run of scheme characters
#: holding a letter, the letter its first one, and a scheme of two letters
#: or more after one or more ``/`` or ``\\`` (``s3:/u:p@h``,
#: ``ssh:\\\\u:p@h``), or of one letter after ``://``. A run only starts
#: after a character that is none, so each run is tried once and a search
#: stays linear.
WIDE_URL_START = re.compile(
    r"(?<![A-Za-z0-9+.-])(?:[0-9+.-]*[A-Za-z][A-Za-z0-9+.-]+:[/\\]+"
    r"|[0-9+.-]*[A-Za-z]://[/\\]*)"
)
_LETTER = re.compile(r"[A-Za-z]")
_SLASH = re.compile("/")
_HEAD = re.compile(PARAM_HEAD)
_DELIMITER = re.compile("[&;#]")
#: How many secret parameter values the end of a user information is moved
#: out of at most (each step reads the user information again).
_SECRET_STEPS = 8
#: Where a parameter value ends.
_VALUE_END = re.compile(r"[&;#]")


@dataclass
class FoundUrl:
    """A URL of a value: its span, its user information and the parameters
    the masker masks."""

    start: int
    end: int
    #: The span of the user information (from after ``://`` to its ``@``).
    userinfo: tuple[int, int] | None = None
    #: Whether that user information is an account name (``git@``).
    account: bool = False
    #: Each parameter named like a secret, as (start, value start, end,
    #: refused); one not refused has a weak name.
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


class _Reader:
    """The URLs of a value, read in order."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.starts = _Memo(text, WIDE_URL_START)
        self._slashes = _Memo(text, _SLASH)

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
        at = None
        colon = self.text.index(":", scheme)
        if has_userinfo(self.text, scheme, colon + 1):
            at = self._userinfo_end(start, self._slashes.start(start))
        host = start
        if at is not None:
            at, host = self._outside_secret_value(start, at)
        if at is not None:
            found.userinfo = (start, at)
            name = self.text[scheme:colon]
            found.account = is_account_name(name, self.text[start:at])
            host = max(host, at + 1)
        found.end = self._params(found, host)
        return found

    def _userinfo_end(self, start: int, end: int) -> int | None:
        """:func:`userinfo_end` of the authority from *start* to *end*."""
        return userinfo_end(self.text, start, end)

    def _outside_secret_value(self, start: int, at: int) -> tuple[int, int]:
        """The ``@`` ending the user information from *start* to *at*, and
        where the host starts, read so that the ``@`` is in no secret
        parameter's value (``https://u:#P@h?token=a@b``: ``P@`` ends it).
        When no ``@`` before such a parameter can (``https://u:p?token=x@h``,
        as RFC 3986 reads it), or more than :data:`_SECRET_STEPS` parameters
        would be stepped over, the host starts after the rest of the
        value."""
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
        value_end = _VALUE_END.search(self.text, first + 1)
        return first, len(self.text) if value_end is None else value_end.start()

    def _secret_head(self, start: int, at: int) -> int | None:
        """Where the parameter named like a secret whose value holds the
        ``@`` at *at* starts, if one from *start* does."""
        heads = deque(_HEAD.finditer(self.text, start, at), maxlen=1)
        if not heads or _DELIMITER.search(self.text, heads[0].end(), at):
            return None
        return heads[0].start() if is_secret_name(heads[0].group("name")) else None

    def _params(self, found: FoundUrl, host: int) -> int:
        """Add to *found* each parameter after *host* named like a secret,
        and return where the URL ends: at the end of the value, or where a
        URL inside it starts, unless a secret value runs over that start."""
        pos = host
        while True:
            bound = self.starts.start(pos)
            resume = self._segment(found, pos, bound)
            if resume is None:
                return bound
            pos = resume

    def _segment(self, found: FoundUrl, pos: int, bound: int) -> int | None:
        """Add to *found* each parameter from *pos* to *bound* named like a
        secret; a refused one whose value reaches *bound* (where a URL inside
        starts) runs on over it, to the end of the value. Return where such a
        value ends, else ``None``."""
        for param in iter_params(WHOLE_PARAM_RE, self.text, pos, bound, weak=False):
            if not is_secret_param(param):
                continue
            refused = is_secret_param(param, weak=False)
            whole = param
            if refused and param.end() == bound:
                run = param_run(
                    WHOLE_PARAM_RE, self.text, param.start(), len(self.text)
                )
                whole = run or param
            found.params.append((whole.start(), whole.start(3), whole.end(), refused))
            if whole is not param:
                return whole.end()
        return None


def find_urls(text: str) -> list[FoundUrl]:
    """Each URL of *text*, a URL-typed value, in order (the reading: this
    module's docstring)."""
    reader = _Reader(text)
    urls: list[FoundUrl] = []
    while (found := reader.next_url(urls[-1].end if urls else 0)) is not None:
        urls.append(found)
    return urls
