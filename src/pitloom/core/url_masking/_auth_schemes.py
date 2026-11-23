# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The credential after an HTTP authentication scheme in a text
(``Authorization: Bearer <token>``, ``Basic <base64>``), as a build's output
or an HTTP client's debug line prints it: masked by
:func:`~pitloom.core.url_masking.masked_given_path`, the scheme kept
(``Bearer ***``).

See also: :mod:`pitloom.core.url_masking._boundary` (where a scheme word or
a header name may start) and :mod:`pitloom.core.url_masking._tokens` (a
token of a known shape, masked first, so ``Bearer ghp_***`` keeps its
prefix). Standard library only.

The rule, in two passes:

* **After a header name** (``Authorization`` or ``Proxy-Authorization``, any
  case, an optional quote, ``:`` or ``=``, an optional quote): the scheme
  ``Bearer``, ``Basic``, ``token`` or ``Digest``, its separators, then the
  credential whatever its length or shape: the run of RFC 6750 ``b64token``
  characters (letters, digits, ``-._~+/`` and ``=``) is masked. A
  placeholder (``<token>``, ``${TOKEN}``, ``$GITHUB_TOKEN``) starts with
  none of them and is kept; a prose word after the scheme is masked
  (``Authorization: Bearer token required`` prints ``Bearer *** required``).
  For ``Digest`` only the value of ``response=`` is masked (the hash a
  password makes), up to the next header name or the end of the line.
* **After a scheme word alone** (``Bearer`` or ``Basic``, any case): prose
  follows these words too (``the bearer of bad news``, ``Basic
  usage/configuration``), so the run is masked only when it holds 8
  characters or more and looks random: a ``~`` or ``+``, ``=`` padding at its
  end, digits only, a word of 20 letters or digits or more, or a word (a run
  of letters and digits between the other characters) holding a single
  lower-case letter next to capitals or digits (``dXNlcjpwYXNz``,
  ``s3cr3t``), 2 digits or more before its end (``abcd1234efgh``), or
  digits at its end at least as many as its letters (``abcd1234``). So
  ``types/values``, ``tutorial2024``, ``RFC-6750-style``,
  ``Latin1Supplement`` and ``requests.auth.HTTPBearer`` are prose. A
  ``Basic`` credential must also be standard base64 (RFC 7617).

Both passes: the word starts not glued to a letter, digit, ``_`` or ``-``
(``X-Authorization`` is no header name), or right after an escape sequence; the
separators are spaces, tabs, no-break spaces, ``%20`` and the escaped tab
and no-break space, once or doubled (``\\t``, ``\\\\t``, ``\\xa0``). A ``.``
ending the run ends a sentence and is kept; a run is masked whole, so a
credential in a file name loses the extension after it (``Bearer
s3cr3tvalue99.gguf`` prints ``Bearer ***``).

Missed: after a scheme word alone, a credential of letters only without a
single lower-case letter between capitals (``abcdefghij``,
``Abcdefghijklmnop``), or with few digits at its end; a ``Digest`` header
spread over lines.

