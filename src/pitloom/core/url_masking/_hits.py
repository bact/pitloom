# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What may be a credential in a URL-typed value, read as a whole: the hits
the detector reports (:func:`pitloom.core.url_masking.find_url_credentials`)
and the masker hides (:func:`pitloom.core.url_masking.masked_given_path`), so
the two never disagree.

See also: :mod:`pitloom.core.url_masking._detect` (the field rule),
:mod:`pitloom.core.url_masking._urls` (the URL scanner),
:mod:`pitloom.core.url_masking._params` (the secret and weak names),
:mod:`pitloom.core.url_masking._tokens` (the token shapes) and
:mod:`pitloom.core.purl` (which builds a PURL with the helpers here).
Standard library only.

A value is read by what it is, as a whole, never as prose that holds URLs.
What it is starts in its first word (to its first white space), where the
masker would read it, so a character that may not start it hides nothing
(``!https://u:p@h``, ``(pkg:...``, ``!u:p@h:x``); what starts after white
space is prose (``see https://u:p@h``, ``! https://u:p@h``):

* a URL (a scheme and ``/`` or ``\\`` in its first word, as a masker reads
  one: ``s3:/u:p@h``, ``ssh:\\\\u:p@h`` and ``Docs:https://u:p@h`` too),
  read as ``urllib`` reads it
  (:func:`~pitloom.core.url_masking._urls.find_urls`), to its end: white
  space is a character of it, so the value is read whole, and every URL in
  it too (conservative: ``https://h/x see https://u:p@h2/y`` is found);
* a PEP 508 requirement with a direct reference (``name @ URL``, with
  extras and a marker), whose URL is read so;
* an scp-style address ``user:password@host:path`` (a dotless host and a
  slashless path too: ``build:42@ci:linux``), with no white space in it
  (``build:42@ci:linux now`` is a sentence), unless a URL starts before it;
* a PURL (``pkg:`` after no letter or digit, before any URL start), whose
  qualifiers are read as parameters: one named like a
  secret (``token=...``) is a hit, and each value is read so as written and
  after each percent-decode, at most :data:`PURL_DECODE_ROUNDS`. A ``#``
  after the qualifiers stays part of the last value (a URL's fragment such
  as ``download_url=https://h/x#token=T`` is read as one); what follows
  the PURL's first ``#`` (its subpath) is read too, as written and after
  each decode, as a value nested in a URL is.

White space around the whole value is not part of it, nor a format
character (Unicode ``Cf``: a byte order mark, a zero-width space), a tab,
a CR or an LF anywhere in it, nor a C0 control at its start (``urllib``
drops each), nor one pair of ``<>`` or quotes enclosing it (:func:`normalised`).
A URL's query value is read as a whole scp-style address too
(``?next=u:p@h:o/r``), a URL in it as a URL; each query or fragment value
and the whole fragment of a URL also after each percent-decode, as a
qualifier value is (``?next=https%3A%2F%2Fu%3Ap%40h``), but with no
``nesting`` hit when still encoded; a PURL qualifier value as a
whole value or an access token; a PURL subpath, a path, for a URL anywhere
in it, an access token or a whole scp-style address. A URL after the first
word of a value of no kind above (``urn:x https://u:p@h``) is not read,
unless the value is an identifier Pitloom stores (*embedded*,
:func:`iter_hits`), which is read as written and after each percent-decode
too (an id built from a name percent-encodes its ``/``:
``https:%2F%2Fu:p@h``).

In a URL a hit is a user information (an account name on an ``ssh`` or
``git`` URL apart), a parameter named like a secret, a parameter value
holding more than
:data:`~pitloom.core.url_masking._params.MAX_QUERY_MARKS` ``?``, and an
access token's shape anywhere in it (:mod:`~pitloom.core.url_masking._tokens`).
A parameter with a weak name (``code``, ``session``...) and an accepted
account name are weak. A qualifier value still changed by the last decode
is a hit (``nesting``): it is encoded deeper than read. Each value is read
a bounded number of times, without recursion.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from typing import Literal, NamedTuple
from urllib.parse import unquote

from pitloom.core.url_masking._params import (
    MAX_QUERY_MARKS,
    WHOLE_PARAM_RE,
    is_secret_name,
    is_secret_param,
    is_weak_name,
    iter_params,
)
from pitloom.core.url_masking._tokens import TOKEN_RE
from pitloom.core.url_masking._urls import WIDE_URL_START, find_urls
from pitloom.core.url_masking._userinfo import SCP_USERINFO_RE

__all__ = [
    "PURL_DECODE_ROUNDS",
    "FindingKind",
    "Hit",
    "iter_hits",
    "normalised",
    "purl_qualifiers",
    "qualifier_hits",
    "qualifier_levels",
    "split_enclosed",
    "subpath_hits",
    "without_format",
]

#: How many times a PURL qualifier value is percent-decoded at most (a value
#: that is a URL encoded twice: ``%253A``).
PURL_DECODE_ROUNDS = 5
#: A PEP 508 requirement with a direct reference, as a whole value: a name,
#: extras, ``@`` and the URL, to white space; what follows white space (a
#: marker, a comment, a requirements file's ``--hash=...``) is not read.
_REQUIREMENT = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?(?:\s*\[[^\[\]]*\])?"
    r"\s*@\s*(?P<url>\S+)(?:\s.*)?",
    re.DOTALL,
)
#: The closing character of each pair that may enclose a whole value.
_ENCLOSING = {"<": ">", '"': '"', "'": "'"}
_SPACE = re.compile(r"\s")
#: A PURL's start in a value's first word: ``pkg:`` (any case) after no
#: letter or digit.
_PURL_START = re.compile(r"(?<![A-Za-z0-9])(?i:pkg):")
#: A query value of a URL (to the next ``&``, ``;`` or ``#``).
_QUERY_VALUE = re.compile(r"[?&;]([^&;#=?]*)=([^&;#]*)")
#: A query or fragment parameter value of a URL, to the next ``&``, ``;``
#: or ``#``.
_ANY_PARAM_VALUE = re.compile(r"[?&;#][^&;#=?]*=([^&;#]*)")

#: What a hit is: a user information or a parameter named like a secret
#: (``secret``), an account name (``account``), a weak name (``weak``), an
#: scp-style password (``scp``), a value nested or encoded deeper than read
#: (``nesting``), an access token's shape (``token``).
FindingKind = Literal["secret", "token", "scp", "nesting", "weak", "account"]


class Hit(NamedTuple):
    """What may be a credential, as found in a value."""

    kind: FindingKind
    #: The URL, address, token or qualifier as found (decoded, for a PURL
    #: qualifier at a depth): it holds the credential.
    view: str
    #: Told, never refused (a weak name, an accepted account name).
    weak: bool = False
    #: What a message shows when the masker cannot mask *view* itself (a
    #: qualifier encoded deeper than read).
    shown: str | None = None


def _first_word_end(text: str) -> int:
    """Where the first word of *text* ends: at its first white space, else
    at its end."""
    space = _SPACE.search(text)
    return len(text) if space is None else space.start()


def _url_start(text: str) -> int | None:
    """Where the first URL of *text* starts when it starts in its first
    word (``!https://u:p@h``, ``Docs:https://u:p@h``); else ``None``: a
    URL after white space is in prose (``see https://u:p@h``)."""
    found = WIDE_URL_START.search(text, 0, _first_word_end(text))
    return None if found is None else found.start()


def _reads_as_url(value: str, *, scp: bool) -> bool:
    """Whether *value* is read as a URL: one starts in its first word
    (:func:`_url_start`), before any scp-style address (with *scp*) there
    (``alice:pw@host:/srv/r`` is an address)."""
    url = _url_start(value)
    if url is None or not scp:
        return url is not None
    address = _scp_start(value)
    return address is None or url <= address


def _purl_start(text: str, *, scp: bool) -> int | None:
    """Where *text* is read as a PURL from: the first ``pkg:`` in its first
    word, after no letter or digit, when no URL and (with *scp*) no
    scp-style address starts before it (``!pkg:pypi/x``;
    ``https://h/pkg:x`` is a URL, ``u:p@h:o/pkg:x`` an address); else
    ``None``."""
    found = _PURL_START.search(text, 0, _first_word_end(text))
    if found is None:
        return None
    others = (_url_start(text), _scp_start(text) if scp else None)
    if any(other is not None and other < found.start() for other in others):
        return None
    return found.start()


def _url_hits(url: str, *, account: bool, decode: bool = True) -> list[Hit]:
    """The hits of *url*, a value that is one URL (a URL inside it, such as
    ``?r=https://...``, is read on its own): each user information,
    parameter named like a secret or weak, and token shape; with *decode*,
    those of each query value and fragment once percent-decoded too
    (:func:`_decoded_value_hits`)."""
    hits: list[Hit] = []
    for found in find_urls(url):
        span = url[found.start : found.end]
        if found.userinfo is not None:
            hits.append(
                Hit("account", span, weak=account)
                if found.account
                else Hit("secret", span)
            )
        for _, value, end, refused in found.params:
            if url.count("?", value, end) > MAX_QUERY_MARKS:
                hits.append(Hit("nesting", span))
            elif refused:
                hits.append(Hit("secret", span))
            else:
                hits.append(Hit("weak", span, weak=True))
        hits += (
            Hit("scp", value[2])
            for value in _QUERY_VALUE.finditer(url, found.start, found.end)
            if _is_scp(value[2])
        )
        if decode:
            hits += _decoded_value_hits(url, found.start, found.end, account=account)
    hits += (Hit("token", found.group()) for found in TOKEN_RE.finditer(url))
    return hits


def _decoded_value_hits(url: str, start: int, end: int, *, account: bool) -> list[Hit]:
    """The hits of each query or fragment parameter value of the URL of
    *url* from *start* to *end*, and of its whole fragment, read as a whole
    value or an access token (as a PURL qualifier value is), or for its
    parameters (:func:`_decoded_level_hits`), after each
    percent-decode that changes it, at most :data:`PURL_DECODE_ROUNDS`
    (``?next=https%3A%2F%2Fu%3Ap%40h``); as written, the scan of the URL
    reads them. A decoded value is read without decoding it again, so each
    character is read a bounded number of times. A value still encoded
    after the last decode is not read deeper, and is no hit: a redirect
    chain may encode a plain URL many times."""
    # A parameter value is no query: a parameter starts only after a
    # delimiter in it (``next=a%26token%3DT``), never at its start
    # (``filter=auth%3Dbasic``). A fragment is a parameter list itself
    # (``#access_token%3DT``).
    values = [("", found[1]) for found in _ANY_PARAM_VALUE.finditer(url, start, end)]
    mark = url.find("#", start, end)
    if mark >= 0:
        values.append(("#", url[mark + 1 : end]))
    hits: list[Hit] = []
    for head, value in values:
        if "%" not in value:
            continue
        for level in qualifier_levels(value)[0][1:]:
            hits += _decoded_level_hits(normalised(level), head, account=account)
    return hits


def _decoded_level_hits(value: str, head: str, *, account: bool) -> list[Hit]:
    """:func:`_qualifier_value_hits` of *value*, one decode depth of a URL's
    query value or fragment, a URL in it read without decoding again; any
    other value is read for its parameters too, after *head* (``#`` for a
    fragment, else nothing: :func:`_param_hits`: a relative target
    ``/cb?token=T``, ``a&token=T``, a fragment's ``access_token=T``)."""
    value = value.strip()
    if _reads_as_url(value, scp=True):
        hits = _url_hits(value, account=account, decode=False)
    else:
        hits = [Hit("scp", value)] if _is_scp(value) else []
        hits += _param_hits(head + value, value)
    token = TOKEN_RE.fullmatch(value)
    return hits if token is None else [*hits, Hit("token", token.group())]


def _param_hits(text: str, value: str) -> list[Hit]:
    """The hits of the parameters of *text*, a decoded value that is no URL
    (*value*, after its head): each named like a secret (``secret``) or weak
    (``weak``), or holding more than
    :data:`~pitloom.core.url_masking._params.MAX_QUERY_MARKS` ``?``
    (``nesting``), as the scan of a URL reads them; a parameter starts
    after a delimiter only."""
    if "=" not in text:
        return []
    hits: list[Hit] = []
    for param in iter_params(WHOLE_PARAM_RE, text, 0, len(text), weak=False):
        if not is_secret_param(param):
            continue
        if param.group(3).count("?") > MAX_QUERY_MARKS:
            hits.append(Hit("nesting", value))
        elif is_secret_param(param, weak=False):
            hits.append(Hit("secret", value))
        else:
            hits.append(Hit("weak", value, weak=True))
    return hits


def _is_scp(value: str) -> bool:
    """Whether *value* is, as a whole, an scp-style address with a
    password (:func:`_scp_start`)."""
    return _scp_start(value) is not None


def _scp_start(value: str) -> int | None:
    """Where the scp-style address with a password of *value* starts, when
    *value* has no white space: where the masker reads one, so after a
    character that may not start it too (``!u:p@h:x``); else ``None``."""
    if _SPACE.search(value) is not None:
        return None
    found = SCP_USERINFO_RE.search(value)
    return None if found is None else found.start()


def _qualifier_value_hits(value: str, *, scp: bool, account: bool) -> list[Hit]:
    """The hits of a PURL qualifier value as a whole value
    (:func:`_value_hits`), or an access token when it is one."""
    hits = _value_hits(value, scp=scp, account=account)
    token = TOKEN_RE.fullmatch(value.strip())
    return hits if token is None else [*hits, Hit("token", token.group())]


def _subpath_value_hits(value: str, *, scp: bool, account: bool) -> list[Hit]:
    """The hits of a PURL subpath, a path: a whole scp-style address (with
    *scp*), else a URL anywhere in it and an access token."""
    value = value.strip()
    if scp and _is_scp(value):
        return [Hit("scp", value)]
    return _url_hits(value, account=account)


def _value_hits(value: str, *, scp: bool, account: bool) -> list[Hit]:
    """The hits of *value* when, as a whole (without the white space around
    it), it is a URL or (with *scp*) an scp-style address, either starting
    in its first word (this module's docstring); none for anything else."""
    value = value.strip()
    if _reads_as_url(value, scp=scp):
        return _url_hits(value, account=account)
    if scp and _is_scp(value):
        return [Hit("scp", value)]
    return []


def purl_qualifiers(purl: str) -> tuple[str, list[str]]:
    """*purl* as (the part before ``?``, its qualifiers), a ``#`` and what
    follows it kept in the last qualifier (this module's docstring); no
    qualifiers when it has no ``?``."""
    head, mark, rest = purl.partition("?")
    return head, rest.split("&") if mark else []


def qualifier_levels(value: str) -> tuple[list[str], bool]:
    """*value* as written and after each percent-decode that changes it, at
    most :data:`PURL_DECODE_ROUNDS`, and whether one more would still
    change it."""
    levels = [value]
    for _ in range(PURL_DECODE_ROUNDS):
        plain = unquote(levels[-1])
        if plain == levels[-1]:
            return levels, False
        levels.append(plain)
    return levels, unquote(levels[-1]) != levels[-1]


def qualifier_hits(item: str, *, scp: bool, account: bool) -> list[Hit]:
    """The hits of the PURL qualifier *item* (``key=value``): its name when
    it names a secret (or a weak one) and it has a value, its value as
    written and after each percent-decode (:func:`qualifier_levels`), and
    ``nesting`` when one more decode would still change it."""
    key, _, value = item.partition("=")
    shown = f"{key}=***"
    hits: list[Hit] = []
    if value:
        if is_secret_name(key, weak=False):
            hits.append(Hit("secret", item, shown=shown))
        elif is_weak_name(key):
            hits.append(Hit("weak", item, weak=True, shown=shown))
    return hits + _levels_hits(
        _qualifier_value_hits, item, value, shown, scp=scp, account=account
    )


def _levels_hits(
    reader: Callable[..., list[Hit]],
    item: str,
    value: str,
    shown: str | None,
    **flags: bool,
) -> list[Hit]:
    """The hits of *value*, a qualifier value or subpath of *item*, by
    *reader* with *flags* (``scp``, ``account``) as written and after each
    percent-decode (:func:`qualifier_levels`), each :func:`normalised`, and
    ``nesting`` (shown as *shown*, else as the masker shows *item*) when one
    more decode would still change it."""
    hits: list[Hit] = []
    levels, deeper = qualifier_levels(value)
    for level in levels:
        # Each depth as a reader reads it: a format character, a tab, CR
        # or LF a decode shows (``%E2%80%8B``) hides nothing there either.
        hits += reader(normalised(level), **flags)
    if deeper:
        hits.append(Hit("nesting", item, shown=shown))
    return hits


def subpath_hits(purl: str, *, scp: bool, account: bool) -> list[Hit]:
    """The hits of what follows the first ``#`` of *purl* (its subpath, or a
    URL fragment in its last qualifier), read as a nested value at each
    decode depth; none without a ``#``."""
    _, mark, subpath = purl.partition("#")
    if not mark:
        return []
    return _levels_hits(
        _subpath_value_hits, purl, subpath, None, scp=scp, account=account
    )


def without_format(text: str) -> str:
    """*text* without its format characters (Unicode category ``Cf``: a byte
    order mark, a zero-width space), which a client or a copy drops, so one
    inside a scheme (``https\\u200b://``) hides nothing."""
    if text.isascii():
        return text
    return "".join(c for c in text if unicodedata.category(c) != "Cf")


#: What ``urllib.parse.urlsplit`` deletes anywhere in a URL (tab, CR, LF),
#: and strips from its start (a C0 control or a space: WHATWG's "C0 control
#: or space"); the same on Python 3.10 and 3.14.
_URLLIB_DELETES = str.maketrans("", "", "\t\r\n")
_URLLIB_LEADING = "".join(map(chr, range(0x21)))


def normalised(text: str) -> str:
    """*text* as a reader reads it: without its format characters (Unicode
    category ``Cf``: a byte order mark, a zero-width space, which a client
    or a copy drops), without a tab, CR or LF anywhere and a C0 control or
    a space at its start (which ``urllib`` drops: ``htt\tps://u:p@h`` is
    ``https://u:p@h``), the white space around it and one pair of enclosing
    ``<>`` or quotes (``<https://...>``)."""
    plain = without_format(text).translate(_URLLIB_DELETES)
    return split_enclosed(plain.lstrip(_URLLIB_LEADING))[1]


def split_enclosed(text: str) -> tuple[str, str, str]:
    """*text*, a value with no format character, as (what is before it,
    the value as :func:`normalised` reads it, what is after it): the white
    space around it and one pair of enclosing ``<>`` or quotes."""
    start, end = len(text) - len(text.lstrip()), len(text.rstrip())
    if end - start > 1 and _ENCLOSING.get(text[start]) == text[end - 1]:
        inner = text[start + 1 : end - 1]
        start += 1 + len(inner) - len(inner.lstrip())
        end = max(start, end - 1 - (len(inner) - len(inner.rstrip())))
    return text[:start], text[start:end], text[end:]


def iter_hits(
    text: str, *, scp: bool, account: bool, embedded: bool = False
) -> list[Hit]:
    """Each hit of *text*, a URL-typed value read as a whole (this module's
    docstring) once :func:`normalised`, in order; with *embedded* (an
    identifier Pitloom stores, never prose), each URL and access token
    anywhere in it too (``urn:x:https://u:p@h``), as written and after each
    percent-decode, as a PURL qualifier is read."""
    text = normalised(text)
    hits = _whole_hits(text, scp=scp, account=account)
    if embedded:
        hits += _levels_hits(_embedded_hits, text, text, None, scp=scp, account=account)
    return hits


def _embedded_hits(text: str, *, scp: bool, account: bool) -> list[Hit]:
    """The URLs and access tokens anywhere in *text*, an identifier Pitloom
    stores at one decode depth: an id built from a name percent-encodes it
    (``https:%2F%2Fu:p@h``), so each depth is read (:func:`_levels_hits`)."""
    del scp
    # Each depth of the whole text is read, so a value in it is not decoded
    # again on its own.
    return _url_hits(text, account=account, decode=False)


def _whole_hits(text: str, *, scp: bool, account: bool) -> list[Hit]:
    """The hits of *text*, :func:`normalised`, by what it is as a whole."""
    start = _purl_start(text, scp=scp)
    if start is not None:
        text = text[start:]
        hits: list[Hit] = []
        for item in purl_qualifiers(text)[1]:
            hits += qualifier_hits(item, scp=scp, account=account)
        return hits + subpath_hits(text, scp=scp, account=account)
    requirement = _REQUIREMENT.fullmatch(text)
    if requirement is not None:
        return _value_hits(requirement["url"], scp=False, account=account)
    return _value_hits(text, scp=scp, account=account)
