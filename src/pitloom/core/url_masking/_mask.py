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
from collections.abc import Callable
from urllib.parse import unquote

from pitloom.core.url_masking._auth_schemes import mask_auth_schemes
from pitloom.core.url_masking._boundary import word_start
from pitloom.core.url_masking._hits import (
    PURL_DECODE_ROUNDS,
    purl_qualifiers,
    qualifier_hits,
    qualifier_levels,
    subpath_hits,
    without_format,
)
from pitloom.core.url_masking._params import mask_free_params
from pitloom.core.url_masking._scan import masked_once
from pitloom.core.url_masking._tokens import TOKEN_RE, mask_tokens
from pitloom.core.url_masking._userinfo import mask_scp

__all__ = ["masked_given_path"]

#: A Package URL in a text, to white space, also right after an escape
#: sequence (:func:`~pitloom.core.url_masking._boundary.word_start`).
_PURL_WORD = re.compile(word_start("A-Za-z0-9+.-") + r"(?i:pkg):\S+")
#: What ends a sentence, a quotation or an enclosing ``<>`` after a PURL in
#: a text.
_PURL_TAIL = ":.,;)]>'\""


def _holds_hit(item: str) -> bool:
    """Whether the PURL qualifier *item* holds a hit
    (:func:`~pitloom.core.url_masking._hits.qualifier_hits`) or, at a decode
    depth, an access token's shape anywhere in its value."""
    if qualifier_hits(item, scp=True, account=False):
        return True
    levels, _ = qualifier_levels(item.partition("=")[2])
    return any(TOKEN_RE.search(level) for level in levels)


def _masked_purl(found: re.Match[str]) -> str:
    """The PURL *found* with its subpath written as ``***`` when it holds a
    hit (:func:`~pitloom.core.url_masking._hits.subpath_hits`, a token
    anywhere in it included), and the value of each qualifier that holds
    one (:func:`_holds_hit`). The punctuation ending a sentence after it
    (``pkg:...?token=***: not found``) is kept, as after a URL's value."""
    word = found.group()
    purl = word.rstrip(_PURL_TAIL)
    return _masked_purl_text(purl) + word[len(purl) :]


def _masked_purl_text(purl: str) -> str:
    """:func:`_masked_purl` of the PURL *purl*."""
    before, mark, _ = purl.partition("#")
    if mark and subpath_hits(purl, scp=True, account=False):
        purl = f"{before}#***"
    head, qualifiers = purl_qualifiers(purl)
    if not qualifiers:
        return purl
    kept = [
        item.partition("=")[0] + "=***" if _holds_hit(item) else item
        for item in qualifiers
    ]
    return f"{head}?{'&'.join(kept)}"


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


