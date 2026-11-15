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
  ``wide``);
* a PEP 508 requirement with a direct reference (``name @ URL``, with
  extras and a marker), whose URL is read so;
* an scp-style address ``user:password@host:path`` (a dotless host and a
  slashless path too: ``build:42@ci:linux``);
* a PURL, whose qualifier values are each read so as written and after
  each percent-decode, at most :data:`PURL_DECODE_ROUNDS`.

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
from typing import Literal, NamedTuple
from urllib.parse import unquote

from pitloom.core.url_masking._params import MAX_QUERY_MARKS
from pitloom.core.url_masking._strip import WIDE_URL_START, find_urls
from pitloom.core.url_masking._tokens import TOKEN_RE
from pitloom.core.url_masking._userinfo import SCP_USERINFO_RE

__all__ = [
    "PURL_DECODE_ROUNDS",
    "FindingKind",
    "Hit",
    "is_purl",
    "iter_hits",
    "qualifier_hits",
    "split_purl",
]

#: How many times a PURL qualifier value is percent-decoded at most (a value
#: that is a URL encoded twice: ``%253A``).
PURL_DECODE_ROUNDS = 5
#: A PEP 508 requirement with a direct reference, as a whole value: a name,
#: extras, ``@``, the URL and, after white space, a marker.
_REQUIREMENT = re.compile(
    r"\s*[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?\s*(?:\[[^\[\]]*\])?"
    r"\s*@\s*(?P<url>\S+)(?:\s+;.*)?\s*",
    re.DOTALL,
)
_SPACE = re.compile(r"\s")

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


def split_purl(purl: str) -> tuple[str, list[str], str]:
    """*purl* as (the part before ``?``, its qualifiers, ``#`` and the
    subpath); no qualifiers when it has no ``?``."""
    head, mark, rest = purl.partition("?")
    if not mark:
        return purl, [], ""
    query, hash_mark, subpath = rest.partition("#")
    return head, query.split("&"), hash_mark + subpath


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
    hits += (Hit("token", found.group()) for found in TOKEN_RE.finditer(url))
    return hits


def _value_hits(value: str, *, scp: bool, account: bool) -> list[Hit]:
    """The hits of *value* when, as a whole, it is a URL or (with *scp*) an
    scp-style address; none for anything else."""
    lead = len(value) - len(value.lstrip())
    if WIDE_URL_START.match(value, lead) is not None:
        return _url_hits(value[lead:], account=account)
    if (
        scp
        and SCP_USERINFO_RE.match(value) is not None
        and _SPACE.search(value) is None
    ):
        return [Hit("scp", value)]
    return []


def qualifier_hits(item: str, *, scp: bool, account: bool) -> list[Hit]:
    """The hits of the PURL qualifier *item* (``key=value``): of its value
    as written and after each percent-decode, at most
    :data:`PURL_DECODE_ROUNDS`, and ``nesting`` when the last one still
    changed it."""
    key, _, level = item.partition("=")
    hits: list[Hit] = []
    for _ in range(PURL_DECODE_ROUNDS + 1):
        hits += _value_hits(level, scp=scp, account=account)
        plain = unquote(level)
        if plain == level:
            return hits
        level = plain
    hits.append(Hit("nesting", item, shown=f"{key}=***"))
    return hits


def iter_hits(text: str, *, scp: bool, account: bool) -> list[Hit]:
    """Each hit of *text*, a URL-typed value read as a whole (this module's
    docstring), in order."""
    if is_purl(text):
        hits: list[Hit] = []
        for item in split_purl(text)[1]:
            hits += qualifier_hits(item, scp=scp, account=account)
        return hits
    requirement = _REQUIREMENT.fullmatch(text)
    if requirement is not None:
        return _value_hits(requirement["url"], scp=False, account=account)
    return _value_hits(text, scp=scp, account=account)
