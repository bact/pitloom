# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What may be a credential in a URL-typed value, read as a whole: the hits
the detector reports (:func:`pitloom.core.url_masking.find_url_credentials`)
and the masker hides (:func:`pitloom.core.url_masking.masked_given_path`), so
the two never disagree.

See also: :mod:`pitloom.core.url_masking._detect` (the field rule),
:mod:`pitloom.core.url_masking._strip` (the URL scanner),
:mod:`pitloom.core.url_masking._params` (the secret and weak names),
:mod:`pitloom.core.url_masking._tokens` (the token shapes) and
:mod:`pitloom.core.purl` (which builds a PURL with the helpers here).
Standard library only.

A value is read by what it is, as a whole, never as prose that holds URLs:

* a URL (a scheme and ``/`` or ``\\`` at its start, as a masker reads one:
  ``s3:/u:p@h`` and ``ssh:\\\\u:p@h`` too), read as ``urllib`` reads it
  (:func:`~pitloom.core.url_masking._strip.find_urls`, ``whole`` and
  ``wide``), to its end: white space is a character of it, so a value that
  starts with a URL is read whole, and every URL in it too (conservative:
  ``https://h/x see https://u:p@h2/y`` is refused);
* a PEP 508 requirement with a direct reference (``name @ URL``, with
  extras and a marker), whose URL is read so;
* an scp-style address ``user:password@host:path`` (a dotless host and a
  slashless path too: ``build:42@ci:linux``), with no white space in it
  (``build:42@ci:linux now`` is a sentence);
* a PURL, whose qualifiers are read as parameters: one named like a
  secret (``token=...``) is a hit, and each value is read so as written and
  after each percent-decode, at most :data:`PURL_DECODE_ROUNDS`. A ``#``
  after the qualifiers stays part of the last value (a URL's fragment such
  as ``download_url=https://h/x#token=T`` is read as one); what follows
  the PURL's first ``#`` (its subpath) is read too, as written and after
  each decode, as a value nested in a URL is.

White space around the whole value is not part of it, nor a format
character (Unicode ``Cf``: a byte order mark, a zero-width space) anywhere
in it, nor one pair of ``<>`` or quotes enclosing it (:func:`normalised`).
A URL's query value is read as a whole scp-style address too
(``?next=u:p@h:o/r``), a URL in it as a URL; a PURL qualifier value as a
whole value or an access token; a PURL subpath, a path, for a URL anywhere
in it, an access token or a whole scp-style address. A URL inside a value
of no kind above (``urn:x:https://u:p@h``) is not read, unless the value is
an identifier Pitloom stores (*embedded*, :func:`iter_hits`).

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
    is_secret_name,
    is_weak_name,
)
from pitloom.core.url_masking._strip import WIDE_URL_START, find_urls
from pitloom.core.url_masking._tokens import TOKEN_RE
from pitloom.core.url_masking._userinfo import SCP_USERINFO_RE

__all__ = [
    "PURL_DECODE_ROUNDS",
    "FindingKind",
    "Hit",
    "is_purl",
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
#: A query value of a URL (to the next ``&``, ``;`` or ``#``).
_QUERY_VALUE = re.compile(r"[?&;]([^&;#=?]*)=([^&;#]*)")

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


def is_purl(text: str) -> bool:
    """Whether *text* is a Package URL (``pkg:``, any case)."""
    return text[:4].lower() == "pkg:"


def _url_hits(url: str, *, account: bool) -> list[Hit]:
    """The hits of *url*, a value that is one URL (a URL inside it, such as
    ``?r=https://...``, is read on its own): each user information,
    parameter named like a secret or weak, and token shape."""
    hits: list[Hit] = []
    for found in find_urls(url, whole=True, wide=True):
        span = url[found.start : found.end]
        if found.userinfo is not None:
            hits.append(
                Hit("account", span, weak=account)
                if found.account
                else Hit("secret", span)
            )
        for _, value, end, removed in found.params:
            if url.count("?", value, end) > MAX_QUERY_MARKS:
                hits.append(Hit("nesting", span))
            elif removed:
                hits.append(Hit("secret", span))
            else:
                hits.append(Hit("weak", span, weak=True))
        hits += (
            Hit("scp", value[2])
            for value in _QUERY_VALUE.finditer(url, found.start, found.end)
            if _is_scp(value[2])
        )
    hits += (Hit("token", found.group()) for found in TOKEN_RE.finditer(url))
    return hits


def _is_scp(value: str) -> bool:
    """Whether *value* is, as a whole, an scp-style address with a
    password."""
    return SCP_USERINFO_RE.match(value) is not None and _SPACE.search(value) is None


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
    it), it is a URL or (with *scp*) an scp-style address; none for
    anything else."""
    value = value.strip()
    if WIDE_URL_START.match(value) is not None:
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
    percent-decode (:func:`qualifier_levels`), and
    ``nesting`` (shown as *shown*, else as the masker shows *item*) when one
    more decode would still change it."""
    hits: list[Hit] = []
    levels, deeper = qualifier_levels(value)
    for level in levels:
        hits += reader(level, **flags)
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


def normalised(text: str) -> str:
    """*text* as a reader reads it: without its format characters (Unicode
    category ``Cf``: a byte order mark, a zero-width space, which a client
    or a copy drops), the white space around it and one pair of enclosing
    ``<>`` or quotes (``<https://...>``)."""
    return split_enclosed(without_format(text))[1]


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
    anywhere in it too (``urn:x:https://u:p@h``)."""
    text = normalised(text)
    hits = _whole_hits(text, scp=scp, account=account)
    if embedded:
        hits += _url_hits(text, account=account)
    return hits


def _whole_hits(text: str, *, scp: bool, account: bool) -> list[Hit]:
    """The hits of *text*, :func:`normalised`, by what it is as a whole."""
    if is_purl(text):
        hits: list[Hit] = []
        for item in purl_qualifiers(text)[1]:
            hits += qualifier_hits(item, scp=scp, account=account)
        return hits + subpath_hits(text, scp=scp, account=account)
    requirement = _REQUIREMENT.fullmatch(text)
    if requirement is not None:
        return _value_hits(requirement["url"], scp=False, account=account)
    return _value_hits(text, scp=scp, account=account)