def masked_given_path(
    text: str, *, line: bool = False, free_params: bool = False
) -> str:
    """*text*, a path as given or a message naming one, with the credentials
    of each URL in it replaced: the user information by ``***:***``, a
    secret parameter's value by ``***``; every other character is printed as
    given, so a path that only looks like a URL keeps its separators. A URL
    reaches a path check as a path, and a line names it without its
    credentials. The user information runs to the last ``@`` before the
    next ``/`` or the end of *text*, and in a message *line* before the next
    white space other than a tab or a line break, which a URL parser deletes
    (``URL=https://h: unreachable; contact a@b.org`` keeps the address),
    either not in a secret parameter's value (masking the value
    would uncover a later ``@``); a quote is a character of it, never its
    end. When its ``@`` is in a secret value, the rest of that value is
    masked too (``https://u:p?token=x@h/x`` prints ``https://***:***@***``:
    RFC 3986 reads ``x@h/x`` as the token's). The rest of a URL runs to the
    end of *text*, or to the quote closing the one before it: one no
    backslash escapes, before white space or the end (after at most four
    characters ending a sentence: ``'...': not found``), so a quote inside
    a value does not close it. In a *line* a URL that is not quoted ends at
    the first white space after its user information, and each URL of the
    line is masked: a log sentence's URL is read so, and a secret after a
    space in its path (``https://h/a b?token=T``) is not masked; a
    ``KEY=VALUE`` value that starts with a URL is read whole instead
    (:mod:`pitloom.cli.kv_output`). A secret value runs to the next ``&``,
    ``#`` or the URL's end (to a ``;`` too when a ``;`` opened it: a path
    parameter), over a ``;``, a quote, and over white space unless in a
    *line* outside quotes. The masked text is masked again until nothing changes,
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
    (``download_url=***``), and the credential after a ``Bearer`` or
    ``Basic`` scheme (``Authorization: Bearer ***``,
    :mod:`~pitloom.core.url_masking._auth_schemes`). A token, an scp-style
    address, a PURL or a scheme may start right after an escape sequence
    (``\\t``, ``\\x1b``: a text escaped before it is masked,
    :mod:`~pitloom.core.url_masking._boundary`).

    A format character (Unicode ``Cf``: a byte order mark, a zero-width
    space) is dropped, as a reader drops it, when that shows a credential to
    mask (``https\\u200b://u:p@h``), so one inside a URL hides nothing
    (:func:`~pitloom.core.url_masking._hits.without_format`); else it is
    kept, so a message can still show it (a bidirectional override).

    After one separator (``https:/u:p@h``, a ``//`` a path collapsed) a
    scheme has a user information unless a ``/`` or ``\\`` comes before it
    (``/x/T10:/a@b`` is a path); a scheme a URL uses has one there too
    (:func:`~pitloom.core.url_masking._userinfo.has_userinfo`:
    ``/cwd/https:/u:p@h``). So a relative path
    ``backup:/u@h/x`` is read as a collapsed URL and its ``u`` masked: a
    credential shown costs more than a path's ``@`` hidden.

    Out of scope: a password holding a raw ``/``, or in a *line* white space
    other than a tab or a line break, is not a user information (RFC 3986
    percent-encodes both), so it is not masked. Accepted partial leaks, none
    showing the start of a secret: in a *line*, a secret value holding a
    space in a URL that is not quoted is masked to the space (``?token=SEC
    RET`` prints ``?token=*** RET``), and the punctuation ending a sentence
    or a quotation is kept after a value, so a secret ending in it shows
    that end (``?token=abc...`` prints ``?token=***...``, ``?token=ab'``
    prints ``?token=***'``); in a quoted URL, a secret value holding the
    URL's quote before white space or the end, after at most four such
    punctuation characters, is masked to that quote (``'...?token=ab'. cd'``
    prints ``'...?token=***'. cd'``); a value ending in a backslash escapes
    the closing quote, so its URL runs on to the next quote that closes.

    A credential shown only once the text is percent-decoded (an id built
    from a name encodes its ``/``: ``https:%2F%2Fu:p@h``) is masked at the
    shallowest decode depth that shows it, which is then what is printed
    (:func:`~pitloom.core.url_masking._hits.qualifier_levels`, as the
    detector reads an identifier), and that text is read again, at most
    :data:`~pitloom.core.url_masking._hits.PURL_DECODE_ROUNDS` times: a
    deeper depth can break what a shallower one shows
    (``u:se%252Fcret@h`` decodes to ``u:se/cret@h``, no user information),
    so it is never what is printed. A text that decoding shows nothing more
    in is printed as given, except a parameter value or fragment still
    encoded after the last decode (``?next=...%2525...``): it is printed as
    ``***`` (:func:`_masked_deep_values`), since what it hides cannot be
    read; when every round showed a credential (decoys, each a level
    deeper), each value still encoded is printed so.

    With *free_params* (a log line), the value of a parameter named like a
    secret is masked with or without a URL around it, at every decode depth
    too (:func:`~pitloom.core.url_masking.mask_free_params`: a request
    target ``GET /x?token=T``).
    """
    masked = _masked_formats(text, line=line, free_params=free_params)
    for _ in range(PURL_DECODE_ROUNDS):
        if "%" not in masked:
            return masked
        shown = _first_masked_level(
            qualifier_levels(masked)[0][1:], line=line, free_params=free_params
        )
        if shown is None:
            return _masked_deep_values(masked, _deeper_than_read)
        masked = shown
    # Every round showed a credential (decoys, each a level deeper): what is
    # still encoded was not read to its end, so it is not printed.
    return _masked_deep_values(masked, _still_encoded)


#: A query or fragment parameter, or a fragment, in a text: its delimiter
#: and what follows it to the next delimiter or white space.
_SEGMENT = re.compile(r"([?&;#])([^?&;#\s]*)")


def _deeper_than_read(value: str) -> bool:
    """Whether *value* is still encoded after
    :data:`~pitloom.core.url_masking._hits.PURL_DECODE_ROUNDS` decodes."""
    return "%25" in value and qualifier_levels(value)[1]


def _still_encoded(value: str) -> bool:
    """Whether a decode changes *value*."""
    return "%" in value and unquote(value) != value


def _masked_deep_values(text: str, hides: Callable[[str], bool]) -> str:
    """*text* with each parameter value (after its first ``=``) or fragment
    (:data:`_SEGMENT`) that *hides* is true of written as ``***``
    (:func:`_deeper_than_read`, :func:`_still_encoded`). Linear: each
    segment is decoded a bounded number of times."""
    if "%" not in text:
        return text

    def masked(found: re.Match[str]) -> str:
        mark, segment = found.groups()
        name, equals, value = segment.partition("=")
        if not equals:
            name, value = "", segment
        return f"{mark}{name}{equals}***" if hides(value) else found.group()

    return _SEGMENT.sub(masked, text)


def _first_masked_level(
    levels: list[str], *, line: bool, free_params: bool
) -> str | None:
    """The first of *levels* (decode depths, shallowest first) that the
    masker changes, masked; ``None`` when it changes none."""
    for level in levels:
        shown = _masked_formats(level, line=line, free_params=free_params)
        if shown != level:
            return shown
    return None


def _masked_formats(text: str, *, line: bool, free_params: bool) -> str:
    """:func:`masked_given_path` of *text* as written: a format character
    dropped when that shows a credential."""
    plain = without_format(text)
    if plain != text:
        masked = _masked(plain, line=line, free_params=free_params)
        if masked != plain:
            return masked
    return _masked(text, line=line, free_params=free_params)


def _masked(text: str, *, line: bool, free_params: bool) -> str:
    """:func:`masked_given_path` of *text* as it is."""
    text = mask_auth_schemes(mask_scp(mask_tokens(_masked_purls(text))))
    masked = masked_once(text, line=line)
    passes = 1
    while masked != text and passes < _MASK_PASSES:
        text, masked = masked, masked_once(masked, line=line)
        passes += 1
    return mask_free_params(masked) if free_params else masked
