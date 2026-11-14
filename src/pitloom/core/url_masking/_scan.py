# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The scanner of :func:`pitloom.core.url_masking.masked_given_path`: where
the URLs of a text are, their user information and their secret values.

See also: :mod:`pitloom.core.url_masking` (the public functions) and
:mod:`pitloom.core.url_masking._params` (the secret parameters). Standard
library only.
"""

from __future__ import annotations

import re

from pitloom.core.url_masking._params import (
    PARAM_HEAD,
    PARAM_RE,
    WHOLE_PARAM_RE,
    free_value_end,
    is_secret_name,
)

#: A run of scheme characters, ``:`` and a separator: where a URL may start
#: in a text, the scheme from the run's first letter (``1https://``). Each
#: run is tried once, so the search is linear.
_SCHEME_RUN_RE = re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z0-9+.-]+:[/\\]")
_LETTER_RE = re.compile(r"[A-Za-z]")
_SPACE_RE = re.compile(r"\s")
_AT_RE = re.compile("@")
_HEAD_RE = re.compile(PARAM_HEAD)
#: The quotes a message puts around a path it names.
_QUOTES = "'\""


def _closing(quote: str) -> str:
    """A *quote* that closes a URL: no backslash escapes it (an even run of
    backslashes before it: ``repr`` writes ``'a\\'b'``), and white space or
    the end follows it, after at most four characters ending a sentence or
    a quotation (``'...': not found``, ``('...', 'b')``), so a quote inside
    a secret value (``?token=a'b``) is not one. The match ends at the
    quote."""
    return rf"(?<!\\)(?:\\\\)*{quote}(?=[:.,;!?)\]}}>'\"]{{0,4}}(?:\s|\Z))"


_CLOSING_QUOTE = {quote: re.compile(_closing(quote)) for quote in _QUOTES}


def _ends(line: bool, quote: str) -> tuple[str, str]:
    """What ends a user information (a ``/``, in a *line* white space too)
    and what ends a parameter value, of a URL opened by *quote* (or none):
    a delimiter, the closing quote, in a *line* white space when no quote
    opened the URL. As regular expressions."""
    if quote:
        value_end = rf"[&;#]|{_closing(quote)}"
    else:
        value_end = r"[&;#\s]" if line else "[&;#]"
    return (r"[/\s]" if line else "/"), value_end


_ENDS: dict[tuple[bool, str], tuple[str, str]] = {
    (line, quote): _ends(line, quote)
    for line in (False, True)
    for quote in ("", *_QUOTES)
}
#: For each (line, opening quote): what ends a parameter value, and a
#: scanner of where a user information can end (``stop``), each parameter
#: start (``head``) and each value end (``end``).
_VALUE_END: dict[tuple[bool, str], re.Pattern[str]] = {
    key: re.compile(end) for key, (_, end) in _ENDS.items()
}
_BOUNDARY: dict[tuple[bool, str], re.Pattern[str]] = {
    key: re.compile(rf"(?P<head>{PARAM_HEAD})|(?P<stop>{stop})|(?P<end>{end})")
    for key, (stop, end) in _ENDS.items()
}
_STOP = {False: re.compile("/"), True: re.compile(r"[/\s]")}
#: The schemes read as a URL after one separator even in a path segment
#: (``/cwd/https:/u:p@h``, a URL a path resolved), the last ``+`` part
#: (``git+https``). Another scheme after one separator is a URL unless a
#: ``/`` or ``\\`` comes before it (``/x/T10:/a@b`` is a path).
_URL_SCHEMES = frozenset(
    {"http", "https", "ftp", "ftps", "sftp", "ssh", "git", "svn", "hg", "bzr"}
    | {"s3", "s3a", "s3n", "gs", "hf", "ws", "wss", "file", "rsync", "ldap"}
    | {"ldaps", "az", "abfs", "abfss", "hdfs", "smb", "webdav", "davs"}
)


def _next_url(text: str, pos: int, end: int) -> tuple[int, int] | None:
    """The first URL in *text* from *pos* to *end*: the start of its scheme
    and the index of its first separator, or ``None``."""
    while (run := _SCHEME_RUN_RE.search(text, pos, end)) is not None:
        separator = run.end() - 1
        letter = _LETTER_RE.search(text, run.start(), separator - 1)
        if letter is not None and separator - 1 - letter.start() >= 2:
            return letter.start(), separator
        pos = run.end()
    return None


def _has_userinfo(text: str, scheme: int, separator: int) -> bool:
    """Whether the URL whose scheme starts at *scheme* can have a user
    information: after two separators, after one for a scheme a URL uses
    (:data:`_URL_SCHEMES`), else after one unless a path separator comes
    before the scheme (a path segment ``T10:``)."""
    if text.startswith(("//", "\\\\"), separator):
        return True
    name = text[scheme : separator - 1].lower()
    if name.rpartition("+")[2] in _URL_SCHEMES:
        return True
    return not scheme or text[scheme - 1] not in "/\\"


class _Scan:
    """A text being masked, and the positions its masker asks: the first
    match of a pattern at or after a position, remembered while the asked
    positions stay before it, so the URLs of a text, asked in order, read
    each character a bounded number of times (``ab:\\a`` repeated with no
    ``/`` after it)."""

    def __init__(self, text: str, *, line: bool) -> None:
        self.text = text
        self.line = line
        self._found: dict[re.Pattern[str], tuple[int, int]] = {}
        self._stops: dict[str, tuple[int, int]] = {}
        self._head = (-1, -1, -1)

    def next(self, pattern: re.Pattern[str], pos: int) -> int:
        """The index of the last character of the first match of *pattern*
        at or after *pos*, or the length of the text."""
        asked, found = self._found.get(pattern, (-1, -1))
        if not asked <= pos <= found:
            match = pattern.search(self.text, pos)
            found = len(self.text) if match is None else match.end() - 1
            self._found[pattern] = (pos, found)
        return found

    def quote(self, scheme: int) -> str:
        """The quote before the scheme starting at *scheme*, or ``""``."""
        quote = self.text[scheme - 1] if scheme else ""
        return quote if quote in _QUOTES else ""

    def _secret_head_end(self, pos: int) -> int:
        """Where the first parameter start (``delimiter name=``) at or after
        *pos* with a secret name ends, or the length of the text."""
        asked, start, end = self._head
        if not asked <= pos <= start:
            start = end = len(self.text)
            for head in _HEAD_RE.finditer(self.text, pos):
                if is_secret_name(head.group("name")):
                    start, end = head.start(), head.end()
                    break
            self._head = (pos, start, end)
        return end

    def _open_stop(self, pos: int, quote: str) -> int:
        """The first stop at or after *pos*, where a value ends, that is
        not in the value of a secret parameter, or the length of the text.
        Each stop's answer depends on the text since the value end before
        it only, so it is remembered while the asked positions stay before
        it."""
        asked, found = self._stops.get(quote, (-1, -1))
        if asked <= pos <= found:
            return found
        found, secret = len(self.text), False
        for part in _BOUNDARY[self.line, quote].finditer(self.text, pos):
            if part.group("head") is not None:
                named = is_secret_name(part.group("name"))
                secret = named or (secret and part.group()[0] == "?")
            elif part.group("end") is not None:
                secret = False
            elif not secret or (self.line and not quote and part.group() != "/"):
                found = part.start()
                break
        self._stops[quote] = (pos, found)
        return found

    def _userinfo_end(self, start: int, quote: str) -> int:
        """Where the user information starting at *start* can end at the
        latest: the first ``/`` (in a *line* white space too) that is not in
        a secret parameter's value, as the masker reads one (to a delimiter,
        the closing quote, in a *line* white space when no quote opened the
        URL), so masking a value never uncovers a later ``@``. A value read
        from before *start* does not count."""
        bound = self.next(_VALUE_END[self.line, quote], start)
        stop = self.next(_STOP[self.line], start)
        # A stop that ends a value too (white space) is never in one.
        if stop == bound or (stop < bound and self._secret_head_end(start) > stop):
            return stop
        return self._open_stop(bound, quote)

    def userinfo(self, url: tuple[int, int]) -> tuple[int, int] | None:
        """The span of the user information of the *url* (scheme start,
        separator), or ``None``: to the last ``@`` before the next ``/`` or
        the end of the text, in a *line* before white space too, either not
        in a secret parameter's value (:meth:`_userinfo_end`). A quote does
        not end it (RFC 3986 allows ``'`` there); a ``\\`` does not either
        (after ``:\\``, a Windows path's, it may be a separator or the
        password's: the two cannot be told apart, so a path's ``@`` may be
        masked too, but no password is left shown)."""
        scheme, start = url
        if not _has_userinfo(self.text, scheme, start):
            return None
        while start < len(self.text) and self.text[start] in "/\\":
            start += 1
        first_at = self.next(_AT_RE, start)
        # No @ left: no user information, whatever its end.
        if first_at >= len(self.text):
            return None
        end = self._userinfo_end(start, self.quote(scheme))
        if first_at >= end:
            return None
        at = self.text.rfind("@", start, end)
        return (start, at) if at > start else None

    def value_tail(self, userinfo: tuple[int, int], quote: str) -> int | None:
        """Where the secret parameter value holding the ``@`` that ends the
        *userinfo* (start, ``@``) ends, or ``None`` when no such value holds
        it (``u@h?token=a@b`` is ``u@h?token=a`` and ``b``: ``b`` is the
        value's too). The user information is scanned once, and replaced."""
        start, at = userinfo
        if self._secret_head_end(start) > at:
            return None
        secret = False
        for part in _BOUNDARY[self.line, quote].finditer(self.text, start):
            if part.start() >= at:
                break
            if part.group("head") is not None:
                named = is_secret_name(part.group("name"))
                secret = named or (secret and part.group()[0] == "?")
            elif part.group("end") is not None:
                secret = False
        if not secret:
            return None
        return self.next(_VALUE_END[self.line, quote], at + 1)

    def url_end(self, scheme: int, after: int) -> tuple[int, bool]:
        """Where the URL whose scheme starts at *scheme* ends, searched from
        *after* (its user information's ``@``, else its separator), and
        whether it is quoted: at the quote closing the one before it
        (:func:`_closing`), else at the end of the text (a path or URL can
        hold a space)."""
        quote = self.quote(scheme)
        if not quote:
            return len(self.text), False
        end = self.next(_CLOSING_QUOTE[quote], after)
        return (end, end < len(self.text))


def _secret_spans(
    text: str, start: int, end: int, *, line: bool
) -> tuple[list[tuple[int, int, str]], int]:
    """The value of each parameter named like a secret
    (:func:`~pitloom.core.url_masking._params.is_secret_name`) from *start*
    to *end* of *text*, as spans to replace by ``***``, and where the URL
    ends: before the next URL, which is masked on its own, unless it is
    inside a secret value (``?token=ab:/cd`` is one value), and in a *line*
    at white space. In a *line* a value ends as in free text
    (:func:`~pitloom.core.url_masking._params.free_value_end`), at white
    space and before the punctuation ending a sentence (``?token=***: a
    Hugging Face model``). Each character is scanned a bounded number of
    times."""
    spans: list[tuple[int, int, str]] = []
    url_from = start + 1
    while True:
        following = _next_url(text, url_from, end)
        bound = limit = end if following is None else following[0]
        space = _SPACE_RE.search(text, start, bound) if line else None
        if space is not None:
            bound = limit = space.start()
        elif following is not None:
            limit = end
        resume = _secret_values(text, (start, bound, limit), spans, line=line)
        if resume is None:
            return spans, bound
        start = url_from = resume


def _secret_values(
    text: str,
    scan: tuple[int, int, int],
    spans: list[tuple[int, int, str]],
    *,
    line: bool,
) -> int | None:
    """Add to *spans* the value of each secret parameter of *text* in the
    *scan* (start, bound, limit): from start to bound, where a value that
    reaches the bound runs on to the limit (it reads into the next URL).
    Return where such a value ends, to scan on from there, else ``None``."""
    pattern = PARAM_RE if line else WHOLE_PARAM_RE
    start, bound, limit = scan
    for param in pattern.finditer(text, start, bound):
        if not is_secret_name(param.group(2)):
            continue
        whole = param
        if param.end() == bound < limit:
            whole = pattern.match(text, param.start(), limit) or param
        value_end = free_value_end(whole) if line else whole.end(3)
        spans.append((whole.start(3), value_end, "***"))
        if whole is not param:
            return whole.end()
    return None


def _url_spans(
    scan: _Scan, url: tuple[int, int]
) -> tuple[list[tuple[int, int, str]], int]:
    """The spans of the *scan*'s text to replace, with their replacement, in
    the *url* (scheme start, separator): its user information
    (:meth:`_Scan.userinfo`) and the rest of a secret value its ``@`` is in
    (:meth:`_Scan.value_tail`), then each secret value
    (:func:`_secret_spans`, from there or the separator, to the URL's end:
    :meth:`_Scan.url_end`), and where the URL ends."""
    spans: list[tuple[int, int, str]] = []
    after = url[1]
    userinfo = scan.userinfo(url)
    if userinfo is not None:
        spans.append((*userinfo, "***:***"))
        after = userinfo[1]
        tail = scan.value_tail(userinfo, scan.quote(url[0]))
        if tail is not None and tail > after + 1:
            spans.append((after + 1, tail, "***"))
            after = tail
    end, quoted = scan.url_end(url[0], after)
    secrets, end = _secret_spans(scan.text, after, end, line=scan.line and not quoted)
    return spans + secrets, end


def masked_once(text: str, *, line: bool) -> str:
    """One pass of :func:`pitloom.core.url_masking.masked_given_path` over *text*."""
    parts: list[str] = []
    done = 0
    scan = _Scan(text, line=line)
    while (url := _next_url(text, done, len(text))) is not None:
        spans, end = _url_spans(scan, url)
        for start, stop, replacement in spans:
            parts += (text[done:start], replacement)
            done = stop
        parts.append(text[done:end])
        done = end
    if not parts:
        return text
    parts.append(text[done:])
    return "".join(parts)
