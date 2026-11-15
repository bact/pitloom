# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The masker of a path as given or a message
(:func:`masked_given_path`): one rule that hides every URL credential,
scp-style password, access token and PURL qualifier the detector refuses.

See also: :mod:`pitloom.core.url_masking._scan` (its URL scanner) and
:mod:`pitloom.core.url_masking._hits` (what the detector refuses). Standard
library only.
"""

from __future__ import annotations

import re

from pitloom.core.url_masking._hits import qualifier_hits, split_purl
from pitloom.core.url_masking._scan import masked_once
from pitloom.core.url_masking._tokens import mask_tokens
from pitloom.core.url_masking._userinfo import mask_scp

__all__ = ["masked_given_path"]

#: A Package URL in a text, to white space.
_PURL_WORD = re.compile(r"(?<![A-Za-z0-9+.-])(?i:pkg):\S+")


def _masked_purl(found: re.Match[str]) -> str:
    """The PURL *found* with the value of each qualifier that holds a hit
    (:func:`~pitloom.core.url_masking._hits.qualifier_hits`) written as
    ``***``."""
    head, qualifiers, tail = split_purl(found.group())
    if not qualifiers:
        return found.group()
    kept = [
        item.partition("=")[0] + "=***"
        if qualifier_hits(item, scp=True, account=False)
        else item
        for item in qualifiers
    ]
    return f"{head}?{'&'.join(kept)}{tail}"


def _masked_purls(text: str) -> str:
    """*text* with each PURL in it masked (:func:`_masked_purl`)."""
    return _PURL_WORD.sub(_masked_purl, text)


#: How many times :func:`masked_given_path` masks a text at most. A ``/`` or
#: white space in a secret value does not end a user information, so the
#: masking of one URL uncovers nothing of its own; a later URL masked in
#: another context (quoted or not) can take away the stop that ended an
#: earlier URL's (``u@"https:\h&u@:ab:\#sig=/a/b" ?\a/b'u:p@``). Random and
#: searched texts settle after two masking passes.
_MASK_PASSES = 4


def masked_given_path(text: str, *, line: bool = False) -> str:
    """*text*, a path as given or a message naming one, with the credentials
    of each URL in it replaced: the user information by ``***:***``, a
    secret parameter's value by ``***``; every other character is printed as
    given, so a path that only looks like a URL keeps its separators. A URL
    reaches a path check as a path, and a line names it without its
    credentials. The user information runs to the last ``@`` before the
    next ``/`` or the end of *text*, and in a message *line* before the next
    white space (``URL=https://h: unreachable; contact a@b.org`` keeps the
    address), either not in a secret parameter's value (masking the value
    would uncover a later ``@``); a quote is a character of it, never its
    end. When its ``@`` is in a secret value, the rest of that value is
    masked too (``https://u:p?token=x@h/x`` prints ``https://***:***@***``:
    RFC 3986 reads ``x@h/x`` as the token's). The rest of a URL runs to the
    end of *text*, or to the quote closing the one before it: one no
    backslash escapes, before white space or the end (after at most four
    characters ending a sentence: ``'...': not found``), so a quote inside
    a value does not close it. In a *line* a URL that is not quoted ends at
    the first white space after its user information, and each URL of the
    line is masked. A secret value runs to the next ``&``, ``;``, ``#`` or
    the URL's end, over a quote, and over white space unless in a *line*
    outside quotes. The masked text is masked again until nothing changes,
    at most :data:`_MASK_PASSES` times (a URL masked in a quoted context
    can take away the stop that ended an earlier URL's user information),
    so masking a masked text changes nothing unless a text needs more
    passes than that; none found so far needs more than two. The one
    masker of a path as given and of an ``ERROR:`` line
    (:func:`pitloom.logging_config.print_error`).

    Also masked, so it hides all the detector refuses
    (:func:`pitloom.core.url_masking.find_url_credentials`): an access
    token's shape (``ghp_***``), the password of an scp-style address, and
    the value of a PURL qualifier that holds a hit once percent-decoded
    (``download_url=***``).

    After one separator (``https:/u:p@h``, a ``//`` a path collapsed) a
    scheme has a user information unless a ``/`` or ``\\`` comes before it
    (``/x/T10:/a@b`` is a path); a scheme a URL uses has one there too
    (:data:`~pitloom.core.url_masking._userinfo.URL_SCHEMES`:
    ``/cwd/https:/u:p@h``). So a relative path
    ``backup:/u@h/x`` is read as a collapsed URL and its ``u`` masked: a
    credential shown costs more than a path's ``@`` hidden.

    Out of scope: a password holding a raw ``/``, or in a *line* white
    space, is not a user information (RFC 3986 percent-encodes both), so it
    is not masked. Accepted partial leaks, none showing the start of a
    secret: in a *line*, a secret value holding a space in a URL that is not
    quoted is masked to the space (``?token=SEC RET`` prints ``?token=***
    RET``), and the punctuation ending a sentence or a quotation is kept
    after a value, so a secret ending in it shows that end
    (``?token=abc...`` prints ``?token=***...``, ``?token=ab'`` prints
    ``?token=***'``); in a quoted URL, a secret value holding the URL's
    quote before white space or the end, after at most four such
    punctuation characters, is masked to that quote (``'...?token=ab'.
    cd'`` prints ``'...?token=***'. cd'``); a value ending in a backslash
    escapes the closing quote, so its URL runs on to the next quote that
    closes.
    """
    text = mask_scp(mask_tokens(_masked_purls(text)))
    masked = masked_once(text, line=line)
    passes = 1
    while masked != text and passes < _MASK_PASSES:
        text, masked = masked, masked_once(masked, line=line)
        passes += 1
    return masked