Linear: each run is read once in a lookahead after its scheme and
separators, and runs never overlap; a ``Digest`` header's ``response=`` is
looked for only up to the next header name or line end.
"""

from __future__ import annotations

import heapq
import io
import re
from collections.abc import Iterator

from pitloom.core.url_masking._boundary import word_start

__all__ = ["mask_auth_schemes"]

#: The separators after a scheme.
_SEPARATORS = r"(?:[ \t\xa0]|\\{1,2}t|\\{1,2}xa0|%20)+"
#: A run of ``b64token`` characters, in a lookahead (group ``run``).
_RUN = r"(?=(?P<run>[A-Za-z0-9._~+/=-]*))"
#: A scheme word alone, its separators and its run.
_SCHEME_RE = re.compile(
    "(?=[Bb])"
    + word_start("A-Za-z0-9_-")
    + r"(?P<scheme>(?i:bearer|basic))"
    + _SEPARATORS
    + _RUN
)
#: White space or an escaped tab around a header's ``:`` or ``=``.
_GAP = r"(?:\s|\\{1,2}t)*"
#: An optional quote, also escaped (``\\"``).
_QUOTE = r"(?:\\{0,2}[\"'])?"
#: A header name, its value's scheme, the separators and the run.
_HEADER_RE = re.compile(
    "(?=[APap])"
    + word_start("A-Za-z0-9_-")
    + r"(?i:(?:proxy-)?authorization)"
    + _QUOTE
    + _GAP
    + "[:=]"
    + _GAP
    + _QUOTE
    + r"(?P<scheme>(?i:bearer|basic|token|digest))"
    + _SEPARATORS
    + _RUN
)
#: The ``response=`` value of a ``Digest`` header (group ``value``).
_DIGEST_RESPONSE = re.compile(
    word_start("A-Za-z0-9_-") + r"(?i:response)\s*=\s*\"?(?P<value>[^\"\s,]+)"
)
#: A ``Basic`` credential: standard base64.
_BASE64 = re.compile(r"[A-Za-z0-9+/]+={0,2}")
#: A word of a run: letters and digits.
_WORD = re.compile(r"[A-Za-z0-9]+")
#: The runs of one kind of character in a word.
_KIND = re.compile(r"[a-z]+|[A-Z]+|[0-9]+")
#: The fewest characters of a credential after a scheme word alone.
_SHORTEST = 8
#: A word this long is a credential whatever it holds.
_LONG = 20
#: Characters of a ``b64token`` prose holds in no word.
_TOKEN_MARKS = frozenset("~+")


def _looks_random(word: str) -> bool:
    """Whether *word*, letters and digits, mixes them as a random string
    does, not as a word, a name or a version (see the module's rule)."""
    if len(word) >= _LONG:
        return True
    runs = _KIND.findall(word)
    letters = sum(len(run) for run in runs if not run[0].isdigit())
    last = len(runs) - 1
    for index, run in enumerate(runs):
        if len(run) == 1 and run.islower() and last > 0:
            return True
        if run[0].isdigit() and (
            (index < last and len(run) >= 2)
            or (0 < index == last and len(run) >= letters)
        ):
            return True
    return False


def _is_credential(scheme: str, core: str) -> bool:
    """Whether *core*, the run after the scheme word *scheme* without its
    ending ``.``, is a credential, not prose (see the module's rule)."""
    if len(core) < _SHORTEST:
        return False
    if scheme.lower() == "basic" and _BASE64.fullmatch(core) is None:
        return False
    return (
        core.endswith("=")
        or core.isdigit()
        or not _TOKEN_MARKS.isdisjoint(core)
        or any(_looks_random(word) for word in _WORD.findall(core))
    )


def _header_spans(text: str) -> Iterator[tuple[int, int]]:
    """The credential after each header name in *text*, in order. A
    ``Digest`` header's ``response=`` is looked for up to the next header
    name or the line end: without that bound, a line of many headers would
    be read once per header."""
    headers = _HEADER_RE.finditer(text)
    header = next(headers, None)
    while header is not None:
        following = next(headers, None)
        start = header.end()
        if header.group("scheme").lower() != "digest":
            core = header.group("run").rstrip(".")
            if core:
                yield start, start + len(core)
        else:
            stop = len(text) if following is None else following.start()
            line_end = text.find("\n", start, stop)
            response = _DIGEST_RESPONSE.search(
                text, start, stop if line_end < 0 else line_end
            )
            if response is not None:
                yield response.span("value")
        header = following


def _scheme_spans(text: str) -> Iterator[tuple[int, int]]:
    """The credential after each scheme word alone in *text*, in order."""
    for found in _SCHEME_RE.finditer(text):
        core = found.group("run").rstrip(".")
        if _is_credential(found.group("scheme"), core):
            yield found.end(), found.end() + len(core)


def mask_auth_schemes(text: str) -> str:
    """*text* with the credential after each ``Authorization`` header's
    scheme, and each ``Bearer`` or ``Basic`` scheme word that a credential
    follows, written as ``***``, the scheme, its separators and a ``.``
    ending the run kept (see the module's rule). Both passes read *text*
    as given, so a scheme word the first masks as a credential
    (``Authorization: Basic Bearer s3cr3t99``) still masks the run after it;
    spans that overlap or touch are written as one ``***``."""
    out = io.StringIO()
    done = 0
    for start, end in heapq.merge(_header_spans(text), _scheme_spans(text)):
        if start <= done and out.tell():
            done = max(done, end)
            continue
        out.write(text[done:start])
        out.write("***")
        done = end
    if not out.tell():
        return text
    out.write(text[done:])
    return out.getvalue()
